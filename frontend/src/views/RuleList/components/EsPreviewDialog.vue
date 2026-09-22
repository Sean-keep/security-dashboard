<template>
  <el-dialog
    :model-value="modelValue"
    title="ES查询预览"
    width="900px"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-if="loading" style="text-align:center;padding:40px">
      <el-icon class="is-loading" :size="32"><Loading /></el-icon>
      <p style="margin-top:12px;color:#888">查询中...</p>
    </div>
    <div v-else-if="data.length">
      <el-alert :title="`查询结果：${data.length} 条`" type="success" :closable="false" style="margin-bottom:12px" />
      <el-table :data="data" :max-height="400" stripe size="small">
        <el-table-column v-for="col in columns" :key="col" :prop="col" :label="col" min-width="120" show-overflow-tooltip />
      </el-table>
    </div>
    <el-empty v-else description="暂无数据" />
    <template #footer>
      <el-button type="primary" @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { Loading } from '@element-plus/icons-vue'

defineProps({
  modelValue: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  data: { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:modelValue'])
</script>
