<template>
  <div class="user-edit-header">
    <a-breadcrumb class="breadcrumb">
      <a-breadcrumb-item>
        <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
      </a-breadcrumb-item>
      <a-breadcrumb-item>
        <span class="breadcrumb-current">用户配置</span>
      </a-breadcrumb-item>
    </a-breadcrumb>

    <a-space>
      <a-button size="large" @click="emit('cancel')">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>

  <div v-if="saveStatus !== 'idle'" class="save-status-bar">
    <a-alert
      v-if="saveStatus === 'saving'"
      type="info"
      :banner="true"
      message="保存中…"
      :closable="false"
      show-icon
    />
    <a-alert
      v-else-if="saveStatus === 'saved'"
      type="success"
      :banner="true"
      message="已自动保存"
      :closable="true"
      show-icon
      @close="emit('clearSaveStatus')"
    />
    <a-alert
      v-else-if="saveStatus === 'error'"
      type="error"
      :banner="true"
      :message="saveErrorMessage || '保存失败，请重试'"
      :closable="true"
      show-icon
      @close="emit('clearSaveStatus')"
    />
  </div>
</template>

<script setup lang="ts">
import { ArrowLeftOutlined } from '@ant-design/icons-vue'

defineProps<{
  saveStatus: 'idle' | 'saving' | 'saved' | 'error'
  saveErrorMessage: string
}>()

const emit = defineEmits<{
  cancel: []
  clearSaveStatus: []
}>()
</script>

<style scoped>
.user-edit-header {
  max-width: 1400px;
  margin: 0 auto 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.breadcrumb-link {
  display: inline-flex;
  align-items: center;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
  white-space: nowrap;
}

.breadcrumb-current {
  display: inline-flex;
  align-items: center;
  color: var(--ant-color-text);
  font-weight: 600;
  white-space: nowrap;
}

.save-status-bar {
  max-width: 1400px;
  margin: -8px auto 16px;
}

@media (max-width: 768px) {
  .user-edit-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
