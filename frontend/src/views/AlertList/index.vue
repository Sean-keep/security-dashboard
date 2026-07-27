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
            <el-button size="small" type="danger" plain :disabled="!multipleSelection.length" @click="batchDeleteAlerts">批量删除</el-button>
            <el-button size="small" plain :disabled="!multipleSelection.length" @click="batchUpdate('confirmed')">批量确认</el-button>
            <el-button size="small" plain :disabled="!multipleSelection.length" @click="batchUpdate('resolved')">批量解决</el-button>
          </div>
        </div>
      </template>
      <el-table :data="tableData" stripe @selection-change="onSelectionChange" ref="tableRef">
        <el-table-column type="selection" width="40" />
        <el-table-column prop="title" label="告警标题" min-width="120" show-overflow-tooltip />
        <el-table-column prop="content" label="告警内容" min-width="250" show-overflow-tooltip />
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
        <el-table-column prop="created_at" label="时间" width="160" />
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
    <el-dialog v-model="detailVisible" title="告警详情" width="680px" destroy-on-close>
      <el-descriptions :column="2" border v-if="detailData.id">
        <el-descriptions-item label="严重等级">
          <el-tag :type="severityTag(detailData.severity)">{{ detailData.severity }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="处理状态">
          <el-tag :type="statusTag(detailData.status)">{{ statusLabel(detailData.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="来源IP">{{ detailData.src_ip || '-' }}</el-descriptions-item>
        <el-descriptions-item label="目标IP">{{ detailData.dst_ip || '-' }}</el-descriptions-item>
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
          <pre class="raw-log">{{ detailData.raw_log }}</pre>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { alerts } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

const tableData = ref([])
const total = ref(0)
const multipleSelection = ref([])
const detailVisible = ref(false)
const detailData = ref({})
const tableRef = ref()

const filterForm = reactive({ keyword: '', severity: '', status: '' })
const timePreset = ref('today')
const pagination = reactive({ page: 1, page_size: 20 })

const severityTag = (s) => ({ critical: 'danger', high: 'warning', medium: 'info', low: 'success' }[s] || 'info')
const statusTag = (s) => ({ pending: 'warning', confirmed: 'primary', resolved: 'success', false_positive: 'info' }[s] || 'info')
const statusLabel = (s) => ({ pending: '待处理', confirmed: '已确认', resolved: '已解决', false_positive: '误报' }[s] || s)

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
    // Filter out summary alerts and deduplicate by content
    const seen = new Set()
    tableData.value = (res.data.list || []).filter(row => {
      const content = row.content || row.title || ''
      // Skip summary alerts (created by scheduler, e.g. "规则「xxx」定时执行完成")
      if (content.startsWith('规则「')) return false
      // Deduplicate by rule_name + content
      const key = (row.rule_name || '') + '|' + content
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    total.value = res.data.total
  } catch (e) {}
}

const filterChange = () => { pagination.page = 1; loadData() }
const onTimePresetChange = () => { pagination.page = 1; loadData() }
const resetFilter = () => { Object.assign(filterForm, { keyword: '', severity: '', status: '' }); timePreset.value = 'today'; filterChange() }
const onSelectionChange = (rows) => { multipleSelection.value = rows }

const openDetail = async (row) => {
  try {
    const res = await alerts.get(row.id)
    detailData.value = res.data
    detailVisible.value = true
  } catch (e) {}
}

const quickConfirm = (row) => updateAlert(row.id, 'confirmed')
const quickResolve = (row) => updateAlert(row.id, 'resolved')
const markFalsePositive = (row) => updateAlert(row.id, 'false_positive')

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
  span { font-size:14px; color:#666; }
}
.toolbar-actions { display:flex; gap:8px; }
.alert-item { display:flex; flex-direction:column; gap:2px; }
.alert-title-row { display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
.rule-name { font-weight:700; font-size:13px; color:#303133; }
.alert-title-text { font-weight:600; font-size:13px; color:#409EFF; }
.alert-content-text { font-size:12px; color:#666; line-height:1.5; word-break:break-all; max-width:400px; }
.ip-text { font-family:'Courier New',monospace; color:#409EFF; }
.suggestion-text { font-size:12px; color:#666; }
.empty-text { color:#bbb; }
.raw-log {
  background:#f5f5f5; padding:10px; border-radius:6px;
  font-size:12px; max-height:200px; overflow:auto;
  white-space:pre-wrap; word-break:break-all; margin:0;
}
.pagination-wrap { display:flex; justify-content:flex-end; margin-top:16px; }
</style>
