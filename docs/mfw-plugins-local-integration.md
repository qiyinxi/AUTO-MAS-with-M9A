# MFW 插件族联调说明

本文只适用于联调分支 `int/mfw-plugins-20261122`：宿主已经不再登记内置的 MaaFW / M9A / MSS，
这三类托管交给插件 `maafw_adapter`、`m9a_adapter`、`mss_adapter`，它们依赖三块积木服务插件
（`maafw_agent_env`、`maafw_runner`、`maafw_project_update`）和两块库
（`auto-mas-maafw-interface`、`auto-mas-maafw-native`）。八个包的 0.1.0 都已发到 PyPI。

两种用法：

- **只想联调、不改插件包**：看第 1 节「从 PyPI 装」。
- **要改插件包源码**：看第 2 节「本地目录接入」。

第 3 节写现在能做什么、不能做什么，第 4 节是踩过的坑。下面的命令和接口都是 2026-11-22
实际跑通的（端口 36196，可换成任何空闲端口）。

## 1. 从 PyPI 装

### 1.1 拉分支、建环境

分支在 fork `qiyinxi/AUTO-MAS-with-M9A` 上。在主仓里开一棵新工作树：

```powershell
git fetch https://github.com/qiyinxi/AUTO-MAS-with-M9A.git int/mfw-plugins-20261122
git worktree add <树目录> -b int/mfw-plugins-20261122 FETCH_HEAD
Set-Location <树目录>
$uv = '<uv.exe 的路径>'          # 本机是 D:\MAS\code\main\environment\python\Scripts\uv.exe
& $uv sync --frozen --group dev
Copy-Item .env.example .env      # 开发环境标记，没有它后端会去占正式版的 36163
```

要看界面的，再在 `frontend` 里 `corepack yarn install --immutable`，按平常的方式起前端。

### 1.2 起后端

```powershell
$env:AUTO_MAS_ENV       = 'dev'
$env:AUTO_MAS_HTTP_PORT = '36196'
$env:AUTO_MAS_UV_EXE    = $uv
# 数据站的插件目录还没收录这几个新包，让宿主刷新目录时按包名去 PyPI 补上：
$env:AUTO_MAS_PLUGIN_EXTRA_PACKAGES = 'auto-mas-maafw-adapter,auto-mas-m9a-adapter,auto-mas-mss-adapter'
& .\.venv\Scripts\python.exe main.py
```

`AUTO_MAS_PLUGIN_EXTRA_PACKAGES` 是这条分支加的：逗号分隔的发行包名，刷新插件目录时逐个读
PyPI 的单包元数据补进目录（日志「按包名从 PyPI 补充插件目录：…」）。数据站收录以后就不用设了。
配置里**已经有** MFW / M9A / MSS 托管的，不设也行，见 1.4。

### 1.3 在插件中心装三个专项

界面上：插件中心 → 刷新目录 → 依次「安装」再「启用」：

1. `auto-mas-maafw-adapter`（MFW）——装它时三块积木和两块库会作为依赖一起装上；
   启用它时三块积木按依赖关系一起启用。
2. `auto-mas-m9a-adapter`（M9A）
3. `auto-mas-mss-adapter`（MSS）

**不用重启**，也不用逐个启用积木。每个专项安装约 10–30 秒（第一次要解析依赖、下载）。

走接口时（插件中心的按钮就是这些配置触发器）：

```text
POST /api/plugin_catalog/refresh  {}
POST /api/plugin_catalog/get      {}           → data 的键是目录项 uid，info.package_name 是包名
POST /api/config/triggers/write   {"configUid": "<目录项 uid>", "group": "info", "field": "install", "value": true}
                                               → data 是任务 uid
POST /api/config/triggers/result  {"taskId": "<任务 uid>"}   → data.state 由 running 变成 succeeded
POST /api/plugin_registry/get     {}           → data 的键是注册项 uid，info.plugin_name 是插件标识
POST /api/config/triggers/write   {"configUid": "<注册项 uid>", "group": "info", "field": "enable", "value": true}
POST /api/config/triggers/result  {"taskId": "<任务 uid>"}
```

实测（干净数据）：装 `auto-mas-maafw-adapter` 用了 8.6 s，之后 `maafw_adapter` 和三块积木都是
`disabled`；启用 `maafw_adapter` 0.4 s，四个都变成 `enabled`。M9A、MSS 各装 14 s，启用即成。

### 1.4 配置里已有托管（从内置版或本地目录接入换过来）

什么都不用点：起后端时宿主发现配置里有 `MaaFWConfig` / `M9AConfig` / `MSSConfig` /
`MSSPlanConfig`，会在激活配置前自动从 PyPI 装上并启用三个专项（连同积木和库），
托管、账号、计划表原样接上。实测启动多花约 10 秒，日志里没有「插件化升级」的 WARNING。

之前用第 2 节的目录联接接入过的，**先拆联接**（`scripts\dev\link_mfw_plugins.ps1 -Unlink`）再起，
否则宿主继续用本地源码；起后端时也不要再设 `UV_CONFIG_FILE`。

### 1.5 怎么确认装好了

```text
POST /api/plugin/list   {}   → maafw_adapter、m9a_adapter、mss_adapter、maafw_agent_env、
                               maafw_runner、maafw_project_update 都是 state=enabled、source=installed、
                               version=0.1.0、last_error 为空
GET  /api/scripts/types      → 含 "M9A"、"MaaFW"、"MSS"
```

装好以后重启后端，九个插件（含模拟器插件）自动启用，不用再点。

### 1.6 走一遍主路径

```text
POST /api/scripts/add                      {"type": "MaaFW"}            （M9A / MSS 同理）→ scriptId
POST /api/scripts/maafw/embedded/reimport  {"scriptId": ..., "sourcePath": "<项目目录>"}
POST /api/scripts/maafw/preview            {"scriptId": ..., "path": ""}  → controllers / resources / tasks
POST /api/scripts/update                   {"scriptId": ..., "data": {"Info": {"Controller": ..., "Resource": ...}}}
POST /api/scripts/user/add                 {"scriptId": ...}            → userId
POST /api/scripts/maafw/agent-env/prepare  {"scriptId": ..., "path": "", "force": false}   （可能联网装依赖）
POST /api/plan/add                         {"type": "MSSPlan"}          （MSS 计划表）
```

`/api/scripts/maafw/*` 这组路径和内置版一样，由插件挂载（`maafw_project_update` 挂 15 个，
`maafw_adapter` 挂外壳配置导入的 3 个），所以**前端的 MFW / M9A / MSS 页面不用改**，装好插件就能用。

实测用的项目目录（只读）：

| 类型 | 项目 | 目录 |
| --- | --- | --- |
| MaaFW | MAA_bbb v1.13.3 | `D:\MAS\test\walkref\maabbb` |
| M9A | M9A v4.9.0 | `D:\MAS\test\walkref\m9a` |
| MSS | MaaStellaSora v1.4.4 | `D:\MAS\test\mfw-src\StellaSora-v1.4.4` |

`D:\MAS\test\walkref\starres` 是 MaaStarResonance（星痕共鸣），不是 MSS（星塔旅人），
导入到 MSS 托管会被拒绝（「这不是 MSS 项目」），这是正确行为。

PowerShell 的 `Invoke-RestMethod` 解析不了同时带 `info` 和 `Info` 两个键的响应（托管和账号接口
都是这样），调这些接口用 Python：

```python
import json, urllib.request
def call(path, body=None, method="POST"):
    req = urllib.request.Request("http://127.0.0.1:36196" + path, method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())
```

## 2. 本地目录接入（改插件包的人用）

插件源码改了想马上在宿主里看效果，用目录联接把六个插件包接进 `plugins\`，两块库用本地打的 wheel。

### 2.1 打两块库的 wheel

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

### 2.2 接入六个插件

从宿主树根：

```powershell
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

### 2.3 起后端

同 1.2，但多设一个 `UV_CONFIG_FILE`，不用设 `AUTO_MAS_PLUGIN_EXTRA_PACKAGES`：

```powershell
$env:UV_CONFIG_FILE = Join-Path $env:TEMP 'mfwint\wheels\uv.toml'
```

首次启动时宿主联合解析插件依赖，两块库从 wheel 目录装进 `plugins\pypi\site-packages`
（宿主命令行自带 `--find-links`，`UV_FIND_LINKS` 会被盖掉，只有 `UV_CONFIG_FILE` 里的 find-links
会合并进去）。

### 2.4 启用插件

六个插件被发现为 `source=local`、`state=disabled`。按 1.3 的接口对注册项写 `info.enable`，顺序：
`maafw_agent_env` → `maafw_runner` → `maafw_project_update` → `maafw_adapter` → `m9a_adapter` →
`mss_adapter`（直接启用三个专项也会先启用积木）。启用状态会落盘，之后重启后端自动启用。
积木改了要重启后端；专项可以在插件中心重载。

### 2.5 拆除

```powershell
pwsh -NoProfile -File scripts\dev\link_mfw_plugins.ps1 -Unlink
```

只删联接，不碰目标仓库。拆完想换成 PyPI 版，按 1.4 直接起后端即可。

## 3. 现在能做什么、不能做什么

能做（两种用法都实测过）：

- 装插件、启用、重启后自动启用；`/api/scripts/types` 出现三种类型。
- 新建 MFW / M9A / MSS 托管，导入项目，预览，补控制器与资源，新建账号，准备 agent 环境。
- 前端 MFW 编辑页会调的端点都返回 200：内嵌状态、来源列表、复用已有托管的项目、预览、
  包名推断、更新检查（`action=check`）、更新作业、Mirror 酱 CDK 查询、准备环境、
  外壳配置实例的列出 / 导入 / 覆盖、项目图标、任务说明图片。
- 新建 MSS 计划表、MSS 账号页的计划表下拉。
- 已有托管的配置从内置版 / 本地接入换到 PyPI 版，托管和账号原样接上。

不能做或没人验证过：

- **运行还没有人验证过**：没派发过运行，没拉过游戏和模拟器，`action=apply` 的项目更新也没点过。
- 新账号的任务队列是空的（宿主不给插件类型配置回调），删托管后副本要到下次启动才清，
  复制托管不带视图。
- MCP 没有 MFW 相关的六个工具。
- 前端的 OpenAPI 生成物没有按插件形态重新生成。

插件包自己的已知问题见积木仓库 `docs/known-issues-0.1.0.md`
（<https://github.com/AUTO-MAS-Project/AUTO-MAS-MaaFW/blob/main/docs/known-issues-0.1.0.md>）。

## 4. 遇到问题先看这里

- **插件中心里找不到这几个包**：数据站的插件目录还没收录。起后端前设
  `AUTO_MAS_PLUGIN_EXTRA_PACKAGES`（见 1.2），再刷新目录。设 `AUTO_MAS_PLUGIN_INDEX_URL` 为空、让宿主走
  PyPI 总索引也不行：PyPI 的 `/simple/` 总索引有缓存，2026-11-22 当天还查不到这几个包名。
- **日志里有「插件依赖解析失败（https://mirrors.aliyun.com/pypi/simple/）… was not found」**：
  阿里云镜像还没同步新包，宿主会自动换下一个镜像（实测清华源有），安装照常成功，可以不管。
- **安装报「插件 `xxx` 正在使用本地源码，请先移除该工程后再安装发行包」**：`plugins\` 下还留着
  第 2 节的目录联接，先 `-Unlink`。
- **安装报「已有插件安装等待重启或恢复，请先重启后端完成该操作」**：上一次安装失败了，宿主等下次启动
  回滚。重启后端，看日志里失败的原因再装。
- **打开 MFW 页面报「这个接口由 MFW 插件提供，插件还没装上或没启用…」，或新建托管报
  「MaaFW 托管由插件提供…」**：插件没装上或没启用，按第 1 节装。
- **启动日志有一串 `UserWarning: Field name "Info" in "MaaFWUserConfig" shadows an attribute…`**：
  插件配置类的字段名和宿主基类同名，不影响使用。
- **首次在配置已有 MFW 托管时启动，日志有「已回收 MFW 共用运行时库」**：插件的维护任务清了一遍没人用的
  共用运行时库，之后准备环境照常成功。
- **配置里有 MFW 托管、插件却装不上**（断网、PyPI 不通）：后端照常起来，托管按内置类型原样保留、
  不能运行，启动通知会提示；网通了重启即自动补装。
- **停后端**：开发模式下 `POST /api/core/close` 只做清理、不退出。`.venv\Scripts\python.exe` 是启动器，
  真正监听端口的是它的子进程，要按进程树停：

  ```powershell
  $owner = (Get-NetTCPConnection -LocalPort 36196 -State Listen).OwningProcess
  function Get-Tree($id) { Get-CimInstance Win32_Process -Filter "ParentProcessId=$id" | ForEach-Object { $_; Get-Tree $_.ProcessId } }
  $all = @(Get-CimInstance Win32_Process -Filter "ProcessId=$owner") + @(Get-Tree $owner)
  $parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$owner").ParentProcessId
  $all += @(Get-CimInstance Win32_Process -Filter "ProcessId=$parent" | Where-Object { $_.CommandLine -match 'main\.py' })
  $all | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Get-NetTCPConnection -LocalPort 36196 -State Listen -ErrorAction SilentlyContinue   # 应为空
  ```

- **用 Start-Process 起后端时**：不要用管道或 `$x = ...` 接常驻进程的输出（子进程会继承管道句柄，
  调用方一直等不到结束），用 `-RedirectStandardOutput` / `-RedirectStandardError` 重定向到文件。
- 运行数据都在树根被忽略的 `config\ data\ debug\ temp\ plugins\pypi\` 下；想从零再来，停后端后把这几个
  目录挪走即可。
