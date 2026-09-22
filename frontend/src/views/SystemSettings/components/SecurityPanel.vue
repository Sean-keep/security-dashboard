<template>
  <!-- ══ 安全设置 ══ -->
  <el-card shadow="never" class="mb-16">
    <template #header>
      <div class="card-header">
        <span class="card-title">登录安全策略</span>
      </div>
    </template>
    <el-form :model="securityForm" label-width="140px" size="default" style="max-width:560px">
      <el-form-item label="登录最大尝试次数">
        <el-input-number v-model="securityForm.login_max_attempts" :min="1" :max="20" />
        <span class="form-hint">连续失败超过此次数后，账户被临时锁定</span>
      </el-form-item>
      <el-form-item label="登录锁定时长">
        <el-input-number v-model="securityForm.login_lockout_minutes" :min="1" :max="1440" />
        <span class="form-hint">锁定后等待多少分钟自动解除（分钟）</span>
      </el-form-item>
    </el-form>
    <div class="card-footer">
      <el-button type="primary" size="small" :loading="securitySaving" @click="saveSecurity">保存策略</el-button>
      <span v-if="securitySaved" class="test-msg ok">保存成功</span>
    </div>
  </el-card>
</template>

<script setup>
import { useSystemSettings } from '../composables/useSystemSettings'

const {
  securityForm,
  securitySaving,
  securitySaved,
  saveSecurity
} = useSystemSettings()
</script>

<style lang="scss" scoped>
.mb-16 { margin-bottom: 16px; }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.test-msg {
  font-size: 13px;
  margin-left: 4px;
  &.ok { color: #67c23a; }
  &.fail { color: #f56c6c; }
}

.form-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}
</style>
