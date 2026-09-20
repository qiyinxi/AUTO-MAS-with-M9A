/**
 * Runtime 后端监督链路的灰度开关与可执行文件定位
 *
 * 灰度期同时存在两条后端启动链路：
 * - `off`（默认）：Electron 自己 spawn `python.exe`，就绪靠健康检查，停止靠 scoped taskkill；
 * - `development` / `managed`：交给 `auto-mas-runtime.exe backend supervise` 监督。
 *
 * 一次生命周期只走一条链路：模式非 `off` 却找不到可执行文件时，按 `RUNTIME_NOT_FOUND`
 * 失败并展示，绝不静默回退旧链路——否则用户会在不知情的情况下拿到另一套端口与关闭语义。
 *
 * 灰度开关的来源分三级，优先级从高到低：
 * 1. 环境变量 `AUTO_MAS_RUNTIME_MODE`；
 * 2. 设置界面持久化的用户选择（`<appRoot>/config/frontend_config.json` 的
 *    `Runtime.LaunchMode`，与 `main.ts` 的 `loadConfig()/saveConfig()` 同一份文件）；
 * 3. 构建默认值：打包安装且已捆绑 Runtime 时默认 `managed`，否则 `off`——即打包安装且带
 *    Runtime 的用户默认走新链路，开发者跑源码默认仍走旧链路，除非显式设了环境变量。
 *
 * 任一级取值非法都记 warning 后落到下一级，不再像早前只有环境变量一级时那样直接判 `off`。
 */

import { app } from 'electron'
import * as fs from 'fs'
import * as path from 'path'

import { getLogger } from '../logger'

const logger = getLogger('Runtime启动配置')

/** 捆绑在安装包 resources 目录下的 Runtime 文件名。 */
export const RUNTIME_EXECUTABLE_NAME = 'auto-mas-runtime.exe'

/** 灰度开关的环境变量名。 */
export const RUNTIME_MODE_ENV = 'AUTO_MAS_RUNTIME_MODE'

/** 手动指定 Runtime 可执行文件路径的环境变量名。 */
export const RUNTIME_EXE_ENV = 'AUTO_MAS_RUNTIME_EXE'

/**
 * 指定受监督后端监听端口的环境变量名（传给 `backend supervise --port`）。
 *
 * 不设时 Runtime 按模式取缺省值（managed 36163、development 36164）。同一台机器上要并存
 * 第二份安装（比如用 development 模式跑一份测试包）时，两份都落到缺省端口就会互相撞上，
 * 这个口子让测试包挪到别的端口；正式安装不需要碰它。
 */
export const RUNTIME_PORT_ENV = 'AUTO_MAS_RUNTIME_PORT'

const RUNTIME_PORT_MIN = 1024
const RUNTIME_PORT_MAX = 65535

/**
 * 后端启动链路。
 *
 * `development` 监督开发者自己的源码检出（要求 `<repo>/main.py`、`<repo>/pyproject.toml`
 * 与已存在的 `<repo>/.venv`，Runtime 不创建它们）；`managed` 监督 Runtime 自己维护的受管工作区。
 */
export type RuntimeLaunchMode = 'off' | 'development' | 'managed'

const RUNTIME_LAUNCH_MODES: readonly RuntimeLaunchMode[] = ['off', 'development', 'managed']

/** 持久化设置比运行时开关多一个哨兵值：`auto` 表示不覆盖，跟随构建默认值。 */
export type PersistedRuntimeLaunchMode = RuntimeLaunchMode | 'auto'

const PERSISTED_RUNTIME_LAUNCH_MODES: readonly PersistedRuntimeLaunchMode[] = [
  'auto',
  ...RUNTIME_LAUNCH_MODES,
]

/** 最终生效值来自哪一级，供设置界面展示「当前由环境变量强制」之类的说明。 */
export type RuntimeLaunchModeSource = 'env' | 'setting' | 'default'

/** 一次解析的完整结果：生效模式 + 来源。 */
export interface RuntimeLaunchModeResolution {
  mode: RuntimeLaunchMode
  source: RuntimeLaunchModeSource
}

/** 灰度开关关闭时的定位信息：不去找可执行文件。 */
export interface RuntimeDisabledLaunchConfig {
  mode: 'off'
  runtimePath: null
  appRoot: string
}

/** 走 Runtime 监督链路时的定位信息。 */
export interface RuntimeSupervisedLaunchConfig {
  mode: Exclude<RuntimeLaunchMode, 'off'>
  /** 找不到可执行文件时为 null，由调用方按 `RUNTIME_NOT_FOUND` 处理。 */
  runtimePath: string | null
  /**
   * 传给 `--app-root` 的 Runtime 根目录：Runtime 在它下面维护 `runtime/`、`runtime-state/`、
   * `logs/runtime/`。`managed` 模式就是安装根（与 `dataRoot` 相同）；`development` 模式是仓外
   * 的独立目录（见 `resolveDevelopmentRuntimeRoot`），**不是**用户数据根，读配置不能用它。
   */
  appRoot: string
  /** `development` 模式传给 `--repo`（源码根）；`managed` 模式不传。 */
  repo?: string
  /** 传给 `--port` 的监听端口；未指定时不传，由 Runtime 按模式取缺省值。 */
  port?: number
  /**
   * 用户数据根，即传入 `resolveRuntimeLaunchConfig` 的 `getAppRoot()`：`config/Config.json`、
   * `config/frontend_config.json` 等都在它下面。凡是读用户配置的地方一律用它，不用 `appRoot`。
   */
  dataRoot: string
}

/** 一次启动所需的全部定位信息，按 `mode` 判别。 */
export type RuntimeLaunchConfig = RuntimeDisabledLaunchConfig | RuntimeSupervisedLaunchConfig

function isRuntimeLaunchMode(value: string): value is RuntimeLaunchMode {
  return (RUNTIME_LAUNCH_MODES as readonly string[]).includes(value)
}

/** 供 IPC 校验渲染进程传入值使用。 */
export function isPersistedRuntimeLaunchMode(value: unknown): value is PersistedRuntimeLaunchMode {
  return (
    typeof value === 'string' &&
    (PERSISTED_RUNTIME_LAUNCH_MODES as readonly string[]).includes(value)
  )
}

/** 持久化设置文件路径，须与 `main.ts` 的 `loadConfig()`/`saveConfig()` 保持一致。 */
function resolveSettingsPath(appRoot: string): string {
  return path.join(appRoot, 'config', 'frontend_config.json')
}

/**
 * 读取持久化设置里的启动方式。
 *
 * 文件不存在、字段缺失、类型不对或 JSON 损坏都视为「未设置」而不是报错——设置文件在用户
 * 从未碰过这一项时本就可能没有 `Runtime` 节点，这不是异常情况。
 */
function readPersistedLaunchMode(appRoot: string): string | undefined {
  try {
    const settingsPath = resolveSettingsPath(appRoot)
    if (!fs.existsSync(settingsPath)) return undefined

    const parsed = JSON.parse(fs.readFileSync(settingsPath, 'utf8')) as {
      Runtime?: { LaunchMode?: unknown }
    }
    const value = parsed.Runtime?.LaunchMode
    return typeof value === 'string' ? value : undefined
  } catch (error) {
    logger.warn(
      `读取持久化的 Runtime 启动方式设置失败，改按构建默认值处理: ${
        error instanceof Error ? error.message : String(error)
      }`
    )
    return undefined
  }
}

/** 读取持久化设置里的端口；文件不存在、字段缺失或不是数字都视为「未设置」。 */
function readPersistedRuntimePort(appRoot: string): unknown {
  try {
    const settingsPath = resolveSettingsPath(appRoot)
    if (!fs.existsSync(settingsPath)) return undefined

    const parsed = JSON.parse(fs.readFileSync(settingsPath, 'utf8')) as {
      Runtime?: { Port?: unknown }
    }
    return parsed.Runtime?.Port
  } catch {
    // JSON 损坏在 readPersistedLaunchMode 里已经记过 warning，这里不重复
    return undefined
  }
}

function parseRuntimePort(value: unknown): number | undefined {
  const port = typeof value === 'string' ? Number(value.trim()) : value
  if (typeof port !== 'number' || !Number.isInteger(port)) return undefined
  if (port < RUNTIME_PORT_MIN || port > RUNTIME_PORT_MAX) return undefined
  return port
}

/**
 * 解析受监督后端的监听端口：环境变量 `AUTO_MAS_RUNTIME_PORT` > 持久化设置 `Runtime.Port` >
 * 不指定（Runtime 缺省）。非法取值记 warning 后落到下一级。
 */
export function resolveRuntimePort(appRoot: string): number | undefined {
  const rawEnv = process.env[RUNTIME_PORT_ENV]
  if (rawEnv !== undefined && rawEnv.trim() !== '') {
    const port = parseRuntimePort(rawEnv)
    if (port !== undefined) return port
    logger.warn(
      `${RUNTIME_PORT_ENV} 取值非法：${rawEnv}，改按持久化设置处理（须是 ${RUNTIME_PORT_MIN}-${RUNTIME_PORT_MAX} 的整数）`
    )
  }

  const rawSetting = readPersistedRuntimePort(appRoot)
  if (rawSetting !== undefined && rawSetting !== null && rawSetting !== '') {
    const port = parseRuntimePort(rawSetting)
    if (port !== undefined) return port
    logger.warn(`持久化的 Runtime 端口设置非法：${String(rawSetting)}，改按 Runtime 缺省端口处理`)
  }

  return undefined
}

/** 构建默认值：打包安装且已捆绑 Runtime 才默认切新链路，源码开发默认走旧链路。 */
function resolveBuildDefaultLaunchMode(): RuntimeLaunchMode {
  const packaged = Boolean(app?.isPackaged)
  return packaged && resolveRuntimeExecutable() !== null ? 'managed' : 'off'
}

/**
 * 解析灰度开关，并带上生效来源。
 *
 * 优先级：环境变量 `AUTO_MAS_RUNTIME_MODE` > 持久化的用户设置 > 构建默认值。任一级取值
 * 非法都记 warning 后落到下一级，而不是直接判 `off`——最终结果永远来自某一级的合法取值，
 * 不会因为拼错一个单词就整体失效。
 */
export function resolveRuntimeLaunchModeDetail(appRoot: string): RuntimeLaunchModeResolution {
  const rawEnv = process.env[RUNTIME_MODE_ENV]
  if (rawEnv !== undefined && rawEnv.trim() !== '') {
    const normalizedEnv = rawEnv.trim().toLowerCase()
    if (isRuntimeLaunchMode(normalizedEnv)) {
      return { mode: normalizedEnv, source: 'env' }
    }
    logger.warn(
      `${RUNTIME_MODE_ENV} 取值非法：${rawEnv}，改按持久化设置处理（可选值：off/development/managed）`
    )
  }

  const rawSetting = readPersistedLaunchMode(appRoot)
  if (rawSetting !== undefined && rawSetting.trim() !== '') {
    const normalizedSetting = rawSetting.trim().toLowerCase()
    if (normalizedSetting !== 'auto') {
      if (isRuntimeLaunchMode(normalizedSetting)) {
        return { mode: normalizedSetting, source: 'setting' }
      }
      logger.warn(`持久化的 Runtime 启动方式设置非法：${rawSetting}，改按构建默认值处理`)
    }
    // normalizedSetting === 'auto'：用户显式选择跟随构建默认值，直接走下一级。
  }

  return { mode: resolveBuildDefaultLaunchMode(), source: 'default' }
}

/** 只要最终生效模式时用这个；需要在界面上展示来源时用 `resolveRuntimeLaunchModeDetail`。 */
export function resolveRuntimeLaunchMode(appRoot: string): RuntimeLaunchMode {
  return resolveRuntimeLaunchModeDetail(appRoot).mode
}

function isExistingFile(candidate: string): boolean {
  try {
    return fs.statSync(candidate).isFile()
  } catch {
    return false
  }
}

/**
 * 定位 `auto-mas-runtime.exe`。
 *
 * 优先用环境变量显式指定的路径，其次查安装包捆绑位置 `process.resourcesPath`。
 * 尚未捆绑时返回 null，由调用方转成 `RUNTIME_NOT_FOUND`。
 */
export function resolveRuntimeExecutable(): string | null {
  const configured = process.env[RUNTIME_EXE_ENV]?.trim()
  if (configured) {
    if (isExistingFile(configured)) {
      return path.resolve(configured)
    }
    logger.warn(`${RUNTIME_EXE_ENV} 指向的文件不存在：${configured}`)
  }

  // 非 Electron 环境（单元测试）下 resourcesPath 不存在。
  const resourcesPath = typeof process.resourcesPath === 'string' ? process.resourcesPath : ''
  if (resourcesPath) {
    const bundled = path.join(resourcesPath, RUNTIME_EXECUTABLE_NAME)
    if (isExistingFile(bundled)) {
      return bundled
    }
  }

  return null
}

/** `development` 模式下 Runtime 根目录在 userData 里的子目录名。 */
export const RUNTIME_DEVELOPMENT_ROOT_DIRNAME = 'auto-mas-runtime'

/**
 * `development` 模式的 Runtime 根目录（`--app-root`）。
 *
 * Runtime 明确拒绝根目录位于开发源码目录内（`INVALID_ARGUMENT`，
 * `reason=runtime_root_inside_development_repo`），而 Electron 开发态的 `getAppRoot()` 恰好就是
 * 源码仓根；源码仓也不该被 Runtime 的 `runtime/`、`runtime-state/`、`logs/runtime/` 污染。
 * 所以 Runtime 根目录放到仓外：
 * - Electron 环境：`<userData>/auto-mas-runtime`。开发态的 userData 已由 `applyInstanceIdentity()`
 *   与正式版分开（`<appData>/<name>-dev`），两版各自一份 Runtime 布局，互不干扰；
 * - 非 Electron 环境（单元测试、脚本）：源码根的同级目录 `<父目录>/<源码根目录名>-runtime`，
 *   与源码根一一对应且可预测，不依赖任何全局状态。
 *
 * 这里只算路径，不创建目录：Runtime 要求 `--app-root` 已存在，由真正要起 Runtime 的调用方
 * （`backendService`）在首次使用前创建。
 */
export function resolveDevelopmentRuntimeRoot(dataRoot: string): string {
  if (typeof app?.getPath === 'function') {
    return path.join(app.getPath('userData'), RUNTIME_DEVELOPMENT_ROOT_DIRNAME)
  }
  const sourceRoot = path.resolve(dataRoot)
  return path.join(path.dirname(sourceRoot), `${path.basename(sourceRoot)}-runtime`)
}

/**
 * 汇总本次启动的模式与路径。
 *
 * `appRoot` 参数是用户数据根（`getAppRoot()`）。`managed` 模式下它同时就是 Runtime 根目录；
 * `development` 模式下它是开发者跑的这份源码检出，作为 `--repo` 传给 Runtime，而 Runtime 根目录
 * 另取仓外位置（见 `resolveDevelopmentRuntimeRoot`）。
 */
export function resolveRuntimeLaunchConfig(appRoot: string): RuntimeLaunchConfig {
  const mode = resolveRuntimeLaunchMode(appRoot)
  if (mode === 'off') {
    return { mode, runtimePath: null, appRoot }
  }

  const port = resolveRuntimePort(appRoot)
  if (mode === 'development') {
    return {
      mode,
      runtimePath: resolveRuntimeExecutable(),
      appRoot: resolveDevelopmentRuntimeRoot(appRoot),
      repo: appRoot,
      port,
      dataRoot: appRoot,
    }
  }

  return {
    mode,
    runtimePath: resolveRuntimeExecutable(),
    appRoot,
    repo: undefined,
    port,
    dataRoot: appRoot,
  }
}
