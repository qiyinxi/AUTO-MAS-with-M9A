<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.migrate.title') }}</h3>
    </div>

    <a-alert type="info" show-icon :message="t('edit.migrate.pitch')">
      <template #description>
        <div>{{ t('edit.migrate.desc') }}</div>
        <a-button
          type="primary"
          class="migrate-button"
          :disabled="!sourcePath"
          @click="open = true"
        >
          {{ t('edit.migrate.action') }}
        </a-button>
        <div v-if="!sourcePath" class="form-hint">{{ t('edit.migrate.needPath') }}</div>
      </template>
    </a-alert>

    <a-modal
      v-model:open="open"
      :title="t('edit.migrate.confirmTitle')"
      :confirm-loading="migrating"
      :ok-text="t('edit.migrate.action')"
      @ok="handleMigrate"
    >
      <p>{{ t('edit.migrate.confirmBody', { path: sourcePath }) }}</p>
      <!-- AUTO-MAS 不碰原目录：投影万一漏了文件，它是唯一退路；删不删用户自己决定。 -->
      <p class="migrate-keep">{{ t('edit.migrate.keepSource') }}</p>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { Modal, message } from 'ant-design-vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { useMaaFWManagedApi } from '@/composables/useMaaFWManagedApi'

const { t } = useI18n()

const props = defineProps<{
  scriptId: string
  /** 当前的 Info.Path；为空时无从迁移 */
  sourcePath: string
}>()

const emit = defineEmits<{ migrated: [] }>()

const { migrating, migrateToManaged } = useMaaFWManagedApi()

const open = ref(false)

async function handleMigrate() {
  const result = await migrateToManaged({ scriptId: props.scriptId })
  if (!result.ok) {
    // 导入闸门的拒绝理由就是用户要看的东西：迁移不成多半是项目本身不合规。
    Modal.error({ title: t('edit.migrate.failed'), content: result.message, width: 560 })
    return
  }
  open.value = false
  message.success(result.message)
  emit('migrated')
}
</script>

<style scoped>
.migrate-button {
  margin-top: 12px;
}

.migrate-keep {
  margin-top: 8px;
  color: var(--ant-color-text-secondary, #666);
}
</style>
