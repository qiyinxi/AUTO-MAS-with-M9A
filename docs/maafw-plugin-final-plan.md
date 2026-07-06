# MaaFW 插件化拆分与直控应用最终方案（终稿）

> 日期：2026-07-06
> 状态：终稿，待 Claude 审核
> 输入：背景 PDF《MaaFW 插件化与 M9A 专项适配背景文档》（2026-06-25，31 页）、方案 A（`D:\11111.md`）、方案 B（`docs/maafw-plugin-split-plan.md`）、AUTO-MAS `dev_v2` 代码核查
> 性质：只出方案，不落实现

---

## 0. 两份方案的仲裁结论

方案 A 与方案 B 的共识部分（interface 独立、maaend 只消费解析器、周月规则归 M9A、通知走 automas-notification、不把插件脚本类型写回主程序脚本配置大 union、不手改生成文件、旧配置只读兼容）全部保留，不再重复论证。以下是分歧点的最终裁决：

| # | 分歧点 | 方案 A | 方案 B | 最终决定 | 理由 |
|---|--------|--------|--------|----------|------|
| 1 | 基础包切法 | interface + runner + agent 三包 + core 薄壳 | interface + project（更新+agent 环境）+ runner 三包 | **采 B**：interface / project / runner 三个基础包 | agent 环境准备（venv、command plan）是项目资产管理问题，与更新同属 project；agent 子进程的启停连接与 Tasker 会话强耦合（A 自己的 `attach_agent()` 就是证据），归 runner 会话生命周期 |
| 2 | agent 是否独立成插件 | 独立 `maafw-agent` | 不独立 | **不独立** | 独立包没有受益方：maaend 不需要它，m9a 走完整链路；且 AgentClient 依赖 maa wheel，拆开也省不掉依赖，只会把一个会话的生命周期散到三个插件里 |
| 3 | 项目更新归属 | maafw-core | mfw-project | **project 包** | 更新是纯项目目录操作，无 maa 依赖，和 agent 环境准备同属"项目资产服务"，语义内聚 |
| 4 | 控制器形态 | 三个控制器插件族 | 收在 runner 内，ADB 委托 emulator 服务 | **采 A/PDF：插件族**（adb / desktop 先行，playcover 预留），**同时吸收 B**：controller-adb 声明 `wants=["emulator"]`，adb 路径/实例/能力一律消费 emulator 服务，不复刻 MuMuManager 逻辑 | 控制器拆族是背景 PDF 的**已决策项**（安装裁剪、互斥 UX、缺失降级）；B 的"ADB 责任归 emulator"与拆族不矛盾，是正交的正确约束 |
| 5 | M9A 形态 | project pack（type_key=MaaFW） | 独立插件注册 ScriptType=M9A | **目标形态 = project pack**（PDF 已决策）；**过渡期允许** ScriptAdapterPlugin 形态做 PoC（PDF 的"临时实现路线"），B 的形态定位为过渡而非终点 | project pack 是背景文档明确的目标 SDK 形态；M9A 的差异（默认值、周月规则、任务语义、专项用户页）都在 pack 能力范围内，不满足"必须拆新核心"的任何一条判据 |
| 6 | core 薄壳与元包 | core 薄壳 + 元包两个包 | 无 core，full 插件聚合 | **合并为一个包**：`automas-script-maafw` = 编排插件（注册 ScriptType=MaaFW + 持有 registry），用 pip extras（`[adb]`/`[desktop]`/`[full]`）承担一键安装，不再单发元包 | 下沉三个基础包后 core 只剩编排钩子，与"完整插件"就是同一个东西；元包用 extras 表达即可，少维护一个空壳包 |
| 7 | 服务命名 | `maafw.interface` | `mfw.interface.v1` | **`maafw.*.v1`**：统一 maafw 前缀 + 显式版本号 | maaend 是外部消费者，契约必须可版本化；前缀与背景 PDF、PyPI 包名族保持一致 |
| 8 | UI 包 | 独立 `maafw-ui` | 各插件自带 custom element | **第一版随 `automas-script-maafw` 内部分发**，按共享组件层组织（TaskQueueEditor / TaskOptionEditor / DescriptionView），第二个 project pack 出现复用需求时再拆独立包 | 即 A 的待确认项 5 与 PDF 待确认项 3 的保守解，避免提前拆包 |
| 9 | 直控应用路径 | 模式 A/B（纯 pipeline / +agent）+ 零代码接入 | host-agnostic core + 独立宿主 | **合并**：三进程模型固化为标准架构，runner worker 的 JSON 行协议就是宿主无关边界；每个包坚持"纯核心模块 + 薄插件适配层"分层；独立宿主排入 P7 | 代码核查发现现状已是 worker 子进程直控（见 §1），B 的 host-agnostic 主张实际上已经有天然落点，A 的两种模式在 worker 内部区分即可 |
| 10 | 周/月规则机制 | pack 声明 `period_rules` | 通用机制 + 专项声明 | **机制在 `automas-script-maafw`（不带任何默认规则），规则由 pack 声明** | 两案实质一致，取 B 的表述更严谨：通用层只有 period key 记录与跳过判定，"哪些任务是周/月任务"永远是专项知识 |

对方案 A 的两处事实修正：

1. A 称"runner.py 已 in-process 直控"。**实际是三进程模型**：MAS 主进程 → `AutoProxy.py:888` 拉起 `runner_worker.py` 子进程（maa binding 宿主，JSON 行协议回报事件）→ agent 再是第三个子进程。maa 不在 MAS 主进程内加载。这个模型必须保留（崩溃隔离 + DLL/GIL 隔离），插件化不得把 maa 拉回主进程。
2. A 的文件映射表遗漏了 6 个文件（`runner_worker.py`、`pipeline_override.py`、`task_config.py`、`interface_preview.py`、`window_service.py`、`control_capabilities.py`），完整映射见附录 A。

对方案 B 的两处修正：

1. B 把 `window_service.py` 归入 runner。控制器拆族后，窗口扫描/句柄匹配是 desktop provider 的能力，**归 controller-desktop**。
2. B 未拆控制器插件族，与背景 PDF 的已决策项冲突，本方案按 PDF 执行。

---

## 1. 关键代码事实（本方案的依据）

| 事实 | 来源 | 对方案的影响 |
|------|------|-------------|
| MaaFW 执行是三进程：主进程 / runner worker（`import maa`，JSON 行协议）/ agent 子进程 | `app/task/MaaFW/AutoProxy.py:888`、`runner_worker.py`、`runner.py:37-53` | runner 插件保留 worker 子进程模型；worker 协议成为直控应用的宿主无关边界 |
| 插件宿主三件套齐备：`ScriptAdapterPlugin` / `ScriptAdapterDefinition` / `ScriptAdapterHooks` / `ScriptAdapterRuntime` | `app/plugins/script_adapter.py:454-703` | 编排插件直接可写，无需改宿主 |
| General 已用 `ScriptAdapterHooks` 完成迁移，okww 已用 `ScriptAdapterPlugin` 发布 | `app/task/general/adapter.py:25`、`plugins/okww_adapter` | 两条迁移样板都在 |
| emulator 已是独立插件，`provides = "emulator"` | `plugins/pypi/site-packages/emulator/plugin.py:127` | controller-adb 直接 `wants=["emulator"]` |
| ServiceRegistry 同一服务名单一 owner；provides/needs/wants + 拓扑排序 + 两阶段重算 | `app/plugins/service_registry.py` | 控制器/pack 不抢同名服务，走 registry 注册 provider（与 automas-notification 模式一致） |
| `app/task/MaaFW/` 共 15 个模块（含两案都没映射全的 6 个） | 目录清单 | 附录 A 给出全量映射 |
| 当前 PI 解析器已覆盖 V2（import 合并/scan_select/preset/agent 等） | `interface_loader.py` + `interface_models.py` | interface 插件以搬迁为主，不重写 |

---

## 2. 最终插件拆分

共 **7 个包**（5 个第一批 + 1 个预留 + 1 个外部）。基础包 headless（不注册脚本类型、不注册页面），应用包才碰 ScriptType 与 UI。

```
┌────────────────────────── MAS 插件宿主 ──────────────────────────┐
│   ScriptAdapterPlugin / ServiceRegistry / PluginServer / Page    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                │  automas-script-maafw        │  编排插件
                │  ScriptType=MaaFW            │  maafw.registry.v1
                │  （内含共享 UI 组件层）       │  零代码项目接入
                └──┬──────────┬──────────┬────┘
      needs        │          │          │         registry 注册
   ┌───────────────┘          │          └───────────────┬──────────────┐
   ▼                          ▼                          ▼              ▼
┌─────────────┐  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ maafw-      │  │ maafw-project   │  │ controller-adb   │  │ controller-      │
│ interface   │  │ 更新 + agent 环境│  │ wants: emulator  │  │ desktop          │
│ 纯解析，零   │  │ maafw.project.v1│  │ maafw.controller │  │ Win32            │
│ maa 依赖    │  │ maafw.agent.v1  │  │ .adb             │  │ maafw.controller │
│ interface.v1│  └─────────────────┘  └──────────────────┘  │ .desktop         │
└─────────────┘           ▲                                  └──────────────────┘
   ▲    ▲                 │ needs
   │    │        ┌────────┴────────┐
   │    └────────│ maafw-runner    │  直控运行器（worker 子进程宿主）
   │             │ maafw.runner.v1 │  agent 子进程启停归会话
   │             └─────────────────┘
   │
   │ needs（仅此一项）
┌──┴────────────┐          ┌──────────────────────────────┐
│ maaend 专项    │          │ automas-script-maafw-pack-m9a │
│ （外部维护）    │          │ M9A 专项包：默认值/周月/文案    │
└───────────────┘          │ needs: script-maafw           │
                           │ 通知走 automas-notification    │
                           └──────────────────────────────┘
```

### 2.1 `automas-maafw-interface` —— PI V2 解析器（P1 交付，maaend 唯一消费物）

- **provides**: `maafw.interface.v1`；**依赖**: pydantic、json5。**零 maa 依赖，零 MAS 业务依赖**。
- **职责**：`interface.json`/`.jsonc` 读取；`import` 递归合并（循环/冲突检测）；`scan_select` 展开；i18n 键解析；task/option/preset/controller/resource 引用一致性校验；内存+磁盘缓存（签名失效重载）；任务快照归一化（`task_config.py` 的 Snapshot 模型第一阶段随本包）；预览 DTO（`interface_preview.py`）。
- **输出契约**：稳定 DTO（字段名承诺不变，`extra="allow"` 允许增量）；顶层携带 `interface_version` 与 `capabilities`，消费方按能力探测而非版本猜测。
- **服务接口**（v1 冻结面）：

```text
maafw.interface.v1.load(path, force_reload=False) -> InterfaceModel
maafw.interface.v1.preview(path) -> InterfacePreview
maafw.interface.v1.build_default_snapshot(interface, preset=None) -> TaskSnapshot
maafw.interface.v1.normalize_snapshot(interface, snapshot) -> TaskSnapshot
maafw.interface.v1.normalize_execution_payload(interface, tasks, options, controller, resource) -> ExecutionPayload
maafw.interface.v1.rescan_option(path, option_name) -> OptionCases
maafw.interface.v1.validate(interface) -> ValidationReport
```

- **HTTP 路由**（可选）：`/maafw/interface/preview`、`/maafw/interface/rescan-option`。
- **边界**：不启动 tasker、不读写用户配置、不依赖 emulator/Notify/TaskManager、不含任何专项任务名。

### 2.2 `automas-maafw-project` —— 项目资产服务（P2 交付）

- **provides**: `maafw.project.v1`（项目更新）+ `maafw.agent.v1`（agent 环境）；**needs**: `maafw.interface.v1`。**零 maa 依赖**。
- **`maafw.project.v1`**：GitHub / MirrorChyan 更新检查、全量/增量包下载与应用（路径越界防护、失败不破坏项目目录）。
- **`maafw.agent.v1`**：解析 `interface.agent`（child_exec/child_args/identifier/embedded）；分类四种运行形态（项目自带 Python / 项目可执行 / 隔离 venv / 外部命令）；创建维护项目专属 venv（本地 `deps/*.whl` 优先 + 镜像回退，只装项目 `requirements.txt`，绝不污染主 .venv）；生成 agent command plan；注入 `PI_*` 环境变量约定。
- **关键边界**：只"准备环境和命令计划"，**不持有 agent 子进程**——启停连接归 runner 会话。`embedded: true` 一律翻译为 isolated subprocess 策略，禁止在 MAS 主进程 import 项目 agent 代码。

```text
maafw.project.v1.check_update(project_path, interface, channel, cdk) -> UpdateCandidate
maafw.project.v1.apply_update(project_path, candidate) -> UpdateResult
maafw.agent.v1.classify(interface.agent) -> AgentMode
maafw.agent.v1.prepare_env(project_path, interface.agent) -> AgentEnvResult
maafw.agent.v1.build_command_plans(project_path, interface.agent) -> AgentPlan[]
```

### 2.3 `automas-maafw-runner` —— 直控运行器（P3 交付）

- **provides**: `maafw.runner.v1`；**needs**: `maafw.interface.v1`、`maafw.project.v1`；**依赖**: maa wheel。
- **架构铁律**：保留现有 **worker 子进程模型**。maa binding 只在 worker 进程加载；主进程侧是会话管理器（拉起 worker、按 JSON 行协议收发事件、超时/停止/清理）。一个 session = 一个 worker 进程。
- **职责**：run plan 构建（任务列表 + `pipeline_override.py` 深合并）；worker 内 Library/Controller/Resource/Tasker 创建；agent 子进程按 `AgentPlan` 启动 → `AgentClient` 连接 → 会话结束关闭（纯 pipeline 项目全程不触碰 agent）；事件流（log / task_start / task_done / task_failed / session_done / session_error）；错误截图与失败节点摘要；`control_capabilities.py` 中的 runtime DLL 探测归本包。
- **device 输入是中性结构**（不感知 provider）：`{type: Adb|Win32, adbPath, address, hWnd, screencapMethods, inputMethods, config}`。ADB 的来源永远是 controller-adb ↔ emulator 服务，runner 只接受解析结果。

```text
maafw.runner.v1.build_plan(project_path, interface, selection) -> RunPlan
maafw.runner.v1.create_session(run_plan, device, agent_plan|None, callbacks) -> SessionId
maafw.runner.v1.run(session_id) -> RunResult
maafw.runner.v1.stop(session_id) -> StopResult
maafw.runner.v1.dispose(session_id) -> None
```

### 2.4 控制器插件族（P3/P4 交付，Gamepad / playcover 预留）

控制器包**不注册脚本类型**，启动后向 `maafw.registry.v1` 注册 provider（与 automas-notification 的"主服务注册表 + 通道插件"同构）。

| 包 | controller_types | provides | 要点 |
|----|------------------|----------|------|
| `automas-maafw-controller-adb` | `["Adb"]` | `maafw.controller.adb` | `wants=["emulator"]`；adb 路径/地址/实例/EmulatorExtras 全部消费 emulator 服务；设备就绪检查；`control_capabilities.py` 的模拟器能力部分归此 |
| `automas-maafw-controller-desktop` | `["Win32"]` | `maafw.controller.desktop` | `window_service.py` 归此：窗口扫描、句柄匹配、窗口正则；截图/输入方式选择 |
| `automas-maafw-controller-gamepad`（预留） | `["Gamepad"]` | `maafw.controller.gamepad` | **不进第一批**；先等 Win32 桌面控制跑通，再确认手柄输入能力是否应独立成族 |
| `automas-maafw-controller-playcover`（预留） | `["PlayCover"]` | `maafw.controller.playcover` | 仅占位声明，不进第一批 |

**provider 最小接口**（注册进 registry）：

```python
class ControllerProvider:
    key: str                      # "adb" / "desktop" / "gamepad" / "playcover"
    display_name: str
    controller_types: list[str]
    async def decorate_schema(self, schema, config, ctx) -> dict   # 注入本族字段
    async def precheck(self, runtime) -> str                       # "Pass" 或失败原因
    def build_device_config(self, iface_controller, user_fields) -> DeviceSpec
    async def cleanup(self, runtime) -> None
```

**运行时规则**：一个脚本实例只激活一个控制器族；两族可同装但单个运行计划只选其一；UI 只渲染当前 provider 字段；未安装的族显示"能力缺失"而非渲染无效表单。

### 2.5 `automas-script-maafw` —— 编排插件（P4 交付）

- **provides**: `maafw.registry.v1`；**needs**: interface + project + runner 三个 v1 服务；extras：`[adb]` `[desktop]` `[full]`。
- **职责**：
  - 注册 `ScriptAdapterDefinition(type_key="MaaFW")`，实现 `ScriptAdapterHooks`：`check`（interface 校验 + provider precheck + agent 环境检查）→ `prepare`（更新检查 + agent env + 建 session）→ `run_auto_proxy`（runner.run）→ `finalize`（provider cleanup + session dispose）→ `on_crash`（截图 + 摘要）。
  - `decorate_script_schema` / `decorate_user_schema`：按当前 provider 注入字段。
  - 持有 `maafw.registry.v1`：controller provider 与 project pack 的注册/查询/分发（拓扑保证：controllers/packs `needs maafw.registry.v1`，天然后启动）。
  - **零代码项目接入**：本地路径 + Git 仓库两种来源（第一版不接 MaaHub/release 下载源）。
  - **通用周期机制**：period key 记录与跳过判定（用户级 `Data.PeriodTaskRecords`），**不带任何默认规则**。
  - **共享 UI 组件层随包分发**：`MaaFWTaskQueueEditor`、`MaaFWTaskOptionEditor`、`MaaFWDescriptionView`、controller/resource 兼容提示。脚本页/用户页优先复用 `PluginScriptEdit.vue` / `PluginUserEdit.vue` / `SchemaForm.vue` / `useSchemaActionRunner.ts`，专用组件只补队列拖拽、嵌套 option、agent 环境面板。
- **project pack SDK**（目标形态，第一版只声明元数据，不开放 run plan hook）：

```python
class MaaFWProjectPackDefinition(BaseModel):
    key: str; display_name: str
    project_repo: str | None; interface_path: str = "interface.json"
    supported_controllers: list[str]; default_controller: str
    default_resource: str | None; default_preset: str | None
    default_task_queue: list[str] | None
    period_rules: list[PeriodRule]        # PeriodRule(task_name, scope=daily|weekly|monthly, limit)
    reserved_task_semantics: dict         # 启动/关闭/切账号等保留任务名
    icon: str | None; notes: str | None

class MaaFWProjectPackPlugin:
    def build_project_packs(self) -> list[MaaFWProjectPackDefinition]: ...
```

### 2.6 `automas-script-maafw-pack-m9a` —— M9A 专项包（P5 交付）

- **needs**: `automas-script-maafw`（extras 拉 adb；desktop 为可选 extra，保留 PC 扩展点——PDF 已决策）。
- **只声明差异**：默认仓库/发布源、默认 controller=adb、默认 resource（官服/B 服/国际服）、默认 preset 与任务队列、周月规则（`IfPsychubeDailyOnce` → `PeriodRule("Psychube", daily, 1)`；`IfSleepDreamMonthlyOnce` → `PeriodRule("SleepDream", monthly, 1)`）、启动/关闭/切账号保留任务语义、M9A 文案与风险提示、专项用户工作台页（队列/预设/说明渲染，复用共享组件层）。
- **不做**：interface 解析、runner、更新器、通知通道（结构化结果 → M9A 文案翻译 → `automas-notification` 投递）。
- **M9A 项目资产不进 MAS 仓库**：`agent/main.py`、`bootstrap.py`、`agent_runtime.py`、`deps/*.whl`、`resource/**` 仍是 M9A 项目资产，由 project/runner 按路径消费。
- **过渡策略**：若 P5 启动时 pack SDK 尚未固化，允许先以 `ScriptAdapterPlugin` 形态发 PoC（复用三基础服务，绝不复制 runner），SDK 固化后迁回 pack 形态。此为唯一认可的 B 形态使用场景。

### 2.7 maaend 专项（外部维护，非本人负责）

- 只 `needs=["maafw.interface.v1"]`；不装 project/runner/controller/maa wheel。
- 本人交付边界：解析器本体 + MaaEnd `interface.json` 解析样例（`D:\maafwin\MaaEnd-win-x86_64-v1.16.0-beta.1`）+ 消费文档 + 集成清单。`__MXU_*` 任务语义、`config/mxu-MaaEnd.json` 读写、MaaEnd UI 一概不承诺。
- maaend 未来若要复用 runner，由其维护者自行决定从"只消费 parser"升级为"消费 full"。

---

## 3. mfw 与 m9a 同步推进路线

两者都是本人负责，按一条主线推进；每阶段主程序保持可运行（内置路径先改为内部调用新服务，最后才降级）。

| 阶段 | 目标 | 关键验收 |
|------|------|----------|
| **P0 契约盘点** | 冻结四组 v1 DTO（interface/project/agent/runner），不动代码 | 用 `D:\maafwin` 的 M9A、MaaEnd、Maa_bbb 发行目录做解析样例过一遍字段；确认 emulator 服务面（adbPath/address/instance/capability）满足 controller-adb 需要 |
| **P1 抽 interface** | `automas-maafw-interface` 上线 | M9A / MaaEnd 的 interface 均可解析（含 import 链、scan_select、preset）；主程序 MaaFW 内置路径改为经 service 调用（保留 fallback）；maaend 可开始集成 |
| **P2 抽 project** | 更新 + agent 环境独立 | 更新失败不破坏项目目录；venv 准备不污染主 .venv；M9A 的 `./python/python.exe -u ./agent/main.py` 与 Maa_bbb 的 embedded 均能产出明确 command plan |
| **P3 抽 runner + controller-adb** | 直控会话模型成立 | 纯 pipeline 项目 ADB 直控跑通 smoke task（无 agent）；随后 M9A agent 子进程启动、连接、随会话关闭；stop/dispose 能清理 worker、agent、日志 tailer |
| **P3.5 计划表注册化** | 为 MaaFW 计划表铺地基 | MAA 计划表行为不变；后端计划类型按注册表分发；前端计划页按 descriptor 渲染；不可用的 General/Custom 占位移除 |
| **P4 编排插件 + controller-desktop** | `ScriptType=MaaFW` 闭环 | 只装 script-maafw[adb] 即可零代码创建并运行通用 MaaFW 脚本；desktop 窗口扫描可用；`MaaFWPlanConfig` / `MaaFWPlanTable` 可用；未装族显示能力缺失；旧内置 MaaFW 进入兼容期 |
| **P5 m9a-pack + 迁移工具** | M9A 专项等价 | 队列顺序/周月跳过/资源默认值/通知结果与旧专项可对照；M9A 计划模板可用；旧 `MaaFWConfig`/`M9AConfig` 一键生成 `PluginScriptConfig` / MaaFW 计划表（只创建不覆盖）；映射表见背景 PDF"旧 M9A 字段迁移映射" |
| **P6 前端通用化 + 降级** | 去专用页 | `builtin:maafw` / `builtin:m9a` 编辑器降级为只读兼容入口；任务队列/option 编辑走共享组件层；插件卸载后旧配置只读保留 |
| **P7 直控应用** | 见 §4 | headless CLI smoke 跑通 = host-agnostic 验收 |

**全程红线**：脚本配置 API 的大 union 不新增 MaaFW/M9A 分支；计划表若新增 `MaaFWPlanConfig`，只走计划表注册与 OpenAPI 生成流程；不手改 `frontend/src/api/**` 生成文件；通知不重复造通道；每阶段旧数据可读。

---

## 4. 直控应用计划（非寄生态）

### 4.1 定位修正

现状已经是直控（worker 子进程 `import maa` 驱动 Tasker），不存在"从寄生转直控"的工程；真正要做的是**把直控能力从内置类型抽成插件，并让它可以脱离 MAS 宿主运行**。

| 维度 | 寄生态（MFAAvalonia / MFW.exe 宿主） | 直控态（本方案） |
|------|--------------------------------------|------------------|
| 宿主 | 外部 GUI 是宿主 | MAS（或未来独立宿主）是唯一宿主 |
| MaaFW | GUI 内置 runtime | runner worker 子进程直控 |
| Agent | GUI 启动 | runner 会话受管子进程 |
| 配置/通知/更新 | GUI 自带 | PluginScriptConfig / automas-notification / maafw.project.v1 |

### 4.2 两种运行形态（worker 内部区分，插件面不变）

- **形态一：纯直控**（pipeline-only 项目）：session 不含 agent_plan，worker 直接跑，无 venv 无子进程。
- **形态二：直控 + 受管 agent**（M9A、Maa_bbb 等有 custom 代码）：project 包备好 env 与 command plan → runner 会话内启动 agent 子进程、`AgentClient` 连接、结束回收。`embedded: true` 一律转 isolated subprocess。

### 4.3 宿主无关分层（每个包的硬性结构约束）

```
automas_maafw_xxx/
  core/        # 纯逻辑：不 import PluginContext、不 import app.*，只依赖 pydantic/maa/标准库
  plugin.py    # 薄适配层：注册 service/route/page，把 ctx 能力桥接给 core
```

- `maafw.interface/project/runner` 的 core 模块必须可被任意 Python 程序直接 import。
- runner worker 的 **JSON 行协议**是第二道宿主无关边界：任何宿主（MAS、CLI、未来独立 GUI）只要会拉子进程、读写 stdio，就能驱动完整 MaaFW 会话。
- **验收方式（P7）**：交付一个 `maafw-smoke` headless CLI——不启动 MAS，直接 import 三个 core 包：打开项目目录 → 解析 interface → 选 controller/resource/task → 绑 ADB 或 Win32 → 跑一条 task → 输出日志与结果。CLI 跑通即证明分层成立。

### 4.4 独立直控应用路线（P7 之后，按需启动）

1. **宿主候选**：先 CLI（P7 交付物），后按需做独立 GUI（可复用 MAS 前端组件层，Electron 壳或 Tauri 壳另议——不在本方案范围内定型）。
2. 独立宿主自带：配置存储、日志、通知适配（core 只产出结构化结果）。
3. **M9A 直控应用** = 同一套 core + m9a pack 的默认值/周月规则/文案，只替换宿主壳。
4. 从零创建直控应用的作者路径（与背景 PDF 三档接入一致）：先做标准 MaaFW 项目（interface.json + resource + 可选 agent）→ MAS 零代码接入跑 smoke → 需要分发再发 project pack → 只有非标准生命周期才写完整 ScriptAdapter。

---

## 5. MaaFW 应用基础与形态演进

### 5.1 结论

**不新造应用底座。**"MaaFW 应用"的基础就是 AUTO-MAS 本体（Electron 壳 + FastAPI 后端 + 插件宿主）+ maafw 插件组，以**风味发行版**的形式存在。`alpha-package/` 里已有的 `AUTO-MAS-maafw-stable-v5.4.0-beta.1-*` 手工包就是这个形态的雏形，本方案把它正式化（见 §6）。独立 slim 宿主只在风味包无法满足时才启动（P7 后按需），且优先裁剪现有 Electron 壳，不另起新栈。

### 5.2 应用基础栈（五层，自下而上）

| 层 | 内容 | 归属 |
|----|------|------|
| L1 项目资产 | interface.json / resource / agent / requirements | 项目作者（M9A、Maa_bbb…），不进任何安装包 |
| L2 core 库 | interface / project / runner 三包的 `core/` 模块，纯 Python import 面 | 宿主无关，任何程序可直接消费 |
| L3 worker 协议 | runner worker 的 JSON 行协议（stdio） | 进程级宿主无关边界 |
| L4 插件适配层 | 7 个包的 `plugin.py`（service/route/page 注册） | 绑定 MAS 插件宿主 |
| L5 宿主 | AUTO-MAS → maafw 风味发行版 → slim 宿主（远期可选） | 见 5.3 |

L2/L3 两道边界是 §4.3 分层约束的直接产物：换宿主只换 L5，L4 以下原样复用。

### 5.3 形态演进三阶段

| 形态 | 时点 | 内容 | 面向 |
|------|------|------|------|
| **形态 1：标准包 + 市场安装** | P4 起自然可用 | 用户装标准 AUTO-MAS，从插件市场装 `automas-script-maafw[...]` + pack | 已有 MAS 用户 |
| **形态 2：maafw 风味发行版**（主推） | P4 后 | Full 包 + 预 seed 插件组 + 预置 maa 运行时，开箱即用、离线可用 | M9A / MaaFW 用户群，不关心 MAS 生态的人 |
| **形态 3：独立直控应用（slim host）** | P7 后按需 | 见 5.4 | 品牌独立 / 体积敏感场景 |

### 5.4 形态 3 的技术决策（预定，触发前不投入）

- **GUI 壳**：裁剪现有 Electron 壳——共享组件层、pluginBootstrapService、镜像轮换、更新与签名基建全部现成；**不选** Tauri/新栈，除非出现明确的体积/内存硬指标。
- **后端**：两档任选其一——(a) 最小 FastAPI 宿主，只装 maafw 插件组（复用 L4）；(b) 无插件宿主，直接 import L2 core（更小，但放弃插件生态与市场）。默认 (a)。
- **CLI**：`maafw-smoke` console script 随 `automas-maafw-runner` 发布（P7 验收物），同时就是服务器挂机 / 无 GUI 场景的正式形态，不算"应用"的降级品。
- **启动形态 3 的判据**（满足任一才立项）：① 风味包体积被 MAS 主体拖累且用户明确抱怨；② maafw 发版节奏被 MAS 主程序发版强耦合阻塞；③ 需要独立品牌分发（独立官网/独立更新源）。

---

## 6. 打包与发布计划

### 6.1 现有打包体系盘点（事实）

| 环节 | 现状 | 来源 |
|------|------|------|
| 应用构建 | `build-app.yml`（workflow_dispatch）：yarn build → electron-builder win-unpacked → SignPath 签主程序 | `.github/workflows/build-app.yml` |
| 双包产物 | **Lite**（Inno Setup 精简安装包 + zip）；**Full**（从 `download.auto-mas.top` 拉 `environment.zip` 预置 Python 环境后再打，带 actions/cache） | 同上 |
| 版本源 | `res/version.json`（tag/prerelease/changelog）+ `frontend/package.json` | 同上 |
| 发布通道 | GitHub Release（自动建 `release/<ver>` 分支 + tag）→ CNB 同步 → MirrorChyan（独立 workflow） | `build-app.yml` / `sync-cnb.yml` / `mirrorchyan.yml` |
| 插件进包方式 | **不进安装器**。Electron 主进程 `pluginBootstrapService.ts` 首启把 `auto-mas-core>=5.2.0` 与 `[tool.auto-mas.plugin-bootstrap]` 声明包装进 `plugins/pypi/site-packages`（镜像轮换 + 哈希记账） | `frontend/electron/services/pluginBootstrapService.ts` |
| **关键限制** | CI 带 `if: github.repository == 'AUTO-MAS-Project/AUTO-MAS' && (main\|\|dev)`——**本 fork（AUTO-MAS-with-M9A / dev_v2）触发不了官方构建**，这就是 alpha 包手工打的原因 | `build-app.yml:37` |
| 手工雏形 | `alpha-package/AUTO-MAS-maafw-stable-<ver>-<commit>-<ts>`（其一带 `-fixed-` 手工修补重打） | 未跟踪目录，无脚本 |

### 6.2 轨 A：插件包发布（PyPI）

**发布节奏与里程碑绑定**：

| 里程碑 | 首发包 | 初始版本 |
|--------|--------|----------|
| P1 | `automas-maafw-interface` | 0.1.0 |
| P2 | `automas-maafw-project` | 0.1.0 |
| P3 | `automas-maafw-runner`、`automas-maafw-controller-adb` | 0.1.0 |
| P4 | `automas-script-maafw`、`automas-maafw-controller-desktop` | 0.1.0 |
| P5 | `automas-script-maafw-pack-m9a` | 0.1.0 |

**版本策略**：0.x 期间 DTO 允许调整（每次破坏性变更 minor +1 并在 changelog 标注）；`maafw.*.v1` 契约冻结时全族升 **1.0.0**，此后 v1 DTO 只增不改，破坏性变更必须开 `.v2` 服务名共存过渡。interface 包承诺最严（maaend 外部消费方），冻结前主动请 maaend 维护者过一遍字段。

**发布流程**：沿用官方文档 publish 页流程（`python -m build` + twine，TestPyPI 先行验证），问题版本走 yank 不删包。发布顺序按依赖方向：interface → project → runner/controller → script-maafw → pack。

**依赖矩阵要点**：interface/project 零 maa 依赖（轻包，秒装）；runner 锁 maa wheel 兼容区间（`maa>=x.y,<x.y+N`，P3 时定）；pack-m9a 通过 extras 拉链（`automas-script-maafw[adb]`）。

**进入自举/市场**：maafw 插件组对普通用户经插件市场安装；对风味包经 `[tool.auto-mas.plugin-bootstrap]` 声明 seed（复用现有机制，**不发明新机制**）。

### 6.3 轨 B：应用发行（maafw 风味包正式化）

**命名规范**（收敛现有手工命名）：

```
AUTO-MAS-maafw-<channel>-<version>-<commit>          # channel ∈ alpha | beta | stable
```

时间戳仅本地手工构建保留；废除 `-fixed-` 后缀——修补一律滚新 commit 重打。

**风味包内容** = Full 包 + 两层预置：

1. **预 seed 插件**：构建时把 seed 清单（`automas-script-maafw[full]` + `automas-script-maafw-pack-m9a` + `automas-notification` 及其通道 + 全部传递依赖）以离线 wheel 形式 `pip install --target` 进 `plugins/pypi/site-packages`，并写好 bootstrap 哈希记账 → 首启零下载、零 PyPI 依赖。
2. **预置 maa 运行时**：maa wheel 与 MaaFramework 原生 DLL 随包（进 environment 层或独立 `runtime/maafw/` 目录，P3 定型 worker 的 runtime 查找顺序后落位）。

M9A 项目资产（resource/agent/deps）**不进安装器**，仍走 `maafw.project.v1` 的项目更新机制首次拉取。

**构建方式三步走**：

| 阶段 | 方式 | 产物 |
|------|------|------|
| 短期（现在～P3） | 手工流程脚本化：`scripts/build_maafw_flavor`（方案名，实现另议）——输入官方 Full 包或本地构建产物，执行 seed + runtime 预置 + 重命名压缩 | `maafw-alpha`，无签名（明示） |
| 中期（P4～P6） | fork 加独立 workflow（workflow_dispatch，dev_v2 可触发；SignPath 用 test-signing 或无签） | `maafw-beta` |
| **终局（插件化完成）** | **fork 归并上游**：maafw 差异全部收敛为"插件 + seed 清单"后，fork 不再携带核心代码改动；maafw 风味变成官方 `build-app.yml` 的一个矩阵项（Full 步骤后追加 seed 步骤） | `maafw-stable`，官方签名 |

终局这一条是插件化在打包侧的直接红利：**风味包与官方包的差异从"一个 fork"缩小为"一份 seed 清单"**。

**发布通道**：GitHub Release + CNB 沿用；MirrorChyan 是否为 maafw 风味开独立 rid（vs 共用 `AUTO_MAS`）→ 待确认项 9。

### 6.4 轨 C：直控应用打包（P7+）

- `maafw-smoke` CLI：`[project.scripts]` console script 随 runner 包发布，pipx 可独立安装，无需任何 GUI/宿主。
- slim host（若按 5.4 判据立项）：electron-builder 配置复用，独立 `productName`/`appId`，Inno Setup 模板参数化（现有 `.iss` 生成逻辑已在 workflow 内联，抽成模板即可复用）。

### 6.5 打包时间线总表

| 里程碑 | PyPI 动作 | 应用包动作 |
|--------|-----------|-----------|
| P1 | interface 0.1 上 TestPyPI→PyPI | — |
| P2 | project 0.1 | — |
| P3 | runner + controller-adb 0.1；锁 maa 区间 | 风味脚本化（alpha 不再纯手工）；worker runtime 查找顺序定型 |
| P4 | script-maafw + controller-desktop 0.1 | fork 独立 workflow 上线（maafw-beta）；seed 清单进 bootstrap 声明 |
| P5 | pack-m9a 0.1 | 风味包内置 M9A 迁移工具入口 |
| P6 | 全族 1.0（契约冻结） | maafw-stable 候选 |
| P7 | runner 附带 maafw-smoke script | fork 归并上游评估；slim host 判据复核 |

### 6.6 打包专属风险

1. **maa wheel 体积与更新**：原生 wheel 较大，进 environment.zip 会拖累所有官方包——倾向放风味包独立预置层，P3 与 worker runtime 查找顺序一起定。
2. **离线完整性**：seed 的传递依赖必须锁全（wheel 锁文件），否则首启仍会触网，风味包"开箱即用"承诺失效。
3. **双通道漂移**：市场安装（在线）与风味 seed（离线）的版本可能不一致——seed 清单生成必须从同一份锁文件出，风味包发版时同步刷新。
4. **fork 存续期的签名空窗**：中期 beta 包若无正式签名，需在发布说明明示，避免用户混淆官方签名包。

### 6.7 插件包本体打包（含前端资产）

插件包不是只有 `plugin.py`。带 UI 的包必须把 Python 后端、前端构建产物、静态资源和版本契约一起发布进同一个 wheel，风味包再把这些 wheel 离线 seed 进去。

**wheel 内容约定**：

```text
automas_script_maafw/
  core/                         # 宿主无关 Python 逻辑
  plugin.py                     # MAS 适配层
  frontend/
    manifest.json               # 页面声明、入口、渲染模式、最小宿主版本
    assets/                     # Vite 构建后的 js/css/icon，文件名带 hash
```

- `pyproject.toml` 必须通过 package-data / include 机制把 `frontend/manifest.json` 和 `frontend/assets/**` 打进 wheel；不允许首启再跑 `npm install` 或拉 CDN。
- 前端构建在 Python 打包前完成：`yarn build` 产出插件前端资产，`python -m build` 只封装已经冻结的产物。CI / 本地脚本都按这个顺序。
- 插件页面由 `ctx.page.register` 声明，静态资源由插件 HTTP route 或宿主插件静态文件服务暴露；`PluginFrontendLoader` 按 `plugin_id + version + asset hash` 加载，避免旧缓存污染新版本。
- manifest 至少声明：`id`、`version`、`min_auto_mas_version`、`frontend_api_version`、`render`（优先 custom element，必要时 iframe）、`entry`、`style`、`icon`、`routes/actions`。
- 风味包 seed 时记录 wheel hash 与前端 asset hash；市场安装与离线 seed 都从同一份锁文件生成，防止同版本后端加载不同前端。
- 开发期可允许 manifest 指向本地 dev server 做 HMR，但发布 wheel 只允许相对静态资产入口。

**前端资产分包策略**：第一版 `automas-script-maafw` 内置共享组件层；`pack-m9a` 只带专项页面、模板和文案。第二个 project pack 真的复用这套组件后，再评估拆 `automas-script-maafw-ui`，不要提前维护空 UI 包。

---

## 7. 前端体验与计划表方案

### 7.1 前端结论：不降级用户体验

插件化不能把现有 MaaFW / M9A 前端体验退化成一张通用 schema 表。第一版前端按"共享复杂组件 + 少量 schema 表单"组织：

| 区域 | 处理方式 |
|------|----------|
| 项目路径、更新源、controller、resource 等标量配置 | 走 `PluginScriptEdit.vue` / `PluginUserEdit.vue` + `SchemaForm.vue`，复用 Ant Design Vue 表单体验 |
| 任务队列、拖拽排序、任务 option、任务说明 | 继续使用专用组件：`MaaFWTaskQueueEditor`、`MaaFWTaskOptionEditor`、`MaaFWDescriptionView` |
| M9A 专项工作台 | `pack-m9a` 提供专项页，复用共享队列/option/说明组件，只覆盖默认模板、周月规则提示、游戏文案和通知摘要 |
| controller 缺失 / provider 未安装 | 显示能力缺失与安装动作，不渲染无效表单 |

UI 语言沿用 AUTO-MAS 当前桌面业务界面：Ant Design Vue、现有主题 token、现有页面间距与交互节奏。复杂队列页若 custom element 的热更、拖拽或主题注入体验不达标，P4/P5 允许先走"宿主内置组件桥接"过渡；这只是装载方式过渡，不是把页面重写成低配表单。

### 7.2 计划表结论：计划表与 PeriodRule 分工

`PeriodRule` 只解决"本周期成功一次后跳过"；它不是计划表。MaaFW / M9A 需要类似现有 MAA 的计划表能力，允许用户配置不同日期执行不同任务：

| 能力 | 归属 | 示例 |
|------|------|------|
| 今天跑哪些任务、顺序、每个任务 option | 计划表 | 周一跑日常 + 银行，周二跑日常 + 洞悉材料 |
| 某任务本周 / 本月成功一次后本周期跳过 | `period_rules` + `Data.PeriodTaskRecords` | `Psychube` 每周一次，`SleepDream` 每月一次 |
| 专项默认模板 | project pack | M9A 提供"日常模板 / 周常模板 / 月常模板" |

组合规则：运行前先按计划表取出"今天的 TaskSnapshot"，再交给 `period_rules` 做周期跳过，最后送 runner。若用户希望"周任务失败后明天继续补"，就在多个 weekday 的队列里都放该任务，`period_rules` 会在成功后自动跳过；第一版不做 cron 和复杂补跑 DSL。

### 7.3 当前计划表前置改造

当前仓库计划表仍是 MAA 单类型实现：后端 `PlanIndexItem` 只允许 `MaaPlanConfig`，前端 `plan/index.vue` 只渲染 `MaaPlanTable`，"通用/自定义计划"只是注释预留。MaaFW 计划表不能直接塞进 MAA 表，需要先做一次无行为变化的注册化改造：

1. 后端建立计划类型注册表（等价于 `PLAN_BOOK`）：记录 create type、config class、schema class、consumer、用户引用字段和默认名。
2. `add/get/update/delete/reorder` 仍共用现有 `/api/plan` 编排，但按注册表分发；未知类型明确失败，不回退成 `MaaPlanConfig`。
3. 删除计划时只清理匹配 consumer 的用户引用，锁定用户阻止删除；不能像当前实现一样只遍历 `MAA`。
4. 前端建立计划类型 descriptor registry：label、默认名、create type、table component、selector tag 都从 registry 来；`PlanHeader` 不再保留不可用的 General/Custom 占位。
5. schema 改动后只能通过 OpenAPI 生成器更新前端 API；不手改 `frontend/src/api/**`。

这个前置改造本身不改变 MAA 现有体验，是 P4 前必须完成的地基。

### 7.4 `MaaFWPlanConfig` 数据模型

第一版只新增一个 MaaFW 专用计划表类型，不新增 `M9APlanConfig`。M9A 是 MaaFW project pack，先通过 `ProjectPackKey="m9a"` 使用同一张 MaaFW 计划表；如果未来某个 pack 的计划字段明显超出 MaaFW TaskSnapshot，再单独加自己的计划类型。

```text
MaaFWPlanConfig
  Info:
    Name: str
    Mode: "ALL" | "Weekly"
    ProjectPackKey: str | None      # None = 通用 MaaFW，"m9a" = M9A pack
    InterfaceSignature: str | None  # interface 任务/option 变更检测
  ALL / Monday / Tuesday / ... / Sunday:
    Preset: str | None
    Resource: str | None
    TaskSnapshot: list[MaaFWTaskSnapshotItem]

MaaFWTaskSnapshotItem
  task_id: str                      # 稳定主键，优先 interface task name / entry
  enabled: bool
  repeat_count: int | None
  options: dict[str, Any]
```

原则：

- 计划表存"今天要跑的队列快照"，不存 runner session、不存设备实例、不存通知配置。
- `TaskSnapshot` 进入运行前必须再次经 `maafw.interface.v1.normalize_snapshot()` 校验，避免项目更新后旧任务名静默失效。
- `InterfaceSignature` 只用于提示和重新校验，不阻止用户手动修复。
- `ProjectPackKey` 用于筛选模板、文案和可选任务目录；不是泛型字段引擎。

### 7.5 用户侧消费路径

MaaFW / M9A 用户配置增加计划引用，而不是把计划表复制进用户配置：

```text
Task.QueueMode = "Fixed" | "Plan"
Task.PlanId = "<uuid>" | ""
```

- `Fixed`：沿用用户页当前任务队列。
- `Plan`：用户页队列区变只读，显示"来自计划表"、今日队列摘要、跳转到计划管理；保存时只保存 `PlanId`。
- combobox 只返回 consumer 匹配的计划：通用 MaaFW 用户看 `ProjectPackKey=None` 或兼容 pack；M9A 用户看 `ProjectPackKey="m9a"` 的计划。
- `check()` 阶段若计划缺失、计划类型不匹配、interface 校验失败，返回用户可操作消息："请在计划管理中选择有效的 MaaFW 计划表"。

### 7.6 计划表 UI

`MaaFWPlanTable.vue` 不复刻 MAA 关卡表格，而是复用任务队列组件，提供两层视图：

| 视图 | 用途 |
|------|------|
| 配置视图 | `ALL` 或 7 个 weekday tab/列；每一天是一套可拖拽 TaskSnapshot，支持从 pack 模板填充、复制到其他日期、清空 |
| 简化视图 | 用任务名/tag 汇总一周安排，便于扫一眼确认哪天跑哪些任务 |

交互要求：

- 拖拽必须有明确 handle，任务内的开关、select、option 按钮不被拖拽热区吞掉。
- option 编辑仍用 `MaaFWTaskOptionEditor`，不要把嵌套 option 压成一行 JSON。
- 空计划显示可执行动作：从当前用户队列生成、从 pack 模板生成、手动添加任务。
- 周月一次任务在任务行旁显示周期标识，但不由计划表强制完成；是否跳过由运行时 `period_rules` 决定。

### 7.7 计划表里程碑

| 阶段 | 动作 |
|------|------|
| P3.5 | 计划表注册化改造，MAA 行为不变；移除前端不可用的 General/Custom 占位 |
| P4 | `MaaFWPlanConfig` + `MaaFWPlanTable` 随通用 MaaFW 插件可用，支持 `ALL` / `Weekly` |
| P5 | `pack-m9a` 提供 M9A 计划模板、周月规则标识、旧 M9A 队列到计划表的只创建迁移 |
| P6 | 用户页计划模式只读来源、今日队列摘要、跳转计划管理全部收敛到共享组件 |

---

## 8. 配置归属（冻结）

| 配置 | 归属 |
|------|------|
| 项目路径/项目名/版本/更新源/ProjectPack 标识 | 脚本级 `PluginData.Config.Info` / `Update` |
| 当前控制器族 | 脚本级 `Info.Controller` |
| ADB 地址/模拟器实例/窗口句柄等族字段 | controller provider `decorate_schema` 注入 |
| 用户 resource / 账号 | 用户级 `Info.*` |
| 任务队列/启用/option | 用户级 `Task.TaskSnapshot`（稳定 task_id 为主键，不用展示名） |
| 计划表引用 | 用户级 `Task.QueueMode` / `Task.PlanId` |
| 不同日期的任务队列 | `MaaFWPlanConfig.ALL/Monday/.../Sunday.TaskSnapshot` |
| 周期跳过记录/运行计数 | 用户级 `Data.PeriodTaskRecords` |
| 周月规则声明 | project pack `period_rules` |
| 通知开关 | 用户级 `Notify.*`，通道归 automas-notification |
| 调试绘制/错误截图/日志级别 | `Run.Debug` / `Run.Draw` / `Run.Log` |

原则：脚本级描述"项目怎么被 MAS 管理"，用户级描述"这个账号怎么跑"。

---

## 9. 风险清单

1. **PI V2 版本漂移**：解析器输出 `interface_version` + `capabilities`，消费方按能力探测；上游 v2.6+ 新字段靠 `extra="allow"` 透传。
2. **maa wheel 版本锁定**：runner 锁兼容版本区间；worker 进程隔离使主程序不受项目侧 maa 版本影响，但 worker 自身版本策略要在 P3 明确（跟随 MAS 依赖 or 项目 deps 优先）。
3. **agent 环境复杂度**：四种运行形态都要有可观测日志（venv 创建、pip 回退、PI_* 注入、连接重试）。
4. **服务时序**：registry 模式依赖拓扑排序（controllers/packs needs registry）；provider 注册发生在 on_start，编排插件需容忍 provider 迟到（两阶段重算已支持）。
5. **前端 custom element 体验**：P4 前先用 okww/General 的既有表面验证复杂页面（队列拖拽）在插件前端下的开发与热更体验，不达标则先走宿主内置组件过渡。
6. **计划表静态 API 与插件动态能力冲突**：若上游拒绝核心计划表注册化，MaaFW 计划只能先落在插件自有页面，体验会弱于 MAA 计划管理；本方案不推荐该降级。
7. **迁移安全**：迁移工具只创建新配置不覆盖旧值；插件缺失时旧配置只读展示；回滚 = 禁用插件。
8. **maaend 协作边界**：只承诺 `maafw.interface.v1` 契约与样例，不承诺任何 MXU 语义，避免维护责任越界。

---

## 10. 给 Claude 的审核清单

1. 分歧 #1/#2 的裁决：agent 环境归 project、agent 子进程归 runner 会话——是否认可这条切线？还是应该像方案 A 一样独立 agent 插件？
2. 分歧 #5：M9A 以 project pack 为目标形态、ScriptAdapterPlugin 仅作过渡——过渡期判据（"pack SDK 未固化"）是否足够客观，会不会造成过渡形态长期滞留？
3. 分歧 #6：core 与元包合并为 `automas-script-maafw` + extras——MAS 插件市场的安装流程对 pip extras 的支持需要确认；若市场不支持 extras，是否退回独立元包？
4. §4.3 的宿主无关分层是否应该更进一步：三个 core 直接发普通 PyPI 包（非 MAS 插件），MAS 插件包只做适配壳？（当前方案是"一包两层"，不拆双包）
5. worker JSON 行协议要不要在 P0 一并冻结为 v1 契约（利于独立宿主提前并行开发），还是留作 runner 内部实现细节到 P7 再冻结？
6. `PeriodRule` 放在编排插件的通用机制里，规则由 pack 声明——scope 枚举（daily/weekly/monthly）是否需要预留 cron 式自定义周期？
7. P1 让主程序内置路径改调新服务但保留 fallback——fallback 的存续期限是否应该显式定为"P4 结束即删"，避免双路径长期共存？
8. maa wheel 的落位：进官方 `environment.zip`（所有包变大）还是仅风味包预置层（标准包用户装 runner 时需在线拉 wheel）？本方案倾向后者，需确认标准包用户的体验可接受。
9. MirrorChyan 通道：maafw 风味发行版用独立 rid 还是共用 `AUTO_MAS`？独立 rid 便于风味包独立节奏，但多一份通道维护。
10. fork 归并上游的条件与时点：本方案定为"maafw 差异收敛为插件 + seed 清单之后"（约 P6），是否需要更早与上游确认官方 CI 接纳风味矩阵项的意愿——若上游不接纳，中期 fork workflow 就是长期形态。
11. 计划表方案是否接受"先核心计划表注册化，再新增 `MaaFWPlanConfig`"？若不接受，是否允许 MaaFW 插件自带计划页面并暂时不进入主 `/plans`？
12. `MaaFWPlanConfig` 第一版由 M9A 通过 `ProjectPackKey="m9a"` 复用，是否足够；还是应一开始就新增独立 `M9APlanConfig`？

---

## 附录 A：`app/task/MaaFW/` 全量文件映射（15 文件）

| 现有文件 | 去向 | 说明 |
|----------|------|------|
| `interface_models.py` | maafw-interface | Pydantic 模型，字段名冻结为 v1 契约 |
| `interface_loader.py` | maafw-interface | 解析/import 合并/scan_select/缓存 |
| `interface_preview.py` | maafw-interface | 预览 DTO |
| `task_config.py` | maafw-interface | TaskSnapshot 归一化；若多 UI 复用膨胀再议独立 profile 层 |
| `project_updater.py` | maafw-project | GitHub/MirrorChyan 更新 |
| `run_plan.py` | maafw-runner | run plan + agent command plan 构建（后者迁 project 的 `maafw.agent.v1`） |
| `pipeline_override.py` | maafw-runner | override 深合并/Builder |
| `runner.py` | maafw-runner | worker 侧直控实现（maa 导入面全在此） |
| `runner_worker.py` | maafw-runner | worker 子进程入口 + JSON 行协议 |
| `control_capabilities.py` | 拆两半 | 模拟器 EmulatorExtras 能力 → controller-adb（经 emulator 服务）；runtime DLL 探测 → maafw-runner |
| `window_service.py` | controller-desktop | 窗口扫描/句柄匹配/正则选择 |
| `manager.py` | automas-script-maafw | 改写为 `ScriptAdapterHooks` 编排 |
| `AutoProxy.py` | automas-script-maafw | → `run_auto_proxy`（会话驱动改经 `maafw.runner.v1`） |
| `__init__.py` | — | 随迁移消解 |
| `app/task/M9A/**`（manager/AutoProxy/task_loader/tools） | pack-m9a | 专项语义（队列/周月/文案）迁 pack；通用部分消解进基础包 |
| `app/models/config.py` 的 `MaaFWConfig`/`M9AConfig` | 废弃 | 迁移工具只读旧值 → `PluginScriptConfig` |
| `frontend/**/MaaFW*.vue`、`M9A*.vue` | script-maafw 组件层 / pack-m9a | 脚本壳 → PluginScriptEdit 体系；用户工作台 → pack 专项页；TaskOptionEditor/DescriptionView → 共享组件层 |

## 附录 B：包依赖与安装组合

```
automas-maafw-interface      深度 0   零 maa 依赖
automas-maafw-project        深度 1   needs: interface.v1
automas-maafw-runner         深度 2   needs: interface.v1 + project.v1；dep: maa
automas-maafw-controller-adb     深度 1*  needs: registry.v1；wants: emulator
automas-maafw-controller-desktop 深度 1*  needs: registry.v1
automas-script-maafw         编排     needs: interface/project/runner v1；provides: registry.v1
                             extras: [adb] [desktop] [full]
automas-script-maafw-pack-m9a     needs: automas-script-maafw[adb]；通知: automas-notification
（预留）automas-maafw-controller-gamepad / automas-maafw-controller-playcover / automas-script-maafw-ui（组件层拆包时机见分歧 #8）
```

| 场景 | 安装 |
|------|------|
| maaend（只读 interface） | `automas-maafw-interface` |
| 纯 pipeline 直控 | `automas-script-maafw[adb]` |
| M9A 完整 | `automas-script-maafw-pack-m9a`（依赖链自动拉全）+ `automas-notification` |
| 全家桶 | `automas-script-maafw[full]` |
| maafw 风味发行版 | Full 包 + 离线 seed（`automas-script-maafw[full]` + `pack-m9a` + `automas-notification` 及通道）+ maa 运行时预置，见 §6.3 |
