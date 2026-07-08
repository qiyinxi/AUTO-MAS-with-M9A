# MaaEnd 专项：MaaFW 基础插件接入说明

本文给 MaaEnd 专项开发者看。当前建议：MaaEnd 先只接 ProjectInterface 解析；如果只需要更新能力，再单独接 `automas-maafw-project-update`。不要因为接更新而引入 runner、agent-env 或 M9A pack。

## 1. 可直接消费的包

| 需求 | 包 | 服务 |
| --- | --- | --- |
| 解析 ProjectInterface | `automas-maafw-interface` | `maafw.interface.v1` |
| 更新 MaaFW 项目目录 | `automas-maafw-project-update` | `maafw.project_update.v1` |

这两个包不依赖 `automas-maafw-runner`。MaaEnd 不跑 MaaFW tasker 时，不需要安装 runner。

## 2. Interface 服务

`maafw.interface.v1` 只做只读解析：

```text
load(path, force_reload=False) -> MaaFWInterface
preview(path, force_reload=False) -> MaaFWInterfacePreviewData
validate(interface) -> ValidationReport
build_default_snapshot(interface, preset=None) -> TaskSnapshot
normalize_snapshot(interface, snapshot) -> TaskSnapshot
normalize_execution_payload(interface, tasks, options, controller, resource) -> (tasks, options)
rescan_option(path, option_name) -> list[dict]
```

它不启动 tasker，不处理模拟器，不写 MaaEnd/MXU 配置，不包含 M9A 周/月任务语义。

## 3. Update 服务

`maafw.project_update.v1` 只负责项目更新：

```text
list_providers()
check_update(interface, current_version, source_config, proxy, send_log)
apply_update(project_path, candidate, proxy, send_log)
update_if_needed(project_path, interface, mirror_cdk, channel, proxy, send_log, source_config)
```

当前 provider：

- `github_release`
- `mirrorchyan`

更新服务负责下载、校验、路径安全检查、解包、应用和失败回滚。它不启动 MaaEnd，不启动 MaaFW runner，不创建 agent 环境，也不发送通知。

## 4. MaaEnd 接入建议

后端接入形态：

```text
MaaEnd service/API
  -> maafw.interface.v1.preview(project_path)
  -> MaaEnd 自己映射成 MXU/UI 需要的数据
  -> MaaEnd 自己保存 mxu / 用户配置
```

如果只接更新：

```text
MaaEnd update flow
  -> maafw.interface.v1.load(project_path)
  -> maafw.project_update.v1.update_if_needed(...)
  -> MaaEnd 自己决定是否刷新 interface / mxu 配置
```

不要让 MaaEnd 前端直接依赖通用 MaaFW 页面。MaaEnd 可以复用 DTO，但 UI 和配置落盘仍归 MaaEnd 专项。

## 5. 暂不接入的能力

| 能力 | 包 | 暂不接的原因 |
| --- | --- | --- |
| MaaFW runner | `automas-maafw-runner` | 需要 MaaEnd + MXU 真实运行样例确认任务是否能等价转换成 MaaFW run plan |
| agent 环境准备 | `automas-maafw-agent-env` | 只有 MaaEnd 确认需要 ProjectInterface agent 声明时再接 |
| M9A pack | `automas-script-maafw-pack-m9a` | 只包含 M9A 专项一次性任务初始值、通知翻译和迁移入口，MaaEnd 不应消费 |
| controller provider | `automas-maafw-controller-*` | 只有 MaaEnd 决定复用 MaaFW controller 直控时再接 |

## 6. Review 检查点

- MaaEnd 不 import `automas-maafw-runner`，除非后续单独验证运行样例。
- MaaEnd 可单独 import `automas-maafw-project-update`，且不会因此隐式安装 runner。
- MaaEnd 不复制 `interface_loader.py`，只消费 `maafw.interface.v1`。
- MaaEnd 不拿 M9A 的 `Psychube` / `SleepDream` 一次性任务初始值。
- GitHub Release 和 MirrorChyan 更新源需要用 MaaEnd/MXU 实际发行包样例验收。

## 7. 交付基线与后续变更约定（2026-07-08 起生效）

以下 wheel 已于 2026-07-08 交付 MaaEnd 专项适配者，构成兼容基线：

- `automas_maafw_interface-0.1.0`（2026-07-08 构建，含 `__no_plugin_config__` 声明）
- `automas_maafw_project_update-0.1.0`（同上）

自交付起，对这两个包的任何改动必须遵守：

1. **分发必 bump 版本**：修改后分发前提升 `pyproject.toml` 版本号（bug 修复升修订号，新增能力升次版本号），不允许再出现同版本号、不同内容的 wheel。
2. **v1 契约向后兼容**：本文第 2、3 节列出的方法签名与语义不得破坏；新增能力通过可选参数或新增方法实现。
3. **破坏性变更走新服务名**：需要不兼容变更时不修改 `maafw.interface.v1` / `maafw.project_update.v1`，应新开 `.v2` 服务并与 MaaEnd 专项提前对齐迁移窗口。
