<script setup lang="ts">
/**
 * 给真机添加一个无线调试地址。后端当场连一次认认是哪台手机：认得出就沿用它的设备号，
 * 连不上也照样添加，启动时再连。
 */
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'

import type { Emulator2PathItem } from '@/api'
import { useEmulator2PhoneApi } from '@/composables/useEmulator2PhoneApi'

const props = defineProps<{
  open: boolean
  emulatorId: string
  /** 只传真机路径 */
  paths: Emulator2PathItem[]
}>()
const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'added'): void
}>()

const { t, te } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const { loading, error, addPhoneAddress } = useEmulator2PhoneApi()

const address = ref('')
const pathId = ref('')

const visible = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
})

const pathOptions = computed(() =>
  props.paths.map(path => ({ value: path.pathId, label: path.installPath }))
)

watch(
  () => props.open,
  open => {
    if (!open) return
    address.value = ''
    pathId.value = props.paths[0]?.pathId ?? ''
  }
)

const reasonLabel = (reason: string) => {
  const key = `emulator2.phone.addressReason.${reason}`
  return te(key) ? t(key) : reason
}

const confirm = async () => {
  const value = address.value.trim()
  if (!value || !pathId.value) return
  const response = await addPhoneAddress(props.emulatorId, pathId.value, value)
  if (response === null) {
    logger.error(`添加无线设备失败: ${error.value}`)
    message.error(t('emulator2.phone.toast.addFailed'))
    return
  }
  if (response.code !== 200 || !response.ok) {
    message.warning(response.reason ? reasonLabel(response.reason) : response.message)
    return
  }
  const slot = response.slot ?? ''
  if (response.identified) {
    message.success(t('emulator2.phone.toast.addressAdded', { slot }))
  } else {
    message.info(t('emulator2.phone.toast.addressPending', { slot }))
  }
  visible.value = false
  emit('added')
}
</script>

<template>
  <a-modal
    v-model:open="visible"
    :title="t('emulator2.phone.addressTitle')"
    :confirm-loading="loading"
    :ok-text="t('emulator2.add')"
    :ok-button-props="{ disabled: !address.trim() || !pathId }"
    @ok="confirm"
  >
    <a-form layout="vertical">
      <a-form-item v-if="paths.length > 1" :label="t('emulator2.phone.addressPath')">
        <a-select v-model:value="pathId" :options="pathOptions" />
      </a-form-item>
      <a-form-item
        :label="t('emulator2.phone.addressLabel')"
        :extra="t('emulator2.phone.addressHint')"
      >
        <a-input
          v-model:value="address"
          :placeholder="t('emulator2.phone.addressPlaceholder')"
          @press-enter="confirm"
        />
      </a-form-item>
    </a-form>
  </a-modal>
</template>
