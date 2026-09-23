<template>
  <div class="pip-container">
    <div class="pip-header">
      <div class="pip-search">
        <el-input
          :model-value="installName"
          placeholder="输入包名，如：requests 或 requests==2.28.0"
          size="large"
          clearable
          @update:model-value="emit('update:installName', $event)"
        >
          <template #prepend>包名</template>
        </el-input>
      </div>
      <div class="pip-actions">
        <el-button type="primary" size="large" @click="emit('install')" :loading="installing">
          <el-icon><Download /></el-icon> 安装
        </el-button>
        <el-button size="large" @click="emit('refresh')" :loading="loading">
          <el-icon><Refresh /></el-icon> 刷新列表
        </el-button>
      </div>
    </div>

    <div v-if="result.msg" class="pip-msg" :class="result.ok ? 'pip-ok' : 'pip-err'">
      <el-icon>{{ result.ok ? 'CircleCheck' : 'CircleClose' }}</el-icon>
      {{ result.msg }}
    </div>

    <div class="pip-list-container">
      <div class="pip-list-header">
        <span>已安装的包 ({{ packages.length }})</span>
      </div>
      <div v-if="packages.length" class="pip-list">
        <div class="pip-item" v-for="pkg in packages" :key="pkg.name">
          <div class="pip-info">
            <span class="pip-name">{{ pkg.name }}</span>
            <span class="pip-version">v{{ pkg.version }}</span>
          </div>
          <el-button type="danger" link size="small" @click="emit('uninstall', pkg.name)">
            <el-icon><Delete /></el-icon> 卸载
          </el-button>
        </div>
      </div>
      <el-empty v-else-if="!loading" description="点击刷新加载已安装的包" :image-size="80" />
      <div v-else class="pip-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>加载中...</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Download, Refresh, Delete, Loading } from '@element-plus/icons-vue'

defineProps({
  packages: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  installing: { type: Boolean, default: false },
  installName: { type: String, default: '' },
  result: { type: Object, default: () => ({ ok: false, msg: '' }) }
})

const emit = defineEmits(['update:installName', 'install', 'refresh', 'uninstall'])
</script>

<style scoped>
/* 依赖管理 */
.pip-container {
  padding: 20px;
}

.pip-header {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.pip-search {
  flex: 1;
}

.pip-actions {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

.pip-msg {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 14px;
}

.pip-msg .el-icon {
  font-size: 18px;
}

.pip-ok {
  background: var(--el-color-success-light-9);
  color: var(--el-color-success);
}

.pip-err {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}

.pip-list-container {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
}

.pip-list-header {
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  font-weight: 600;
  font-size: 14px;
  border-bottom: 1px solid var(--el-border-color-light);
}

.pip-list {
  max-height: 500px;
  overflow-y: auto;
}

.pip-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  transition: background 0.2s;
}

.pip-item:last-child {
  border-bottom: none;
}

.pip-item:hover {
  background: var(--el-fill-color-light);
}

.pip-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pip-name {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.pip-version {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.pip-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: var(--el-text-color-secondary);
}

.pip-loading .el-icon {
  font-size: 20px;
}
</style>
