# MFW 插件族本地联调步骤

本文只适用于联调分支 `int/mfw-plugins-*`：宿主已经不再登记内置的 MaaFW / M9A / MSS，
这三类托管交给插件 `maafw_adapter`、`m9a_adapter`、`mss_adapter`。插件还没发 PyPI，
所以用「本地源码布局 + 库 wheel 目录」联调。

下面的命令就是 2026-11-22 实际跑通的那一套（端口 36196，可换成任何空闲端口）。
跑通的范围：插件环境准备、六个插件发现与启用、`/api/scripts/types` 出现三种类型、
三种类型各自新建托管 → 导入项目 → 补控制器与资源 → 新建账号 → 预览 → 准备 agent 环境。
**没有派发过运行**，真机跑一轮还没做。

## 0. 目录

| 角色 | 目录 |
| --- | --- |
| 联调宿主树 | `D:\MAS\code\trees\mfwint` |
| 积木仓库（两块库 + 三块服务插件） | `D:\MAS\code\blocks`，包在 `packages\auto-mas-maafw-*` |
| 三个专项仓库 | `D:\MAS\code\adapters\maafw`、`m9a`、`mss` |
| 库 wheel 与 uv.toml | `$env:TEMP\mfwint\wheels`（树外，随时可重建） |

## 1. 打两块库的 wheel

从积木仓库已提交的 HEAD 导出再打，不直接用工作目录（避免残留的 `build\lib` 混进 wheel）：

```powershell
$uv  = 'D:\MAS\code\main\environment\python\Scripts\uv.exe'
$w   = Join-Path $env:TEMP 'mfwint'
$src = Join-Path $w 'blk'
if (Test-Path $src) { Remove-Item -Recurse -Force $src }
New-Item -ItemType Directory -Force $src | Out-Null
git -C D:\MAS\code\blocks archive --format=tar -o "$w\blk.tar" HEAD
tar -xf "$w\blk.tar" -C $src
New-Item -ItemType Directory -Force "$w\wheels" | Out-Null
foreach ($p in 'auto-mas-maafw-interface', 'auto-mas-maafw-native') {
    & $uv build --wheel "$src\packages\$p" --out-dir "$w\wheels"
}
```

库改过、版本号没变时，重打之后接入脚本要加 `-RefreshLibraries`（删 `plugins\pypi\environment.json`
并清 uv 缓存里的两块库），否则宿主沿用已装的旧库。

## 2. 接入六个插件

从宿主树根：

```powershell
Set-Location D:\MAS\code\trees\mfwint
$b = 'D:\MAS\code\blocks\packages'
pwsh -NoProfile -File scripts\dev\link_mfw_plugins.ps1 `
  -AgentEnv "$b\auto-mas-maafw-agent-env" `
  -Runner "$b\auto-mas-maafw-runner" `
  -ProjectUpdate "$b\auto-mas-maafw-project-update" `
  -MaaFWAdapter D:\MAS\code\adapters\maafw `
  -M9AAdapter D:\MAS\code\adapters\m9a `
  -MssAdapter D:\MAS\code\adapters\mss `
  -WheelDir "$env:TEMP\mfwint\wheels"
```

脚本在 `plugins\` 下建六个目录联接，并在 wheel 目录写 `uv.toml`（`[pip] find-links`
指向 wheel 目录）。联接已被 `.gitignore` 忽略，不要提交。

## 3. 起后端

不要用管道或 `$x = ...` 接常驻进程的输出（子进程会继承管道句柄，调用方一直等不到结束），
用 `Start-Process` 重定向到文件：

```powershell
$tree = 'D:\MAS\code\trees\mfwint'
$log  = Join-Path $env:TEMP 'mfwint\backend'
New-Item -ItemType Directory -Force $log | Out-Null
$env:AUTO_MAS_ENV       = 'dev'
$env:AUTO_MAS_HTTP_PORT = '36196'
$env:AUTO_MAS_UV_EXE    = 'D:\MAS\code\main\environment\python\Scripts\uv.exe'
$env:UV_CONFIG_FILE     = Join-Path $env:TEMP 'mfwint\wheels\uv.toml'
$p = Start-Process -FilePath "$tree\.venv\Scripts\python.exe" -ArgumentList 'main.py' `
  -WorkingDirectory $tree -WindowStyle Hidden -PassThru `
  -RedirectStandardOutput "$log\out.txt" -RedirectStandardError "$log\err.txt"
```

`.venv\Scripts\python.exe` 是启动器，真正监听端口的是它拉起的子进程（基础解释器）。

首次启动时宿主联合解析插件依赖，两块库从 wheel 目录装进 `plugins\pypi\site-packages`
（两块库不在 PyPI 上，靠 `UV_CONFIG_FILE` 里的 find-links 才解析得到；实测解析和安装都成功）。
看 `err.txt` 或 `debug\app.log` 里「插件 uv」「插件依赖」的行。

## 4. 启用插件

插件中心的启用按钮对应配置触发器。走 API 时先查注册表拿记录 uid，再写 `info.enable`：

```text
POST /api/plugin_registry/get   {}                         → data 的键是记录 uid，info.plugin_name 是标识
POST /api/config/triggers/write {"configUid": "<uid>", "group": "info", "field": "enable", "value": true}
                                                           → data 是任务 uid
POST /api/config/triggers/result {"taskId": "<任务 uid>"}  → data.state 为 succeeded 即完成
POST /api/plugin/list            {}                        → 各插件 state、last_error
```

顺序：`maafw_agent_env` → `maafw_runner` → `maafw_project_update` → `maafw_adapter` →
`m9a_adapter` → `mss_adapter`。启用状态会落盘，之后重启后端六个插件自动启用。

确认类型：`GET /api/scripts/types` 应含 `MaaFW`、`M9A`、`MSS`。

## 5. 主路径（每种类型一遍）

```text
POST /api/scripts/add                      {"type": "MaaFW"}            （M9A / MSS 同理）→ scriptId
POST /api/scripts/maafw/embedded/reimport  {"scriptId": ..., "sourcePath": "<项目目录>"}
POST /api/scripts/maafw/preview            {"scriptId": ..., "path": ""}  → controllers / resources / tasks
POST /api/scripts/update                   {"scriptId": ..., "data": {"Info": {"Controller": ..., "Resource": ...}}}
POST /api/scripts/user/add                 {"scriptId": ...}            → userId
POST /api/scripts/user/get                 {"scriptId": ..., "userId": ...}
POST /api/scripts/maafw/agent-env/prepare  {"scriptId": ..., "path": "", "force": false}   （可能联网装依赖）
```

实测用的项目目录（只读）：

| 类型 | 项目 | 目录 |
| --- | --- | --- |
| MaaFW | MAA_bbb v1.13.3 | `D:\MAS\test\walkref\maabbb` |
| M9A | M9A v4.9.0 | `D:\MAS\test\walkref\m9a` |
| MSS | MaaStellaSora v1.4.4 | `D:\MAS\test\mfw-src\StellaSora-v1.4.4` |

注意：`D:\MAS\test\walkref\starres` 是 MaaStarResonance（星痕共鸣），不是 MSS（星塔旅人），
导入到 MSS 托管会被拒绝（「这不是 MSS 项目」），这是正确行为。

PowerShell 的 `Invoke-RestMethod` 解析不了同时带 `info` 和 `Info` 两个键的响应（大小写不敏感，
会原样返回字符串），托管和账号接口都是这样。实测时用 Python 的 `urllib` + `json` 调接口。

## 6. 停后端

开发模式下 `POST /api/core/close` 只做清理、不退出进程。按进程树停：先找监听端口的进程，
连同它的父进程（启动器）和所有子进程一起结束，再确认端口不再监听：

```powershell
$owner = (Get-NetTCPConnection -LocalPort 36196 -State Listen).OwningProcess
function Get-Tree($id) { Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" | ForEach-Object { $_; Get-Tree $_.ProcessId } }
$all = @(Get-CimInstance Win32_Process -Filter "ProcessId=$owner") + @(Get-Tree $owner)
$parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$owner").ParentProcessId
$all += @(Get-CimInstance Win32_Process -Filter "ProcessId=$parent" | Where-Object { $_.CommandLine -match 'main\.py' })
$all | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Get-NetTCPConnection -LocalPort 36196 -State Listen -ErrorAction SilentlyContinue   # 应为空
```

## 7. 拆除

```powershell
pwsh -NoProfile -File scripts\dev\link_mfw_plugins.ps1 -Unlink
```

只删联接，不碰目标仓库。运行数据在树根被忽略的 `config\ data\ debug\ plugins\pypi\` 下。
