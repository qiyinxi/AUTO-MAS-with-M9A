# MaaFW 插件化落地评审

本文按当前代码状态评审 MaaFW 插件化实现。结论：通用 MaaFW 已迁出 `app/task/MaaFW/**`，新建解析、更新、agent 环境、runner、controller 能力都由插件包承载；`app/task/M9A/**` 暂时保留，用于后续升级迁移和只读兼容。

## 1. 包拆分结构

当前形成 8 个可独立构建的 PyPI 包：

| 包 | 服务/入口 | 职责 |
| --- | --- | --- |
| `automas-maafw-interface` | `maafw.interface.v1` | ProjectInterface 解析、import 合并、预览 DTO、任务快照归档 |
| `automas-maafw-project-update` | `maafw.project_update.v1` | MaaFW 项目更新，支持 MirrorChyan 与 GitHub Release，不依赖 runner |
| `automas-maafw-agent-env` | `maafw.agent_env.v1` | agent command plan 和项目声明环境准备 |
| `automas-maafw-runner` | `maafw.runner.v1` | run plan、pipeline override、worker 子进程、MaaFW Tasker 执行 |
| `automas-maafw-controller-adb` | `maafw.controller.adb` | ADB controller provider 与 device spec |
| `automas-maafw-controller-win32` | `maafw.controller.win32` | Win32 窗口扫描、句柄匹配和 Win32 device spec |
| `automas-script-maafw` | `ScriptType=MaaFW`、`maafw.registry.v1` | MaaFW 脚本类型注册、运行编排、controller/pack registry |
| `automas-script-maafw-pack-m9a` | `maafw.pack.m9a.v1`、`ScriptType=M9A` | M9A 独立脚本类型注册、周/月规则、通知翻译、旧配置只创建迁移入口；底层复用 MaaFW runner |

`automas-maafw-project-update` 是单独更新插件。MaaEnd 如果只需要更新能力，可以只接 `automas-maafw-interface` + `automas-maafw-project-update`，不用安装 runner、agent-env 与 M9A pack。

## 2. 主程序改动

`app/core/script_types.py` 不再内建注册 `MaaFW`。`MaaFW` 由 `automas-script-maafw` 通过插件注册。

`app/task/__init__.py` 不再导出 `MaaFWManager`。旧的 `app/task/MaaFW/**` 目录已经删除，代码搜索中 `app.task.MaaFW` 为 0 命中。

`app/api/scripts.py` 保留现有 MaaFW HTTP 契约，但内部实现改为调用插件服务。

| API | 当前实现 |
| --- | --- |
| `/api/scripts/maafw/interface/preview` | `MaaFWInterfaceService.preview()` |
| `/api/scripts/maafw/project/update` | `MaaFWProjectUpdateService.update_if_needed()` + `MaaFWAgentEnvService.prepare_env()` |
| `/api/scripts/maafw/agent-env/prepare` | `MaaFWAgentEnvService.prepare_env()` |
| `/api/scripts/maafw/windows/preview` | `MaaFWDesktopControllerService` |

没有手改 OpenAPI 生成的前端代码。

## 3. MaaFW 运行链

`automas-script-maafw` 新增 `runner_task.py`，替代旧 `app.task.MaaFW.AutoProxyTask`。

- 仍使用现有 `MaaFWConfig` / `MaaFWUserConfig` 兼容模型承接插件配置，降低落地风险。
- 通过 `MaaFWInterfaceService` 读取 interface。
- 通过 `MaaFWRunnerService.build_plan()` 构建 run plan。
- 通过 `MaaFWRunnerService.run_worker()` 启动 runner worker。
- 保留用户代理次数、剩余天数、运行日志、成功通知、前后置脚本、周/月周期跳过记录。
- ADB 运行仍消费 MAS 模拟器配置启动实例并生成 device config。
- Win32 运行通过 Win32 controller provider 匹配窗口或使用用户配置的 `HWnd`。

`MaaFWRunnerService` 导入不加载 `maa`；只有 worker 子进程执行时才加载 `maa`。

## 4. M9A 边界

M9A 旧内嵌目录本轮不删除，原因是后续还需要升级迁移和只读兼容入口。

`automas-script-maafw-pack-m9a` 当前负责注册独立 `ScriptType=M9A`，并只在 MaaFW 通用运行链路上补充专项知识：

- `Psychube` 每周一次。
- `SleepDream` 每月一次。
- 通用 runner 结果到 M9A 用户可理解的通知文案的翻译。
- 旧 M9A 配置到插件配置的只创建迁移草案。

后续前端入口命名需要按双形态迁移策略处理，本轮不实施：

- 新插件入口显示为 `M9A`，不加“插件版”后缀；它是后续唯一正式新建和运行入口。
- 旧嵌入版本如仍出现在新增脚本或兼容入口中，显示为 `M9A（嵌入版）` 或 `旧 M9A（嵌入版）`。
- 旧嵌入版本保留 `M9AConfig` / `M9AUserConfig` 和必要读取逻辑，只服务旧配置反序列化、只读展示、迁移入口和必要数据读取，不注册为可运行 `type_key="M9A"`。
- 迁移只创建新的 `PluginScriptConfig` / `PluginUserConfig`，并设置 `Meta.PluginTypeKey = "M9A"`；不覆盖旧 M9A 配置。
- 迁移稳定后删除旧新增入口、旧运行链路和旧复杂编辑页。

它声明 M9A pack 默认值，包括项目来源、默认 controller、默认 resource、默认 preset、默认任务队列和周期规则；这些默认值只作为 MaaFW 通用运行链路的 pack metadata 输入，不代表 M9A 拥有独立 runner。

## 5. MaaEnd 可消费边界

MaaEnd 专项插件开发的边界是：

- 只解析 ProjectInterface：接 `maafw.interface.v1`。
- 只做项目更新：接 `maafw.project_update.v1`。
- 不需要 runner 时，不接 `maafw.runner.v1`。
- 不需要 M9A 规则时，不接 `maafw.pack.m9a.v1`。

项目更新插件已补齐 GitHub Release，同时保留 MirrorChyan。它只负责检查、下载、路径安全校验、解包、应用和回滚，不启动 tasker，不创建 agent 环境，不接管通知。

## 6. 验证结果

已执行编译检查：

```powershell
py -3.12 -m compileall app\api\scripts.py app\task\__init__.py plugins\automas_script_maafw\src tests\plugins\test_maafw_import_boundaries.py
```

结果：通过。

已执行插件单测：

```powershell
py -3.12 -m unittest tests.plugins.test_maafw_import_boundaries tests.plugins.test_maafw_script_adapter tests.plugins.test_maafw_interface_plugin tests.plugins.test_maafw_project_update_plugin tests.plugins.test_maafw_agent_env_plugin tests.plugins.test_maafw_runner_plugin tests.plugins.test_maafw_pack_m9a_plugin tests.plugins.test_maafw_controller_plugins
```

结果：

```text
Ran 24 tests in 1.433s
OK
```

代码搜索：

```powershell
rg -n 'app\.task\.MaaFW|task/MaaFW|task\\MaaFW|app\\task\\MaaFW' app plugins tests pyproject.toml
```

结果：无命中。

## 7. 评审重点

建议重点 review：

- `plugins/automas_script_maafw/src/automas_script_maafw/runner_task.py` 是否覆盖旧 AutoProxy 的必要运行语义。
- `app/api/scripts.py` 的 MaaFW 兼容路由是否保持现有前端契约。
- `automas-maafw-project-update` 是否满足 MaaEnd 的 GitHub/MirrorChyan 更新样例。
- `automas-script-maafw-pack-m9a` 是否只声明 M9A 默认项目、默认 controller/resource/preset、默认队列和周期规则，而不复制 MaaFW runner 或写死到通用 MaaFW 层。
- `app/task/M9A/**` 保留是否足够支撑后续迁移，是否还有需要提前抽到 pack-m9a 的只读能力。
