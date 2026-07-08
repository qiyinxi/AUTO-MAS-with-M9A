# MaaFW 插件化 old/new 兼容验收门

> 状态：兼容验收门草案
> 日期：2026-07-06
> 依据：docs/maafw插件化最终实现方案.md 第 2.2 节、docs/maafw-plugin-code-audit.md、docs/maafw-plugin-p0-contract.md
> 约束：任何旧路径切换前，都必须完成 old/new 对照，并把结果写入审核材料

本文档定义 MaaFW 插件化过程中 old（M9A 仍有 app/task/M9A/** 旧运行链路；MaaFW 旧运行链路 app/task/MaaFW/** 已删除，仅保留 MaaFWConfig/MaaFWUserConfig 配置类用于迁移）与 new（automas-maafw-* 插件包实现）的兼容验收门。每个对照对象都有明确的验收标准和测试方法。只有全部对照通过并经人工确认后，才允许把旧 M9A 路径切到新服务。

M9A 的目标状态是作为 MaaFW project pack 迁入插件体系，并直接复用 MaaFW runner 运行；本验收门用于证明旧 `M9A.exe` 进程驱动行为能被新 runner 等价承载，而不是重新决定 M9A 是否插件化。

## 1. 验收门总览

| 对照对象 | 验收要求 | 状态 |
| --- | --- | --- |
| interface 解析结果 | import 合并后的 task、option、preset、controller、resource 列表不丢字段 | P1 待执行 |
| TaskSnapshot | 旧队列能 normalize 成新快照，新快照能还原旧运行所需信息 | P1 待执行 |
| option 选择结果 | 旧 task option 照常可读；新增 scope、value、args、raw 只增不删 | P1 待执行 |
| runner payload | 旧 MaaFW runner 所需 task name / option 参数仍能生成；M9A pack 迁入后能生成 MaaFW runner 可消费的等价 payload，且默认项目/controller/resource/preset 均通过通用约束 | P3/P5 待执行 |
| 前端任务构建 | 通用 MaaFW 和 M9A 共用 MaaFWTaskBuilder；M9A 不能复制一套任务构建器 | P4/P5 待执行 |
| project update | MaaFW 现有资源升级能力迁入 `maafw.project.v1`；M9A 旧更新能力由通用更新服务替换；MaaEnd 消费范围另验收 | P2/P5 待执行 |
| 旧配置迁移 | 只创建新配置，不覆盖旧配置；插件缺失时旧配置仍可只读查看 | P5/P6 待执行 |

## 2. 对照对象 1：interface 解析结果

### 2.1 验收要求

import 合并后的 task、option、preset、controller、resource 列表不丢字段。

### 2.2 对照表

| 字段类别 | 旧实现（app/task/MaaFW/interface_models.py + interface_loader.py） | 新实现（maafw.interface.v1） | 兼容要求 |
| --- | --- | --- | --- |
| controller 列表 | `MaaFWController`（extra="allow"） | `ControllerDefinition`（extra="allow" + raw） | 字段不丢；raw 保留原始 JSON |
| resource 列表 | `MaaFWResource`（extra="allow"） | `ResourceDefinition`（extra="allow" + raw） | 字段不丢；raw 保留原始 JSON |
| task 列表 | `MaaFWTask`（extra="allow"） | `TaskDefinition`（extra="allow" + raw） | 字段不丢；raw 保留原始 JSON |
| option 字典 | `MaaFWOption`（extra="allow"） | `OptionDefinition`（extra="allow" + scopes + raw） | 字段不丢；新增 scopes（聚合展示用）；raw 保留原始 JSON |
| option 引用关系 | 无（隐式） | `OptionReference`（含 scope/owner） | 新增结构，承载权威作用域；旧消费者忽略 |
| option cases | `MaaFWOptionCase`（extra="allow"） | `OptionCase`（extra="allow" + args + raw） | 字段不丢；新增 args；raw 保留原始 JSON |
| option inputs | `MaaFWInputCase`（extra="allow"） | `InputCase`（extra="allow" + raw） | 字段不丢；raw 保留原始 JSON |
| preset 列表 | `MaaFWPreset`（extra="allow"） | `PresetDefinition`（extra="allow" + raw） | 字段不丢；raw 保留原始 JSON |
| group 列表 | `MaaFWGroup`（extra="allow"） | `GroupDefinition`（extra="allow" + raw） | 字段不丢；raw 保留原始 JSON |
| agent | `MaaFWAgent`（extra="allow"） | `AgentDefinition`（extra="allow" + raw） | 字段不丢；raw 保留原始 JSON |
| import 合并 | 硬冲突策略（重名 raise） | 硬冲突策略（重名 raise） | 策略一致 |
| import 片段约束 | IMPORTABLE_KEYS = {"task","option","preset","import"} | 同 | 一致 |
| scan_select 展开 | 加载期扫描 scan_dir 填 cases | 同 | 一致 |
| 缓存签名 | mtime_ns + size 元组 | 同 | 一致 |
| 缓存路径 | data/cache/maafw_interface_loader/{sha256}.json | 同 | 一致（或可配置） |
| i18n 解析 | $key 替换（在 run_plan._load_i18n_mapping） | 迁入 interface 包内 | 输出一致 |
| 校验链 | task_context → option_references → presets | 同 | 一致 |
| interface_version | Literal[2] | Literal[2] | 一致 |
| capabilities | 无 | 新增 list[str] | 新增字段，旧消费者忽略 |

### 2.3 测试方法

1. 准备至少 2 个本地样例（M9A + MaaEnd 或其他 MaaFW 项目）。
2. 用旧 `load_interface_model_cached` 和新 `maafw.interface.v1.load` 分别解析。
3. 对比输出：
   - controller/resource/task/option/preset/group/agent 列表长度一致
   - 每个元素的字段值一致（含 extra 透传字段）
   - import_count 一致
   - scan_select cases 一致
4. 对比缓存行为：
   - 同一输入的缓存签名一致
   - force_reload 后结果一致

### 2.4 已知差异（允许）

- 新实现新增 `capabilities`、`import_count`、`scopes`、`args`、`raw` 字段——只增不删。
- 新实现的 `OptionDefinition` 新增 `scopes: list[str] | None`（聚合展示用，不绑定单一 scope）；权威作用域信息放在新增的 `OptionReference` 上。
- 新实现的 `OptionReference` 是新增结构，承载 option 的引用关系和 scope；旧消费者忽略此字段。
- 新实现的 `OptionCase` 新增 `args` 字段（从 case 声明中提取）。
- 新实现的 `raw` 字段保留原始 JSON 片段。

## 3. 对照对象 2：TaskSnapshot

### 3.1 验收要求

旧队列能 normalize 成新快照，新快照能还原旧运行所需信息。

### 3.2 对照表

| 字段 | 旧实现（task_config.py MaaFWTaskPresetSnapshot） | 新实现（maafw.interface.v1 TaskSnapshot） | 兼容要求 |
| --- | --- | --- | --- |
| taskOrder | list[str]，去重补全（按 interface.task 顺序） | 同 | 一致 |
| taskChecked | dict[str, bool]，按合法 task_id 归一 | 同 | 一致 |
| taskOptions | dict[str, dict[str, OptionValue]]，OptionValue = str / list[str] / dict[str, str] | 同 + 可选 OptionSelection 结构化格式 | 旧格式可读；新格式可选 |
| CUSTOM_PRESET_NAME | "__auto_mas_custom_preset__" | 同 | 保留键冻结 |
| selectedPreset | str | 同 | 一致 |
| presets | dict[str, MaaFWTaskPresetSnapshot] | 同 | 一致 |

### 3.3 option 归一化对照

| option.type | 旧归一化 | 新归一化 | 兼容要求 |
| --- | --- | --- | --- |
| select / scan_select / switch | string（default_case 或首个 case） | 同 | 一致 |
| checkbox | list[string]（default_case 列表与 case 名交集） | 同 | 一致 |
| input | dict[string, value]（每个 input_case.default） | 同 | 一致 |
| bool | 无（旧代码未显式处理） | bool（默认 False） | 新增类型，旧代码透传 |
| number | 无 | int/float（默认 0） | 新增类型，旧代码透传 |
| 未知类型 | 透传 | 原值透传 | 一致 |

### 3.4 测试方法

1. 从现有用户配置中提取 TaskSnapshot（JSON 字符串）。
2. 用旧 `normalize_snapshot` 和新 `maafw.interface.v1.normalize_snapshot` 分别归一化。
3. 对比输出：
   - taskOrder 一致
   - taskChecked 一致
   - taskOptions 的旧格式值一致
4. 反向验证：
   - 新快照能被旧 runner 消费（task_names + task_options 格式可生成）

### 3.5 已知差异（允许）

- 新实现可选输出 `OptionSelection` 结构化格式（含 scope/value/args/raw），但旧 `str | list[str] | dict[str, str]` 格式继续可读。
- 新实现新增 `bool` / `number` / 未知类型的显式归一化（旧代码透传，新代码也透传但标注类型）。

## 4. 对照对象 3：option 选择结果

### 4.1 验收要求

旧 task option 照常可读；新增 scope、value、args、raw 只增不删。

### 4.2 对照表

| 维度 | 旧实现 | 新实现 | 兼容要求 |
| --- | --- | --- | --- |
| option 值格式 | `str | list[str] | dict[str, str]` | 同 + OptionSelection 结构化格式 | 旧格式可读；新格式可选 |
| select 选中 case | value = case name（string） | value = case name, args = case.args | value 一致；args 新增 |
| multi_select / checkbox | value = case name 列表 | value = 列表, args = 按 case.args 顺序列表 | value 一致；args 新增 |
| bool | 无 | value = bool | 新增类型 |
| input | value = dict[input_name, input_value] | 同 | 一致 |
| number | 无 | value = int/float | 新增类型 |
| scope（在 OptionSelection 上） | 无（通过引用位置隐式确定） | OptionSelection 显式标注 scope | 新增字段，标注本次选择属于哪个作用域 |
| scope（在 OptionReference 上） | 无（隐式） | OptionReference 承载权威作用域 | 新增结构，描述 option 的引用关系 |
| raw | 无 | 保留原始 JSON | 新增字段 |

### 4.3 测试方法

1. 从现有用户配置中提取 taskOptions。
2. 用旧 `normalize_task_options_by_task` 和新 `maafw.interface.v1` 的 option 归一化分别处理。
3. 对比输出：
   - 旧格式值（str / list[str] / dict[str, str]）一致
   - 新格式的 value 与旧格式值语义一致
   - 新增的 scope / args / raw 不影响旧格式可读性

### 4.4 已知差异（允许）

- 新增 `scope`（在 `OptionReference` 和 `OptionSelection` 上）/ `value` / `args` / `raw` 字段——只增不删。
- `OptionDefinition` 不绑定单一 scope，新增 `scopes: list[str] | None` 仅供聚合展示。
- `select` 选中 case 时，新实现额外输出 `args`（从 case.args 提取）；如果没有 args，退回 value。
- `multi_select` 新实现按选择顺序输出 args 列表。

## 5. 对照对象 4：runner payload

### 5.1 验收要求

旧 MaaFW runner 所需 task name / option 参数仍能生成；结构化 payload 不能丢 agent args。M9A 迁入 MaaFW runner 时，还必须证明 M9A 默认项目来源、默认 controller、默认 resource（服务器）、默认 preset、默认队列、新脚本一次性任务初始值、任务 option 和日志/通知语义能映射为 runner 可消费的 payload 或 pack sidecar 数据。

### 5.2 对照表

| 维度 | 旧实现（run_plan.py + AutoProxy.py） | 新实现（maafw.runner.v1） | 兼容要求 |
| --- | --- | --- | --- |
| task name 列表 | normalize_task_execution_payload 返回 tuple[list[str], taskOptions] | ExecutionPayload.tasks: list[str] | 一致 |
| task options | dict[str, dict[str, OptionValue]] | ExecutionPayload.options: dict[str, list[OptionSelection]] | 旧格式可生成；新格式可选 |
| controller name | MaaFWRunPlan.controllerName | RunPlan.controller_name | 一致 |
| controller type | MaaFWRunPlan.controllerType | RunPlan.controller_type | 一致 |
| resource name | MaaFWRunPlan.resourceName | RunPlan.resource_name | 一致 |
| M9A 默认 controller/resource/preset | 旧 M9A 配置和默认资源 | pack 预填值 + 通用 MaaFW interface 校验 | 不绕过通用约束 |
| M9A 默认项目来源 | 旧 M9A 路径配置 | pack 推荐来源 + maafw.project.v1 管理 | 按普通 MaaFW 脚本拉取 |
| resource paths | MaaFWResourceBundlePlan.paths | ResourceBundlePlan.paths | 一致 |
| agent plans | MaaFWAgentCommandPlan[] | AgentPlan[] | 字段一致 |
| pi_env | MaaFWRunPlan.piEnv | RunPlan.pi_env | 一致 |
| skipped tasks | MaaFWSkippedTaskPlan[] | SkippedTaskPlan[] | 一致 |
| pipeline_override | MaaFWPipelineOverrideBuilder | 同（迁入 runner 包） | 输出一致 |
| device config | MaaFWDeviceConfig | DeviceSpec | 字段一致 |
| run result | MaaFWRunResult | RunResult | 字段一致 |
| worker 协议 | JSON 行（log/result/error） | 同 | 一致 |

### 5.3 测试方法

1. 用同一 interface + 同一 snapshot + 同一 controller/resource，分别用旧 `build_maafw_run_plan` 和新 `maafw.runner.v1.build_plan` 构建。
2. 对比输出：
   - task name 列表一致
   - controller/resource 一致
   - agent plans 一致
   - pi_env 一致
   - skipped tasks 一致
3. 用同一 run_plan + device，分别用旧 runner 和新 runner 执行 smoke task。
4. 对比运行结果：
   - completed_tasks 一致
   - failed_task 一致
   - error_message 一致

### 5.4 已知差异（允许）

- 新实现 `ExecutionPayload.options` 使用 `OptionSelection` 结构化格式，但旧 `dict[str, dict[str, OptionValue]]` 格式仍可生成。
- 新实现 `RunPlan` 新增 `raw` 字段保留原始数据。

## 6. 对照对象 5：前端任务构建

### 6.1 验收要求

通用 MaaFW 和 M9A 共用 MaaFWTaskBuilder；M9A 不能复制一套任务构建器。

### 6.2 对照表

| 维度 | 旧实现 | 新实现（P4/P5） | 兼容要求 |
| --- | --- | --- | --- |
| MaaFW 任务构建器 | MaaFWUserEdit.vue（1907 行，自包含） | MaaFWTaskBuilder + MaaFWTaskQueueEditor + MaaFWTaskOptionEditor | 功能等价 |
| MaaFW 选项编辑器 | MaaFWTaskOptionEditor.vue（540 行，递归） | MaaFWTaskOptionEditor（共享组件） | 功能等价 |
| MaaFW 说明查看 | MaaFWDescriptionView.vue（198 行） | MaaFWDescriptionView（共享组件） | 功能等价 |
| M9A 任务构建器 | TaskQueueSection.vue（826 行）+ TaskOptionRenderer.vue（350 行） | M9A 工作台页复用 MaaFWTaskBuilder，pack 只预填默认项目/controller/resource/preset 并提供模板/文案/一次性任务初始值 | M9A 不复制构建器 |
| M9A 选项编辑器 | TaskOptionRenderer.vue（独立实现） | 复用 MaaFWTaskOptionEditor，并通过兼容层承载 M9A 数据结构差异 | 功能等价 |
| M9A 说明查看 | 无 | 复用 MaaFWDescriptionView | 新增功能 |
| 任务队列拖拽 | draggable | draggable | 一致 |
| controller/resource 联动 | MaaFWUserEdit 内部实现 | useMaaFWTaskBuilder composable | 功能等价 |
| preset 应用 | MaaFWUserEdit 内部实现 | useMaaFWTaskBuilder.applyPreset | 功能等价 |
| TaskSnapshot 持久化 | useUserApi().updateUser | 同 | 一致 |

### 6.3 测试方法

1. 在通用 MaaFW 脚本中用新共享组件构建任务队列。
2. 在 M9A pack 中用新共享组件构建任务队列（预填默认项目来源、controller、resource、preset，注入 M9A 模板和周月标签）。
3. 对比：
   - 两者使用同一套 MaaFWTaskBuilder
   - M9A 没有复制任务构建器
   - TaskSnapshot 输出格式一致
   - controller/resource 联动一致
   - preset 应用一致
   - M9A 默认值只作为预填，不绕过通用 MaaFW 校验

### 6.4 落地时机

P4：共享前端组件层随 `automas-script-maafw` 落地。
P5：M9A pack 复用共享组件。
P6：内置页降级为只读兼容入口。

## 7. 对照对象 6：project update

### 7.1 验收要求

MaaFW 现有资源升级能力迁入 `maafw.project.v1` 后，更新检查、下载、应用、失败回滚和路径安全行为保持等价。M9A pack 迁入后，旧 M9A 残缺更新能力不再参与运行，项目资源升级统一走 `maafw.project.v1`。MaaEnd 是否消费 project update / runner 需要 MaaEnd + MXU 样例单独验收，不作为 P1 默认承诺。

### 7.2 对照表

| 维度 | 旧实现 | 新实现 | 兼容要求 |
| --- | --- | --- | --- |
| MaaFW 更新检查 | `app/task/MaaFW/project_updater.py` | `maafw.project.v1.check_update` | 更新源、版本、latest 判定一致 |
| MaaFW 更新应用 | `project_updater.py` 全量/增量包应用 | `maafw.project.v1.apply_update` | 路径安全、临时目录、失败不破坏项目目录 |
| 更新源 | `Update.Source` / `Channel` / `MirrorChyanCDK` | project service 入参或插件配置 | 字段语义不漂移 |
| M9A 旧更新 | `M9AConfig.Run.IfAutoUpdateAfterQueue` 等旧字段 | pack-m9a 调用 `maafw.project.v1` | 旧字段只读迁移，不作为运行期更新路径 |
| MaaEnd 可能消费 | MaaEnd / MXU 现有更新和运行方式 | 待验收后选择 project / runner 服务 | 不把 MXU 业务语义写进 project 包 |

### 7.3 测试方法

1. 准备同一 MaaFW 项目目录，分别用旧 `project_updater.py` 和新 `maafw.project.v1` 做 dry-run/update 对照。
2. 对比 `UpdateCandidate` / `UpdateResult`：版本、来源、日志、updated、message、raw。
3. 构造失败场景，确认项目目录未被破坏，临时目录被清理或可恢复。
4. 对 M9A pack，确认旧更新字段迁移后只作为输入，运行期调用的是 `maafw.project.v1`。
5. 对 MaaEnd，只记录样例验收结论：是否需要 project update、是否需要 runner、是否仍只消费 interface。

### 7.4 落地时机

P2：`maafw.project.v1` 抽出并完成 MaaFW 更新对照。
P5：M9A pack 接入通用 project update。
MaaEnd：后续由 MaaEnd + MXU 样例验证，不绑定 P1/P2。

## 8. 对照对象 7：旧配置迁移

### 8.1 验收要求

只创建新配置，不覆盖旧配置；插件缺失时旧配置仍可只读查看。

### 8.2 对照表

| 维度 | 旧实现 | 新实现 | 兼容要求 |
| --- | --- | --- | --- |
| MaaFWConfig | app/models/config.py MaaFWConfig（6 分组） | PluginScriptConfig（插件级） | 旧配置只读兼容 |
| MaaFWUserConfig | app/models/config.py MaaFWUserConfig（5 分组） | PluginUserConfig（插件级） | 旧配置只读兼容 |
| M9AConfig | app/models/config.py M9AConfig（3 分组） | PluginScriptConfig（pack-m9a） | 旧配置只读兼容 |
| M9AUserConfig | app/models/config.py M9AUserConfig（4 分组） | PluginUserConfig（pack-m9a） | 旧配置只读兼容 |
| TaskSnapshot | JSON 字符串存 in Task.TaskSnapshot | 同 | 格式兼容 |
| WeeklyOnceTasks | MaaFWConfig_Run | pack schema 新脚本初始值 | 迁移只创建，不覆盖 |
| MonthlyOnceTasks | MaaFWConfig_Run | pack schema 新脚本初始值 | 迁移只创建，不覆盖 |
| PeriodTaskRecords | MaaFWUserConfig_Data | 用户级 Data | 迁移只创建，不覆盖 |
| M9A LastPsychubeDate | M9AUserConfig_Data | 用户级周期记录兼容字段 | 迁移只创建，不覆盖 |
| M9A Resource（服务器） | M9AUserConfig_Info.Resource | PluginUserConfig resource | 迁移只创建，不覆盖；必须匹配通用 resource |
| M9A 默认 preset / 队列 | M9A 默认模板和用户 Task.Queue | PluginUserConfig TaskSnapshot | 迁移只创建，不覆盖 |
| M9A 旧更新字段 | M9AConfig_Run.IfAutoUpdateAfterQueue 等 | pack/project update 配置 | 迁移只创建，不覆盖；运行期不再使用旧字段 |

### 8.3 迁移规则

1. 迁移工具只创建新配置，不覆盖旧值。
2. 旧值保留只读，迁移后仍可查看。
3. 插件缺失时旧配置仍可只读查看（M9A 通过 LEGACY_SCRIPT_TYPE_METADATA 中的 legacy fallback provider；MaaFW 已从该表中移除，旧运行链路已删除）。
4. M9A 保留在 LEGACY_SCRIPT_TYPE_METADATA 中；MaaFW 已从中移除——旧运行链路已删除，仅保留插件侧 `legacy_config_class_name` 做配置迁移。

### 8.4 测试方法

1. 准备有旧 MaaFWConfig/M9AConfig 的用户数据。
2. 执行迁移工具。
3. 验证：
   - 旧配置仍存在且只读
   - 新配置已创建且值正确
   - 禁用插件后旧配置仍可只读查看
   - 启用插件后新配置走插件路径

### 8.5 落地时机

P5：M9A pack 迁移入口。
P6：旧 M9A 配置只读兼容入口（MaaFW 旧运行链路已删除，MaaFWConfig/MaaFWUserConfig 仅保留用于插件侧配置迁移）。

## 9. 验收流程

### 9.1 阶段门

| 阶段 | 验收门 | 通过条件 |
| --- | --- | --- |
| P1 完成时 | interface 解析结果 + TaskSnapshot + option 选择结果对照 | 全部对照通过 + 人工确认 |
| P2 完成时 | project update 对照 | MaaFW 旧更新等价 + M9A 替换映射明确 |
| P3 完成时 | runner payload 对照 | 全部对照通过 + 人工确认 |
| P4/P5 完成时 | 前端任务构建对照 | 全部对照通过 + 人工确认 |
| P5/P6 完成时 | 旧配置迁移对照 | 全部对照通过 + 人工确认 |

### 9.2 人工确认要求

每个验收门通过后，需人工确认以下事项：
1. 对照报告完整且可复现。
2. 已知差异均为"只增不删"。
3. 没有破坏性变更未记录。
4. M9A 旧路径仍可正常运行（MaaFW 旧运行链路已删除，无旧路径需要保持）；P1 facade 默认不启用，且不新增旧配置项。
5. 新路径可独立运行（不依赖旧路径）。

### 9.3 切换条件

只有以下条件全部满足，才允许把旧 M9A 路径切到新服务（MaaFW 已无旧运行路径，不适用切换条件）：
1. 当前阶段验收门全部通过。
2. 人工确认完成。
3. M9A 旧路径仍保留作为 fallback（MaaFW 已无旧运行路径）。
4. 切换可通过新增的独立机制控制（默认不切换），**不通过修改 `M9AConfig` 旧配置项实现**。
5. 切换后有回退机制。

## 10. 已知风险与处理

| 风险 | 处理 |
| --- | --- |
| PI V2 继续漂移 | DTO 输出 interface_version + capabilities，新字段 extra="allow" 透传 |
| 过早切换旧路径 | P0/P1 默认不切运行路径；old/new 对照通过并人工确认后再切 |
| option 结构破坏兼容 | 新增 scopes/scope(在 OptionReference 和 OptionSelection 上)/value/args/raw 只增不删；`OptionDefinition` 不绑定单一 scope；旧 task option 输出继续可生成 |
| 迁移误覆盖 | 迁移工具只创建，不覆盖；旧值保留只读 |
| interface_preview 耦合 | 解耦 run_plan/task_config 的私有函数依赖，迁入 interface 包内 |
| M9A task_loader 独立 import 合并 | P5 评估是否统一到 interface 包，还是保持 M9A 独立实现 |
| MaaEnd 消费范围不明 | P1 只承诺 interface；project update / runner 消费必须另做 MaaEnd + MXU 样例验收 |

## 11. 待人工确认事项

1. **本地样例来源**：验收门测试需要至少 2 个本地样例（M9A + MaaEnd）。当前硬性限制不允许访问外部目录，需人工提供样例。

2. **M9A task_loader 是否统一**：M9A 有独立的 import 合并逻辑（task_loader.py），与 MaaFW interface_loader 存在逻辑重叠但数据结构不同。需确认：P5 是否统一到 interface 包，还是保持 M9A 独立实现。本文档建议保持独立，因为 M9A 有回退到 resource/tasks/*.json 的双路径加载。

3. **M9A legacy fallback**：M9A 保留在 LEGACY_SCRIPT_TYPE_METADATA 中作为 legacy fallback provider。MaaFW 已从中移除——旧运行链路（app/task/MaaFW/）已删除，不需要 legacy fallback；插件侧 `legacy_config_class_name="MaaFWConfig"` 仅用于旧配置迁移，不提供运行期 fallback。

4. **MaaEnd 是否消费 project update / runner**：MaaEnd P1 只确认 `maafw.interface.v1`。是否还要消费 `maafw.project.v1` 更新能力和 `maafw.runner.v1` 运行能力，需要 MaaEnd + MXU 样例验证后再决定。

4. **facade 启用方式**：P1 只允许只读 facade / compat proxy 和 old/new 对照测试，**不新增旧配置项（不引入 `MaaFWConfig.UsePluginInterface` 之类的字段）**，不切换默认运行路径。facade 默认不启用，启用方式（环境变量？feature flag？测试入口？）留待 P1 实现前由人工确认，且启用方式不应导致旧 `MaaFWConfig` / `M9AConfig` 结构变更。

5. **验收门执行环境**：对照测试需要能运行旧 MaaFW/M9A 代码和新 interface 包代码的环境。需确认：是否在当前仓库环境执行，还是需要独立的测试环境。
