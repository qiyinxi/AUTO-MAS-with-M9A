# MaaFW 插件化最终实现方案

> 状态：可开工方案
> 日期：2026-07-06
> 范围：AUTO-MAS 后端、前端插件页、MaaFW/M9A 插件包、风味发行版打包

本文描述准备实现的最终方案。目标是把当前内置在 AUTO-MAS 主程序中的 MaaFW / M9A 能力拆成可安装、可复用、可打包的插件组，同时保留现有直控运行能力、M9A 专项体验和未来独立宿主的可能性。

## 1. 总目标

MaaFW 插件化完成后，系统应满足四个结果：

1. MaaFW 的通用能力从主程序内置代码迁出，形成稳定的基础插件服务。
2. M9A 不再复制 MaaFW 运行逻辑，而是作为 MaaFW project pack 声明自己的默认值、任务语义、周月规则、文案和页面。
3. 前端仍保持专用队列、option、说明等复杂体验，不退化成纯 schema 表单。
4. 插件包、前端资产、离线 seed、maa runtime 和 maafw 风味发行版都有明确打包路径。

一句话结构：

```text
AUTO-MAS 插件宿主
  -> automas-script-maafw      # 注册 MaaFW 脚本类型，编排基础服务和 UI
      -> automas-maafw-interface
      -> automas-maafw-project
      -> automas-maafw-runner
      -> automas-maafw-controller-adb / desktop
      -> automas-script-maafw-pack-m9a
```

## 2. 不变红线

这些约束是实现时的硬边界：

1. MaaFW 的 maa binding 不能回到 AUTO-MAS 主进程内加载。继续保留“主进程 -> runner worker 子进程 -> agent 子进程”的三进程模型。
2. `automas-maafw-interface` 只解析 ProjectInterface，不启动 tasker、不读写用户配置、不依赖 emulator、通知、任务管理器，也不包含 M9A / MaaEnd 任务语义。
3. agent 环境准备属于 project 服务；agent 子进程的启动、连接和回收属于 runner 会话。
4. ADB 路径、模拟器实例和模拟器扩展能力来自 emulator 插件；MaaFW runner 不复刻 MuMuManager 逻辑。
5. 控制器按插件族拆分。第一批实现 adb 和 win32，gamepad / playcover 只预留。
6. M9A 的目标形态是 MaaFW project pack，不在最终形态里注册独立脚本类型。只有 pack SDK 尚未落地时，允许临时用 ScriptAdapterPlugin 做过渡 PoC，但不能复制 runner。
7. 周/月任务机制通用，规则由 project pack 声明。通用 MaaFW 层不内置任何 M9A 默认周月任务。
8. 通知通道走 `automas-notification`，MaaFW / M9A 只产出结构化结果和专项文案。
9. 后端 schema 变更后，前端 API 代码只能通过 OpenAPI 生成器更新，不手改 `frontend/src/api/**`。
10. 旧 `MaaFWConfig` / `M9AConfig` 只读兼容和迁移，迁移工具只创建新配置，不覆盖旧值。
11. 当前阶段不实现计划表，不新增 `MaaFWPlanConfig`、`QueueMode`、`PlanId`、`PLAN_BOOK`、`planTypeRegistry`、`MaaFWPlanTable`。

### 2.1 开工护栏

P0 / P1 只允许做契约、审计、只读 facade、低风险新增文件和兼容验证，不允许默认切换现有 MaaFW / M9A 运行路径。

执行顺序必须遵守：

1. 先读现有实现，形成代码事实和迁移映射。
2. 再冻结 `maafw.interface.v1`、`maafw.project.v1`、`maafw.agent.v1`、`maafw.runner.v1` 的 DTO 草案。
3. 再补只读 facade 或新包脚手架。
4. 最后做 old/new 输出对照。
5. 只有对照结果通过并经过人工确认后，才允许把旧 MaaFW / M9A 路径切到新服务。

P0 / P1 明确禁止：

- 删除、移动或重命名旧 `app/task/MaaFW/**`、`app/task/M9A/**` 文件。
- 修改现有脚本调度入口的默认路径。
- 新增计划表相关模型、字段、页面或注册表。
- 手改 OpenAPI 生成文件。
- 为了新 scoped option 改坏旧 task option 的输出结构。

### 2.2 兼容验收门

任何旧路径切换前，都必须完成 old/new 对照，并把结果写入审核材料：

| 对照对象 | 必须一致或兼容 |
| --- | --- |
| interface 解析结果 | import 合并后的 task、option、preset、controller、resource 列表不丢字段 |
| TaskSnapshot | 旧队列能 normalize 成新快照，新快照能还原旧运行所需信息 |
| option 选择结果 | 旧 task option 照常可读；新增 `scope`、`value`、`args`、`raw` 只增不删 |
| runner payload | 旧 runner 所需 task name / option 参数仍能生成；结构化 payload 不能丢 agent args |
| 前端任务构建 | 通用 MaaFW 和 M9A 共用 `MaaFWTaskBuilder`；M9A 不能复制一套任务构建器 |
| 旧配置迁移 | 只创建新配置，不覆盖旧配置；插件缺失时旧配置仍可只读查看 |

## 3. 最终包结构

第一批落地 6 个核心包，另加 1 个 M9A pack。基础包尽量 headless，只有编排包和 pack 负责脚本类型、页面和用户可见体验。

| 包 | 类型 | 对外服务 / 能力 | 依赖 | 第一阶段职责 |
| --- | --- | --- | --- | --- |
| `automas-maafw-interface` | 基础包 | `maafw.interface.v1` | pydantic、json5 | ProjectInterface V2 解析、校验、预览、任务快照归一化 |
| `automas-maafw-project` | 基础包 | `maafw.project.v1`、`maafw.agent.v1` | interface | 项目更新、agent 环境准备、agent command plan |
| `automas-maafw-runner` | 基础包 | `maafw.runner.v1` | interface、project、maa wheel | runner session、worker 子进程、Tasker 直控、事件流 |
| `automas-maafw-controller-adb` | 控制器包 | `maafw.controller.adb` | registry；wants emulator | ADB device spec、模拟器能力消费、ADB precheck |
| `automas-maafw-controller-win32` | 控制器包 | `maafw.controller.win32` | registry | Win32 窗口扫描、句柄匹配、Win32 device spec |
| `automas-script-maafw` | 编排插件 | `maafw.registry.v1`、`ScriptType=MaaFW` | interface、project、runner | MaaFW 脚本生命周期、provider registry、共享 UI 组件层 |
| `automas-script-maafw-pack-m9a` | project pack | M9A pack definition | script-maafw、notification | M9A 默认队列、周月规则、专项页面、文案和迁移入口 |

安装组合：

| 场景 | 安装 |
| --- | --- |
| MaaEnd 只消费解析器 | `automas-maafw-interface` |
| 通用 MaaFW ADB 直控 | `automas-script-maafw[adb]` |
| 通用 MaaFW 全控制器 | `automas-script-maafw[full]` |
| M9A 完整体验 | `automas-script-maafw-pack-m9a` + `automas-notification` |
| maafw 风味发行版 | Full 包 + 离线 seed + maa runtime 预置 |

## 4. 基础服务契约

### 4.1 `maafw.interface.v1`

职责：

- 读取 `interface.json` / `interface.jsonc`。
- 处理 `import` 递归合并、循环检测和冲突检测。
- import 合并完成后再做必填字段和引用校验；单个被导入片段允许只提供 options、tasks、agents、settings 等局部内容，不能因为 root 或片段暂时缺少 task 就提前失败。
- 展开 `scan_select`。
- 解析 i18n 字段。
- 解析 ProjectInterface 中声明的实际任务目录，包括任务入口、分组、任务显示信息、option 元数据、preset 引用和默认任务快照。
- 解析不同作用域的 option / setting / pretask / hotkey / global option 元数据，保留其作用域和原始结构。
- 校验 task / option / preset / controller / resource 引用一致性。
- 输出稳定 DTO，顶层带 `interface_version` 和 `capabilities`。
- 提供任务快照归一化和预览 DTO。

服务接口：

```text
maafw.interface.v1.load(path, force_reload=False) -> InterfaceModel
maafw.interface.v1.preview(path) -> InterfacePreview
maafw.interface.v1.validate(interface) -> ValidationReport
maafw.interface.v1.build_default_snapshot(interface, preset=None) -> TaskSnapshot
maafw.interface.v1.normalize_snapshot(interface, snapshot) -> TaskSnapshot
maafw.interface.v1.normalize_execution_payload(interface, tasks, options, controller, resource) -> ExecutionPayload
maafw.interface.v1.rescan_option(path, option_name) -> OptionCases
```

option 解析与传参契约：

```text
OptionDefinition
  key: str
  scope: "task" | "global" | "setting" | "pretask" | "hotkey" | "controller" | "resource"
  type: "bool" | "select" | "multi_select" | "input" | "number" | str
  label: str
  description: str | None
  cases: list[OptionCase]
  default: OptionValue | None
  raw: dict

OptionCase
  name: str
  args: str | list | dict | bool | int | float | None
  raw: dict

OptionSelection
  key: str
  scope: str
  value: bool | str | int | float | list | dict | None
  args: str | list | dict | bool | int | float | None
  raw: dict
```

规则：

- `select` 选中某个 case 时，`value` 保留选择结果，`args` 保留该 case 声明的 `args`；如果没有 `args`，再退回 `value`。
- `multi_select` 保留选择列表，并按选择顺序输出对应 `args` 列表。
- `bool` / `input` / `number` 保留用户输入的原始类型，不提前转成字符串。
- `normalize_execution_payload()` 输出结构化 option 结果，由 runner 或 agent adapter 决定怎么注入给 agent；不要只传 task name，也不要把所有 option 提前压成一段不可逆字符串。
- parser 只保证结构稳定和引用合法，不解释某个 option 对游戏逻辑的含义。

可选 HTTP route：

```text
POST /maafw/interface/preview
POST /maafw/interface/rescan-option
```

实现边界：

- 不 import `app/core`、`app/task`、`app/api`。
- 不启动 MaaFW tasker。
- 不读写 AUTO-MAS 用户配置。
- 不出现 M9A、MaaEnd、MXU 等专项任务名。
- 只解析“有哪些任务、任务怎么配置”，不决定“今天跑哪些任务、任务失败后如何补跑、周月规则如何跳过、通知文案如何表达”。
- 不强行决定 global option、setting、pretask、hotkey 应该放在哪个 UI 面板；interface 输出 scope，前端和 pack 根据产品体验决定摆放。
- DTO 字段名作为 v1 契约维护，新增字段允许，破坏性变更必须新开 v2 服务名。

### 4.2 `maafw.project.v1` 与 `maafw.agent.v1`

`automas-maafw-project` 负责“项目资产”，包含更新和 agent 环境两组能力。它不持有 agent 进程，只准备可执行命令方案。

职责：

- 检查 GitHub / MirrorChyan 更新。
- 下载并应用全量包或增量包，防止路径越界，失败不破坏项目目录。
- 解析 `interface.agent` 中的 `child_exec`、`child_args`、`identifier`、`embedded`。
- 判断 agent 运行形态：项目自带 Python、项目可执行文件、隔离 venv、外部命令。
- 创建项目专属 venv，只安装项目 `requirements.txt`，不污染 AUTO-MAS 主环境。
- 生成 `AgentPlan`，包括命令、工作目录、环境变量、连接参数和日志标识。

服务接口：

```text
maafw.project.v1.check_update(project_path, interface, channel, cdk) -> UpdateCandidate
maafw.project.v1.apply_update(project_path, candidate) -> UpdateResult

maafw.agent.v1.classify(interface.agent) -> AgentMode
maafw.agent.v1.prepare_env(project_path, interface.agent) -> AgentEnvResult
maafw.agent.v1.build_command_plans(project_path, interface.agent) -> AgentPlan[]
```

实现边界：

- project 包零 maa 依赖。
- `embedded: true` 不允许在主进程 import 项目 agent 代码，统一转成 isolated subprocess 策略。
- 只处理项目目录，不处理用户侧任务队列、通知或账号。

### 4.3 `maafw.runner.v1`

runner 是 MaaFW 直控执行层。它负责会话、worker 子进程、Tasker、agent 子进程和事件流。

架构要求：

```text
AUTO-MAS 主进程
  -> runner session manager
      -> runner_worker.py 子进程   # 只在这里 import maa
          -> MaaFW Tasker
      -> agent 子进程              # 仅在项目声明 agent 时启动
```

职责：

- 根据 interface、任务快照、controller、resource 构建 `RunPlan`。
- 深合并 pipeline override。
- 启动 worker 子进程，并通过 JSON 行协议收发事件。
- 在 worker 内创建 Library / Controller / Resource / Tasker。
- 根据 `AgentPlan` 启动 agent 子进程、连接 `AgentClient`、会话结束后回收。
- 发送 `log`、`task_start`、`task_done`、`task_failed`、`session_done`、`session_error` 等事件。
- 支持 stop / dispose 清理 worker、agent、日志 tailer 和临时资源。
- 输出失败摘要、错误截图、日志路径和结构化运行结果。

服务接口：

```text
maafw.runner.v1.build_plan(project_path, interface, selection) -> RunPlan
maafw.runner.v1.create_session(run_plan, device, agent_plan|None, callbacks) -> SessionId
maafw.runner.v1.run(session_id) -> RunResult
maafw.runner.v1.stop(session_id) -> StopResult
maafw.runner.v1.dispose(session_id) -> None
```

`device` 是 provider 解析后的中性结构：

```text
type: "Adb" | "Win32"
adbPath: str | None
address: str | None
hWnd: int | None
screencapMethods: list[str]
inputMethods: list[str]
config: dict
```

实现边界：

- runner 不扫描模拟器，不调用 MuMuManager。
- runner 不关心 provider 来自 adb、win32 还是未来 playcover，只接受 `DeviceSpec`。
- runner core 不 import `PluginContext`，插件适配层只负责把 service / route / callback 接进 core。

## 5. 控制器插件族

控制器插件不注册脚本类型，只向 `maafw.registry.v1` 注册 provider。这样脚本编辑页可以根据已安装 provider 渲染字段，未安装时显示能力缺失，而不是渲染无效配置。

provider 最小接口：

```python
class ControllerProvider:
    key: str
    display_name: str
    controller_types: list[str]

    async def decorate_schema(self, schema, config, ctx) -> dict: ...
    async def precheck(self, runtime) -> str: ...
    def build_device_config(self, iface_controller, user_fields) -> DeviceSpec: ...
    async def cleanup(self, runtime) -> None: ...
```

第一批 provider：

| provider | 包 | 范围 |
| --- | --- | --- |
| `adb` | `automas-maafw-controller-adb` | 消费 emulator 服务，生成 ADB device spec，处理 ADB capability precheck |
| `win32` | `automas-maafw-controller-win32` | 窗口扫描、句柄选择、Win32 device spec |

运行规则：

- 一个脚本实例只选择一个控制器族。
- 多个控制器包可以同时安装。
- `decorate_schema` 只注入当前选择族的字段。
- `precheck` 失败返回可操作文案，例如“未安装 emulator 插件”或“未找到匹配窗口”。

## 6. 编排插件 `automas-script-maafw`

`automas-script-maafw` 是完整 MaaFW 脚本类型的入口，也是 controller provider 和 project pack 的注册中心。

### 6.1 后端职责

它注册 `ScriptAdapterDefinition(type_key="MaaFW")`，并实现 `ScriptAdapterHooks`：

```text
check
  -> interface 校验
  -> controller provider precheck
  -> agent 环境可用性检查

prepare
  -> 可选项目更新
  -> agent env / command plan
  -> runner create_session

run_auto_proxy
  -> runner.run(session_id)

finalize
  -> provider cleanup
  -> runner.dispose(session_id)

on_crash
  -> 截图、日志、失败摘要
```

同时提供：

- `maafw.registry.v1`，用于注册 controller provider 和 project pack。
- `decorate_script_schema`，按 controller provider 注入脚本级配置字段。
- `decorate_user_schema`，注入用户级 resource、任务队列、通知、运行选项。
- 通用周期机制：读取 pack 的 `period_rules`，运行时维护 `Data.PeriodTaskRecords`。
- 旧配置只读兼容入口和迁移入口。

### 6.2 数据归属

| 配置 | 归属 |
| --- | --- |
| 项目路径、项目名、版本、更新源、ProjectPack 标识 | 脚本级 `PluginData.Config.Info` / `Update` |
| 当前控制器族 | 脚本级 `Info.Controller` |
| ADB 地址、模拟器实例、窗口句柄等族字段 | controller provider 注入 |
| 用户 resource、账号 | 用户级 `Info.*` |
| 固定任务队列、启用状态、option | 用户级 `Task.TaskSnapshot` |
| 周期跳过记录 | 用户级 `Data.PeriodTaskRecords` |
| 通知开关 | 用户级 `Notify.*`，通道归 `automas-notification` |
| 调试绘制、截图、日志级别 | `Run.Debug` / `Run.Draw` / `Run.Log` |

原则：脚本级描述“这个 MaaFW 项目怎么被 AUTO-MAS 管理”，用户级描述“这个账号怎么跑”。

### 6.3 Project Pack SDK

M9A 这种专项不复制 runner，而是声明一个 project pack。

```python
class MaaFWProjectPackDefinition(BaseModel):
    key: str
    display_name: str
    project_repo: str | None
    interface_path: str = "interface.json"
    supported_controllers: list[str]
    default_controller: str
    default_resource: str | None
    default_preset: str | None
    default_task_queue: list[str] | None
    period_rules: list[PeriodRule]
    reserved_task_semantics: dict
    icon: str | None
    notes: str | None

class MaaFWProjectPackPlugin:
    def build_project_packs(self) -> list[MaaFWProjectPackDefinition]: ...
```

第一版 pack SDK 只允许声明元数据、默认值、模板、规则和文案，不开放 run plan hook。只有出现明确非标准生命周期时，才讨论完整 ScriptAdapter。

## 7. M9A Pack

`automas-script-maafw-pack-m9a` 是 M9A 的最终目标形态。

它负责：

- 声明 `key="m9a"` 的 project pack。
- 提供默认项目来源、默认 controller、默认 resource、默认 preset。
- 提供默认任务队列、日常/周常/月常模板。
- 声明 M9A 周/月周期规则，例如 `Psychube` 每周一次、`SleepDream` 每月一次。
- 提供 M9A 专项用户页，复用共享任务队列、option、说明组件。
- 把通用 runner 结果翻译成 M9A 用户能理解的通知标题和正文。
- 提供旧 M9A 配置到插件配置的只创建迁移入口。

它不负责：

- ProjectInterface 解析。
- runner、worker、agent 进程管理。
- emulator / ADB 解析。
- 通知通道实现。
- MaaEnd 或其他 MaaFW 项目的任务语义。

M9A 项目资产不进 AUTO-MAS 安装器。`resource/**`、`agent/main.py`、`bootstrap.py`、`agent_runtime.py`、`deps/*.whl` 等仍属于 M9A 项目目录，由 `maafw.project.v1` 拉取和管理。

## 8. 后端落地路径

后端按“先抽服务，后迁脚本类型”的方式推进，避免一次性搬空导致不可运行。

### 8.1 模块边界

| 责任 | 位置 |
| --- | --- |
| 请求/响应 schema | `app/models/schema.py` 或插件自己的 schema 模块 |
| HTTP 路由 | 对应插件 route；主程序 API 只保留兼容期代理 |
| 全局编排、脚本生命周期 | `automas-script-maafw` 的 adapter hooks |
| 纯 MaaFW 解析 / 更新 / runner | 各基础包的 `core/` |
| controller 能力 | controller provider 包 |
| 旧内置数据迁移 | `automas-script-maafw` / `pack-m9a` 的迁移服务 |

### 8.2 当前文件迁移映射

| 当前文件 | 目标归属 | 说明 |
| --- | --- | --- |
| `app/task/MaaFW/interface_models.py` | `automas-maafw-interface` | DTO 字段冻结为 v1 契约 |
| `app/task/MaaFW/interface_loader.py` | `automas-maafw-interface` | import 合并、scan_select、缓存 |
| `app/task/MaaFW/interface_preview.py` | `automas-maafw-interface` | 预览 DTO |
| `app/task/MaaFW/task_config.py` | `automas-maafw-interface` | TaskSnapshot 归一化 |
| `app/task/MaaFW/project_updater.py` | `automas-maafw-project` | 项目更新 |
| `app/task/MaaFW/run_plan.py` | `automas-maafw-runner` | run plan 构建；agent plan 迁到 project |
| `app/task/MaaFW/pipeline_override.py` | `automas-maafw-runner` | pipeline override 深合并 |
| `app/task/MaaFW/runner.py` | `automas-maafw-runner` | worker 侧 MaaFW 直控 |
| `app/task/MaaFW/runner_worker.py` | `automas-maafw-runner` | worker 子进程入口和 JSON 行协议 |
| `app/task/MaaFW/control_capabilities.py` | runner + controller-adb | runtime DLL 探测归 runner；模拟器能力归 controller-adb |
| `app/task/MaaFW/window_service.py` | controller-win32 | 窗口扫描、句柄匹配、正则选择 |
| `app/task/MaaFW/manager.py` | `automas-script-maafw` | 改写为 ScriptAdapterHooks |
| `app/task/MaaFW/AutoProxy.py` | `automas-script-maafw` | 会话驱动改走 `maafw.runner.v1` |
| `app/task/M9A/**` | `automas-script-maafw-pack-m9a` | 专项队列、周月、文案；通用部分消解 |
| `app/models/config.py` 的 `MaaFWConfig` / `M9AConfig` | 只读兼容，后续废弃 | 迁移到 `PluginScriptConfig` |

### 8.3 API 与 schema 原则

- 新 HTTP endpoint 使用 `*In` / `*Out` schema，显式 `response_model`。
- route handler 只做 transport mapping，不写长流程逻辑。
- 插件内部服务优先通过 `ctx.service` 消费，不直接 import 其他插件内部模块。
- 涉及 OpenAPI 的主程序 schema 改动后，前端 API 通过生成器更新。
- 兼容期主 API 可以代理到插件 route，但需要在 P4 结束时明确 fallback 删除时间点。

## 9. 前端落地路径

插件化不能让 MaaFW / M9A 前端体验降级。前端采用“schema 表单 + 专用复杂组件”混合方案。

### 9.1 页面组织

| 区域 | 实现方式 |
| --- | --- |
| 项目路径、更新源、controller、resource 等标量字段 | 复用 `PluginScriptEdit.vue` / `PluginUserEdit.vue` + `SchemaForm.vue` |
| 通用任务构建 | `MaaFWTaskBuilder` 组件层：从 interface tasks / preset / option 构建 `TaskSnapshot` |
| 任务队列、拖拽排序、任务 option、任务说明 | `MaaFWTaskQueueEditor`、`MaaFWTaskOptionEditor`、`MaaFWDescriptionView` |
| M9A 专项工作台 | pack-m9a 提供专项页，直接复用 `MaaFWTaskBuilder` 和队列/option/说明组件，只覆盖模板、周月提示、文案 |
| controller 缺失 | 显示能力缺失、安装动作或配置指引，不渲染无效字段 |
| 旧内置 MaaFW / M9A | 兼容期只读入口 + 迁移入口 |

### 9.2 组件分包

第一版共享组件层随 `automas-script-maafw` 分发：

```text
automas_script_maafw/
  frontend/
    manifest.json
    assets/
    components/
      MaaFWTaskQueueEditor
      MaaFWTaskOptionEditor
      MaaFWDescriptionView
```

共享组件层按“任务构建核心 + 专项包装页”划分：

| 组件 / composable | 归属 | 作用 |
| --- | --- | --- |
| `MaaFWTaskBuilder` | `automas-script-maafw` | 通用任务构建面板，接收 interface、resource、preset、初始 `TaskSnapshot` 和 scoped options，输出可运行快照 |
| `MaaFWTaskQueueEditor` | `automas-script-maafw` | 队列增删、启用、排序、复制、从模板填充 |
| `MaaFWTaskOptionEditor` | `automas-script-maafw` | 根据 interface option 元数据编辑任务 option |
| `MaaFWDescriptionView` | `automas-script-maafw` | 渲染任务说明、option 说明和限制提示 |
| `useMaaFWTaskBuilder` | `automas-script-maafw` | 快照 normalize、preset 应用、scoped option 默认值合并、dirty 状态 |
| M9A 工作台页 | `pack-m9a` | 注入 M9A 模板、默认队列、周月标签、游戏文案和通知摘要 |

`pack-m9a` 不复制任务构建组件。它只把 M9A 的 pack metadata、模板、周期标识和文案传给通用组件层，再监听通用组件输出的 `TaskSnapshot` 保存到用户配置。

通用组件层不写 M9A 任务名白名单，不判断周/月归属，不生成 M9A 通知文案；这些专项知识都由 `pack-m9a` 通过输入数据提供。`global`、`setting`、`pretask`、`hotkey` 等作用域先作为 scoped option 交给组件，组件只提供可组合面板和事件，不在底层固定它们必须出现在某个页面位置。等第二个 project pack 真正复用这套组件后，再评估拆 `automas-script-maafw-ui`，不要提前维护空 UI 包。

### 9.3 交互要求

- 页面继续使用 Ant Design Vue 和现有主题 token，不新增 MaaFW 专属颜色系统、按钮系统或营销式布局。
- 颜色、边框、背景、状态色需要兼容亮色和暗色主题。
- 任务队列拖拽必须有明确 handle，不能吞掉开关、select、option 按钮点击。
- option 编辑继续用结构化表单，不把嵌套 option 压成一行 JSON。
- 任务说明和 option 文案来自 interface / pack，不在组件里写死游戏文案。
- 插件 custom element 如果在复杂拖拽、主题注入或 HMR 上体验不达标，P4/P5 允许先走宿主内置组件桥接过渡。过渡只改变装载方式，不降低功能。

## 10. 插件包打包

带 UI 的插件包必须把 Python 后端、前端构建产物、静态资源和版本契约一起发布进同一个 wheel。

推荐 wheel 结构：

```text
automas_script_maafw/
  core/
  plugin.py
  frontend/
    manifest.json
    assets/
      index-<hash>.js
      index-<hash>.css
      icon.svg
```

打包要求：

1. `pyproject.toml` 通过 package-data / include 机制把 `frontend/manifest.json` 和 `frontend/assets/**` 打进 wheel。
2. 前端先 `yarn build`，Python 再 `python -m build` 封装已冻结产物。
3. 发布 wheel 不允许首启再跑 `npm install`，也不从 CDN 拉插件页面资产。
4. 开发期可让 manifest 指向本地 dev server 做 HMR，发布包只能使用相对静态资产入口。
5. `manifest.json` 至少声明 `id`、`version`、`min_auto_mas_version`、`frontend_api_version`、`render`、`entry`、`style`、`icon`、`routes/actions`。
6. `PluginFrontendLoader` 按 `plugin_id + version + asset hash` 加载，避免旧缓存污染新版本。

插件发布顺序：

```text
interface
  -> project
  -> runner + controller
  -> script-maafw
  -> pack-m9a
```

版本策略：

- 0.x 阶段允许 DTO 调整，破坏性变更 minor +1 并写 changelog。
- `maafw.*.v1` 契约冻结时全族升 1.0.0。
- 1.0 后 v1 DTO 只增不改，破坏性变更开 `.v2` 服务名并共存过渡。
- interface 包冻结最严，因为 MaaEnd 等外部消费者只依赖它。

## 11. 应用打包与风味发行版

插件市场安装解决已有 AUTO-MAS 用户；maafw 风味发行版解决“开箱即用、离线可用”的用户。

### 12.1 风味包内容

maafw 风味包 = AUTO-MAS Full 包 + 两层预置：

1. 离线 seed 插件：
   - `automas-script-maafw[full]`
   - `automas-script-maafw-pack-m9a`
   - `automas-notification` 及需要的通道
   - 全部传递依赖
2. maa runtime：
   - maa wheel
   - MaaFramework 原生 DLL
   - worker runtime 查找顺序在 P3 定型

M9A 项目资产不进安装器，仍由 `maafw.project.v1` 首次拉取或更新。

### 12.2 命名规范

```text
AUTO-MAS-maafw-<channel>-<version>-<commit>
```

`channel` 取 `alpha`、`beta`、`stable`。本地手工构建可以临时带时间戳，但不再使用 `-fixed-` 后缀；修补应滚新 commit 重打。

### 12.3 构建阶段

| 阶段 | 方式 | 产物 |
| --- | --- | --- |
| 短期，P3 前 | 把现有手工 alpha 流程脚本化 | `maafw-alpha`，可无签名但需明示 |
| 中期，P4-P6 | fork 增加独立 workflow，可从 `dev_v2` 触发 | `maafw-beta` |
| 终局，P6 后 | maafw 差异收敛为插件 + seed 清单，成为官方构建矩阵项 | `maafw-stable`，官方签名 |

关键要求：

- seed 插件和市场安装使用同一份锁文件，避免同版本后端加载不同前端资产。
- 风味包 seed 时记录 wheel hash 和前端 asset hash。
- 离线 seed 必须锁全传递依赖，首启不应触网。
- maa runtime 倾向只在风味包预置层携带，不拖大所有官方标准包。

## 12. 直控应用预留

当前 AUTO-MAS 已经是直控，不需要从外部 GUI 寄生态切换。未来要做的是让直控能力离开 MAS 宿主也能运行。

每个基础包内部必须保持两层：

```text
automas_maafw_xxx/
  core/        # 宿主无关，不 import PluginContext，不 import app.*
  plugin.py    # MAS 适配层，注册 service / route / page
```

runner worker 的 JSON 行协议是第二道宿主无关边界。任何宿主只要能拉子进程并读写 stdio，就可以驱动 MaaFW 会话。

P7 验收物：

```text
maafw-smoke
  -> 打开项目目录
  -> 解析 interface
  -> 选择 controller / resource / task
  -> 绑定 ADB 或 Win32
  -> 跑一条 task
  -> 输出日志和结构化结果
```

如果未来满足以下任一条件，再立项 slim host：

- maafw 风味包体积被 AUTO-MAS 主体拖累且用户明确抱怨。
- maafw 发版节奏被 AUTO-MAS 主程序强耦合阻塞。
- 需要独立品牌分发、独立官网或独立更新源。

默认 slim host 方案优先裁剪现有 Electron 壳，不另起 Tauri / 新前端栈。

## 13. 分阶段实施路线

### P0：契约盘点

目标：冻结最小 v1 服务面，不移动代码。

交付：

- `maafw.interface.v1`、`maafw.project.v1`、`maafw.agent.v1`、`maafw.runner.v1` DTO 草案。
- M9A、MaaEnd、Maa_bbb 等本地样例解析记录。
- emulator 服务能力确认：adbPath、address、instance、capability。
- worker JSON 行协议是否需要在 P0 冻结的结论。

验收：

- 能列出每个 DTO 的字段、可选性、默认值和兼容策略。
- MaaEnd 只依赖 interface 的边界清楚。

### P1：抽出 interface 包

目标：先交付 MaaEnd 也能消费的通用解析器。

交付：

- `automas-maafw-interface`。
- `maafw.interface.v1` service。
- 可选 HTTP route：preview / rescan-option。
- 新增只读 facade 或兼容代理，让旧 MaaFW 代码可以在人工确认后调用新 service；默认运行路径仍保持旧实现。

验收：

- M9A `interface.json` 可解析。
- MaaEnd `interface.json` 可解析，imports 后能得到任务列表。
- scan_select、preset、resource/controller 限制能被检测。
- interface 包安装不拉 maa wheel。
- old/new interface 输出对照文档完成，且没有切换默认运行路径。

### P2：抽出 project 包

目标：把项目更新和 agent 环境准备从 runner 中拆出。

交付：

- `automas-maafw-project`。
- `maafw.project.v1` 更新服务。
- `maafw.agent.v1` 环境准备和 command plan。

验收：

- 更新失败不会破坏项目目录。
- agent 环境准备不污染 AUTO-MAS 主 Python。
- M9A 的项目自带 Python + agent 能形成明确 `AgentPlan`。
- embedded agent 被转换为 isolated subprocess。

### P3：抽出 runner 与 controller-adb

目标：直控会话服务成立。

交付：

- `automas-maafw-runner`。
- `automas-maafw-controller-adb`。
- worker 子进程模型保留。
- runner session 事件流。
- ADB device spec 来自 emulator 服务。

验收：

- 纯 pipeline 项目可在 ADB 下跑 smoke task。
- 有 agent 的项目可启动、连接、回收 agent 子进程。
- stop / dispose 能清理 worker、agent、日志 tailer。
- maa wheel 兼容版本区间和 runtime 查找顺序定型。

### P4：编排插件与 desktop controller

目标：通用 MaaFW 作为完整插件闭环运行。

交付：

- `automas-script-maafw`。
- `automas-maafw-controller-win32`。
- `ScriptType=MaaFW`。
- 共享前端组件层。
- 旧内置 MaaFW 进入兼容期。

验收：

- 用户只装 `automas-script-maafw[adb]` 即可创建并运行通用 MaaFW 脚本。
- desktop 窗口扫描可用。
- 未安装 controller 族时显示能力缺失。
- 旧配置能只读展示并引导迁移。

### P5：M9A pack

目标：M9A 专项以 project pack 形态完成等价迁移。

交付：

- `automas-script-maafw-pack-m9a`。
- M9A 默认模板、周月规则、专项用户页、通知文案。
- 旧 M9A 队列和用户配置迁移入口。

验收：

- M9A 不依赖外部 MFAAvalonia UI 也能完成任务队列运行。
- 周月跳过只影响 M9A。
- M9A 通知文案由 pack 生成并走 `automas-notification`。
- 迁移只创建新配置，不覆盖旧值。

### P6：前端通用化与稳定发布

目标：完成内置页降级和插件组契约冻结。

交付：

- `builtin:maafw` / `builtin:m9a` 编辑器降级为只读兼容入口。
- 任务队列、option、说明收敛到共享组件。
- 插件组 1.0 候选。
- maafw-stable 风味包候选。

验收：

- 禁用插件后旧配置仍可只读查看。
- 启用插件后新配置走插件路径。
- v1 服务契约只增不改。

### P7：host-agnostic 验收

目标：证明 core 可离开 AUTO-MAS 宿主运行。

交付：

- `maafw-smoke` CLI。
- runner worker JSON 行协议文档。
- slim host 是否立项的复核结论。

验收：

- 不启动 AUTO-MAS，CLI 能打开项目、解析 interface、绑定设备、跑一条任务、输出日志和结果。

## 14. 验证要求

文档阶段：

- 检查文件存在、标题完整、章节覆盖后端、前端、插件打包、阶段验收。
- 不需要运行前端 lint / build。
- 确认全文没有重新引入计划表实现项，除红线中的“不实现计划表”声明外，不出现 `MaaFWPlanConfig`、`QueueMode`、`PlanId` 等落地任务。

实现阶段：

- 后端服务包：单元测试覆盖 parser、project update path safety、agent command plan、runner event flow。
- 切换旧路径前：必须完成 interface、TaskSnapshot、option selection、runner payload 的 old/new 对照。
- runner：必须有 stop / dispose / crash path 测试或 smoke。
- 前端业务代码：至少运行 `yarn lint`。
- 前端构建、路由、插件资产变更：运行对应 build。
- schema 改动：重新生成前端 API，不能手改生成文件。
- 准备提交前：按仓库规则从 `frontend` 运行 `yarn format` 再 `yarn lint`。

## 15. 主要风险与处理

| 风险 | 处理 |
| --- | --- |
| PI V2 继续漂移 | DTO 输出 `interface_version` + `capabilities`，新字段 `extra="allow"` 透传 |
| maa wheel 体积大 | 标准包在线安装，风味包离线预置；不拖大所有官方包 |
| agent 环境复杂 | 所有 env 创建、pip 回退、连接重试都输出可观测日志 |
| 服务启动时序 | registry 使用 needs / wants 和两阶段重算，编排插件容忍 provider 迟到 |
| custom element 复杂交互不稳定 | P4/P5 可用宿主内置组件桥接过渡，但不删功能 |
| 过早切换旧路径 | P0/P1 默认不切运行路径；old/new 对照通过并人工确认后再切 |
| option 结构破坏兼容 | 新增 `scope/value/args/raw` 只增不删；旧 task option 输出继续可生成 |
| 迁移误覆盖 | 迁移工具只创建，不覆盖；旧值保留只读 |
| MaaEnd 维护越界 | 只承诺 `maafw.interface.v1` 和样例，不承诺 MXU 业务语义 |
