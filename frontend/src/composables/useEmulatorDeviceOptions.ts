import { translate as t } from '@/i18n'
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { Emulator20Service, Service, type ComboBoxItem } from '@/api'
import { PHONE_TYPE, markPhoneOptions, type DeviceSelectOption } from '@/views/Emulator/phoneLogic'

/**
 * 实例下拉的缓存放在模块级、跨页面共用。
 *
 * 六个脚本编辑页各自 new 一份 composable，页内缓存只对"同一页里反复切换模拟器"有用；
 * 用户在几个脚本之间来回点时，每进一页都要重新问一遍后端，下拉框先显示裸设备号、
 * 再跳成名字。实例名几乎不变，缓存一分钟足够；模拟器页增删实例时显式作废。
 */
const DEVICE_OPTIONS_TTL_MS = 60_000

/** 一条模拟器配置里的真机，以及哪些脚本能用它们（后端给的放行名单） */
interface PhoneSupport {
  slots: Set<string>
  scriptTypes: string[]
}

const NO_PHONES: PhoneSupport = { slots: new Set(), scriptTypes: [] }

interface SharedEntry {
  options: ComboBoxItem[]
  phones: PhoneSupport
  expiresAt: number
}

const sharedDeviceOptions = new Map<string, SharedEntry>()

const readShared = (emulatorId: string): SharedEntry | undefined => {
  const entry = sharedDeviceOptions.get(emulatorId)
  if (!entry) return undefined
  if (Date.now() >= entry.expiresAt) {
    sharedDeviceOptions.delete(emulatorId)
    return undefined
  }
  return entry
}

/** 模拟器页增删了实例 / 路径之后调用，让脚本页下次重新拉列表。 */
export const invalidateEmulatorDeviceOptions = (emulatorId?: string): void => {
  if (emulatorId) sharedDeviceOptions.delete(emulatorId)
  else sharedDeviceOptions.clear()
}

/**
 * 这条配置里哪些设备号是真机。下拉只有名字，类型要另问一次设备表；只有 Emulator 2.0 配置
 * 才问（设备表会枚举设备，别的配置不白跑一趟）。问失败就当没有真机——保存与运行时后端还会再拦。
 */
const loadPhoneSupport = async (emulatorId: string): Promise<PhoneSupport> => {
  try {
    const config = await Service.getEmulatorApiEmulatorGetPost({ emulatorId })
    if (config?.code !== 200 || config.data?.[emulatorId]?.Info?.Type !== 'emulator2') {
      return NO_PHONES
    }
    const response = await Emulator20Service.listDevicesApiEmulator2DevicesPost({
      emulatorId,
      withSettings: false,
    })
    if (response?.code !== 200) return NO_PHONES
    const slots = (response.devices ?? [])
      .filter(device => device.realType === PHONE_TYPE && device.slot)
      .map(device => device.slot)
    return { slots: new Set(slots), scriptTypes: response.phoneScriptTypes ?? [] }
  } catch {
    return NO_PHONES
  }
}

const markOptions = (entry: SharedEntry, scriptType: string): DeviceSelectOption[] =>
  entry.phones.slots.size
    ? markPhoneOptions(
        entry.options,
        value => value !== null && entry.phones.slots.has(value),
        entry.phones.scriptTypes.includes(scriptType),
        t('emulator2.phone.onlyFor', { scripts: entry.phones.scriptTypes.join(' / ') })
      )
    : entry.options

/**
 * ``scriptType``：所在页面的脚本类型（与后端 ``CLASS_BOOK`` 的键一致，如 ``MAA``）。
 * 不在后端放行名单里的脚本，下拉里的真机置灰并写明原因。
 */
export const useEmulatorDeviceOptions = (scriptType = '') => {
  const emulatorDeviceLoading = ref(false)
  const emulatorDeviceOptions = ref<DeviceSelectOption[]>([])
  let requestSequence = 0

  /** 模拟器选择被清空：丢掉本页的选项、作废在飞的请求。共享缓存不动，那是别的页面的。 */
  const clearEmulatorDeviceOptions = () => {
    requestSequence += 1
    emulatorDeviceOptions.value = []
    emulatorDeviceLoading.value = false
  }

  const loadEmulatorDeviceOptions = async (emulatorId: string) => {
    const requestId = ++requestSequence
    emulatorDeviceOptions.value = []

    if (!emulatorId) {
      emulatorDeviceLoading.value = false
      return
    }

    const cached = readShared(emulatorId)
    if (cached) {
      emulatorDeviceOptions.value = markOptions(cached, scriptType)
      emulatorDeviceLoading.value = false
      return
    }

    emulatorDeviceLoading.value = true
    try {
      const response = await Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
        emulatorId,
      })

      if (requestId !== requestSequence) return

      if (response.code === 200) {
        const phones = await loadPhoneSupport(emulatorId)
        if (requestId !== requestSequence) return
        const entry: SharedEntry = {
          options: response.data || [],
          phones,
          expiresAt: Date.now() + DEVICE_OPTIONS_TTL_MS,
        }
        sharedDeviceOptions.set(emulatorId, entry)
        emulatorDeviceOptions.value = markOptions(entry, scriptType)
      } else {
        message.error(response.message || '加载模拟器实例选项失败')
      }
    } catch (error) {
      if (requestId !== requestSequence) return

      const errorMessage = error instanceof Error ? error.message : String(error)
      message.error(t('misc.couldNotLoadEmulator', { p0: errorMessage }))
    } finally {
      if (requestId === requestSequence) {
        emulatorDeviceLoading.value = false
      }
    }
  }

  return {
    emulatorDeviceLoading,
    emulatorDeviceOptions,
    clearEmulatorDeviceOptions,
    loadEmulatorDeviceOptions,
  }
}
