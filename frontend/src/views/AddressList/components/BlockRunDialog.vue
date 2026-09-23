<template>
  <el-dialog v-model="blockResultVisible" title="封禁执行结果" width="640px">
    <div v-loading="blockRunning">
      <div v-if="!blockResults.length && !blockRunning" class="empty-text">暂无结果</div>
      <div v-for="r in blockResults" :key="r.ip" class="block-result-item">
        <div class="block-result-head">
          <span class="ip-text">{{ r.ip }}</span>
          <el-tag :type="r.exit_code === 0 ? 'success' : 'danger'" size="small">{{ r.exit_code === 0 ? '成功' : '失败' }}</el-tag>
        </div>
        <pre v-if="r.stdout" class="block-result-out">{{ r.stdout }}</pre>
        <pre v-if="r.stderr" class="block-result-err">{{ r.stderr }}</pre>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { useAddresses } from '../composables/useAddresses'

const {
  blockResultVisible,
  blockRunning,
  blockResults
} = useAddresses()
</script>

<style lang="scss" scoped>
.ip-text { font-family: 'Courier New', monospace; color: var(--el-color-primary); }
.empty-text { color: var(--el-text-color-placeholder); }
.block-result-item { margin-bottom: 10px; border: 1px solid var(--el-border-color-light); border-radius: 4px; overflow: hidden; }
.block-result-head { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; background: var(--el-fill-color-light); }
.block-result-out { margin: 0; padding: 8px 12px; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 160px; overflow: auto; }
.block-result-err { margin: 0; padding: 8px 12px; font-size: 12px; color: var(--el-color-danger); white-space: pre-wrap; word-break: break-all; max-height: 160px; overflow: auto; }
</style>
