<template>
  <div class="alert-list-page">
    <div class="page-header">
      <h2>告警列表</h2>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-bar">
      <el-form :inline="true" :model="filterForm" size="default">
        <el-form-item label="关键词">
          <el-input v-model="filterForm.keyword" placeholder="标题/IP/内容" clearable style="width:160px" @change="filterChange" />
        </el-form-item>
        <el-form-item label="严重等级">
          <el-select v-model="filterForm.severity" placeholder="全部" clearable style="width:130px" @change="filterChange">
            <el-option label="严重" value="critical" />
            <el-option label="高危" value="high" />
            <el-option label="中危" value="medium" />
            <el-option label="低危" value="low" />
          </el-select>
        </el-form-item>
        <el-form-item label="处理状态">
          <el-select v-model="filterForm.status" placeholder="全部" clearable style="width:130px" @change="filterChange">
            <el-option label="待处理" value="pending" />
            <el-option label="已确认" value="confirmed" />
            <el-option label="已解决" value="resolved" />
            <el-option label="误报" value="false_positive" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-select v-model="timePreset" size="default" style="width:145px" @change="onTimePresetChange">
            <el-option label="最近 1 小时" value="1h" />
            <el-option label="最近 6 小时" value="6h" />
            <el-option label="今日" value="today" />
            <el-option label="最近 1 天" value="1d" />
            <el-option label="最近 7 天" value="7d" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="filterChange">筛选</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 表格 -->
    <el-card shadow="never">
      <template #header>
        <div class="table-toolbar">
          <span>共 <strong>{{ total }}</strong> 条告警</span>
          <div class="toolbar-actions">
            <el-button size="small" plain :loading="exporting" @click="exportCsv">导出CSV</el-button>
            <el-button size="small" type="danger" plain :disabled="!multipleSelection.length" @click="batchDeleteAlerts">批量删除</el-button>
            <el-button size="small" plain :disabled="!multipleSelection.length" @click="batchUpdate('confirmed')">批量确认</el-button>
            <el-button size="small" plain :disabled="!multipleSelection.length" @click="batchUpdate('resolved')">批量解决</el-button>
          </div>
        </div>
      </template>
      <el-table :data="tableData" stripe @selection-change="onSelectionChange" ref="tableRef">
        <el-table-column type="selection" width="40" />
        <el-table-column label="告警标题 / 内容" min-width="560">
          <template #default="{ row }">
            <div class="alert-title-row">
              <span class="alert-title-text">{{ row.title }}</span>
            </div>
            <div class="alert-content-text" :title="row.content">{{ row.content }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="级别" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="severityTag(row.severity)" size="small">{{ row.severity }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="handle_suggestion" label="处理建议" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.handle_suggestion" class="suggestion-text">{{ row.handle_suggestion }}</span>
            <el-button type="primary" link size="small" @click.stop="openSuggestionDialog(row)">填写</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openDetail(row)">详情</el-button>
            <el-button type="success" link size="small" @click="quickConfirm(row)">确认</el-button>
            <el-button type="warning" link size="small" @click="quickResolve(row)">解决</el-button>
            <el-button type="danger" link size="small" @click="deleteAlert(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="pagination.page"
          :page-size="pagination.page_size"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadData"
        />
      </div>
    </el-card>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="告警详情" width="800px" destroy-on-close>
      <el-descriptions :column="2" border v-if="detailData.id" :label-style="{ width: '110px', whiteSpace: 'nowrap', wordBreak: 'keep-all' }" :content-style="{ minWidth: '150px' }">
        <el-descriptions-item label="严重等级">
          <el-tag :type="severityTag(detailData.severity)">{{ detailData.severity }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="处理状态">
          <el-tag :type="statusTag(detailData.status)">{{ statusLabel(detailData.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="来源IP">{{ detailData.src_ip || '-' }}</el-descriptions-item>
        <el-descriptions-item label="目的域名">{{ detailDomain }}</el-descriptions-item>
        <el-descriptions-item label="触发规则">{{ detailData.rule_name || '-' }}</el-descriptions-item>
        <el-descriptions-item label="产生时间">{{ detailData.created_at }}</el-descriptions-item>
        <el-descriptions-item label="确认时间">{{ detailData.confirmed_at || '-' }}</el-descriptions-item>
        <el-descriptions-item label="解决时间">{{ detailData.resolved_at || '-' }}</el-descriptions-item>
        <el-descriptions-item label="告警内容" :span="2">{{ detailData.content }}</el-descriptions-item>
        <el-descriptions-item label="处理建议" :span="2">
          <el-input
            v-model="detailData.handle_suggestion"
            type="textarea"
            :rows="2"
            placeholder="请填写处理建议或处理结果"
            style="max-width:500px"
            @blur="saveSuggestion(detailData)"
          />
        </el-descriptions-item>
        <el-descriptions-item label="原始日志" :span="2">
          <div style="max-width:100%;overflow:hidden;">
            <pre class="raw-log">{{ detailData.raw_log }}</pre>
          </div>
        </el-descriptions-item>
      </el-descriptions>

      <div v-if="detailData.raw_logs" style="margin-top:16px">
        <el-collapse v-model="collapseActive">
          <el-collapse-item name="es_logs">
            <template #title>
              <span style="font-weight:600">ES原始日志 ({{ parsedRawLogs.length }}条)</span>
            </template>
            <div class="raw-logs-container">
              <div v-for="(log, idx) in parsedRawLogs" :key="idx" class="raw-log-entry">
                <div class="raw-log-header">
                  <span class="raw-log-time">{{ log['@timestamp'] || '-' }}</span>
                  <el-tag size="small" type="info">{{ log.request_status || '-' }}</el-tag>
                  <span class="raw-log-ip">{{ log.src_ip || log.remote_addr || '-' }}</span>
                </div>
                <div class="raw-log-detail">
                  <span style="overflow:hidden;text-overflow:ellipsis;max-width:100%;">{{ log.request_method || 'GET' }} {{ log.request_uri || '/' }}</span>
                  <span v-if="log.server_name" class="raw-log-domain">{{ log.server_name }}</span>
                  <span v-if="log.bytes" class="raw-log-bytes">{{ log.bytes }}B</span>
                </div>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { alerts } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const tableData = ref([])
const total = ref(0)
const multipleSelection = ref([])
const detailVisible = ref(false)
const detailData = ref({})
const collapseActive = ref([]) // 默认折叠

// 从 raw_log 提取目的域名
const detailDomain = computed(() => {
  if (!detailData.value.raw_log) return '-'
  try {
    const raw = JSON.parse(detailData.value.raw_log)
    return raw.server_name || raw.domain || raw['攻击域名'] || '-'
  } catch { return '-' }
})
const tableRef = ref()

const filterForm = reactive({ keyword: '', severity: '', status: '' })
const timePreset = ref('today')
const pagination = reactive({ page: 1, page_size: 20 })

const severityTag = (s) => ({ critical: 'danger', high: 'warning', medium: 'info', low: 'success' }[s] || 'info')
const statusTag = (s) => ({ pending: 'warning', confirmed: 'primary', resolved: 'success', false_positive: 'info' }[s] || 'info')
const statusLabel = (s) => ({ pending: '待处理', confirmed: '已确认', resolved: '已解决', false_positive: '误报' }[s] || s)

// 解析ES原始日志JSON
const parsedRawLogs = computed(() => {
  if (!detailData.value.raw_logs) return []
  try {
    const logs = JSON.parse(detailData.value.raw_logs)
    return Array.isArray(logs) ? logs : []
  } catch {
    return []
  }
})

// 根据预设计算 date_from / date_to（ISO 时间戳）
const buildDateRange = () => {
  const now = new Date()
  // 统一转为北京时间（CST, UTC+8）后再格式化，避免 UTC/本地时区混乱
  const toCST = (d) => {
    const cst = new Date(d.getTime() + 8 * 3600 * 1000)
    return cst.toISOString().slice(0, 19).replace('T', ' ')
  }
  const fmtCSTDate = (d) => {
    const cst = new Date(d.getTime() + 8 * 3600 * 1000)
    return cst.toISOString().slice(0, 10)
  }
  switch (timePreset.value) {
    case '1h': {
      const t = new Date(now.getTime() - 1 * 3600 * 1000)
      return { date_from: toCST(t), date_to: toCST(now) }
    }
    case '6h': {
      const t = new Date(now.getTime() - 6 * 3600 * 1000)
      return { date_from: toCST(t), date_to: toCST(now) }
    }
    case 'today': return { date_from: fmtCSTDate(now) + ' 00:00:00', date_to: toCST(now) }
    case '1d': {
      const t = new Date(now.getTime() - 24 * 3600 * 1000)
      return { date_from: toCST(t), date_to: toCST(now) }
    }
    case '7d': {
      const t = new Date(now.getTime() - 7 * 24 * 3600 * 1000)
      return { date_from: toCST(t), date_to: toCST(now) }
    }
    default: return { date_from: fmtCSTDate(now) + ' 00:00:00', date_to: toCST(now) }
  }
}

const loadData = async () => {
  try {
    const range = buildDateRange()
    const res = await alerts.list({
      keyword: filterForm.keyword,
      severity: filterForm.severity,
      status: filterForm.status,
      ...range,
      page: pagination.page,
      page_size: pagination.page_size
    })
    tableData.value = res.data.list || []
    total.value = res.data.total
  } catch (e) {}
}

const filterChange = () => { pagination.page = 1; loadData() }
const onTimePresetChange = () => { pagination.page = 1; loadData() }
const resetFilter = () => { Object.assign(filterForm, { keyword: '', severity: '', status: '' }); timePreset.value = 'today'; filterChange() }
const onSelectionChange = (rows) => { multipleSelection.value = rows }

// ── 导出 CSV（按当前筛选条件导出全部命中，不是当前页）──
const exporting = ref(false)
const exportCsv = async () => {
  exporting.value = true
  try {
    const params = { ...buildDateRange() }
    if (filterForm.keyword) params.keyword = filterForm.keyword
    if (filterForm.severity) params.severity = filterForm.severity
    if (filterForm.status) params.status = filterForm.status

    const res = await alerts.exportCsv(params)
    const blob = new Blob([res], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `alerts_${new Date().toISOString().slice(0, 10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || '未知错误'))
  } finally {
    exporting.value = false
  }
}

const openDetail = async (row) => {
  try {
    const res = await alerts.get(row.id)
    detailData.value = res.data
    detailVisible.value = true
  } catch (e) {}
}

const quickConfirm = (row) => updateAlert(row.id, 'confirmed')
const quickResolve = (row) => updateAlert(row.id, 'resolved')

// 表格列快捷填写处理建议
const openSuggestionDialog = async (row) => {
  if (!detailData.value.id || detailData.value.id !== row.id) {
    const res = await alerts.get(row.id)
    detailData.value = res.data
  }
  detailVisible.value = true
}

// 详情弹窗填写处理建议（失焦保存）
const saveSuggestion = async (row) => {
  try {
    await alerts.update(row.id, { handle_suggestion: row.handle_suggestion || '' })
    loadData()
  } catch (e) {}
}

const updateAlert = async (id, status) => {
  try {
    await alerts.update(id, { status })
    ElMessage.success(`已标记为「${statusLabel(status)}」`)
    loadData()
  } catch (e) {}
}

const batchUpdate = (status) => {
  const ids = multipleSelection.value.map(r => r.id)
  ElMessageBox.confirm(`确定将选中的 ${ids.length} 条告警标记为「${statusLabel(status)}」？`, '确认', { type: 'info' })
    .then(async () => {
      await alerts.batchUpdate(ids, status)
      ElMessage.success('批量更新成功')
      loadData()
    }).catch(() => {})
}

const deleteAlert = (row) => {
  ElMessageBox.confirm(`确定删除此告警？`, '确认删除', { type: 'warning' })
    .then(async () => {
      await alerts.delete(row.id)
      ElMessage.success('删除成功')
      loadData()
    }).catch(() => {})
}

const batchDeleteAlerts = () => {
  const ids = multipleSelection.value.map(r => r.id)
  ElMessageBox.confirm(`确定删除选中的 ${ids.length} 条告警？此操作不可恢复。`, '确认删除', { type: 'warning', confirmButtonClass: 'el-button--danger' })
    .then(async () => {
      await alerts.batchDelete(ids)
      ElMessage.success('批量删除成功')
      loadData()
    }).catch(() => {})
}

import { onMounted } from 'vue'
onMounted(loadData)
</script>

<style lang="scss" scoped>
.alert-list-page { }
.page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; h2 { margin:0; font-size:18px; } }
.filter-bar { margin-bottom: 16px; }
.table-toolbar {
  display:flex; justify-content:space-between; align-items:center;
  span { font-size:14px; color:var(--el-text-color-regular); }
}
.toolbar-actions { display:flex; gap:8px; }
.alert-item { display:flex; flex-direction:column; gap:2px; }
.alert-title-row { display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
.rule-name { font-weight:700; font-size:13px; color:var(--el-text-color-primary); }
.alert-title-text { font-weight:600; font-size:13px; color:var(--el-color-primary); }
.alert-content-text { font-size:12px; color:var(--el-text-color-regular); line-height:1.5; word-break:break-all; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:520px; }
.ip-text { font-family:'Courier New',monospace; color:var(--el-color-primary); }
.suggestion-text { font-size:12px; color:var(--el-text-color-regular); }
.empty-text { color:var(--el-text-color-placeholder); }
.raw-log {
  background:var(--el-fill-color-light); padding:10px; border-radius:6px;
  font-size:12px; max-height:200px; overflow:auto;
  white-space:pre-wrap; word-break:break-all; margin:0;
  max-width:100%; box-sizing:border-box;
  overflow-x:auto; display:block; width:100%;
}
.raw-logs-container { max-height:400px; overflow:auto; }
.raw-log-entry { padding:8px; margin-bottom:6px; background:var(--el-fill-color-light); border-radius:4px; border-left:3px solid var(--el-color-primary); }
.raw-log-header { display:flex; align-items:center; gap:8px; margin-bottom:4px; }
.raw-log-time { font-size:11px; color:var(--el-text-color-secondary); font-family:monospace; }
.raw-log-ip { font-size:12px; color:var(--el-color-primary); font-family:monospace; }
.raw-log-detail { font-size:12px; color:var(--el-text-color-regular); display:flex; gap:12px; flex-wrap:wrap; overflow:hidden; max-width:100%; }
.raw-log-domain { color:var(--el-color-warning); }
.raw-log-bytes { color:var(--el-color-success); }
.pagination-wrap { display:flex; justify-content:flex-end; margin-top:16px; }

</style>

<style>
.el-dialog .el-descriptions__label {
  width: 110px !important;
  min-width: 110px !important;
  white-space: nowrap !important;
  word-break: keep-all !important;
}
.el-dialog .el-descriptions__content {
  overflow: hidden !important;
  max-width: 100% !important;
  word-break: break-all !important;
}
.el-dialog .el-descriptions__cell {
  overflow: hidden !important;
  max-width: 0 !important;
}
.el-dialog {
  max-width: 90vw !important;
}
.el-dialog__body {
  overflow: auto !important;
  max-width: 100% !important;
}
</style>
