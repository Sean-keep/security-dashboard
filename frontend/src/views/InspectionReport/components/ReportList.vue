<template>
  <el-card shadow="never" class="mb-16">
    <template #header>
      <div class="toolbar">
        <span class="card-title">历史巡检报告</span>
        <el-button size="small" :loading="refreshing" @click="emit('refresh')">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </template>

    <el-table :data="reportList" v-loading="refreshing" border stripe size="small">
      <el-table-column prop="id" label="ID" width="70" align="center" />
      <el-table-column prop="report_date" label="报告日期" width="140" />
      <el-table-column prop="generated_at" label="生成时间" width="180" />
      <el-table-column prop="address_count" label="攻击地址" width="110" align="right" />
      <el-table-column prop="script_count" label="脚本数" width="100" align="right" />
      <el-table-column prop="created_by" label="生成人" width="120" />
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button size="small" type="primary" plain @click="emit('preview', row)">预览</el-button>
          <el-button size="small" @click="emit('export', row, 'word')">Word</el-button>
          <el-button size="small" @click="emit('export', row, 'txt')">TXT</el-button>
          <el-button size="small" type="danger" plain @click="emit('remove', row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="reportTotal > 0"
      background
      layout="prev, pager, next, total"
      :total="reportTotal"
      :page-size="reportPageSize"
      :current-page="reportPage"
      @current-change="(p) => emit('page-change', p)"
      style="margin-top:16px;justify-content:center"
    />
  </el-card>
</template>

<script setup>
import { Refresh } from '@element-plus/icons-vue'

defineProps({
  reportList: { type: Array, default: () => [] },
  reportTotal: { type: Number, default: 0 },
  reportPage: { type: Number, default: 1 },
  reportPageSize: { type: Number, default: 10 },
  refreshing: { type: Boolean, default: false }
})

const emit = defineEmits(['refresh', 'page-change', 'preview', 'export', 'remove'])
</script>

<style scoped>
.mb-16 { margin-bottom: 16px; }
.toolbar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.card-title { font-weight: 600; font-size: 13px; }
</style>
