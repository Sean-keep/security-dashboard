<template>
  <el-card shadow="never">
    <template #header>
      <div class="table-toolbar">
        <span>共 <strong>{{ total }}</strong> 条记录</span>
        <div>
          <el-button size="small" plain @click="openBlockConfig">配置封堵参数</el-button>
          <el-button size="small" type="danger" plain :disabled="!multipleSelection.length" @click="blockSelected">批量封禁</el-button>
          <el-button size="small" plain :disabled="!multipleSelection.length" @click="batchLookupCountry">批量查询国家</el-button>

          <el-button size="small" plain @click="exportCsv">导出CSV</el-button>
          <el-button size="small" plain :disabled="!multipleSelection.length" @click="batchDelete">批量删除</el-button>
        </div>
      </div>
    </template>

    <el-table
      ref="tableRef"
      :data="tableData"
      stripe
      v-loading="loading"
      @selection-change="onSelectionChange"
      @sort-change="onSortChange"
    >
      <el-table-column type="selection" width="45" />
      <el-table-column prop="ip_address" label="攻击地址" min-width="150" sortable="custom">
        <template #default="{ row }">
          <span class="ip-text">{{ row.ip_address }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="country" label="国家" width="100">
        <template #default="{ row }">
          <span v-if="row.country" class="country-text">{{ row.country }}</span>
          <span v-else-if="countryLoadingMap[row.ip_address]" class="loading-text">查询中…</span>
          <span v-else class="empty-text">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="domain" label="攻击域名" min-width="150" show-overflow-tooltip />
      <el-table-column prop="start_time" label="首次攻击时间" width="170" sortable="custom" />
      <el-table-column prop="end_time" label="最近攻击时间" width="170" sortable="custom" />
      <el-table-column prop="duration" label="持续时间" width="110" align="center" sortable="custom">
        <template #default="{ row }">
          <span>{{ formatDuration(row.duration) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="attack_count" label="攻击次数" width="120" align="center" sortable="custom" />
      <el-table-column prop="severity" label="威胁等级" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="severityTag(row.severity)" size="small" effect="plain">
            {{ { critical: '严重', high: '高危', medium: '中危', low: '低危' }[row.severity] || row.severity }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="入库时间" width="170" sortable="custom" />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="blockOne(row)">封禁</el-button>
          <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
          <el-button type="danger" link size="small" @click="confirmDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.page_size"
        :total="total"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next"
        @size-change="loadData"
        @current-change="loadData"
      />
    </div>
  </el-card>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  tableData: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  pagination: { type: Object, required: true },
  multipleSelection: { type: Array, default: () => [] },
  countryLoadingMap: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false }
})

const emit = defineEmits([
  'selection-change',
  'sort-change',
  'block-one',
  'open-edit',
  'confirm-delete',
  'open-block-config',
  'block-selected',
  'batch-lookup-country',
  'export-csv',
  'batch-delete',
  'load'
])

const tableRef = ref()

const severityTag = (s) => ({ critical: 'danger', high: 'warning', medium: 'info', low: 'success' }[s] || 'info')

// 将秒数格式化为可读时间（xx天xx时xx分xx秒）
const formatDuration = (seconds) => {
  if (!seconds && seconds !== 0) return '-'
  if (seconds < 60) return seconds + '秒'
  if (seconds < 3600) return Math.floor(seconds / 60) + '分' + (seconds % 60 ? (seconds % 60) + '秒' : '')
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return h + '时' + (m ? m + '分' : '') + (s ? s + '秒' : '')
}

const onSelectionChange = (rows) => emit('selection-change', rows)
const onSortChange = (payload) => emit('sort-change', payload)
const blockOne = (row) => emit('block-one', row)
const openEdit = (row) => emit('open-edit', row)
const confirmDelete = (row) => emit('confirm-delete', row)
const openBlockConfig = () => emit('open-block-config')
const blockSelected = () => emit('block-selected')
const batchLookupCountry = () => emit('batch-lookup-country')
const exportCsv = () => emit('export-csv')
const batchDelete = () => emit('batch-delete')
const loadData = () => emit('load')
</script>

<style lang="scss" scoped>
.table-toolbar { display: flex; justify-content: space-between; align-items: center; span { font-size: 14px; color: var(--el-text-color-regular); } }
.ip-text { font-family: 'Courier New', monospace; color: var(--el-color-primary); }
.country-text { font-size: 13px; color: var(--el-text-color-regular); }
.loading-text { font-size: 12px; color: var(--el-text-color-secondary); }
.empty-text { color: var(--el-text-color-placeholder); }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }
</style>
