# MaaFW 插件化代码审计报告

> 状态：P0 代码事实盘点
> 日期：2026-07-06
> 范围：app/task/MaaFW/**、app/task/M9A/**、app/plugins/**、plugins/okww_adapter/**、app/models/**、app/api/scripts.py、前端 MaaFW/M9A/Plugin 相关页面、frontend/electron/services/pluginBootstrapService.ts、pyproject.toml、打包工作流
> 方法：只读审计，未修改任何运行代码

本文档为 MaaFW 插件化 P0 阶段的代码事实盘点，对照 `docs/maafw插件化最终实现方案.md` 第 8.2 节的迁移映射，逐文件记录当前职责、目标归属、迁移风险和 P0/P1 可动性。所有事实基于当前分支 `feat/maafw-p` 的代码状态，不包含任何修改建议的执行结果。

## 1. 审计总览

### 1.1 仓库状态

- 分支：`feat/maafw-p`，远端 `origin` 指向 `qiyinxi/AUTO-MAS-with-M9A`（fork），`upstream` 指向 `AUTO-MAS-Project/AUTO-MAS`
- 工作区：本次 P0 产出 5 份 untracked 新增文档（均为 `docs/maafw-plugin-*.md`）+ `docs/maafw插件化最终实现方案.md`；无任何已跟踪文件修改，未执行 git add/commit/push
- 审计基线：本文档事实基于审计时点的代码状态，未对运行代码做任何修改

### 1.2 版本号事实

| 来源 | 版本 | 说明 |
| --- | --- | --- |
| `res/version.json` | `v5.4.0-beta.1` | 发行版真相源，被 `build-app.yml` 读取 |
| `pyproject.toml` | `5.2.0` | 落后于 version.json |
| `plugins/auto_mas_core/pyproject.toml` | `5.2.0` | 与根 pyproject 一致 |
| `plugins/okww_adapter/pyproject.toml` | `0.0.1` | 独立版本 |

`check-version-json.yml` 强制每个 PR 改动 `res/version.json`，但不校验 `pyproject.toml` 同步。MaaFW 插件化交付物如需声明 `min_auto_mas_version`，应以 `res/version.json` 为准。

### 1.3 关键架构事实

1. **M9A 与 MaaFW 是完全独立的两条实现线**（审计事实）。M9A 当前通过启动 `M9A.exe` 进程 + 日志文件监控运行；MaaFW 通过 Python agent + pipeline + runner 子进程运行。M9A 目录下不存在 `runner.py` / `runner_worker.py`，不存在 runner 逻辑复制。**注意**：这是当前运行现状的审计事实，不能直接作为"M9A 最终作为 MaaFW project pack runtime"的设计结论。P1 不迁移 M9A runtime；M9A 后续是否迁入 MaaFW project pack / 共享 runner，必须另走兼容验收门（见 docs/maafw-plugin-compatibility-gate.md）。

2. **MaaFW 周期任务字段仅在 MaaFWConfig**。`WeeklyOnceTasks` / `MonthlyOnceTasks` 在 `MaaFWConfig_Run`（脚本级），`PeriodTaskRecords` 在 `MaaFWUserConfig_Data`（用户级记录）。M9A 用 `LastPsychubeDate` / `LastLimboMonth` / `LastLucidscapeMonth` 三个日期字段 + `IfPsychubeDailyOnce` / `IfSleepDreamMonthlyOnce` 两个开关实现周月去重，字段名和机制完全不同。

3. **前端有三套并存的编辑器实现**。MaaFW（自包含 1907 行）、M9A（拆分子组件，TaskQueueSection 826 行 + TaskOptionRenderer 350 行）、Plugin（基于 SchemaForm）。三者互不复用。SchemaForm 不支持「可拖拽排序的递归任务队列 + 递归选项编辑器」这种复杂交互。

4. **两套 API 并存**。旧版 `/api/scripts/*` 被 MaaFW/M9A/MAA/SRC/MaaEnd/Okww/HSR/General 使用；新版 `/api/scripts2/*` + `/api/script-types/*` 被 Plugin 系统使用。`useScriptApi.getScriptsWithUsers` 包含约 1000 行硬编码字段映射，覆盖 8 种用户类型。

5. **无 maafw/m9a flavor 打包**。构建只有 Lite/Full（是否含完整环境 `environment.zip`），MaaFW 与 M9A 随主程序发布；`maafw==5.8.1` 固定在根 `pyproject.toml` 依赖中。M9A 不依赖外部 Python 包。

6. **`auto_mas.script_types` entry point 组在本仓库内无声明**。该组仅由 `app/core/script_types.py` 消费，用于加载第三方脚本类型插件。本仓库的两个内建插件（auto_mas_core、okww_adapter）声明的是 `auto_mas.plugins` 组（插件本体注册），与 `auto_mas.script_types` 是不同分组。

7. **TaskExecuteBase 基类只抽象 3 个方法**：`main_task` / `final_task` / `on_crash`。`check` / `prepare` 是各 Manager 子类约定的钩子，由调度层显式调用，不是基类抽象方法。

## 2. app/task/MaaFW/** 文件审计

### 2.1 文件迁移映射总表

| 当前文件 | 行数 | 当前职责 | 目标归属 | maa 依赖 | app.core 依赖 | 迁移风险 | P0/P1 可动 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `interface_models.py` | 250 | ProjectInterface v2 完整 Pydantic 模型树 | `automas-maafw-interface` | 否 | 否 | 低：纯模型，零外部依赖 | P0 冻结 DTO |
| `interface_loader.py` | 861 | import 合并、scan_select、缓存、校验 | `automas-maafw-interface` | 否 | 否(仅 app.utils 日志) | 中：import 合并是硬冲突策略，缓存签名涵盖 scan 目录 | P0 冻结算法 |
| `interface_preview.py` | 246 | interface 预览 DTO，转 app.models.schema | `automas-maafw-interface` | 否(间接) | 否(依赖 app.models.schema) | 中：反向依赖 run_plan/task_config 私有函数 | P0 记录耦合点 |
| `task_config.py` | 580 | TaskSnapshot 归一化、option 归一化 | `automas-maafw-interface` | 否 | 否 | 中：option 归一化按 type 分派，是前后端共享契约 | P0 冻结归一化 |
| `project_updater.py` | 680 | MirrorChyan 项目更新、全量/增量包应用 | `automas-maafw-project` | 否 | 否(仅 app.utils) | 中：网络 IO + 路径安全 + 回滚逻辑 | P1 抽出 |
| `run_plan.py` | 778 | run plan 构建 + agent command plan | `automas-maafw-runner`(run plan) + `automas-maafw-project`(agent plan) | 否(弱) | 否 | 中：agent plan 与 run plan 混在一个文件，需拆分 | P1 拆分 |
| `pipeline_override.py` | 436 | pipeline override 深合并 | `automas-maafw-runner` | 否 | 否 | 低：纯字典深合并 | P1 迁移 |
| `runner.py` | 2255 | worker 侧 MaaFW 直控（上帝类） | `automas-maafw-runner` | 是(重度) | 否 | 高：2255 行，含 device/agent/venv/sink/tailer 全部职责 | P1+ 拆分 |
| `runner_worker.py` | 77 | 子进程入口 + JSON 行协议 | `automas-maafw-runner` | 否(间接) | 否 | 低：77 行，协议清晰 | P1 迁移 |
| `control_capabilities.py` | 126 | DLL 探测 + 模拟器能力 | runner + controller-adb | 是 | 否 | 中：runtime DLL 探测归 runner，模拟器能力归 controller-adb | P1 拆分 |
| `window_service.py` | 155 | 窗口扫描、句柄匹配 | `automas-maafw-controller-win32` | 是 | 否 | 低：155 行，职责单一 | P1 迁移 |
| `manager.py` | 271 | 脚本管理器（ScriptAdapterHooks 雏形） | `automas-script-maafw` | 否 | 是(Config/EmulatorManager) | 中：METHOD_BOOK 是扩展点，依赖 app.core | P1+ 改写 |
| `AutoProxy.py` | 1679 | 单用户会话驱动 | `automas-script-maafw` | 是 | 是(Config) | 高：1679 行，含 venv/agent/game/period 全部逻辑 | P1+ 改写 |
| `__init__.py` | 70 | 懒加载包导出 | 各包各自维护 | 否 | 否 | 低 | P1 重建 |

### 2.2 maa 依赖矩阵

maa 依赖集中在 4 个文件：`runner.py`（重度，全套 maa 子模块）、`control_capabilities.py`（`maa.__file__` + controller 枚举）、`window_service.py`（`maa.toolkit.Toolkit`）、`AutoProxy.py`（maa.controller 枚举 + maa.toolkit）。

其余 10 个文件无 maa 依赖，可独立测试和迁移。`__init__.py` 通过 `__getattr__` 懒加载，避免 `import app.task.MaaFW` 时立即拉起 maa 依赖。

### 2.3 app.core / app.task / app.api 依赖矩阵

仅 `manager.py` 和 `AutoProxy.py` 依赖 `app.core`（Config / EmulatorManager）。`AutoProxy.py` 还依赖 `app.task.general.tools`（前置/后置脚本执行）。`interface_preview.py` 依赖 `app.models.schema`（API 契约类）。其余文件可在不引入 AUTO-MAS 主框架的情况下迁移到独立包。

### 2.4 M9A / MaaEnd 专项命中

**全部 14 个文件均未出现 M9A、MaaEnd 等专项任务名或脚本适配器逻辑。** 该目录是通用 MaaFW ProjectInterface 适配层。模拟器分支仅涉及 `mumu` 和 `ldplayer`（在 `control_capabilities.py` 的 `_EMULATOR_EXTRA_RELATION` 与 `AutoProxy.py` 的 `_build_adb_control_profile` 中）。

### 2.5 PlanConfig / QueueMode / PlanId 命中

**全部 14 个文件均未命中 PlanConfig、QueueMode、PlanId。** 任务调度走 `TaskExecuteBase` 基类 + `ScriptItem.task_info.mode` + `METHOD_BOOK` 字典分派（仅 `"AutoProxy"` 一种模式）。周期任务（周/月去重）由 `AutoProxyTask` 自行用 `WeeklyOnceTasks` / `MonthlyOnceTasks` / `PeriodTaskRecords` 配置项实现，未走 PlanConfig 注册。

### 2.6 P0 契约冻结关键点

1. **interface_models.py**：`MaaFWInterface` 的字段集（含 `interface_version: Literal[2]`、`import_` alias="import"、所有子模型 `extra="allow"`）是全链路契约源头。`MaaFWTaskOptionsByTask = dict[str, dict[str, MaaFWTaskOptionValue]]` 与 `MaaFWTaskOptionValue = str | list[str] | dict[str, str]` 是 task_config/run_plan/pipeline_override 三方共享的 option 值类型。

2. **interface_loader.py**：import 合并是**硬冲突**策略（task.name / option key / preset.name 重名即 raise，不覆盖），scan_select 在加载期即填充 cases，缓存签名涵盖所有依赖文件 + scan 目录文件 mtime。`IMPORTABLE_KEYS = {"task", "option", "preset", "import"}` 限定片段只允许这四键。import 合并完成后再做 `_validate_task_context_constraints` → `_validate_option_references` → `_validate_presets` 校验链。

3. **task_config.py**：`MaaFWTaskPresetSnapshot`（taskOrder / taskChecked / taskOptions 三字段）是前后端共享的 TaskSnapshot 归一化形态，`CUSTOM_PRESET_NAME = "__auto_mas_custom_preset__"` 是保留键。option 归一化按 type 分派（select/scan_select/switch → string、checkbox → string_list、input → object），value_type 与 case_name_sets 的校验规则是 P0 契约。

4. **runner_worker.py** 的 JSON 行协议（type: log/result/error，stdout 每行一个 JSON）是 AutoProxy 与 runner 子进程的进程边界契约。

### 2.7 interface_models.py 完整 DTO 字段

以下是 `MaaFWInterface` 根模型及其关键子模型的字段清单（基于 `extra="allow"` 透传策略）：

```
MaaFWInterface (populate_by_name, serialize_by_alias)
  interface_version: Literal[2]
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
  welcome: MaaFWDocumentContent | None        # str | list[str]
  description: MaaFWDocumentContent | None
  controller: list[MaaFWController]
  resource: list[MaaFWResource]
  group: list[MaaFWGroup]
  agent: MaaFWAgent | list[MaaFWAgent] | None
  task: list[MaaFWTask]
  option: dict[str, MaaFWOption]
  global_option: list[str] | None
  import_: list[str] | None  (alias="import")
  preset: list[MaaFWPreset]
  + fill_display_defaults 校验器

MaaFWController
  name / label / description / icon / type
  display_short_side: int = 720
  display_long_side: int | None
  display_raw: bool = False
  permission_required: bool | None
  attach_resource_path: bool | None
  option: list[str] | None
  adb: MaaFWAdbController | None
  win32: MaaFWWin32Controller | None
  macos / playcover / gamepad / wlroots

MaaFWResource
  name / label / description / icon
  path: list[str]
  controller: list[str] | None
  option: list[str] | None
  hash: str | None

MaaFWAgent
  child_exec: str | None
  child_args: list[str] | None
  identifier: str | None
  embedded: bool | None

MaaFWTask
  name / label / entry / default_check / description / doc / desc / icon / group
  resource: list[str] | None
  controller: list[str] | None
  pipeline_override: MaaFWPipelineOverride | None
  option: list[str] | None

MaaFWOption
  type: str = "select"
  label / description / icon
  controller: list[str] | None
  resource: list[str] | None
  cases: list[MaaFWOptionCase] | None
  inputs: list[MaaFWInputCase] | None
  scan_dir: str | None
  scan_filter: str | None
  pipeline_override: MaaFWPipelineOverride | None
  default_case: str | None

MaaFWOptionCase
  name / label / description / icon
  option: list[str] | None
  pipeline_override: MaaFWPipelineOverride | None

MaaFWInputCase
  name / label / description / icon / default
  pipeline_type: str | None
  verify: str | None
  verify_error: str | None
  pattern_msg: str | None
  + fill_verify_error_alias 校验器

MaaFWPreset
  name / label / description / icon
  task: list[MaaFWPresetTask]

MaaFWPresetTask
  name: str
  enabled: bool = True
  option: dict[str, MaaFWPresetOptionValue] | None
```

### 2.8 interface_loader.py import 合并算法

```
load_interface_model(base_dir)
  1. _resolve_interface_path       # 找 interface.json / interface.jsonc
  2. _normalize_import_list        # import 必须是非空字符串数组
  3. _normalize_project_relative_path  # 禁绝对路径、禁 ".."、强制项目相对
  4. _resolve_import_path + _is_within_base_dir  # 越界保护
  5. _seed_root_sections           # 先登记根文件的 task/option/preset 名
  6. _merge_imports_into_target    # 递归 DFS
       对每个 fragment:
         a. _validate_importable_fragment  # 只允许 task/option/preset/import 四键
         b. 先递归子 import               # 深度优先
         c. _merge_fragment_sections       # copy.deepcopy 后 task extend / option update / preset extend
       循环检测: stack: list[Path]
       冲突策略: _register_tasks/_register_options/_register_presets 重名即 _raise_conflict
  7. _expand_scan_select_options   # type=="scan_select" 扫描 scan_dir 填 cases
  8. _validate_task_context_constraints  # task.controller/resource 引用存在性
  9. _validate_option_references         # global_option/resource/controller/task.option 引用存在性
 10. _validate_presets                   # preset.task 去重 + case 值校验
```

缓存算法：内存缓存 signature = 文件 mtime_ns + size 元组（根 interface + dependency_paths + scan_select_specs 全部纳入签名）；磁盘缓存落 `data/cache/maafw_interface_loader/{sha256(root)}.json`，30 天过期，24 小时清理一次。

### 2.9 task_config.py option 归一化规则

| option.type | 归一化值类型 | 默认值策略 | 校验规则 |
| --- | --- | --- | --- |
| select / scan_select / switch | string | `option.default_case`，否则首个 case | 校验 case 存在性 |
| checkbox | list[string] | `default_case` 列表与 case 名交集 | 过滤非法 case |
| input | dict[string, value] | 每个 input_case.default | 仅保留声明的 input 名 |

`MaaFWTaskPresetSnapshot` 三字段：
- `taskOrder: list[str]`：任务顺序，去重补全（按 interface.task 顺序）
- `taskChecked: dict[str, bool]`：任务勾选状态，按合法 task_id 归一
- `taskOptions: MaaFWTaskOptionsByTask`：按 controller/resource 过滤可见 option 后的 option 值

### 2.10 runner.py 关键设计事实

- `MaaFWControllerType = Literal["Adb", "Win32"]`，`MAAFW_DIRECT_CONTROLLER_TYPES = {"Adb", "Win32"}`，仅支持这两种控制器。
- `MaaFWDeviceConfig`：type / adbPath / address / hWnd / screencapMethods / inputMethods / screencapMethod / mouseMethod / keyboardMethod / config。
- embedded agent 现已**禁止**在主进程内运行（`_load_embedded_agents` 直接 raise），必须走隔离子进程。
- agent Python 环境三种 runtime_kind：`project_python`（仅健康检查）/ `isolated_venv`（项目专属 venv，按 interfaceHash + requirementsHash 重建）/ `external`（用户自备，跳过）。
- venv 兼容层：`_write_agent_compat_shims` 写 sitecustomize.py，把 `maa.resource.resource` 别名为 `AgentServer`（兼容旧版 MaaFW API）。
- `_ensure_maafw_client_library_mode`：强制 Library 以 client 模式加载（非 AgentServer），防止 `maa.agent` 误导入。

### 2.11 AutoProxy.py 关键设计事实

- runner 子进程隔离：`_run_maafw_worker` 创建专属 venv（`config/maafw_runner_venvs/maafw_runner_{sha256[:16]}`），安装 `RUNNER_VENV_PACKAGES = ("maafw==5.8.1", "pydantic==2.11.7", "json5==0.14.0")` + 项目 requirements.txt，写 job json 到 `runtime/maafw_runner_jobs/`，`asyncio.create_subprocess_exec` 启动 `runner_worker.py`，按 JSON 行协议读 stdout。
- 周月任务去重：`_filter_period_once_tasks` 按 `WeeklyOnceTasks` / `MonthlyOnceTasks` 配置 + `PeriodTaskRecords` 用户数据，把本周/本月已完成的 task 移入 skippedTasks；`_current_period_keys` 用 ISO week + `YYYY-MM`。
- ADB 控制配置：`_build_adb_control_profile` 按 emulator_type 走 mumu / ldplayer 分支。
- Win32 游戏启动：`_ensure_desktop_game_started` 优先检测已有窗口，否则按 Game.Path + Arguments 启动。
- 同路径互斥：`_RUNNING_PROJECT_PATHS: set[str]` + `asyncio.Lock`，同一 project_path 不允许并发运行。

## 3. app/task/M9A/** 文件审计

### 3.1 文件迁移映射总表

| 当前文件 | 行数 | 当前职责 | 目标归属 | 迁移风险 | P0/P1 可动 |
| --- | --- | --- | --- | --- | --- |
| `__init__.py` | 25 | 导出 M9AManager | `automas-script-maafw-pack-m9a` | 低 | P1+ |
| `AutoProxy.py` | 1277 | M9A 自动代理核心（M9A.exe 进程驱动） | `automas-script-maafw-pack-m9a` | 高：含周月规则、通知文案、虚拟用户更新 | P1+ |
| `manager.py` | 463 | M9A 调度器 | `automas-script-maafw-pack-m9a` | 中：METHOD_BOOK + 生命周期 | P1+ |
| `task_loader.py` | 587 | M9A 任务加载器（双路径：interface.json / resource/tasks/*.json） | `automas-script-maafw-pack-m9a` | 中：含独立 import 合并和缓存 | P1+ |
| `tools/notify.py` | 462 | M9A 日志分析和通知文案 | `automas-script-maafw-pack-m9a` | 中：M9ALogAnalyzer + 多通道推送 | P1+ |

### 3.2 M9A 与 MaaFW 架构差异

> **口径说明**：本表是当前运行现状的审计事实，描述 M9A 现在怎么跑、MaaFW 现在怎么跑。它不是 M9A 最终 project pack runtime 的设计结论。P1 不迁移 M9A runtime；M9A 后续是否迁入 MaaFW project pack / 共享 runner，必须另走兼容验收门。

| 维度 | M9A（MFAA 线，现状） | MaaFW（MXU 线，现状） |
| --- | --- | --- |
| 配置方式 | 写 JSON 配置文件（`config/instances/default.json`） | Python agent + pipeline |
| 启动方式 | `ProcessManager.open_process` 启动 `M9A.exe` | `runner.py` + `runner_worker.py` |
| 监控方式 | `LogMonitor.start_monitor_file` 监控日志文件 | 内部 runner 机制 |
| 完成判定 | `wait_event.wait()` 等待日志事件 | runner 返回结果 |
| interface.json | 有（task_loader 双路径加载） | 有（interface_loader 加载） |
| 周月任务 | LastPsychubeDate / LastLimboMonth / LastLucidscapeMonth + 开关 | WeeklyOnceTasks / MonthlyOnceTasks / PeriodTaskRecords |
| 通知文案 | M9ALogAnalyzer 解析日志生成专项文案 | 通用 runner 结果 |

### 3.3 M9A 周月任务规则实现

- `_filter_queue_for_run(queue)`：按 entry（`PSYCHUBE_ENTRY="Psychube"` / `LIMBO_ENTRY="Limbo"` / `LUCIDSCAPE_ENTRY="Lucidscape"`）识别周月任务，读取用户配置的 `LastPsychubeDate`（周）/ `LastLimboMonth`（月）/ `LastLucidscapeMonth`（月），若本周/本月已执行则过滤掉。
- `_update_completed_task_state(completed_entries)`：任务完成后回写这些日期字段。

### 3.4 M9A 默认任务队列和模板

- 模板路径：`m9a_root_path/config/instances/default.json`。
- `build_config()` 读取模板，自动添加"启动游戏"（队列首）、"关闭游戏"（队列尾）、"切换账号"（官服且填账号时插入）。
- `RESERVED_TASK_NAMES = {"启动游戏", "关闭游戏", "切换账号"}`。

### 3.5 M9A task_loader.py 独立 import 合并

M9A 的 `task_loader.py` 有自己独立的 import 合并和缓存逻辑（`_load_interface_tasks` 优先读 interface.json/jsonc，支持 import 递归、scan_select；`_load_all_tasks` 回退读 `resource/tasks/*.json`）。磁盘缓存落 `data/cache/m9a_task_loader/{sha256}.json`。这与 MaaFW 的 `interface_loader.py` 是两套独立实现，存在逻辑重叠但数据结构不同。

## 4. app/plugins/** 插件机制审计

### 4.1 ScriptAdapterHooks 完整接口（9 个方法）

| 类别 | 方法 | 签名 | 默认行为 |
| --- | --- | --- | --- |
| 生命周期（async） | `check` | `(runtime: ScriptAdapterRuntime) -> str` | 返回 "Pass" |
| 生命周期（async） | `prepare` | `(runtime) -> None` | 无操作 |
| 生命周期（async） | `finalize` | `(runtime) -> None` | 无操作 |
| 生命周期（async） | `on_crash` | `(runtime, error: Exception) -> None` | 无操作 |
| 任务工厂（sync） | `run_auto_proxy` | `(runtime) -> TaskExecuteBase` | raise NotImplementedError |
| 任务工厂（sync） | `run_script_config` | `(runtime) -> TaskExecuteBase` | raise NotImplementedError |
| 任务工厂（sync） | `run_manual_review` | `(runtime) -> TaskExecuteBase` | raise NotImplementedError |
| Schema 装饰（async） | `decorate_script_schema` | `(schema, config_data, ctx) -> dict` | 返回原 schema |
| Schema 装饰（async） | `decorate_user_schema` | `(schema, config_data, ctx) -> dict` | 返回原 schema |

`ScriptAdapterRuntime` 提供：`definition` / `script_info` / `task_info` / `script_uid` / `type_key` / `mode` / `plugin_context` / `script_config` / `user_config` / `storage_script_config` / `emulator_manager` / `config_workspace` / `extra` / `check_result` / `begin_time`，以及 `get_service()` / `script_data_path()` / `default_config_file_path()` / `script_root_path()` / `create_config_workspace()` / `initialize_emulator_manager()` / `build_action_context()` / `read_script_data()` / `read_user_data_pairs()` / `build_script_model()` / `build_user_models()` 等方法。

参考实现：`app/task/general/adapter.py` 的 `GeneralAdapterHooks` 完整实现了全部 9 个方法，是新增 ScriptAdapter 插件的最佳模板。

### 4.2 PluginContext 12 个门面

| 门面 | 能力 |
| --- | --- |
| `config` | 配置读写（set/update/reset/to_dict/source_dict） |
| `event` | 事件订阅/发布（on/off/emit_async/emit） |
| `service` | 服务注册/消费（provide/set/get/inject/miss） |
| `server` | HTTP/WebSocket 服务 |
| `runtime` | 运行时操作（info/set/run） |
| `cache` | 缓存管理 |
| `log` | 日志门面 |
| `page` | 页面门面 |
| `logger` | 日志器 |
| `runtime_api` | RuntimeAPI |
| `plugin_name` | 插件名 |
| `instance_id` | 实例 ID |

### 4.3 ServiceRegistry 关键 API

| 方法 | 作用 |
| --- | --- |
| `provide(name, owner)` | 声明服务槽位（重复抛 ValueError） |
| `set(name, value, owner)` | 写入服务值 + before/after 通知 |
| `get(name, default)` | 多提供者时返回 `sorted(providers)[0]` |
| `take(name, owner, default)` | 优先按指定 owner 读取 |
| `bind(owner, needs, wants)` | 绑定依赖声明 |
| `inject(owner, needs, wants, ready)` | 注册动态注入回调 |
| `miss(owner)` | 返回缺失的硬依赖 |
| `ready(name)` / `declared(name)` / `owners(name)` / `users(name)` | 状态查询 |
| `drop(owner)` | 移除实例及其服务值 |

### 4.4 插件注册脚本类型的三条路径

1. **内建注册**：`script_type_registry.bootstrap()` → `_register_builtin_providers()` 硬编码注册 SRC / MaaEnd / M9A / MaaFW / HSR / General 六个类型。M9A 和 MaaFW 的 `manager_factory` 用 `_lazy_manager` 延迟导入。
2. **Entry Point 注册**：从 `auto_mas.script_types` / `automas.script_types` entry point 组加载第三方 provider。
3. **ScriptAdapterPlugin 运行时注册**：插件继承 `ScriptAdapterPlugin`，实现 `build_script_adapters()` 返回 `Sequence[ScriptAdapterDefinition]`，在 `on_start()` 时注册。

### 4.5 两套并存的插件脚本机制

| 机制 | 基类 | 编排器 | 适用场景 |
| --- | --- | --- | --- |
| ScriptAdapter | `ScriptAdapterPlugin` | `BaseAdapterManager` | 专项适配（有独立 Manager/AutoProxy） |
| PluginScript | `PluginLifecycle` + 装饰器 | `PluginScriptManager` | 通用脚本（用装饰器注入钩子） |

两者最终都注册到 `script_type_registry`，由 `ScriptTypeProvider` 统一管理。

### 4.6 事件系统

- `EVENT_CONTRACT_VERSION = "1"`，`EVENT_DISPATCH_MODEL = "async"`。
- 9 个标准事件：`task.start` / `task.progress` / `task.log` / `task.exit` / `script.start` / `script.success` / `script.error` / `script.cancelled` / `script.exit`。
- 纯异步并发分发：按 priority 降序分组，同优先级内 `asyncio.gather` 并发执行，每组执行完再进入下一组。支持 `once` 自动解绑和 `error_policy`（continue/raise）。
- global 作用域只分发给 global 监听器；instance 作用域按 `owner_instance_id == source_instance_id` 路由。

## 5. 前端审计

### 5.1 MaaFW 前端文件

| 文件 | 行数 | 职责 | 是否复用 SchemaForm |
| --- | --- | --- | --- |
| `MaaFWUserEdit.vue` | 1907 | MaaFW 用户编辑核心页（自包含任务构建器） | 否 |
| `MaaFWTaskOptionEditor.vue` | 540 | 递归选项编辑器（switch/select/scan_select/checkbox/input） | 否 |
| `MaaFWDescriptionView.vue` | 198 | Markdown 说明渲染（markdown-it + 自实现 sanitizeHtml） | 否 |
| `MaaFWScriptEdit.vue` | 1884 | MaaFW 脚本配置页（interface preview / agent env / project update / Win32 窗口扫描） | 否 |

### 5.2 M9A 前端文件

| 文件 | 行数 | 职责 | 是否复用 SchemaForm |
| --- | --- | --- | --- |
| `M9AUserEdit.vue` | 333 | M9A 用户编辑页（拆分子组件） | 否 |
| `M9AScriptEdit.vue` | 992 | M9A 脚本配置页（不读 interface） | 否 |
| `M9AUserEdit/TaskQueueSection.vue` | 826 | M9A 任务队列构建器（独立实现） | 否 |
| `M9AUserEdit/TaskOptionRenderer.vue` | 350 | M9A 递归选项渲染器（数据结构与 MaaFW 不同） | 否 |
| `M9AUserEdit/BasicInfoSection.vue` | 240 | 基本信息（硬编码服务器选项） | 否 |
| `M9AUserEdit/M9AUserEditHeader.vue` | 80 | 面包屑导航 | 否 |
| `M9AUserEdit/NotifyConfigSection.vue` | 166 | 通知配置 | 否 |

### 5.3 Plugin 前端文件

| 文件 | 行数 | 职责 |
| --- | --- | --- |
| `PluginScriptEdit.vue` | 345 | 插件脚本编辑页（基于 SchemaForm） |
| `PluginUserEdit.vue` | 425 | 插件用户编辑页（基于 SchemaForm，isOkwwAdapter 时额外渲染 OkwwConfigEditor） |
| `Plugin.vue` | 3319 | 插件管理主页面（实例列表 + 编辑面板 + WebSocket） |
| `PluginPageHost.vue` | 63 | 插件页面 iframe 宿主 |
| `PluginElementHost.vue` | 98 | 插件自定义元素宿主 |
| `PluginMarket.vue` | 637 | 插件市场（独立 WebSocket） |

### 5.4 SchemaForm 接口

- **Props**：`modelValue: Record<string, any>`、`schema: SchemaDefinition`、`readonly?: boolean`、`hideFields?: string[]`、`actionLoadingId?: string`、`layout?: 'single' | 'plugin-grid'`。
- **Emits**：`update:modelValue`、`trigger-action: { field, fieldSchema }`、`validation-change: SchemaValidationErrorMap`。
- **defineExpose**：`validate`。
- 支持字段类型：button/action、autocomplete、ordered-multiselect、multiselect、select、boolean、path、string、slider、number、list、key_value、table、json。

### 5.5 前端 API 两套并存

- **旧版**（`/api/scripts/*`）：`useScriptApi` + `useUserApi` + OpenAPI 生成的 `Service`，被 MaaFW/M9A/MAA/SRC/MaaEnd/Okww/HSR/General 使用。
- **新版**（`/api/scripts2/*` + `/api/script-types/*`）：`useScriptRegistryApi`，被 Plugin 系统使用。
- `useMaaFWApi.prepareAgentEnv` 未使用生成的 `MaaFwService.prepareMaafwAgentEnvApiScriptsMaafwAgentEnvPreparePost`，而是直接用 `apiRequest` 调同一端点（不一致点）。

### 5.6 pluginBootstrapService.ts

- 通过 `uv pip install --target` 把插件包装到 `plugins/pypi/site-packages`。
- 系统包 `auto-mas-core>=5.2.0` 优先用本地 `repo/plugins/auto_mas_core`（开发模式）。
- 入口点组 `auto_mas.plugins` / `automas.plugins`。
- 状态文件 `.plugin_bootstrap_state.json` 记录 hash，避免重复安装。
- 支持 `[tool.auto-mas.plugin-bootstrap]` 下 `packages` 数组声明额外引导包。

## 6. schema / config / API 审计

### 6.1 MaaFWConfig 字段（6 分组）

| 分组 | 字段 |
| --- | --- |
| `Info` | Name, ProjectLabel, Path, Controller, Resource |
| `Emulator` | Id, Index |
| `Device` | AdbPath, AdbAddress, AdbScreencapMethods(默认-57), AdbInputMethods(默认-1), HWnd, Win32ScreencapMethod, Win32MouseMethod, Win32KeyboardMethod, GamepadType, PlayCoverAddress, PlayCoverUuid |
| `Game` | Path, Arguments(ArgumentValidator), WaitTime(默认60), CloseOnFinish(默认True) |
| `Update` | IfAutoUpdate(默认True), Source(Literal["MirrorChyan"]), Channel(Literal["","stable","beta"]), MirrorChyanCDK(EncryptValidator) |
| `Run` | ProxyTimesLimit, RunTimesLimit(默认1), RunTimeLimit(默认30), **WeeklyOnceTasks**(JSONValidator(list)), **MonthlyOnceTasks**(JSONValidator(list)) |

### 6.2 MaaFWUserConfig 字段（5 分组）

| 分组 | 字段 |
| --- | --- |
| `Info` | Name, Status, RemainedDay, IfScriptBeforeTask/ScriptBeforeTask, IfScriptAfterTask/ScriptAfterTask, Notes, Tag(VirtualConfigValidator), Account, **Password(EncryptValidator)**, Controller, Resource |
| `Task` | SelectedPreset, TaskSnapshot(JSONValidator(dict)) |
| `Device` | AdbAddress, HWnd, PlayCoverAddress, PlayCoverUuid |
| `Data` | LastProxyDate, ProxyTimes, IfPassCheck, LastProxyStatus(默认"未知"), **PeriodTaskRecords**(JSONValidator(dict)) |
| `Notify` | Enabled, IfSendStatistic, IfSendMail, ToAddress, IfServerChan, ServerChanKey, CustomWebhooks |

### 6.3 M9AConfig 字段（3 分组）

| 分组 | 字段 |
| --- | --- |
| `Info` | Name(默认"新 M9A 脚本"), Path(FolderValidator) |
| `Emulator` | Id, Index |
| `Run` | ProxyTimesLimit, RunTimesLimit(默认3), RunTimeLimit(默认10), IfAutoUpdateAfterQueue, IfPsychubeDailyOnce, IfSleepDreamMonthlyOnce |

### 6.4 M9AUserConfig 字段（4 分组）

| 分组 | 字段 |
| --- | --- |
| `Info` | Name, Status, RemainedDay, IfScriptBeforeTask/ScriptBeforeTask, IfScriptAfterTask/ScriptAfterTask, Notes, Tag, Resource(默认"官服"), Account |
| `Task` | AvailableTasks(JSONValidator(list)), Queue(JSONValidator(list)) |
| `Data` | LastProxyDate, **LastPsychubeDate**, **LastLimboMonth**, **LastLucidscapeMonth**, ProxyTimes, IfPassCheck |
| `Notify` | 同 MaaFW |

### 6.5 MaaFW API endpoint

| 方法 | 路径 | response_model | 入参 schema |
| --- | --- | --- | --- |
| POST | `/api/scripts/maafw/interface/preview` | `MaaFWInterfacePreviewOut` | `MaaFWInterfacePreviewIn` |
| POST | `/api/scripts/maafw/project/update` | `MaaFWProjectUpdateOut` | `MaaFWProjectUpdateIn` |
| POST | `/api/scripts/maafw/agent-env/prepare` | `MaaFWAgentEnvPrepareOut` | `MaaFWAgentEnvPrepareIn` |
| GET | `/api/scripts/maafw/asset` | `FileResponse` | root, path (query) |
| POST | `/api/scripts/maafw/windows/preview` | `MaaFWWindowPreviewOut` | `MaaFWWindowPreviewIn` |

M9A 仅有一个 endpoint：`POST /api/scripts/m9a/tasks/available`，无 `response_model`、无 `*In`/`*Out` schema、用 query 参数 `script_id`（风格不一致）。

### 6.6 脚本类型注册

M9A 与 MaaFW 的内建 provider 定义（`app/core/script_types.py`）：

| type_key | display_name | script_config_class | user_config_class | supported_modes | manager_factory | editor_kind | is_builtin |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M9A | M9A脚本 | M9AConfig | M9AUserConfig | ("AutoProxy", "ScriptConfig") | `app.task.M9A.manager.M9AManager` | `builtin:m9a` | True |
| MaaFW | MaaFramework 项目 | MaaFWConfig | MaaFWUserConfig | ("AutoProxy", "ScriptConfig") | `app.task.MaaFW.manager.MaaFWManager` | `builtin:maafw` | True |

两者均不支持 `ManualReview` 模式。`LEGACY_SCRIPT_TYPE_METADATA` 只列了 MAA/SRC/MaaEnd/General 四类遗留映射，**M9A 与 MaaFW 不在遗留映射中**，意味着它们没有离线回退，provider 未加载时会被记入 `missing`。

## 7. 模块边界观察

### 7.1 纯模型层（可独立迁移）

`interface_models.py` / `task_config.py` / `pipeline_override.py`：零外部依赖（仅互相引用 + pydantic），可独立测试。`task_config.py` 和 `pipeline_override.py` 用 `try/except ImportError` 兼容包内/直接执行两种 import 模式，说明它们可能被 runner_worker 子进程独立加载。

### 7.2 加载层（可独立迁移）

`interface_loader.py`：仅依赖 `app.utils.get_logger`，无 maa / app.core。适合做缓存与签名。迁移时需把 `app.utils.get_logger` 替换为包内 logger。

### 7.3 预览层（有耦合点）

`interface_preview.py`：依赖 `app.models.schema`（API 契约）+ 反向依赖 `run_plan._load_i18n_mapping` / `_resolve_i18n_value` 和 `task_config._build_task_option_maps` / `build_interface_preset_snapshot`。私有函数被跨模块复用是边界上的耦合点，迁移时需把这些私有函数提升为公共接口或下沉到 interface 包内。

### 7.4 运行层（maa 重度依赖）

`runner.py` 是上帝类（2255 行），含 device / agent / venv / sink / tailer 全部职责。是后续拆分的重点候选。`runner_worker.py`（77 行）是清晰的进程边界。`control_capabilities.py` 需拆分：runtime DLL 探测归 runner，模拟器能力归 controller-adb。`window_service.py`（155 行）职责单一，可直接迁入 controller-win32。

### 7.5 编排层（与主框架集成）

`manager.py` 和 `AutoProxy.py` 是 MaaFW 与 AUTO-MAS 主框架的集成边界。`METHOD_BOOK` 是脚本适配器扩展点。`AutoProxy.py`（1679 行）含 venv / agent / game / period 全部逻辑，是改写为 ScriptAdapterHooks 的重点。

## 8. 审计发现的可关注点

以下为事实陈述，不含修改建议的执行：

1. **版本号不一致**：`res/version.json`（v5.4.0-beta.1）与 `pyproject.toml`（5.2.0）不同步。
2. **M9A endpoint 风格不一致**：`/api/scripts/m9a/tasks/available` 未设置 `response_model`、未定义 `*In`/`*Out` schema、用 query 参数而非 Body。
3. **TaskExecuteBase 接口与文档描述不符**：check/prepare 不是基类抽象方法，是子类约定钩子。
4. **MaaFW `_normalize_maafw_last_status` 含 GBK 乱码映射**（config.py:2200-2208）：`{"鏈煡": "未知", "鎴愬姛": "成功", "澶辫触": "失败", "杩愯涓?": "运行中"}`。
5. **M9AUserConfig 声明了 `related_config` 类属性，MaaFWUserConfig 未声明**（benign 差异）。
6. **`useMaaFWApi.prepareAgentEnv` 未使用生成的 Service 方法**，而是直接用 `apiRequest` 调同一端点。
7. **`PluginMarket.vue` 的 WebSocket 实现独立于 `useWebSocket`**，重连策略（1.5s 固定延迟）与全局 WS（指数退避）不同。
8. **`useScriptApi.getScriptsWithUsers` 是约 1000 行的硬编码字段映射函数**，覆盖 8 种用户类型。
9. **M9A `task_loader.py` 有独立 import 合并逻辑**，与 MaaFW `interface_loader.py` 存在逻辑重叠但数据结构不同。
10. **M9A `BasicInfoSection.vue` 中服务器选项为硬编码数组**（9 项）。

## 9. 审计结论

本次审计覆盖了 MaaFW 插件化涉及的全部后端、前端、schema、config、API、打包文件，建立了完整的"现有文件 -> 当前职责 -> 目标包 -> 迁移风险 -> P0/P1 是否可动"映射。关键结论：

1. **P0 可冻结的契约**全部在 `interface_models.py` / `interface_loader.py` / `task_config.py` 三个文件中，它们零 maa 依赖、零 app.core 依赖，是独立的纯模型/纯解析层。
2. **P1 可抽出的包**包括 interface 包（上述三文件 + preview）、project 包（project_updater + run_plan 的 agent plan 部分）、runner 包（run_plan 的 run plan 部分 + pipeline_override + runner + runner_worker）。
3. **M9A 与 MaaFW 完全独立**（审计事实），不存在 runner 逻辑复制。M9A 当前通过 `M9A.exe` 进程驱动运行，这是审计事实而非最终 project pack runtime 设计结论。P1 不迁移 M9A runtime；M9A 后续是否迁入 MaaFW project pack / 共享 runner，必须另走兼容验收门。
4. **前端三套编辑器互不复用**，共享组件层需要新建，不能简单复用现有 SchemaForm。
5. **无 maafw/m9a flavor 打包**，风味发行版需要从零设计。
