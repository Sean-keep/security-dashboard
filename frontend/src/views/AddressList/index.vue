<template>
  <div class="address-list-page">
    <div class="page-header">
      <h2>攻击地址列表</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增地址</el-button>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-bar">
      <el-form :inline="true" :model="filterForm" size="default">
        <el-form-item label="关键词">
          <el-input v-model="filterForm.keyword" placeholder="IP/域名" clearable style="width:180px" @change="filterChange" />
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
          <span>共 <strong>{{ total }}</strong> 条记录</span>
          <div>
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
        <el-table-column prop="created_at" label="入库时间" width="170" sortable="custom" />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
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

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="600px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="formRules" label-width="100px">
        <el-form-item label="攻击地址" prop="ip_address">
          <el-input v-model="form.ip_address" placeholder="例：1.2.3.4" />
        </el-form-item>
        <el-form-item label="所属国家">
          <div style="display:flex;gap:8px;align-items:center">
            <el-input v-model="form.country" placeholder="手动修改或点击查询，如：中国、美国" style="flex:1" />
            <el-button size="small" @click="queryCountryForForm" :loading="countryQueryLoading" :disabled="!form.ip_address">查询归属</el-button>
          </div>
        </el-form-item>
        <el-form-item label="攻击域名">
          <el-input v-model="form.domain" placeholder="例：example.com" />
        </el-form-item>
        <el-form-item label="首次攻击时间">
          <el-date-picker v-model="form.start_time" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" />
        </el-form-item>
        <el-form-item label="最近攻击时间">
          <el-date-picker v-model="form.end_time" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" />
        </el-form-item>
        <el-form-item label="攻击次数">
          <el-input-number v-model="form.attack_count" :min="0" style="width:100%" />
        </el-form-item>
        <el-form-item label="持续时间(秒)">
          <el-input-number v-model="form.duration" :min="0" style="width:100%" />
        </el-form-item>
        <el-form-item label="严重等级">
          <el-select v-model="form.severity" style="width:100%">
            <el-option label="低危" value="low" />
            <el-option label="中危" value="medium" />
            <el-option label="高危" value="high" />
            <el-option label="严重" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width:100%">
            <el-option label="活跃" value="active" />
            <el-option label="已封禁" value="blocked" />
            <el-option label="白名单" value="whitelist" />
          </el-select>
        </el-form-item>
        <el-form-item label="来源">
          <el-input v-model="form.source" placeholder="来源说明" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="2" placeholder="备注信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saveLoading" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { addresses, inspectApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

// ── 模块级国家缓存（跨组件实例持久，避免重复查询 ipinfo.io） ──
const _countryCache = {}

const tableRef = ref()
const tableData = ref([])
const total = ref(0)
const multipleSelection = ref([])
const dialogVisible = ref(false)
const saveLoading = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const formRef = ref()

const filterForm = reactive({ keyword: '' })
const timePreset = ref('today')
const pagination = reactive({ page: 1, page_size: 20 })
const sortMeta = reactive({ sort_field: 'created_at', sort_order: 'desc' })
// 用普通对象记录正在查询的 IP（key=IP, val=true），替换而非修改，保证 Vue 响应式
const countryLoadingMap = reactive({})  // { '1.2.3.4': true }

const form = ref({
  ip_address: '', country: '', domain: '',
  start_time: '', end_time: '',
  attack_count: 0, duration: 0,
  severity: 'medium', status: 'active',
  source: '', remark: ''
})

const formRules = {
  ip_address: [{ required: true, message: '请输入攻击地址', trigger: 'blur' }]
}

const dialogTitle = computed(() => isEdit.value ? '编辑地址' : '新增地址')

const severityTag = (s) => ({ critical: 'danger', high: 'warning', medium: 'info', low: 'success' }[s] || 'info')
const statusTag = (s) => ({ active: 'danger', blocked: 'warning', whitelist: 'success' }[s] || 'info')
const statusLabel = (s) => ({ active: '活跃', blocked: '已封禁', whitelist: '白名单' }[s] || s)

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

// 根据预设计算 date_from / date_to（北京时间 YYYY-MM-DD HH:mm:ss）
const buildDateRange = () => {
  const now = new Date()
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
    const params = {
      keyword: filterForm.keyword,
      ...range,
      page: pagination.page,
      page_size: pagination.page_size,
      ...sortMeta
    }
    const res = await addresses.list(params)
    tableData.value = res.data.list
    total.value = res.data.total
  } catch (e) {}
}

// 通过 ipinfo.io 自动填充国家信息（带缓存）
const autoFillCountries = async () => {
  // 1. 先从缓存填充已有数据
  let changed = false
  tableData.value.forEach(row => {
    if (!row.country && _countryCache[row.ip_address]) {
      row.country = _countryCache[row.ip_address]
      changed = true
    }
  })

  // 2. 只查缓存中没有的 IP
  const needFetch = tableData.value.filter(r => !r.country && !countryLoadingMap[r.ip_address])
  if (!needFetch.length) return

  const ips = needFetch.map(r => r.ip_address)
  ips.forEach(ip => { countryLoadingMap[ip] = true })
  try {
    const res = await inspectApi.lookupCountry(ips)
    const map = res.data || {}
    // 更新行数据并写入缓存
    tableData.value.forEach(row => {
      if (!row.country && map[row.ip_address]) {
        row.country = map[row.ip_address]
        _countryCache[row.ip_address] = map[row.ip_address]
        changed = true
      }
    })
  } catch (e) {
    console.error('国家信息查询失败', e)
  } finally {
    ips.forEach(ip => { delete countryLoadingMap[ip] })
  }
}

const filterChange = () => { pagination.page = 1; loadData() }
const onTimePresetChange = () => { pagination.page = 1; loadData() }

const resetFilter = () => {
  Object.assign(filterForm, { keyword: '' })
  timePreset.value = 'today'
  filterChange()
}

const onSelectionChange = (rows) => { multipleSelection.value = rows }
const onSortChange = ({ prop, order }) => {
  sortMeta.sort_field = prop || 'created_at'
  sortMeta.sort_order = order === 'ascending' ? 'asc' : 'desc'
  loadData()
}

const openCreate = () => {
  isEdit.value = false; editId.value = null
  form.value = { ip_address:'', country:'', domain:'', start_time:'', end_time:'', attack_count:0, duration:0, severity:'medium', status:'active', source:'', remark:'' }
  dialogVisible.value = true
}
const openEdit = (row) => {
  isEdit.value = true; editId.value = row.id
  form.value = { ...row, start_time: row.start_time || '', end_time: row.end_time || '' }
  dialogVisible.value = true
}

// 手动查询单个 IP 的国家归属（编辑弹框内）
const countryQueryLoading = ref(false)
const queryCountryForForm = async () => {
  const ip = form.value.ip_address?.trim()
  if (!ip) return
  countryQueryLoading.value = true
  try {
    const res = await inspectApi.lookupCountry([ip])
    const country = res.data?.[ip]
    form.value.country = country || '未知'
    ElMessage.success(country ? `查询成功：${country}` : '未找到该 IP 的国家信息')
  } catch (e) { ElMessage.error('查询失败') }
  finally { countryQueryLoading.value = false }
}

const submitForm = async () => {
  try {
    await formRef.value.validate()
    saveLoading.value = true
    if (isEdit.value) {
      await addresses.update(editId.value, form.value)
      ElMessage.success('更新成功')
    } else {
      await addresses.create(form.value)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    loadData()
  } catch (e) {
    if (e && e.errors) throw e  // re-throw validation errors
    ElMessage.error('操作失败: ' + (e?.message || e?.response?.data?.msg || '未知错误'))
  } finally { saveLoading.value = false }
}

const confirmDelete = (row) => {
  ElMessageBox.confirm(`确定删除地址 ${row.ip_address}？`, '确认', { type: 'warning' })
    .then(async () => { await addresses.delete(row.id); ElMessage.success('删除成功'); loadData() })
    .catch(() => {})
}

const batchDelete = () => {
  const ids = multipleSelection.value.map(r => r.id)
  ElMessageBox.confirm(`确定删除选中的 ${ids.length} 条地址？`, '确认', { type: 'warning' })
    .then(async () => { await addresses.batchDelete(ids); ElMessage.success('批量删除成功'); loadData() })
    .catch(() => {})
}

// 批量查询选中地址的国家归属（仅更新无国家的记录）
const batchLookupCountry = async () => {
  const selected = multipleSelection.value
  const noCountry = selected.filter(r => !r.country)
  if (!noCountry.length) {
    ElMessage.info('选中的地址已有国家信息，无需查询')
    return
  }
  const ids = noCountry.map(r => r.id)
  ElMessageBox.confirm(`将为 ${ids.length} 条无国家归属的地址查询 IP 归属地，确定继续？`, '确认', { type: 'info' })
    .then(async () => {
      try {
        const res = await addresses.batchLookupCountry(ids)
        ElMessage.success(res.msg || `查询完成，已更新 ${res.data?.updated || 0} 条`)
        loadData()
      } catch (e) {
        ElMessage.error('批量查询失败：' + (e?.response?.data?.msg || e.message))
      }
    })
    .catch(() => {})
}


// ── 导出 CSV ──
const exportCsv = async () => {
  try {
    const params = buildDateRange()
    params.page = 1
    params.page_size = 100000  // 大范围导出
    if (filterForm.keyword) params.keyword = filterForm.keyword
    if (filterForm.severity) params.severity = filterForm.severity
    if (filterForm.sort_field) params.sort_field = filterForm.sort_field
    if (filterForm.sort_order) params.sort_order = filterForm.sort_order

    const res = await addresses.exportCsv(params)
    // 创建下载链接
    const blob = new Blob([res], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `addresses_${new Date().toISOString().slice(0,10)}.csv`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败：' + (e.message || '未知错误'))
  }
}

onMounted(loadData)
</script>

<style lang="scss" scoped>
.address-list-page { }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; h2 { margin: 0; font-size: 18px; } }
.filter-bar { margin-bottom: 16px; }
.table-toolbar { display: flex; justify-content: space-between; align-items: center; span { font-size: 14px; color: #666; } }
.ip-text { font-family: 'Courier New', monospace; color: #409EFF; }
.country-text { font-size: 13px; color: #606266; }
.loading-text { font-size: 12px; color: #a0a0a0; }
.empty-text { color: #bbb; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }
</style>
