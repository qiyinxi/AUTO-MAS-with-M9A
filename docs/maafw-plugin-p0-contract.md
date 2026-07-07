# MaaFW 插件化 P0 服务契约草案

> 状态：P0 契约冻结草案，待人工审核
> 日期：2026-07-06
> 依据：docs/maafw插件化最终实现方案.md 第 4 节、docs/maafw-plugin-code-audit.md
> 约束：本文档只定义 DTO 和服务接口契约，不包含实现代码，不切换现有运行路径

本文档冻结 MaaFW 插件化第一批 v1 服务契约。契约一旦冻结，DTO 字段名作为 v1 契约维护：新增字段允许，破坏性变更必须新开 v2 服务名。重点细化 `maafw.interface.v1`，因为 interface 包冻结最严（MaaEnd 等外部消费者只依赖它）。

## 1. 契约总览

| 服务名 | 包 | 职责 | 冻结严格度 |
| --- | --- | --- | --- |
| `maafw.interface.v1` | `automas-maafw-interface` | ProjectInterface V2 解析、校验、预览、任务快照归一化 | 最严（外部消费者） |
| `maafw.project.v1` | `automas-maafw-project` | 项目更新、agent 环境准备 | 严 |
| `maafw.agent.v1` | `automas-maafw-project` | agent 运行形态分类、命令方案 | 严 |
| `maafw.runner.v1` | `automas-maafw-runner` | runner session、worker 子进程、Tasker 直控、事件流 | 严 |
| `maafw.controller.adb` | `automas-maafw-controller-adb` | ADB device spec、模拟器能力消费 | 中 |
| `maafw.controller.desktop` | `automas-maafw-controller-desktop` | Win32 窗口扫描、句柄匹配 | 中 |
| `maafw.registry.v1` | `automas-script-maafw` | controller provider 和 project pack 注册中心 | 中 |

版本策略：
- 0.x 阶段允许 DTO 调整，破坏性变更 minor +1 并写 changelog。
- `maafw.*.v1` 契约冻结时全族升 1.0.0。
- 1.0 后 v1 DTO 只增不改，破坏性变更开 `.v2` 服务名并共存过渡。

## 2. maafw.interface.v1（重点细化）

### 2.1 职责边界

interface 包只做"解析 ProjectInterface 有哪些任务、任务怎么配置"，不决定"今天跑哪些任务、任务失败后如何补跑、周月规则如何跳过、通知文案如何表达"。

**做什么**：
- 读取 `interface.json` / `interface.jsonc`
- 处理 `import` 递归合并、循环检测、冲突检测
- import 合并完成后再做必填字段和引用校验
- 展开 `scan_select`
- 解析 i18n 字段
- 解析任务入口、分组、任务显示信息、option 元数据、preset 引用和默认任务快照
- 解析不同作用域的 option / setting / pretask / hotkey / global option 元数据
- 校验 task / option / preset / controller / resource 引用一致性
- 输出稳定 DTO，顶层带 `interface_version` 和 `capabilities`
- 提供任务快照归一化和预览 DTO

**不做什么**：
- 不 import `app/core`、`app/task`、`app/api`
- 不启动 MaaFW tasker
- 不读写 AUTO-MAS 用户配置
- 不出现 M9A、MaaEnd、MXU 等专项任务名
- 不强行决定 global option / setting / pretask / hotkey 应该放在哪个 UI 面板
- 不解释某个 option 对游戏逻辑的含义

### 2.2 服务接口

```
maafw.interface.v1.load(path, force_reload=False) -> InterfaceModel
maafw.interface.v1.preview(path) -> InterfacePreview
maafw.interface.v1.validate(interface) -> ValidationReport
maafw.interface.v1.build_default_snapshot(interface, preset=None) -> TaskSnapshot
maafw.interface.v1.normalize_snapshot(interface, snapshot) -> TaskSnapshot
maafw.interface.v1.normalize_execution_payload(interface, tasks, options, controller, resource) -> ExecutionPayload
maafw.interface.v1.rescan_option(path, option_name) -> OptionCases
```

可选 HTTP route（P1 落地）：
```
POST /maafw/interface/preview
POST /maafw/interface/rescan-option
```

### 2.3 import 合并契约（先合并、后校验）

这是 interface 包最核心的算法契约，任何改动都是破坏性变更。

**合并顺序**：
1. 解析根 interface 文件
2. 递归 DFS 合并所有 import 片段（深度优先：先递归子 import，再合并当前片段）
3. 合并完成后，展开 scan_select（扫描 scan_dir 填充 cases）
4. 最后执行校验链

**import 片段约束**：
- `IMPORTABLE_KEYS = {"task", "option", "preset", "import"}`
- 单个被导入片段允许只提供 task / option / preset / import 等局部内容（仅这四键合法，agent / setting / global_option 不在 v1 import 片段允许范围内）
- 不能因为 root 或片段暂时缺少 task 就提前失败
- 路径安全：禁止绝对路径、禁止 `..`、强制项目相对、越界保护
- 未来 v2 若要把 agent / setting / global_option 纳入 import 片段，必须新开 v2 服务名并共存过渡，v1 的 IMPORTABLE_KEYS 不变

**合并策略**：
- `task`：`list extend`（片段的 task 列表追加到根）
- `option`：`dict update`（片段的 option 字典合并到根）
- `preset`：`list extend`（片段的 preset 列表追加到根）
- `import`：递归处理

**冲突策略（硬冲突，不覆盖）**：
- `task.name` 重名 → raise
- `option` key 重名 → raise
- `preset.name` 重名 → raise

**循环检测**：用 `stack: list[Path]` 记录当前 DFS 路径，遇到已在栈中的文件即 raise。

### 2.4 解析范围

interface 包解析以下 ProjectInterface V2 字段：

| 字段 | 解析范围 | 说明 |
| --- | --- | --- |
| `task` | 任务入口、分组、显示信息、option 引用、controller/resource 限制、pipeline_override | 不解释任务含义 |
| `option` | option 定义（type/cases/inputs/default/scan_dir/pipeline_override） | 不解释 option 对游戏的影响 |
| `preset` | preset 引用、默认任务快照 | 不决定用户应该选哪个 preset |
| `controller` | controller 定义（type/adb/win32/...） | 不启动 controller |
| `resource` | resource 定义（path/controller 引用） | 不加载 resource |
| `group` | 任务分组显示信息 | 仅元数据 |
| `agent` | agent 定义（child_exec/child_args/identifier/embedded） | 仅解析，不启动 |
| `global_option` | 全局 option 引用列表 | 仅记录引用 |
| `import` | 递归合并 | 见 2.3 |
| `languages` | i18n 映射 | 解析 `$key` 替换 |

### 2.5 option 作用域

作用域（scope）不在 `OptionDefinition` 上输出。`OptionDefinition` 表示 option 的原始定义，一个 option 可能被多个位置引用（例如同一个 option 同时被某个 task 和 `global_option` 引用），强行绑定单一 scope 会丢失"一个定义、多处引用"的事实。

**作用域的承载位置**：
- `OptionReference`（解析器输出，描述"谁引用了这个 option"）：必带 scope，是作用域的权威载体
- `OptionSelection`（用户选择结果）：必带 scope，标注这次选择属于哪个作用域
- `OptionDefinition`（原始定义）：不带单一 scope；如需聚合展示，输出 `scopes: list[str] | None`，按引用位置汇总该 option 出现在哪些 scope 中（去重，顺序按 task / global / controller / resource）

| scope | 来源 | v1 是否输出 | 说明 |
| --- | --- | --- | --- |
| `task` | `task.option` 引用的 option | 是 | 任务级 option，绑定到具体 task |
| `global` | `global_option` 列表引用的 option | 是 | 全局 option，影响整个项目 |
| `controller` | `controller.option` 引用的 option | 是 | 控制器级 option |
| `resource` | `resource.option` 引用的 option | 是 | 资源级 option |
| `setting` | interface 中声明的 setting 类 option | **否（v2 待确认）** | 当前 PI V2 规范无显式来源，v1 不解析、不输出 |
| `pretask` | interface 中声明的 pretask 类 option | **否（v2 待确认）** | 当前 PI V2 规范无显式来源，v1 不解析、不输出 |
| `hotkey` | interface 中声明的 hotkey 类 option | **否（v2 待确认）** | 当前 PI V2 规范无显式来源，v1 不解析、不输出 |

**当前代码事实**：现有 `interface_models.py` 中 option 没有显式 scope 字段，scope 是通过引用位置隐式确定的（task.option 引用的就是 task scope，global_option 引用的就是 global scope）。v1 契约不修改 `OptionDefinition` 的字段结构，而是在解析器输出的 `OptionReference` 和用户选择时输出的 `OptionSelection` 上显式标注 scope。`setting` / `pretask` / `hotkey` 三个 scope 当前 PI V2 规范中没有显式来源，标记为"v2 待确认"，v1 不解析、不输出，避免做出超出当前规范的设计结论。

### 2.6 核心 DTO

#### 2.6.1 InterfaceModel

```python
class InterfaceModel(BaseModel):
    interface_version: Literal[2]
    capabilities: list[str]                    # 解析器能力声明，如 ["scan_select", "i18n", "import_merge"]
    languages: list[str] | None
    name: str | None
    label: str | None
    title: str | None
    icon: str | None
    mirrorchyan_rid: str | None
    mirrorchyan_multiplatform: bool | None
    github: str | None
    version: str | None
    contact: str | None
    license: str | None
    welcome: str | list[str] | None
    description: str | list[str] | None
    controller: list[ControllerDefinition]
    resource: list[ResourceDefinition]
    group: list[GroupDefinition]
    agent: AgentDefinition | list[AgentDefinition] | None
    task: list[TaskDefinition]
    option: dict[str, OptionDefinition]        # 所有 option 的完整定义（不含单一 scope）
    option_references: list[OptionReference]   # option 引用关系，权威作用域信息载体
    global_option: list[str] | None            # global option 引用（key 列表）
    preset: list[PresetDefinition]
    import_count: int                          # 合并的 import 片段数量
    model_config = ConfigDict(extra="allow")   # 透传未知字段
```

**冻结理由**：`extra="allow"` 透传策略保证 PI V2 继续漂移时未知字段不丢。`capabilities` 让消费者能检测解析器能力。`import_count` 让前端能显示"合并了 N 个片段"。`option_references` 把作用域信息从 `OptionDefinition` 上分离出来，保留"一个定义、多处引用"的事实。

#### 2.6.2 OptionDefinition

```python
class OptionDefinition(BaseModel):
    key: str                                   # option 的唯一标识
    scopes: list[str] | None                   # 解析器汇总的 scope 列表（去重），仅供聚合展示；不代表单一归属
    type: str                                  # "select" | "scan_select" | "switch" | "checkbox" | "input" | 未知类型透传
    label: str | None
    description: str | None
    icon: str | None
    controller: list[str] | None               # 可见性限制：仅对这些 controller 可见
    resource: list[str] | None                 # 可见性限制：仅对这些 resource 可见
    cases: list[OptionCase] | None             # select/scan_select/switch/checkbox 的可选项
    inputs: list[InputCase] | None             # input 类型的输入项
    scan_dir: str | None                       # scan_select 的扫描目录
    scan_filter: str | None                    # scan_select 的过滤正则
    pipeline_override: dict | None             # option 级 pipeline override
    default_case: str | None                   # 默认选中的 case name
    raw: dict                                  # 原始 JSON 片段，保留不可逆信息
    model_config = ConfigDict(extra="allow")
```

**冻结理由**：
- `OptionDefinition` 表示 option 的原始定义，**不绑定单一 `scope`**。一个 option 可被多处引用（如同时被某个 task 和 `global_option` 引用），单一 scope 会丢失"一定义多处引用"的事实。
- `scopes: list[str] | None` 是 v1 新增字段，仅供前端/pack 聚合展示（如"这个 option 出现在哪些作用域"）。权威作用域信息放在 `OptionReference` 和 `OptionSelection` 上。
- `type` 用 `str` 而非 `Literal`，因为 PI V2 可能引入新类型，解析器透传未知类型，由消费者决定是否支持。
- `raw` 保留原始 JSON，确保任何未被显式建模的字段不丢。

#### 2.6.2a OptionReference（解析器输出的引用关系）

```python
class OptionReference(BaseModel):
    key: str                                   # option key
    scope: Literal["task", "global", "controller", "resource"]   # v1 已知 scope；setting/pretask/hotkey 为 v2 待确认
    owner: str | None                          # 引用者标识，如 task name / "global_option" / controller name / resource name
    raw: dict
    model_config = ConfigDict(extra="allow")
```

**冻结理由**：
- `OptionReference` 描述"谁在哪个 scope 引用了这个 option"，是作用域的权威载体。
- 一个 `OptionDefinition` 可以对应多个 `OptionReference`（同一 option 被多处引用）。
- v1 只输出已知 scope（task / global / controller / resource）。`setting` / `pretask` / `hotkey` 当前 PI V2 规范中没有显式来源，留作 v2 待确认，v1 不输出。
- `InterfaceModel` 在解析时输出 `option_references: list[OptionReference]`（见 2.6.1 的 `option` 字段说明），消费者按 scope 分组即可得到各作用域的 option 列表。

#### 2.6.3 OptionCase

```python
class OptionCase(BaseModel):
    name: str
    label: str | None
    description: str | None
    icon: str | None
    args: str | list | dict | bool | int | float | None   # case 声明的参数，供 runner/agent 使用
    option: list[str] | None                  # 嵌套 option 引用
    pipeline_override: dict | None
    raw: dict
    model_config = ConfigDict(extra="allow")
```

**冻结理由**：
- `args` 是 v1 新增字段，保留 case 声明的参数。当前代码中 case 只有 `pipeline_override`，但 PI V2 规范允许 case 携带 `args`，v1 显式建模。
- `args` 类型为联合类型，因为不同项目可能用不同格式。

#### 2.6.4 InputCase

```python
class InputCase(BaseModel):
    name: str
    label: str | None
    description: str | None
    icon: str | None
    default: str | int | float | bool | None
    pipeline_type: str | None                 # "int" | "float" | "string" | "bool" 等
    verify: str | None                        # 校验正则
    verify_error: str | None                  # 校验失败文案
    pattern_msg: str | None                   # 校验失败提示
    raw: dict
    model_config = ConfigDict(extra="allow")
```

#### 2.6.5 OptionSelection（用户选择结果）

```python
class OptionSelection(BaseModel):
    key: str
    scope: str
    value: bool | str | int | float | list | dict | None   # 用户选择的原始值
    args: str | list | dict | bool | int | float | None    # 从 case.args 提取的参数
    raw: dict                                 # 原始选择记录
    model_config = ConfigDict(extra="allow")
```

**传参契约规则**：

| option.type | value 含义 | args 含义 |
| --- | --- | --- |
| `select` | 选中 case 的 name（string） | 该 case 声明的 `args`；如果没有 `args`，退回 `value` |
| `multi_select` | 选中 case name 列表（list[str]） | 按选择顺序输出对应 case 的 `args` 列表 |
| `switch` | 选中 case 的 name（string） | 同 select |
| `checkbox` | 选中 case name 列表（list[str]） | 同 multi_select |
| `bool` | 原始 bool | None |
| `input` | dict[input_name, input_value] | None |
| `number` | 原始 int/float | None |

**冻结理由**：
- `select` 选中某个 case 时，`value` 保留选择结果（case name），`args` 保留该 case 声明的 `args`；如果没有 `args`，再退回 `value`。
- `multi_select` 保留选择列表，并按选择顺序输出对应 `args` 列表。
- `bool` / `input` / `number` 保留用户输入的原始类型，不提前转成字符串。
- `normalize_execution_payload()` 输出结构化 option 结果，由 runner 或 agent adapter 决定怎么注入给 agent；不要只传 task name，也不要把所有 option 提前压成一段不可逆字符串。

#### 2.6.6 TaskSnapshot

```python
class TaskSnapshot(BaseModel):
    taskOrder: list[str]                       # 任务顺序
    taskChecked: dict[str, bool]               # 任务勾选状态
    taskOptions: dict[str, dict[str, OptionValue]]  # 按任务分组的 option 值
    model_config = ConfigDict(extra="allow")

# OptionValue 兼容旧格式：string | list[string] | dict[string, string]
# v1 新增 OptionSelection 结构化格式，但旧格式继续可读
```

**冻结理由**：
- `taskOrder` / `taskChecked` / `taskOptions` 三字段是现有前后端共享的归一化形态，冻结。
- `CUSTOM_PRESET_NAME = "__auto_mas_custom_preset__"` 是保留键，冻结。
- option 值类型 `OptionValue = str | list[str] | dict[str, str]` 保持兼容；v1 新增的 `OptionSelection` 结构化格式作为可选增强，不替换旧格式。

#### 2.6.7 ExecutionPayload

```python
class ExecutionPayload(BaseModel):
    tasks: list[str]                           # 按顺序执行的任务 name 列表
    options: dict[str, list[OptionSelection]]  # 按任务分组的结构化 option 选择结果
    controller: str | None                     # 选中的 controller name
    resource: str | None                       # 选中的 resource name
    skipped_tasks: list[SkippedTask]           # 被跳过的任务及原因
    model_config = ConfigDict(extra="allow")

class SkippedTask(BaseModel):
    name: str
    reason: str
```

**冻结理由**：
- `normalize_execution_payload()` 输出结构化 option 结果，不要只传 task name，不要提前压成不可逆字符串。
- runner 或 agent adapter 根据 `options` 中的 `args` 决定怎么注入给 agent。
- `skipped_tasks` 记录被跳过的任务及原因（如 controller 不兼容、resource 不匹配），让前端能显示。

#### 2.6.8 ValidationReport

```python
class ValidationReport(BaseModel):
    valid: bool
    errors: list[ValidationError]
    warnings: list[ValidationWarning]
    model_config = ConfigDict(extra="allow")

class ValidationError(BaseModel):
    code: str                                  # 机器可读错误码，如 "task.reference.missing"
    path: str                                  # 错误位置，如 "task[3].option[0]"
    message: str                               # 人类可读错误信息
    severity: Literal["error", "warning"]

class ValidationWarning(BaseModel):
    code: str
    path: str
    message: str
```

**冻结理由**：
- `code` 让前端和工具能按错误码分类处理。
- `path` 精确定位错误位置，便于调试。
- `severity` 区分 error 和 warning，warning 不阻止解析但提醒用户。

#### 2.6.9 其他定义

```python
class ControllerDefinition(BaseModel):
    name: str
    label: str | None
    description: str | None
    icon: str | None
    type: str                                  # "Adb" | "Win32" | 未知类型透传
    display_short_side: int = 720
    display_long_side: int | None
    display_raw: bool = False
    permission_required: bool | None
    attach_resource_path: bool | None
    option: list[str] | None
    adb: dict | None                           # ADB 控制器配置（透传）
    win32: dict | None                         # Win32 控制器配置（透传）
    raw: dict
    model_config = ConfigDict(extra="allow")

class ResourceDefinition(BaseModel):
    name: str
    label: str | None
    description: str | None
    icon: str | None
    path: list[str]
    controller: list[str] | None
    option: list[str] | None
    hash: str | None
    raw: dict
    model_config = ConfigDict(extra="allow")

class GroupDefinition(BaseModel):
    name: str
    label: str | None
    description: str | None
    icon: str | None
    default_expand: bool = True
    raw: dict
    model_config = ConfigDict(extra="allow")

class AgentDefinition(BaseModel):
    child_exec: str | None
    child_args: list[str] | None
    identifier: str | None
    embedded: bool | None
    raw: dict
    model_config = ConfigDict(extra="allow")

class TaskDefinition(BaseModel):
    name: str
    label: str | None
    entry: str | None
    default_check: bool | None
    description: str | list[str] | None
    doc: str | None
    desc: str | None
    icon: str | None
    group: str | None
    resource: list[str] | None
    controller: list[str] | None
    pipeline_override: dict | None
    option: list[str] | None                   # option 引用（key 列表）
    raw: dict
    model_config = ConfigDict(extra="allow")

class PresetDefinition(BaseModel):
    name: str
    label: str | None
    description: str | None
    icon: str | None
    task: list[PresetTask]
    raw: dict
    model_config = ConfigDict(extra="allow")

class PresetTask(BaseModel):
    name: str
    enabled: bool = True
    option: dict[str, Any] | None
    raw: dict
    model_config = ConfigDict(extra="allow")
```

### 2.7 normalize_snapshot 契约

```
normalize_snapshot(interface, snapshot) -> TaskSnapshot
```

**规则**：
1. `taskOrder`：去重补全，按 `interface.task` 顺序排列；snapshot 中存在但 interface 中不存在的 task 保留在末尾并标记（不删除，让用户能看到历史残留）。
2. `taskChecked`：按合法 task_id 归一；interface 中 `default_check=True` 的 task 默认勾选。
3. `taskOptions`：按 controller/resource 过滤可见 option；按 option.type 分派默认值（见 2.8）。

### 2.8 option 归一化规则（冻结）

| option.type | 归一化值类型 | 默认值策略 | 校验规则 |
| --- | --- | --- | --- |
| `select` / `scan_select` / `switch` | string | `option.default_case`，否则首个 case | 校验 case 存在性 |
| `checkbox` | list[string] | `default_case` 列表与 case 名交集 | 过滤非法 case |
| `input` | dict[string, value] | 每个 input_case.default | 仅保留声明的 input 名 |
| `bool` | bool | False | 不校验 |
| `number` | int/float | 0 | 不校验 |
| 未知类型 | 原值透传 | None | 不校验 |

### 2.9 normalize_execution_payload 契约

```
normalize_execution_payload(interface, tasks, options, controller, resource) -> ExecutionPayload
```

**规则**：
1. `tasks`：去重，仅保留 interface 中存在的 task；按 `task.controller` 与当前 controller 集合有交集、`task.resource` 包含当前 resource 过滤兼容性；不兼容的移入 `skipped_tasks`。
2. `options`：按 controller/resource 过滤可见 option；输出 `OptionSelection` 结构化结果（含 `value` / `args` / `raw`）。
3. 不提前把 option 压成字符串；runner 或 agent adapter 决定怎么注入给 agent。

### 2.10 value / args / raw 保留策略

| 字段 | 保留策略 | 说明 |
| --- | --- | --- |
| `value` | 必保留 | 用户选择的原始值，类型由 option.type 决定 |
| `args` | 必保留 | 从 case.args 提取的参数；如果没有 args，退回 value |
| `raw` | 必保留 | 原始 JSON 片段，确保任何未被显式建模的字段不丢 |

**只增不删原则**：v1 契约的 `scopes` / `value` / `args` / `raw` 字段只增不删（`OptionDefinition.scopes` 是聚合展示用，`OptionReference.scope` 和 `OptionSelection.scope` 是权威作用域）。旧 task option 输出继续可生成（兼容 `str | list[str] | dict[str, str]` 格式）。

### 2.11 实现边界

- 不 import `app/core`、`app/task`、`app/api`。
- 不启动 MaaFW tasker。
- 不读写 AUTO-MAS 用户配置。
- 不出现 M9A、MaaEnd、MXU 等专项任务名。
- DTO 字段名作为 v1 契约维护，新增字段允许，破坏性变更必须新开 v2 服务名。

### 2.12 缓存契约

interface 包提供内存缓存和磁盘缓存：

- **内存缓存**：signature = 文件 mtime_ns + size 元组（根 interface + dependency_paths + scan_select_specs 全部纳入签名）。
- **磁盘缓存**：落 `data/cache/maafw_interface_loader/{sha256(root)}.json`，30 天过期，24 小时清理一次。
- `force_reload=True` 时跳过缓存。

### 2.13 与现有代码的映射

| v1 DTO | 现有代码 | 差异 |
| --- | --- | --- |
| `InterfaceModel` | `MaaFWInterface` | 新增 `capabilities`、`import_count`、`option_references`；所有子模型新增 `raw` |
| `OptionDefinition` | `MaaFWOption` | 新增 `scopes`、`raw`（不绑定单一 scope，作用域由 `OptionReference` 承载） |
| `OptionReference` | 无（新结构） | v1 新增，描述 option 引用关系和权威 scope |
| `OptionCase` | `MaaFWOptionCase` | 新增 `args`、`raw` |
| `OptionSelection` | 无（新结构） | v1 新增，结构化 option 选择结果，含 scope/value/args/raw |
| `TaskSnapshot` | `MaaFWTaskPresetSnapshot` | 字段名一致，option 值类型兼容 |
| `ExecutionPayload` | 无（新结构） | v1 新增，替代旧 `normalize_task_execution_payload` 的 tuple 返回 |
| `ValidationReport` | 无（新结构） | v1 新增，替代现有的 raise 异常模式 |

## 3. maafw.project.v1

### 3.1 职责

project 包负责"项目资产"，包含更新和 agent 环境两组能力。它不持有 agent 进程，只准备可执行命令方案。

**做什么**：
- 检查 GitHub / MirrorChyan 更新
- 下载并应用全量包或增量包
- 防止路径越界
- 失败不破坏项目目录
- 解析 `interface.agent` 中的 `child_exec`、`child_args`、`identifier`、`embedded`
- 判断 agent 运行形态
- 创建项目专属 venv
- 生成 `AgentPlan`

**不做什么**：
- 不持有 agent 进程
- 不启动 agent
- 不连接 AgentClient
- project 包零 maa 依赖

### 3.2 服务接口

```
maafw.project.v1.check_update(project_path, interface, channel, cdk) -> UpdateCandidate
maafw.project.v1.apply_update(project_path, candidate) -> UpdateResult
```

### 3.3 DTO

```python
class UpdateCandidate(BaseModel):
    source: Literal["mirrorchyan", "github"] | str
    version: str
    download_url: str
    sha256: str | None
    is_latest: bool                           # 当前已是最新版本时为 True
    raw: dict

class UpdateResult(BaseModel):
    checked: bool
    updated: bool
    current_version: str | None
    latest_version: str | None
    source: str | None
    message: str | None
    logs: list[str]                           # 更新过程日志
    raw: dict
```

### 3.4 实现边界

- project 包零 maa 依赖。
- `embedded: true` 不允许在主进程 import 项目 agent 代码，统一转成 isolated subprocess 策略。
- 只处理项目目录，不处理用户侧任务队列、通知或账号。
- 路径安全：`_resolve_project_relative_path` 禁止绝对路径、`..`、写入 `.mas-update`。

## 4. maafw.agent.v1

### 4.1 职责

agent 服务负责 agent 环境准备和命令方案生成。

### 4.2 服务接口

```
maafw.agent.v1.classify(interface.agent) -> AgentMode
maafw.agent.v1.prepare_env(project_path, interface.agent) -> AgentEnvResult
maafw.agent.v1.build_command_plans(project_path, interface.agent) -> list[AgentPlan]
```

### 4.3 DTO

```python
class AgentMode(BaseModel):
    runtime_kind: Literal["embedded", "project_python", "project_binary", "isolated_venv", "external"]
    embedded: bool                            # 原始 embedded 标志
    needs_subprocess: bool                    # 是否需要隔离子进程（embedded=True 时强制 True）
    raw: dict

class AgentEnvResult(BaseModel):
    ready: bool
    runtime_kind: str
    isolated_venv_path: str | None
    fallback_reason: str | None               # 准备失败时的原因
    logs: list[str]
    raw: dict

class AgentPlan(BaseModel):
    child_exec: str | None
    executable: str | None                    # 解析后的可执行文件路径
    executable_exists: bool
    fallback_reason: str | None
    runtime_kind: str                         # "embedded" | "project_python" | "project_binary" | "isolated_venv" | "external"
    isolated_venv_path: str | None
    child_args: list[str] | None
    command: list[str]                        # 完整命令（executable + child_args）
    cwd: str | None
    identifier: str | None
    embedded: bool
    raw: dict
```

### 4.4 agent 运行形态分类规则

| 条件 | runtime_kind | 说明 |
| --- | --- | --- |
| `child_exec` 不存在且匹配 bundled python pattern | `isolated_venv` | 项目专属 venv，按 interfaceHash + requirementsHash 重建 |
| `child_exec` 存在且是 python/python.exe/pythonw | `project_python` | 项目自带 Python，仅健康检查 |
| `child_exec` 存在且是其他可执行文件 | `project_binary` | 项目可执行文件 |
| `child_exec` 不存在且不匹配 bundled python | `external` | 外部命令，用户自备 |
| `embedded: true` | 强制改写为 isolated subprocess | 不允许主进程 import |

## 5. maafw.runner.v1

### 5.1 架构要求

```
AUTO-MAS 主进程
  -> runner session manager
      -> runner_worker.py 子进程   # 只在这里 import maa
          -> MaaFW Tasker
      -> agent 子进程              # 仅在项目声明 agent 时启动
```

### 5.2 服务接口

```
maafw.runner.v1.build_plan(project_path, interface, selection) -> RunPlan
maafw.runner.v1.create_session(run_plan, device, agent_plan|None, callbacks) -> SessionId
maafw.runner.v1.run(session_id) -> RunResult
maafw.runner.v1.stop(session_id) -> StopResult
maafw.runner.v1.dispose(session_id) -> None
```

### 5.3 DTO

```python
class DeviceSpec(BaseModel):
    type: Literal["Adb", "Win32"] | str
    adbPath: str | None
    address: str | None
    hWnd: int | None
    screencapMethods: list[str]
    inputMethods: list[str]
    config: dict
    raw: dict

class RunPlan(BaseModel):
    project_path: str
    project_name: str | None
    project_label: str | None
    controller_name: str
    controller_type: str
    resource_name: str | None
    resource: ResourceBundlePlan | None
    agents: list[AgentPlan]
    pi_env: dict[str, str]                     # PI_INTERFACE_VERSION 等环境变量
    tasks: list[TaskRunPlan]
    skipped_tasks: list[SkippedTaskPlan]
    raw: dict

class ResourceBundlePlan(BaseModel):
    name: str
    label: str | None
    paths: list[ResolvedPath]
    attached_paths: list[str]
    raw: dict

class ResolvedPath(BaseModel):
    raw: str
    resolved: str
    exists: bool
    is_file: bool
    is_dir: bool

class TaskRunPlan(BaseModel):
    name: str
    label: str | None
    entry: str | None
    options: dict[str, Any]                    # 任务级 option 值
    pipeline_override: dict | None
    raw: dict

class SkippedTaskPlan(BaseModel):
    name: str
    label: str | None
    entry: str | None
    reason: str

class RunResult(BaseModel):
    success: bool
    project_name: str | None
    controller_name: str | None
    resource_name: str | None
    completed_tasks: list[str]
    failed_task: str | None
    error_message: str | None
    logs: list[str]
    raw: dict

class StopResult(BaseModel):
    stopped: bool
    message: str | None

class SessionId(str):
    pass
```

### 5.4 事件流契约

runner session 通过回调或事件流输出以下事件类型：

| 事件类型 | 数据 | 说明 |
| --- | --- | --- |
| `log` | `{message: str}` | 日志行 |
| `task_start` | `{task_name: str}` | 任务开始 |
| `task_done` | `{task_name: str}` | 任务完成 |
| `task_failed` | `{task_name: str, error: str}` | 任务失败 |
| `session_done` | `{result: RunResult}` | 会话完成 |
| `session_error` | `{error: str}` | 会话错误 |

### 5.5 worker JSON 行协议

`runner_worker.py` 与主进程的进程边界契约：

```
stdout 每行一个 JSON，三种 type：
  {"type": "log", "message": "..."}
  {"type": "result", "data": {...}}
  {"type": "error", "error": "...", "message": "..."}
```

退出码：0=成功，1=异常，2=任务失败。

### 5.6 实现边界

- runner 不扫描模拟器，不调用 MuMuManager。
- runner 不关心 provider 来自 adb、desktop 还是未来 playcover，只接受 `DeviceSpec`。
- runner core 不 import `PluginContext`，插件适配层只负责把 service / route / callback 接进 core。
- runner worker 是第二道宿主无关边界，任何宿主只要能拉子进程并读写 stdio 就可以驱动 MaaFW 会话。

## 6. controller provider 契约

### 6.1 provider 接口

```python
class ControllerProvider:
    key: str                                   # provider 唯一标识，如 "adb"、"desktop"
    display_name: str
    controller_types: list[str]                # 支持的 controller type，如 ["Adb"]、["Win32"]

    async def decorate_schema(self, schema, config, ctx) -> dict:
        """按当前选择族注入脚本级配置字段"""

    async def precheck(self, runtime) -> str:
        """运行前检查，返回 'Pass' 或可操作错误文案"""

    def build_device_config(self, iface_controller, user_fields) -> DeviceSpec:
        """从 interface controller 定义和用户字段构建 DeviceSpec"""

    async def cleanup(self, runtime) -> None:
        """运行后清理"""
```

### 6.2 第一批 provider

| provider | 包 | controller_types | 范围 |
| --- | --- | --- | --- |
| `adb` | `automas-maafw-controller-adb` | `["Adb"]` | 消费 emulator 服务，生成 ADB device spec，处理 ADB capability precheck |
| `desktop` | `automas-maafw-controller-desktop` | `["Win32"]` | 窗口扫描、句柄匹配、Win32 device spec |

### 6.3 运行规则

- 一个脚本实例只选择一个控制器族。
- 多个控制器包可以同时安装。
- `decorate_schema` 只注入当前选择族的字段。
- `precheck` 失败返回可操作文案，例如"未安装 emulator 插件"或"未找到匹配窗口"。

## 7. project pack 契约

### 7.1 MaaFWProjectPackDefinition

```python
class MaaFWProjectPackDefinition(BaseModel):
    key: str                                   # pack 唯一标识，如 "m9a"
    display_name: str
    project_repo: str | None                   # 项目仓库地址
    interface_path: str = "interface.json"     # 默认 interface 文件名
    supported_controllers: list[str]           # 支持的 controller type
    default_controller: str                    # 默认 controller
    default_resource: str | None               # 默认 resource
    default_preset: str | None                 # 默认 preset
    default_task_queue: list[str] | None       # 默认任务队列
    period_rules: list[PeriodRule]             # 周期规则
    reserved_task_semantics: dict              # 保留任务语义（如 "启动游戏"、"切换账号"）
    icon: str | None
    notes: str | None
    raw: dict

class PeriodRule(BaseModel):
    task_name: str                             # 任务名
    period: Literal["weekly", "monthly"]       # 周期类型
    storage_key: str                           # 在用户数据中存储完成记录的 key
    label: str | None                          # 显示名
    description: str | None
```

### 7.2 MaaFWProjectPackPlugin

```python
class MaaFWProjectPackPlugin:
    def build_project_packs(self) -> list[MaaFWProjectPackDefinition]: ...
```

第一版 pack SDK 只允许声明元数据、默认值、模板、规则和文案，不开放 run plan hook。只有出现明确非标准生命周期时，才讨论完整 ScriptAdapter。

## 8. maafw.registry.v1

### 8.1 职责

`automas-script-maafw` 提供 registry 服务，用于注册 controller provider 和 project pack。

### 8.2 服务接口

```
maafw.registry.v1.register_controller_provider(provider)
maafw.registry.v1.unregister_controller_provider(key)
maafw.registry.v1.list_controller_providers() -> list[ControllerProvider]
maafw.registry.v1.get_controller_provider(key) -> ControllerProvider | None

maafw.registry.v1.register_project_pack(pack)
maafw.registry.v1.unregister_project_pack(key)
maafw.registry.v1.list_project_packs() -> list[MaaFWProjectPackDefinition]
maafw.registry.v1.get_project_pack(key) -> MaaFWProjectPackDefinition | None
```

### 8.3 服务启动时序

registry 使用 needs / wants 和两阶段重算：
- controller provider 通过 `wants` 声明对 emulator 服务的软依赖（adb provider wants emulator，但 emulator 不可用时仍能注册，只是 precheck 会失败）。
- 编排插件容忍 provider 迟到：provider 注册后触发依赖它的 schema 重算。

## 9. 兼容策略

### 9.1 DTO 兼容

- v1 DTO 字段名冻结，只增不改。
- 破坏性变更新开 v2 服务名并共存过渡。
- `extra="allow"` 透传未知字段，保证 PI V2 继续漂移时未知字段不丢。
- `raw: dict` 保留原始 JSON，确保任何未被显式建模的字段不丢。

### 9.2 旧格式兼容

- `OptionValue = str | list[str] | dict[str, str]` 保持兼容，v1 新增 `OptionSelection` 结构化格式作为可选增强。
- `TaskSnapshot` 三字段（taskOrder / taskChecked / taskOptions）冻结。
- `CUSTOM_PRESET_NAME = "__auto_mas_custom_preset__"` 保留键冻结。
- 旧 task option 输出继续可生成（`normalize_task_execution_payload` 的 tuple 返回保持兼容）。

### 9.3 服务名兼容

- `maafw.*.v1` 服务名冻结。
- 破坏性变更开 `maafw.*.v2` 服务名，v1 和 v2 共存过渡。
- interface 包冻结最严，因为 MaaEnd 等外部消费者只依赖它。

## 10. 待人工确认事项

1. **option 作用域的承载位置**：当前代码中 option 没有显式 scope 字段，scope 是通过引用位置隐式确定的。v1 契约的设计已明确：`OptionDefinition` 不绑定单一 scope（一个 option 可被多处引用），权威作用域放在 `OptionReference`（解析器输出）和 `OptionSelection`（用户选择结果）上；`OptionDefinition.scopes: list[str] | None` 仅供聚合展示。需确认：`setting` / `pretask` / `hotkey` 三个预留 scope 当前 PI V2 规范中没有显式来源，v1 暂不输出，留作 v2 待确认。

2. **OptionSelection 是否替代旧 OptionValue**：旧格式 `str | list[str] | dict[str, str]` 和新结构 `OptionSelection` 并存会增加复杂度。需确认：是逐步迁移到 OptionSelection，还是长期保持双格式。本文档建议 P1 先双格式，P4 评估是否收敛。

3. **ValidationReport 是否替代现有 raise 异常模式**：现有 interface_loader 在冲突时直接 raise。v1 引入 ValidationReport 后，是否所有校验都走 Report 而非 raise。需确认：load() 在有 error 时是返回带 errors 的 InterfaceModel 还是 raise。本文档建议 load() 在 error 时 raise（保持兼容），validate() 返回 Report。

4. **agent plan 是否从 run_plan.py 拆出**：当前 `run_plan.py` 同时包含 run plan 和 agent command plan。方案文档要求 agent plan 迁到 project 包。需确认拆分时机：P1 拆还是 P2 拆。本文档建议 P2 拆（project 包抽出时一起拆）。

5. **worker JSON 行协议是否在 P0 冻结**：方案文档 P0 交付物包含"worker JSON 行协议是否需要在 P0 冻结的结论"。本文档建议 P0 冻结协议骨架（type: log/result/error），但允许 P1/P2 增加事件类型（如 task_start/task_done），因为增加事件类型是向后兼容的。

6. **controller provider 的 DeviceSpec.config 内容**：当前 `MaaFWDeviceConfig.config` 是 `dict`，包含 emulator extras 等内容。需确认 v1 是否冻结 config 的结构，还是保持 dict 透传。本文档建议保持 dict 透传，由 provider 定义具体内容。
