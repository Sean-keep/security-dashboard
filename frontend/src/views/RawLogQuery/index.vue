<template>
  <div class="raw-log-page">
    <div class="page-header">
      <h2>原始日志查询</h2>
      <div class="header-right">
        <el-select v-model="timeRange" style="width:120px" size="default">
          <el-option label="今天" value="today" />
          <el-option label="最近1小时" value="1h" />
          <el-option label="最近6小时" value="6h" />
          <el-option label="最近24小时" value="24h" />
          <el-option label="最近7天" value="7d" />
          <el-option label="最近30天" value="30d" />
        </el-select>
      </div>
    </div>

    <el-card shadow="never" class="query-card">
      <div class="query-row">
        <!-- 左侧：语法输入 -->
        <div class="syntax-col">
          <el-input v-model="syntaxQuery" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
            placeholder="输入查询语法，如：server_name:example.com AND request_status:404"
            @focus="syntaxFocused = true" @blur="syntaxFocused = false"
            :class="{ 'syntax-manual': syntaxManual }" />
        </div>
        <!-- 右侧：条件选择 -->
        <div class="cond-col">
          <div class="cond-row" v-for="(cond, idx) in conditions" :key="idx">
            <el-select v-model="cond.field" placeholder="字段" style="width:120px" size="small" filterable clearable
              @change="onConditionChange">
              <el-option label="全部字段" value="_all" />
              <el-option v-for="f in fields" :key="f.field" :label="f.label" :value="f.field" />
            </el-select>
            <el-select v-model="cond.operator" style="width:80px" size="small" @change="onConditionChange">
              <el-option label="等于" value="equals" />
              <el-option label="不等于" value="not_equals" />
              <el-option label="包含" value="contains" />
              <el-option label="不包含" value="not_contains" />
              <el-option label="大于" value="gt" />
              <el-option label="大于等于" value="gte" />
              <el-option label="小于" value="lt" />
              <el-option label="小于等于" value="lte" />
              <el-option label="存在" value="exists" />
              <el-option label="不存在" value="not_exists" />
            </el-select>
            <el-input v-model="cond.value" placeholder="值" style="width:110px" size="small"
              v-if="!['exists','not_exists'].includes(cond.operator)" @input="onConditionChange" />
            <el-select v-model="cond.logic" style="width:50px" size="small" v-if="idx > 0" @change="onConditionChange">
              <el-option label="且" value="AND" />
              <el-option label="或" value="OR" />
            </el-select>
            <el-button type="danger" :icon="Delete" link size="small" @click="removeCondition(idx)" />
            <el-button size="small" @click="addCondition" v-if="idx === conditions.length - 1 && conditions.length < 5">+</el-button>
          </div>
        </div>
      </div>
      <!-- 操作栏 -->
      <div class="actions-row">
        <el-dropdown @command="loadPreset" trigger="click" v-if="presets.length">
          <el-button size="small">预设 <el-icon class="el-icon--right"><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="(p, i) in presets" :key="i" :command="i">
                {{ p.name }}
                <el-icon style="margin-left:8px" @click.stop="deletePreset(i)"><Delete /></el-icon>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="savePresetDialog">保存</el-button>
        <el-button size="small" @click="resetAll">重置</el-button>
        <el-button type="primary" size="small" @click="doQuery" :loading="loading">查询</el-button>
      </div>
    </el-card>

    <!-- 结果 -->
    <el-card shadow="never" style="margin-top:12px">
      <template #header>
        <div class="result-header">
          <span>共 <strong>{{ total }}</strong> 条记录</span>
          <span v-if="queryTime" class="query-time">耗时 {{ queryTime }}ms</span>
          <el-popover trigger="click" :width="300">
            <template #reference>
              <el-button size="small" link type="primary">选择列</el-button>
            </template>
            <div style="max-height:300px;overflow:auto">
              <el-checkbox v-model="colAllChecked" :indeterminate="colIndeterminate" @change="toggleAllCols" style="margin-bottom:8px">全选</el-checkbox>
              <el-divider style="margin:4px 0" />
              <el-checkbox v-model="col.visible" v-for="col in allColumns" :key="col.key" :label="col.label" @change="saveColPrefs" style="display:block;margin-bottom:4px" />
            </div>
          </el-popover>
        </div>
      </template>
      <el-table :data="tableData" stripe size="small" v-loading="loading" max-height="600"
        @row-click="showDetail" highlight-current-row style="cursor:pointer">
        <el-table-column type="index" width="50" label="#" />
        <el-table-column v-if="isColVisible('timestamp')" prop="@timestamp" label="时间" width="170" show-overflow-tooltip>
          <template #default="{ row }">{{ formatTime(row['@timestamp']) }}</template>
        </el-table-column>
        <el-table-column v-if="isColVisible('src_ip')" label="源IP" width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.src_ip || '-' }}</template>
        </el-table-column>
        <el-table-column v-if="isColVisible('server_name')" prop="server_name" label="域名" width="140" show-overflow-tooltip />
        <el-table-column v-if="isColVisible('request_method')" prop="request_method" label="方法" width="70" align="center" />
        <el-table-column v-if="isColVisible('request_url')" prop="request_url" label="请求URL" min-width="200" show-overflow-tooltip />
        <el-table-column v-if="isColVisible('request_status')" prop="request_status" label="状态码" width="70" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.request_status" :type="statusType(row.request_status)" size="small">{{ row.request_status }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('request_leng')" prop="request_leng" label="请求长度" width="80" align="right" />
        <el-table-column v-if="isColVisible('log_level')" prop="log_level" label="级别" width="60" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.log_level" :type="levelTag(row.log_level)" size="small">{{ row.log_level }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="isColVisible('error_msg')" prop="error_msg" label="错误信息" min-width="200" show-overflow-tooltip />
        <el-table-column v-if="isColVisible('request')" prop="request" label="完整请求" min-width="180" show-overflow-tooltip />
        <el-table-column v-if="isColVisible('pid')" prop="pid" label="PID" width="100" show-overflow-tooltip />
        <el-table-column v-if="isColVisible('log_time')" prop="log_time" label="日志时间" width="160" show-overflow-tooltip />
      </el-table>
      <div class="pagination-wrap">
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total"
          layout="total, sizes, prev, pager, next" :page-sizes="[20, 50, 100, 200]"
          @current-change="doQuery" @size-change="onPageSizeChange" />
      </div>
    </el-card>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" title="日志详情" width="750px" destroy-on-close>
      <div class="detail-kv" v-for="[k, v] in detailFields" :key="k">
        <span class="detail-key">{{ k }}</span>
        <span class="detail-val">{{ v }}</span>
      </div>
      <template #footer>
        <el-button @click="copyJson">复制 JSON</el-button>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 保存预设弹窗 -->
    <el-dialog v-model="presetDialogVisible" title="保存查询预设" width="400px" destroy-on-close>
      <el-input v-model="presetName" placeholder="预设名称" />
      <template #footer>
        <el-button @click="presetDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmSavePreset">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { Delete, ArrowDown } from '@element-plus/icons-vue'
import { rawLogs } from '@/api'
import { ElMessage } from 'element-plus'

const STORAGE_KEY = 'rawlog_presets'
const COL_PREFS_KEY = 'rawlog_col_prefs'

const fields = ref([])
const timeRange = ref('today')
const loading = ref(false)
const tableData = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
const queryTime = ref(null)

const conditions = reactive([
  { enabled: true, field: '', operator: 'equals', value: '', logic: 'AND' }
])

const syntaxQuery = ref('')
const syntaxManual = ref(false)
const syntaxFocused = ref(false)

const detailVisible = ref(false)
const detailData = ref({})
const detailFields = computed(() => {
  if (!detailData.value) return []
  const skip = new Set(['_stages', '_output_mapping'])
  return Object.entries(detailData.value).filter(([k]) => !skip.has(k) && !k.startsWith('_'))
})

const presets = ref([])
const presetDialogVisible = ref(false)
const presetName = ref('')

// ── 列选择 ──
const allColumns = reactive([
  { key: 'timestamp', label: '时间', visible: true },
  { key: 'src_ip', label: '源IP', visible: true },
  { key: 'server_name', label: '域名', visible: true },
  { key: 'request_method', label: '请求方法', visible: true },
  { key: 'request_url', label: '请求URL', visible: true },
  { key: 'request_status', label: '状态码', visible: true },
  { key: 'request_leng', label: '请求长度', visible: true },
  { key: 'log_level', label: '日志级别', visible: true },
  { key: 'error_msg', label: '错误信息', visible: true },
  { key: 'request', label: '完整请求', visible: false },
  { key: 'pid', label: 'PID', visible: false },
  { key: 'log_time', label: '日志时间', visible: false },
])

const isColVisible = (key) => allColumns.find(c => c.key === key)?.visible ?? false

const colAllChecked = computed(() => allColumns.every(c => c.visible))
const colIndeterminate = computed(() => allColumns.some(c => c.visible) && !colAllChecked.value)
const toggleAllCols = (val) => { allColumns.forEach(c => c.visible = val); saveColPrefs() }
const saveColPrefs = () => {
  const prefs = {}
  allColumns.forEach(c => prefs[c.key] = c.visible)
  localStorage.setItem(COL_PREFS_KEY, JSON.stringify(prefs))
}
const loadColPrefs = () => {
  try {
    const prefs = JSON.parse(localStorage.getItem(COL_PREFS_KEY) || '{}')
    allColumns.forEach(c => { if (c.key in prefs) c.visible = prefs[c.key] })
  } catch {}
}

// ── 方法/URL 解析 ──
const parseMethod = (req) => { if (!req) return '-'; return req.split(' ')[0] || '-' }
const parseUri = (req) => { if (!req) return '-'; const parts = req.split(' '); return parts[1] || parts[0] || '-' }
const levelTag = (level) => {
  if (!level) return 'info'
  const l = level.toLowerCase()
  if (l === 'error') return 'danger'
  if (l === 'warn') return 'warning'
  return 'info'
}
const statusType = (s) => { const c = parseInt(s); if (c >= 500) return 'danger'; if (c >= 400) return 'warning'; if (c >= 200 && c < 300) return 'success'; return 'info' }

// ── 条件 → 语法 自动生成 ──
const buildSyntax = () => {
  const active = conditions.filter(c => c.field && (['exists', 'not_exists'].includes(c.operator) || c.value))
  if (!active.length) { syntaxQuery.value = ''; return }
  const parts = active.map((c, i) => {
    let part = i > 0 ? ` ${c.logic} ` : ''
    if (c.field === '_all') return part + (c.operator.startsWith('not_') ? `NOT *${c.value}*` : `*${c.value}*`)
    if (c.operator === 'exists') return part + `_exists_:${c.field}`
    if (c.operator === 'not_exists') return part + `NOT _exists_:${c.field}`
    if (c.operator === 'equals') return part + `${c.field}:${c.value}`
    if (c.operator === 'not_equals') return part + `NOT ${c.field}:${c.value}`
    if (c.operator === 'contains') return part + `${c.field}:*${c.value}*`
    if (c.operator === 'not_contains') return part + `NOT ${c.field}:*${c.value}*`
    if (c.operator === 'gt') return part + `${c.field}:>${c.value}`
    if (c.operator === 'gte') return part + `${c.field}:>=${c.value}`
    if (c.operator === 'lt') return part + `${c.field}:<${c.value}`
    if (c.operator === 'lte') return part + `${c.field}:<=${c.value}`
    return part + `${c.field}:${c.value}`
  })
  syntaxQuery.value = parts.join('')
}
const onConditionChange = () => { if (!syntaxManual.value) buildSyntax() }
watch(syntaxQuery, () => { if (syntaxFocused.value) syntaxManual.value = true })

// ── 条件操作 ──
const addCondition = () => { if (conditions.length >= 5) return; conditions.push({ enabled: true, field: '', operator: 'equals', value: '', logic: 'AND' }) }
const removeCondition = (idx) => { conditions.splice(idx, 1); if (!syntaxManual.value) buildSyntax() }
const resetAll = () => {
  conditions.splice(0, conditions.length); conditions.push({ enabled: true, field: '', operator: 'equals', value: '', logic: 'AND' })
  syntaxQuery.value = ''; syntaxManual.value = false; tableData.value = []; total.value = 0; page.value = 1; queryTime.value = null
}

// ── 查询 ──
const doQuery = async () => {
  loading.value = true; queryTime.value = null; const start = Date.now()
  try {
    const useSyntax = syntaxManual.value && syntaxQuery.value.trim()
    const active = conditions.filter(c => c.field && (['exists', 'not_exists'].includes(c.operator) || c.value))
    if (!useSyntax && !active.length) { ElMessage.warning('请至少添加一个查询条件'); return }
    let payload
    if (useSyntax) {
      payload = { dsl: syntaxQuery.value.trim(), time_range: timeRange.value, page: page.value, page_size: pageSize.value }
    } else {
      payload = {
        conditions: active.map(c => ({ field: c.field === '_all' ? '_all' : c.field, operator: c.field === '_all' ? 'contains' : c.operator, value: c.value })),
        logic: active[0]?.logic || 'AND', time_range: timeRange.value, page: page.value, page_size: pageSize.value
      }
    }
    const res = await rawLogs.query(payload)
    tableData.value = res.data?.records || []; total.value = res.data?.total || 0; queryTime.value = Date.now() - start
  } catch (e) { ElMessage.error('查询失败: ' + (e.message || e)) } finally { loading.value = false }
}
const onPageSizeChange = (size) => { pageSize.value = size; page.value = 1; doQuery() }
const showDetail = (row) => { detailData.value = row; detailVisible.value = true }
const copyJson = () => { navigator.clipboard.writeText(JSON.stringify(detailData.value, null, 2)); ElMessage.success('已复制') }

// ── 预设 ──
const loadPresets = () => { try { presets.value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { presets.value = [] } }
const savePresetDialog = () => { presetName.value = ''; presetDialogVisible.value = true }
const confirmSavePreset = () => {
  if (!presetName.value.trim()) { ElMessage.warning('请输入名称'); return }
  presets.value.push({ name: presetName.value.trim(), conditions: JSON.parse(JSON.stringify(conditions)), syntax: syntaxQuery.value, syntaxManual: syntaxManual.value })
  localStorage.setItem(STORAGE_KEY, JSON.stringify(presets.value)); presetDialogVisible.value = false; ElMessage.success('已保存')
}
const loadPreset = (idx) => {
  const p = presets.value[idx]; if (!p) return
  conditions.splice(0, conditions.length); conditions.push(...(p.conditions || [{ enabled: true, field: '', operator: 'equals', value: '', logic: 'AND' }]))
  syntaxQuery.value = p.syntax || ''; syntaxManual.value = p.syntaxManual || false; if (!syntaxManual.value) buildSyntax()
}
const deletePreset = (idx) => { presets.value.splice(idx, 1); localStorage.setItem(STORAGE_KEY, JSON.stringify(presets.value)) }

// ── 工具 ──
const formatTime = (ts) => { if (!ts) return '-'; return ts.replace('T', ' ').replace(/\.\d+Z?$/, '') }

onMounted(async () => {
  try { const res = await rawLogs.fields(); fields.value = res.data || [] } catch {}
  loadPresets(); loadColPrefs()
})
</script>

<style scoped>
.raw-log-page { padding: 0; }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.page-header h2 { font-size: 18px; font-weight: 600; margin: 0; }

.query-card { }
.query-row { display: flex; gap: 12px; align-items: flex-start; }
.syntax-col { flex: 1; min-width: 0; }
.cond-col { flex: 2; min-width: 0; }
.cond-row { display: flex; align-items: center; gap: 4px; margin-bottom: 4px; }

.syntax-col :deep(.el-textarea__inner) {
  font-family: 'Courier New', monospace;
  font-size: 13px;
  resize: vertical;
}
.syntax-manual :deep(.el-textarea__inner) { color: #E6A23C; }

.actions-row { display: flex; justify-content: flex-end; gap: 6px; padding-top: 8px; border-top: 1px solid var(--el-border-color-lighter); margin-top: 8px; }

.result-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.query-time { font-size: 12px; color: #909399; }
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }

.detail-kv { display: flex; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
.detail-key { width: 160px; flex-shrink: 0; font-size: 12px; color: #909399; font-family: monospace; white-space: nowrap; }
.detail-val { flex: 1; font-size: 12px; color: #303133; word-break: break-all; font-family: monospace; }
</style>
