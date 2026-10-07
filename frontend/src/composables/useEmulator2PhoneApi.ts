import { ref } from 'vue'
import {
  Emulator20Service,
  type Emulator2PathAddOut,
  type Emulator2PhoneAddressAddOut,
  type Emulator2PhoneRestoreOut,
} from '@/api'

/** Emulator 2.0 路径记录里真机的类型键（与后端 ``PHONE_TYPE`` 一致） */
export const PHONE_PATH_TYPE = 'phone'

/**
 * Emulator 2.0 真机的写接口：添加真机（ADB）路径、添加无线调试地址、恢复移除过的手机。
 *
 * 业务失败（``code !== 200`` 或 ``ok=false``）原样交回响应，由调用方按原因码给提示；
 * 只有请求本身失败才写 ``error`` 并返回 ``null``。
 */
export const useEmulator2PhoneApi = () => {
  const loading = ref(false)
  const error = ref('')

  const run = async <T>(request: () => Promise<T>): Promise<T | null> => {
    loading.value = true
    error.value = ''
    try {
      return await request()
    } catch (err) {
      error.value = err instanceof Error ? err.message : String(err)
      return null
    } finally {
      loading.value = false
    }
  }

  const addPhonePath = (emulatorId: string, adbPath: string) =>
    run<Emulator2PathAddOut>(() =>
      Emulator20Service.addPathApiEmulator2PathsAddPost({
        emulatorId,
        installPath: adbPath,
        type: PHONE_PATH_TYPE,
      })
    )

  const addPhoneAddress = (emulatorId: string, pathId: string, address: string) =>
    run<Emulator2PhoneAddressAddOut>(() =>
      Emulator20Service.addPhoneAddressApiEmulator2PhonesAddressAddPost({
        emulatorId,
        pathId,
        address,
      })
    )

  const restorePhone = (emulatorId: string, pathId: string, serial: string) =>
    run<Emulator2PhoneRestoreOut>(() =>
      Emulator20Service.restorePhoneApiEmulator2PhonesRestorePost({
        emulatorId,
        pathId,
        serial,
      })
    )

  return { loading, error, addPhonePath, addPhoneAddress, restorePhone }
}
