<script setup lang="ts">
/**
 * 添加「真机（ADB）」路径：用户选 platform-tools 里的 adb.exe（或它所在的文件夹）。
 * 后端会跑一次 ``adb version`` 校验，并把已经插着的手机收进设备表。
 */
import { computed, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FolderOpenOutlined } from '@ant-design/icons-vue'

import { useEmulator2PhoneApi } from '@/composables/useEmulator2PhoneApi'

const props = defineProps<{ open: boolean; emulatorId: string }>()
const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'added'): void
}>()

const { t, te } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const { loading, error, addPhonePath } = useEmulator2PhoneApi()

const adbPath = ref('')

const visible = computed({
  get: () => props.open,
  set: value => emit('update:open', value),
})

watch(
  () => props.open,
  open => {
    if (open) adbPath.value = ''
  }
)

/** 原因码 → 文案：真机专用的说法优先，其余沿用模拟器那套 */
const reasonLabel = (reason: string) => {
  for (const key of [`emulator2.phone.pathReason.${reason}`, `emulator2.reason.${reason}`]) {
    if (te(key)) return t(key)
  }
  return reason
}

const browse = async () => {
  const paths = await window.electronAPI?.selectFile?.([{ name: 'adb.exe', extensions: ['exe'] }])
  if (paths && paths.length > 0) adbPath.value = paths[0]
}

const confirm = async () => {
  const path = adbPath.value.trim()
  if (!path) return
  const response = await addPhonePath(props.emulatorId, path)
  if (response === null) {
    logger.error(`添加真机路径失败: ${error.value}`)
    message.error(t('emulator2.phone.toast.addFailed'))
    return
  }
  if (response.code !== 200 || !response.ok) {
    message.warning(response.reason ? reasonLabel(response.reason) : response.message)
    return
  }
  message.success(t('emulator2.phone.toast.pathAdded'))
  visible.value = false
  emit('added')
}
</script>

<template>
  <a-modal
    v-model:open="visible"
    :title="t('emulator2.phone.pathTitle')"
    :confirm-loading="loading"
    :ok-text="t('emulator2.add')"
    :ok-button-props="{ disabled: !adbPath.trim() }"
    @ok="confirm"
  >
    <a-form layout="vertical">
      <a-form-item :label="t('emulator2.phone.pathLabel')" :extra="t('emulator2.phone.pathHint')">
        <div class="path-row">
          <a-input
            v-model:value="adbPath"
            :placeholder="t('emulator2.phone.pathPlaceholder')"
            @press-enter="confirm"
          />
          <a-button :icon="h(FolderOpenOutlined)" @click="browse">
            {{ t('emulator2.phone.browse') }}
          </a-button>
        </div>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<style scoped>
.path-row {
  display: flex;
  gap: 8px;
}
</style>
