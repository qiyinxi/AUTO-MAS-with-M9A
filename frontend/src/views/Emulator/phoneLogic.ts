/**
 * Emulator 2.0 里「真机」那一类设备的界面语义。
 *
 * 真机不是 MAS 开的：「启动」是连上并亮屏，「关闭」是熄屏；没有窗口、没有游戏中心、
 * 没有模拟器设置。哪些脚本能用真机由后端说了算（设备表接口的 ``phoneScriptTypes``），
 * 这里只负责照着它把下拉选项置灰。纯函数，不碰网络和组件。
 */
import type { ComboBoxItem, Emulator2DeviceItem } from '@/api'
import { DeviceStatus, effectiveStatus, type Pending } from './emulator2Status'

/** 后端的设备类型键 */
export const PHONE_TYPE = 'phone'

/** 实例下拉的一项：真机在不支持它的脚本里 ``disabled`` */
export type DeviceSelectOption = ComboBoxItem & { disabled?: boolean }

export const isPhoneDevice = (device: Pick<Emulator2DeviceItem, 'realType'>): boolean =>
  device.realType === PHONE_TYPE

/**
 * 把真机选项置灰并在名字后面写明原因。脚本支持真机时原样返回。
 * 置灰而不是藏起来：藏了用户会以为手机没被认出来。
 */
export const markPhoneOptions = <T extends ComboBoxItem>(
  options: T[],
  isPhone: (value: string | null) => boolean,
  allowed: boolean,
  hint: string
): (T & { disabled?: boolean })[] => {
  if (allowed) return options
  return options.map(option =>
    isPhone(option.value)
      ? { ...option, label: `${option.label}（${hint}）`, disabled: true }
      : option
  )
}

/** 当前连接方式：``usb`` / ``wifi`` / ``''``（没有连接） */
export const phoneConnection = (device: Pick<Emulator2DeviceItem, 'phone'>): string =>
  device.phone?.connection ?? ''

/** 不可用的原因码，没有问题时为空串 */
export const phoneReason = (device: Pick<Emulator2DeviceItem, 'phone'>): string =>
  device.phone?.reason ?? ''

interface PhoneActions {
  start: boolean
  stop: boolean
  show: boolean
  hide: boolean
  store: boolean
  settings: boolean
  delete: boolean
}

/**
 * 真机每个按钮能不能点。
 *
 * - 启动（连接并亮屏）：在线也能点——那就是把屏幕点亮；没有进行中的操作即可。
 * - 关闭（熄屏）：只有在线才有意义。
 * - 显示 / 隐藏 / 游戏中心 / 设置：真机没有。
 * - 移除：不要求离线，移除只是不再纳管，不碰手机。
 */
export const phoneActionAvailability = (
  device: Pick<Emulator2DeviceItem, 'availability' | 'status'>,
  pending: Pending | undefined,
  now: number
): PhoneActions => {
  const reachable = device.availability === 'ok'
  const busy = pending !== undefined && now < pending.expiresAt
  const online = effectiveStatus(device, pending, now) === DeviceStatus.ONLINE
  return {
    start: reachable && !busy,
    stop: reachable && online && !busy,
    show: false,
    hide: false,
    store: false,
    settings: false,
    delete: !busy,
  }
}
