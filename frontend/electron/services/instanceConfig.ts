/**
 * 实例配置 - 区分开发环境与用户安装的正式版
 *
 * 两者默认共用同一个后端端口与同一个 Electron userData 目录，导致无法同时运行。
 * 本模块集中提供运行环境判定、后端端口与实例名，供主进程、镜像源服务与后端服务复用。
 *
 * 不依赖本目录下其它服务，避免与 environmentService / mirrorService 形成循环导入。
 */

import * as fs from 'fs'
import * as path from 'path'
import { app } from 'electron'

// ==================== 常量 ====================

// 正式版固定端口；开发环境错开一位，与 main.py 的 DEFAULT_HTTP_PORT / DEV_HTTP_PORT 保持一致
const DEFAULT_HTTP_PORT = 36163
const DEV_HTTP_PORT = 36164

// 全局快捷键是系统级独占资源，两版同时运行时必须错开，否则后注册的一方静默失效
const STOP_ALL_TASKS_SHORTCUT = 'Control+Shift+Alt+M'
const DEV_STOP_ALL_TASKS_SHORTCUT = 'Control+Shift+Alt+N'

// ==================== 工具函数 ====================

// 判断是否处于开发环境
export function isDevelopmentEnvironment(): boolean {
  if (process.env.NODE_ENV === 'development' || Boolean(process.env.VITE_DEV_SERVER_URL)) {
    return true
  }

  return Boolean(app) && !app.isPackaged
}

// 解析端口号，非法值返回 undefined 交由调用方回退
function parsePort(value: string | undefined): number | undefined {
  if (!value || !/^\d+$/.test(value.trim())) {
    return undefined
  }

  const port = Number(value.trim())
  return port >= 1 && port <= 65535 ? port : undefined
}

// 解析后端 HTTP/WS 端口：环境变量优先，其次按运行环境分流
export function resolveHttpPort(): number {
  const configured = parsePort(process.env.AUTO_MAS_HTTP_PORT)
  if (configured !== undefined) {
    return configured
  }

  return isDevelopmentEnvironment() ? DEV_HTTP_PORT : DEFAULT_HTTP_PORT
}

// 打包版按 config/frontend_config.json 的 Instance.Name 另起了身份（第二份安装）时为 true
let namedPackagedInstance = false

// 停止全部任务的全局快捷键，开发环境与另起身份的打包版都错开，以免与正式版互抢
export function resolveStopAllTasksShortcut(): string {
  return isDevelopmentEnvironment() || namedPackagedInstance
    ? DEV_STOP_ALL_TASKS_SHORTCUT
    : STOP_ALL_TASKS_SHORTCUT
}

// 实例名只允许拼进目录名的安全字符，长度有限
const INSTANCE_NAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/

/**
 * 打包版的实例名：exe 同级 `config/frontend_config.json` 里的 `Instance.Name`。
 *
 * 正式安装不写这个字段，行为与从前完全一致。同一台机器要并存第二份打包安装（比如
 * development 模式跑的测试包）时，两份共用 `%APPDATA%\frontend` 会被单实例锁静默挡掉，
 * 写上实例名让它另起 userData。文件不存在、字段缺失或非法一律视为未设置。
 * 不能依赖 environmentService（循环导入），路径直接按 exe 所在目录算。
 */
export function readPackagedInstanceName(): string | undefined {
  try {
    const settingsPath = path.join(
      path.dirname(app.getPath('exe')),
      'config',
      'frontend_config.json'
    )
    if (!fs.existsSync(settingsPath)) return undefined
    const parsed = JSON.parse(fs.readFileSync(settingsPath, 'utf8')) as {
      Instance?: { Name?: unknown }
    }
    const name = parsed.Instance?.Name
    if (typeof name !== 'string') return undefined
    const trimmed = name.trim()
    return INSTANCE_NAME_PATTERN.test(trimmed) ? trimmed : undefined
  } catch {
    return undefined
  }
}

// 后端默认端点，云端镜像配置未下发时使用
export function getDefaultApiEndpoints(): { local: string; websocket: string } {
  const port = resolveHttpPort()
  return {
    local: `http://127.0.0.1:${port}`,
    websocket: `ws://127.0.0.1:${port}`,
  }
}

/**
 * 开发环境改用独立的 userData 目录；打包版按 Instance.Name 另起身份
 *
 * userData 同时决定 Chromium profile 与 requestSingleInstanceLock 的锁键。打包版
 * asar 内的 package.json 仍为 name=frontend，与源码开发版取到同一个目录，后启动的
 * 一方会在窗口创建之前静默退出。必须在 app ready 之前调用。
 */
export function applyInstanceIdentity(): void {
  if (!app) {
    return
  }

  if (!isDevelopmentEnvironment()) {
    const packagedName = readPackagedInstanceName()
    if (packagedName === undefined) return
    namedPackagedInstance = true
    app.setPath('userData', path.join(app.getPath('appData'), packagedName))
    app.setName(packagedName)
    return
  }

  const instanceName = `${app.getName()}-dev`
  app.setPath('userData', path.join(app.getPath('appData'), instanceName))
  app.setName(instanceName)
}
