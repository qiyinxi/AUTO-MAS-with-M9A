import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// 打包态：isPackaged=true，exe 放在一个临时目录下，appData 另一个临时目录
const state = {
  isPackaged: true,
  exeDir: '',
  appData: '',
  name: 'frontend',
  userData: '',
}

vi.mock('electron', () => ({
  app: {
    get isPackaged() {
      return state.isPackaged
    },
    getPath: (key: string) => {
      if (key === 'exe') return path.join(state.exeDir, 'AUTO-MAS.exe')
      if (key === 'appData') return state.appData
      if (key === 'userData') return state.userData
      throw new Error(`unexpected path key ${key}`)
    },
    setPath: (key: string, value: string) => {
      if (key === 'userData') state.userData = value
    },
    getName: () => state.name,
    setName: (value: string) => {
      state.name = value
    },
  },
}))

const { applyInstanceIdentity, readPackagedInstanceName, resolveStopAllTasksShortcut } =
  await import('./instanceConfig')

function writeInstanceName(value: unknown): void {
  const configDir = path.join(state.exeDir, 'config')
  fs.mkdirSync(configDir, { recursive: true })
  fs.writeFileSync(
    path.join(configDir, 'frontend_config.json'),
    JSON.stringify({ Runtime: { LaunchMode: 'development' }, Instance: { Name: value } }),
    'utf8'
  )
}

beforeEach(() => {
  delete process.env.NODE_ENV
  delete process.env.VITE_DEV_SERVER_URL
  state.isPackaged = true
  state.exeDir = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-instance-'))
  state.appData = path.join(state.exeDir, 'appdata')
  state.name = 'frontend'
  state.userData = path.join(state.appData, 'frontend')
})

afterEach(() => {
  fs.rmSync(state.exeDir, { recursive: true, force: true })
})

describe('打包版按 Instance.Name 另起身份', () => {
  it('没有设置文件时什么都不改：userData、名字、快捷键与从前一致', () => {
    applyInstanceIdentity()

    expect(readPackagedInstanceName()).toBeUndefined()
    expect(state.userData).toBe(path.join(state.appData, 'frontend'))
    expect(state.name).toBe('frontend')
    expect(resolveStopAllTasksShortcut()).toBe('Control+Shift+Alt+M')
  })

  it('Instance.Name 合法时 userData 与名字都换成它，快捷键错开', () => {
    writeInstanceName('AUTO-MAS-test')

    applyInstanceIdentity()

    expect(state.userData).toBe(path.join(state.appData, 'AUTO-MAS-test'))
    expect(state.name).toBe('AUTO-MAS-test')
    expect(resolveStopAllTasksShortcut()).toBe('Control+Shift+Alt+N')
  })

  it('非法实例名（路径分隔符、空串、非字符串）按未设置处理', () => {
    for (const bad of ['..\evil', '', 42, ' ']) {
      writeInstanceName(bad)
      expect(readPackagedInstanceName()).toBeUndefined()
    }
  })
})
