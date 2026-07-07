# MaaFW 插件化 P0/P1 可开工任务清单

> 状态：可开工任务清单
> 日期：2026-07-06
> 依据：docs/maafw插件化最终实现方案.md、docs/maafw-plugin-code-audit.md、docs/maafw-plugin-p0-contract.md
> 约束：P0/P1 只允许做契约、审计、只读 facade、低风险新增文件和兼容验证，不允许默认切换现有 MaaFW/M9A 运行路径

本文档列出 P0（契约盘点）和 P1（抽出 interface 包）阶段可开工的具体任务。每个任务标注范围、产出、验收标准和前置依赖。所有任务遵守开工护栏：不删除/移动/重命名旧文件、不切换运行路径、不新增计划表、不手改 OpenAPI 生成文件。

## 1. P0 任务清单（契约盘点）

P0 目标：冻结最小 v1 服务面，不移动代码。

### P0-1 代码审计文档（已完成）

- **范围**：app/task/MaaFW/**、app/task/M9A/**、app/plugins/**、前端相关页面、schema/config/API、打包文件
- **产出**：docs/maafw-plugin-code-audit.md
- **验收**：每个文件有"当前职责 -> 目标包 -> 迁移风险 -> P0/P1 可动"映射
- **状态**：已完成

### P0-2 v1 服务契约草案（已完成）

- **范围**：maafw.interface.v1、maafw.project.v1、maafw.agent.v1、maafw.runner.v1、controller provider、project pack
- **产出**：docs/maafw-plugin-p0-contract.md
- **验收**：能列出每个 DTO 的字段、可选性、默认值和兼容策略；MaaEnd 只依赖 interface 的边界清楚
- **状态**：已完成（草案，待人工审核）

### P0-3 兼容验收门文档（本次交付）

- **范围**：interface 解析结果、TaskSnapshot、option selection、runner payload、旧配置迁移的 old/new 对照
- **产出**：docs/maafw-plugin-compatibility-gate.md
- **验收**：对照表覆盖方案文档第 2.2 节的全部对照对象
- **状态**：本次交付

### P0-4 本地样例解析记录

- **范围**：M9A、MaaEnd、Maa_bbb 等本地样例的 interface.json 解析记录
- **产出**：解析结果对照表（记录每个样例的 task/option/preset/controller/resource 数量、import 片段数、scan_select 数量）
- **验收**：至少一个 M9A 样例和一个 MaaEnd 样例的解析记录
- **前置依赖**：需要访问外部样例目录
- **状态**：**待人工确认事项**——当前硬性限制不允许访问外部目录，需人工提供样例或在 P1 解除限制后执行

### P0-5 emulator 服务能力确认

- **范围**：确认 emulator 服务提供的 adbPath、address、instance、capability
- **产出**：emulator 服务能力清单
- **验收**：能列出 emulator 服务暴露给 controller-adb provider 的全部能力
- **状态**：**待人工确认事项**——需要审计 app/services/emulator 相关代码（本次审计未覆盖 emulator 服务层）

### P0-6 worker JSON 行协议冻结结论

- **范围**：runner_worker.py 的 JSON 行协议是否在 P0 冻结
- **产出**：冻结结论
- **验收**：明确结论写入契约文档
- **状态**：已在 docs/maafw-plugin-p0-contract.md 第 5.5 节给出结论——P0 冻结协议骨架（type: log/result/error），允许 P1/P2 增加事件类型

## 2. P1 任务清单（抽出 interface 包）

P1 目标：先交付 MaaEnd 也能消费的通用解析器。

### P1-1 创建 automas-maafw-interface 包脚手架

- **范围**：新建 `plugins/automas_maafw_interface/` 包目录结构
- **产出**：
  - `plugins/automas_maafw_interface/pyproject.toml`（零 maa 依赖，仅 pydantic + json5）
  - `plugins/automas_maafw_interface/automas_maafw_interface/__init__.py`
  - `plugins/automas_maafw_interface/automas_maafw_interface/models.py`（从 interface_models.py 迁移 DTO）
  - `plugins/automas_maafw_interface/automas_maafw_interface/loader.py`（从 interface_loader.py 迁移）
  - `plugins/automas_maafw_interface/automas_maafw_interface/preview.py`（从 interface_preview.py 迁移）
  - `plugins/automas_maafw_interface/automas_maafw_interface/task_config.py`（从 task_config.py 迁移）
  - `plugins/automas_maafw_interface/automas_maafw_interface/service.py`（v1 服务入口）
- **验收**：
  - `pip install automas-maafw-interface` 不拉 maa wheel
  - 能解析 M9A interface.json
  - 能解析 MaaEnd interface.json，imports 后能得到任务列表
  - scan_select、preset、resource/controller 限制能被检测
- **风险**：低。新增文件，不触碰旧 app/task/MaaFW/** 文件
- **前置依赖**：P0-2 契约审核通过

### P1-2 实现 maafw.interface.v1 服务接口

- **范围**：实现 load / preview / validate / build_default_snapshot / normalize_snapshot / normalize_execution_payload / rescan_option
- **产出**：service.py 中的服务实现
- **验收**：
  - import 合并是硬冲突策略（重名 raise）
  - import 合并完成后再校验（不因片段缺 task 提前失败）
  - import 片段只允许 task / option / preset / import 四键（agent / setting / global_option 不在 v1 允许范围）
  - option 作用域不在 `OptionDefinition` 上绑定单一 scope；权威 scope 在 `OptionReference` 和 `OptionSelection` 上输出（v1 已知 scope：task / global / controller / resource；setting / pretask / hotkey 为 v2 待确认，v1 不输出）
  - `OptionDefinition.scopes: list[str] | None` 仅供聚合展示
  - normalize_execution_payload 输出结构化 OptionSelection
  - 缓存签名涵盖所有依赖文件 + scan 目录
- **风险**：低。纯新增，不影响旧路径

### P1-3 实现可选 HTTP route

- **范围**：POST /maafw/interface/preview、POST /maafw/interface/rescan-option
- **产出**：route handler（在插件包内或主程序兼容代理）
- **验收**：
  - 使用 *In/*Out schema
  - response_model 显式声明
  - route handler 只做 transport mapping
- **风险**：低。新增 route，不改现有 /api/scripts/maafw/interface/preview

### P1-4 新增只读 facade 或兼容代理

- **范围**：提供旧路径旁路可用的只读调用入口，供人工确认后做 old/new 对照；P1 不把旧运行代码接到新 service
- **产出**：app/task/MaaFW/ 下的 facade 调用入口（新增文件，不改旧文件）
- **验收**：
  - facade 调用新 service 的 load/preview/normalize_snapshot
  - 默认运行路径仍保持旧实现（facade 默认不启用）
  - **不新增旧配置项**（不引入 `MaaFWConfig.UsePluginInterface` 之类的字段），启用方式由人工确认（环境变量 / feature flag / 测试入口），且不应导致 `MaaFWConfig` / `M9AConfig` 结构变更
  - old/new 输出对照文档完成
- **风险**：中。需确保 facade 默认不启用，不切换运行路径，不修改旧配置结构
- **前置依赖**：P1-1、P1-2 完成，old/new 对照通过

### P1-5 old/new interface 输出对照

- **范围**：对比旧 interface_loader.load_interface_model_cached 和新 maafw.interface.v1.load 的输出
- **产出**：对照报告
- **验收**：
  - import 合并后的 task、option、preset、controller、resource 列表不丢字段
  - scan_select 展开结果一致
  - 缓存命中率不低于旧实现
- **风险**：低。只读对照，不改运行路径

### P1-6 interface_preview 耦合点解耦

- **范围**：解耦 interface_preview.py 对 run_plan._load_i18n_mapping / _resolve_i18n_value 和 task_config._build_task_option_maps / build_interface_preset_snapshot 的反向依赖
- **产出**：把私有函数提升为 interface 包内的公共接口
- **验收**：
  - preview.py 不再 import run_plan 或 task_config 的私有函数
  - i18n 解析和 option map 构建在 interface 包内独立实现
- **风险**：中。需确保解耦后输出一致

### P1-7 单元测试覆盖

- **范围**：parser、import 合并、scan_select、缓存、option 归一化、snapshot 归一化
- **产出**：测试文件
- **验收**：
  - import 循环检测测试
  - import 冲突检测测试
  - scan_select 展开测试
  - option 按 type 分派归一化测试
  - snapshot 去重补全测试
  - execution_payload 结构化输出测试
- **风险**：低。纯新增测试

## 3. 前端共享组件方案（P4 前细化，P0/P1 只设计不实现）

### 3.1 设计目标

MaaFW 和 M9A 共用任务构建组件，M9A 不复制一套任务构建器。前端采用"schema 表单 + 专用复杂组件"混合方案。

### 3.2 组件分包

第一版共享组件层随 `automas-script-maafw` 分发：

```
automas_script_maafw/
  frontend/
    manifest.json
    assets/
    components/
      MaaFWTaskQueueEditor
      MaaFWTaskOptionEditor
      MaaFWDescriptionView
```

### 3.3 组件设计

| 组件 / composable | 归属 | 作用 | props | emits |
| --- | --- | --- | --- | --- |
| `MaaFWTaskBuilder` | `automas-script-maafw` | 通用任务构建面板 | `interface: InterfacePreview`、`resource: str`、`preset: str`、`snapshot: TaskSnapshot`、`scopedOptions: OptionDefinition[]` | `update:snapshot` |
| `MaaFWTaskQueueEditor` | `automas-script-maafw` | 队列增删、启用、排序、复制、从模板填充 | `taskOrder: string[]`、`taskChecked: Record<string, boolean>`、`tasks: TaskDefinition[]`、`presets: PresetDefinition[]` | `update:taskOrder`、`update:taskChecked` |
| `MaaFWTaskOptionEditor` | `automas-script-maafw` | 根据 interface option 元数据编辑任务 option | `optionNames: string[]`、`options: OptionDefinition[]`、`taskOptions: Record<string, OptionValue>`、`controllerName?`、`resourceName?` | `update:taskOptions` |
| `MaaFWDescriptionView` | `automas-script-maafw` | 渲染任务说明、option 说明和限制提示 | `content?: string`、`basePath?: string` | 无 |
| `useMaaFWTaskBuilder` | `automas-script-maafw` | 快照 normalize、preset 应用、scoped option 默认值合并、dirty 状态 | composable，接收 interface + snapshot | 返回 `{ normalizedSnapshot, applyPreset, isDirty }` |

### 3.4 M9A 工作台页设计

`pack-m9a` 不复制任务构建组件。它只把 M9A 的 pack metadata、模板、周期标识和文案传给通用组件层，再监听通用组件输出的 `TaskSnapshot` 保存到用户配置。

M9A 工作台页职责：
- 注入 M9A 模板（default_task_queue）
- 注入默认队列（dailyPreset / weeklyPreset / monthlyPreset）
- 注入周月标签（Psychube=周常、Limbo=月常、Lucidscape=月常）
- 注入游戏文案和通知摘要
- 监听 `update:snapshot` 保存到用户配置

M9A 工作台页不做什么：
- 不复制 MaaFWTaskBuilder
- 不复制 MaaFWTaskQueueEditor
- 不复制 MaaFWTaskOptionEditor
- 不在组件里写 M9A 任务名白名单
- 不判断周/月归属
- 不生成 M9A 通知文案

### 3.5 scoped option 面板组合

v1 已知 scope（`task` / `global` / `controller` / `resource`）作为 scoped option 交给组件，组件只提供可组合面板和事件，不在底层固定它们必须出现在某个页面位置。`setting` / `pretask` / `hotkey` 三个预留 scope 当前 PI V2 规范无显式来源，v1 不输出，留作 v2 待确认；前端组件层预留扩展点，但 P0/P1 不实现这三个 scope 的面板。

### 3.6 交互要求

- 页面继续使用 Ant Design Vue 和现有主题 token。
- 颜色、边框、背景、状态色需兼容亮色和暗色主题。
- 任务队列拖拽必须有明确 handle，不能吞掉开关、select、option 按钮点击。
- option 编辑继续用结构化表单，不把嵌套 option 压成一行 JSON。
- 任务说明和 option 文案来自 interface / pack，不在组件里写死游戏文案。

### 3.7 落地时机

- P0/P1：只设计，不实现。
- P4：共享前端组件层随 `automas-script-maafw` 落地。
- P5：M9A pack 复用共享组件。
- P6：内置页降级为只读兼容入口。

## 4. P2+ 任务预告（不在本次开工范围）

以下任务在 P1 通过后才开工，本次只记录：

### P2：抽出 project 包
- `automas-maafw-project`（project_updater + agent plan 从 run_plan.py 拆出）
- `maafw.project.v1` 更新服务
- `maafw.agent.v1` 环境准备和 command plan

### P3：抽出 runner 与 controller-adb
- `automas-maafw-runner`（run plan + pipeline_override + runner + runner_worker）
- `automas-maafw-controller-adb`
- worker 子进程模型保留
- runner session 事件流
- ADB device spec 来自 emulator 服务

### P4：编排插件与 desktop controller
- `automas-script-maafw`
- `automas-maafw-controller-win32`
- `ScriptType=MaaFW`
- 共享前端组件层
- 旧内置 MaaFW 进入兼容期

### P5：M9A pack
- `automas-script-maafw-pack-m9a`
- M9A 默认模板、周月规则、专项用户页、通知文案
- 旧 M9A 队列和用户配置迁移入口

### P6：前端通用化与稳定发布
- `builtin:maafw` / `builtin:m9a` 编辑器降级为只读兼容入口
- 任务队列、option、说明收敛到共享组件
- 插件组 1.0 候选
- maafw-stable 风味包候选

### P7：host-agnostic 验收
- `maafw-smoke` CLI
- runner worker JSON 行协议文档
- slim host 是否立项的复核结论

## 5. 开工护栏检查清单

每个 P0/P1 任务开工前必须确认：

- [ ] 不删除、移动或重命名旧 `app/task/MaaFW/**`、`app/task/M9A/**` 文件
- [ ] 不修改现有脚本调度入口的默认路径
- [ ] 不新增计划表相关模型、字段、页面或注册表（MaaFWPlanConfig / QueueMode / PlanId / PLAN_BOOK / planTypeRegistry / MaaFWPlanTable）
- [ ] 不手改 OpenAPI 生成文件（frontend/src/api/**）
- [ ] 不为了新 scoped option 改坏旧 task option 的输出结构
- [ ] 不默认切换旧 MaaFW / M9A 运行路径
- [ ] 新增文件是低风险的（文档、契约草案、只读 facade、测试草案、样例数据结构）
- [ ] 不访问外部目录
- [ ] 不执行 git 写操作
- [ ] 不联网、不提权、不装依赖

## 6. 待人工确认事项

1. **P0-4 本地样例解析**：需要访问外部样例目录（M9A、MaaEnd 项目目录），当前硬性限制不允许。需人工提供样例或在 P1 解除限制。

2. **P0-5 emulator 服务能力确认**：本次审计未覆盖 app/services/emulator 相关代码。需人工确认 emulator 服务暴露给 controller-adb provider 的能力清单。

3. **P1-1 包目录位置**：建议放在 `plugins/automas_maafw_interface/`，与现有 `plugins/auto_mas_core`、`plugins/okww_adapter` 同级。需人工确认是否符合工作区规划。

4. **P1-4 facade 启用方式**：facade 默认不启用，且**不新增旧配置项**（不引入 `MaaFWConfig.UsePluginInterface` 之类的字段，不切换默认运行路径）。需人工确认启用方式（环境变量？feature flag？测试入口？），且启用方式不应导致 `MaaFWConfig` / `M9AConfig` 结构变更。

5. **前端共享组件实现时机**：P0/P1 只设计不实现。需人工确认 P4 是否是合适的实现时机。

6. **option 作用域承载位置**：v1 契约已明确——`OptionDefinition` 不绑定单一 scope，权威 scope 放在 `OptionReference` 和 `OptionSelection` 上，`OptionDefinition.scopes` 仅供聚合展示。`setting` / `pretask` / `hotkey` 三个预留 scope 当前 PI V2 规范无显式来源，v1 不输出，留作 v2 待确认。见 docs/maafw-plugin-p0-contract.md 第 2.5 节和第 10 节。
