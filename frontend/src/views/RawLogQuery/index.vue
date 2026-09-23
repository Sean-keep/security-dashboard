<template>
  <div class="raw-log-page">
    <div class="page-header">
      <h2>原始日志查询</h2>
    </div>

    <!-- 查询栏：Kibana Discover 的核心交互 —— 一条查询栏 + 时间选择器 -->
    <div class="discover-bar">
      <div class="query-input-wrap">
        <el-icon class="query-icon"><Search /></el-icon>
        <input
          v-model="queryText"
          class="query-input"
          type="text"
          spellcheck="false"
          placeholder="输入查询语法，如：server_name:example.com AND request_status:404   （留空查全部）"
          @keydown.enter.prevent="doQuery"
        />
        <el-icon v-if="queryText" class="query-clear" @click="queryText = ''"><Close /></el-icon>
      </div>
      <el-dropdown trigger="click" @command="onTimeChange">
        <button class="time-picker-btn" type="button">
          <el-icon><Clock /></el-icon>
          <span>{{ timeRangeLabel }}</span>
          <el-icon class="caret"><ArrowDown /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="opt in TIME_OPTIONS"
              :key="opt.value"
              :command="opt.value"
              :class="{ 'is-active': opt.value === timeRange }"
            >
              {{ opt.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button type="primary" :loading="loading" @click="doQuery">查询</el-button>
    </div>

    <!-- 筛选胶囊 + 操作行 -->
    <div class="filter-row">
      <div class="pills">
        <el-tag
          v-for="(f, idx) in filters"
          :key="idx"
          class="filter-pill"
          :class="{ negated: f.negated }"
          closable
          @close="removeFilter(idx)"
          @click="editFilter(idx)"
        >
          <span class="pill-negate" @click.stop="toggleNegate(idx)">{{ f.negated ? '−' : '+' }}</span>
          <span class="pill-field">{{ fieldLabel(f.field) }}</span>
          <span class="pill-op">{{ opLabel(f) }}</span>
          <span class="pill-value" v-if="!['exists', 'not_exists'].includes(f.operator)">{{ f.value }}</span>
        </el-tag>
        <el-button size="small" plain class="add-filter-btn" @click="openAddFilter">
          <el-icon><Plus /></el-icon> 添加筛选
        </el-button>
      </div>
      <div class="filter-actions">
        <el-dropdown trigger="click" @command="loadPreset" v-if="presets.length">
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
      </div>
    </div>

    <!-- 结果 -->
    <el-card shadow="never" class="result-card">
      <template #header>
        <div class="result-header">
          <div class="hits">
            <strong>{{ total.toLocaleString() }}</strong>
            <span class="hits-label">条命中</span>
            <span v-if="took !== null" class="took">耗时 {{ took }}ms</span>
          </div>
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
        <el-table-column v-if="isColVisible('timestamp')" prop="@timestamp" label="时间" width="180" show-overflow-tooltip>
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
        <el-table-column v-if="isColVisible('log_time')" prop="log_time" label="日志时间" width="180" show-overflow-tooltip />
      </el-table>

      <el-empty v-if="!loading && !tableData.length" description="无匹配日志" :image-size="80" />

      <div class="pagination-wrap" v-if="total > 0">
        <el-pagination v-model:current-page="page" :page-size="pageSize" :total="total"
          layout="total, sizes, prev, pager, next" :page-sizes="[20, 50, 100, 200]"
          @current-change="doQuery" @size-change="onPageSizeChange" />
      </div>
    </el-card>

    <!-- 添加/编辑筛选 -->
    <el-dialog v-model="filterDialogVisible" :title="editingFilterIdx === null ? '添加筛选' : '编辑筛选'" width="480px" destroy-on-close>
      <el-form label-width="70px">
        <el-form-item label="字段">
          <el-select v-model="filterDraft.field" placeholder="选择字段" filterable style="width:100%">
            <el-option label="全部字段" value="_all" />
            <el-option v-for="f in fields" :key="f.field" :label="`${f.label}（${f.field}）`" :value="f.field" />
          </el-select>
        </el-form-item>
        <el-form-item label="运算符">
          <el-select v-model="filterDraft.operator" style="width:100%">
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
        </el-form-item>
        <el-form-item label="值" v-if="!['exists', 'not_exists'].includes(filterDraft.operator)">
          <el-input v-model="filterDraft.value" placeholder="输入值，回车确认" @keydown.enter.prevent="confirmFilter" />
        </el-form-item>
        <el-form-item label="取反">
          <el-switch v-model="filterDraft.negated" active-text="排除该条件" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="filterDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmFilter">确定</el-button>
      </template>
    </el-dialog>

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
      <el-input v-model="presetName" placeholder="预设名称" @keydown.enter.prevent="confirmSavePreset" />
      <template #footer>
        <el-button @click="presetDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmSavePreset">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Delete, ArrowDown, Plus, Search, Close, Clock } from '@element-plus/icons-vue'
import { rawLogs } from '@/api'
import { ElMessage } from 'element-plus'

const STORAGE_KEY = 'rawlog_presets'
const COL_PREFS_KEY = 'rawlog_col_prefs'

const TIME_OPTIONS = [
  { label: '今天', value: 'today' },
  { label: '最近 1 小时', value: '1h' },
  { label: '最近 6 小时', value: '6h' },
  { label: '最近 24 小时', value: '24h' },
  { label: '最近 7 天', value: '7d' },
  { label: '最近 30 天', value: '30d' }
]

const fields = ref([])
const timeRange = ref('24h')
const loading = ref(false)
const tableData = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(50)
// ES 返回的 took（服务端耗时）。拿不到就显示 null，不再用前端计时冒充。
const took = ref(null)

// 查询栏文本（Lucene）。查询栏是唯一真相源，始终以 dsl 提交。
const queryText = ref('')
// 筛选胶囊。与查询栏合并成一条 Lucene —— 后端的 dsl 通道支持 AND/OR/NOT/括号，
// 而 conditions 通道只有一个全局 AND/OR 开关，表达不了混合逻辑。
const filters = ref([])

const timeRangeLabel = computed(() => TIME_OPTIONS.find(o => o.value === timeRange.value)?.label || timeRange.value)

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

// 筛选弹窗
const filterDialogVisible = ref(false)
const editingFilterIdx = ref(null)
const filterDraft = reactive({ field: '', operator: 'equals', value: '', negated: false })

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

// ── 展示辅助 ──
const levelTag = (level) => {
  if (!level) return 'info'
  const l = level.toLowerCase()
  if (l === 'error') return 'danger'
  if (l === 'warn') return 'warning'
  return 'info'
}
const statusType = (s) => { const c = parseInt(s); if (c >= 500) return 'danger'; if (c >= 400) return 'warning'; if (c >= 200 && c < 300) return 'success'; return 'info' }
const formatTime = (ts) => { if (!ts) return '-'; return ts.replace('T', ' ').replace(/\.\d+Z?$/, '') }

const fieldLabel = (f) => fields.value.find(x => x.field === f)?.label || f
const opLabel = (f) => {
  if (f.operator === 'exists') return '存在'
  if (f.operator === 'not_exists') return '不存在'
  return { equals: '=', not_equals: '≠', contains: '包含', not_contains: '不包含',
           gt: '>', gte: '≥', lt: '<', lte: '≤' }[f.operator] || f.operator
}

// ── 筛选 → Lucene ──
// Lucene 保留字符需要加引号，否则值里的空格/冒号会把查询语义打散。
const needsQuote = (v) => /[\s:(){}[\]^"~*?\\/!+-]|\bAND\b|\bOR\b|\bNOT\b/.test(v)
const quoteVal = (v) => {
  const s = String(v ?? '')
  return needsQuote(s) ? `"${s.replace(/"/g, '\\"')}"` : s
}

const filterToLucene = (f) => {
  const val = quoteVal(f.value)
  let clause
  if (f.field === '_all') {
    if (!val || val === '""') return ''
    clause = f.operator.startsWith('not_') ? `NOT ${val}` : val
  } else if (f.operator === 'exists') {
    clause = `_exists_:${f.field}`
  } else if (f.operator === 'not_exists') {
    clause = `NOT _exists_:${f.field}`
  } else if (f.operator === 'equals') {
    clause = `${f.field}:${val}`
  } else if (f.operator === 'not_equals') {
    clause = `NOT ${f.field}:${val}`
  } else if (f.operator === 'contains') {
    clause = `${f.field}:*${val}*`
  } else if (f.operator === 'not_contains') {
    clause = `NOT ${f.field}:*${val}*`
  } else if (['gt', 'gte', 'lt', 'lte'].includes(f.operator)) {
    const sym = { gt: '>', gte: '>=', lt: '<', lte: '<=' }[f.operator]
    clause = `${f.field}:${sym}${val}`
  } else {
    clause = `${f.field}:${val}`
  }
  // 胶囊上的 − 号：把整条子句包起来取反
  return f.negated ? `NOT (${clause})` : clause
}

// 查询栏文本 + 胶囊 → 一条 dsl。胶囊之间固定 AND（要 OR 就写在查询栏里，和 Kibana 一致）。
const buildDsl = () => {
  const bar = queryText.value.trim()
  const clauses = filters.value
    .filter(f => f.field && (['exists', 'not_exists'].includes(f.operator) || (f.value !== '' && f.value != null)))
    .map(filterToLucene)
    .filter(Boolean)

  if (!bar && !clauses.length) return '*:*'
  if (!bar) return clauses.join(' AND ')
  if (!clauses.length) return bar
  return `(${bar}) AND ${clauses.join(' AND ')}`
}

const onTimeChange = (v) => { timeRange.value = v; page.value = 1; doQuery() }

// ── 筛选胶囊操作 ──
const openAddFilter = () => {
  editingFilterIdx.value = null
  Object.assign(filterDraft, { field: '', operator: 'equals', value: '', negated: false })
  filterDialogVisible.value = true
}
const editFilter = (idx) => {
  editingFilterIdx.value = idx
  Object.assign(filterDraft, filters.value[idx])
  filterDialogVisible.value = true
}
const confirmFilter = () => {
  if (!filterDraft.field) { ElMessage.warning('请选择字段'); return }
  if (!['exists', 'not_exists'].includes(filterDraft.operator) && (filterDraft.value === '' || filterDraft.value == null)) {
    ElMessage.warning('请输入值'); return
  }
  const item = { field: filterDraft.field, operator: filterDraft.operator, value: filterDraft.value, negated: filterDraft.negated }
  if (editingFilterIdx.value === null) filters.value.push(item)
  else filters.value[editingFilterIdx.value] = item
  filterDialogVisible.value = false
  page.value = 1
  doQuery()
}
const removeFilter = (idx) => { filters.value.splice(idx, 1); page.value = 1; doQuery() }
const toggleNegate = (idx) => { filters.value[idx].negated = !filters.value[idx].negated; page.value = 1; doQuery() }

const resetAll = () => {
  filters.value = []
  queryText.value = ''
  tableData.value = []
  total.value = 0
  page.value = 1
  took.value = null
}

// ── 查询 ──
// 始终走 dsl 通道：它能表达混合 AND/OR/NOT，而 conditions 通道只有一个全局开关。
const doQuery = async () => {
  loading.value = true
  took.value = null
  try {
    const res = await rawLogs.query({
      dsl: buildDsl(),
      time_range: timeRange.value,
      page: page.value,
      page_size: pageSize.value
    })
    tableData.value = res.data?.records || []
    total.value = res.data?.total || 0
    took.value = res.data?.took ?? null
  } catch (e) {
    ElMessage.error('查询失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}
const onPageSizeChange = (size) => { pageSize.value = size; page.value = 1; doQuery() }
const showDetail = (row) => { detailData.value = row; detailVisible.value = true }
const copyJson = () => { navigator.clipboard.writeText(JSON.stringify(detailData.value, null, 2)); ElMessage.success('已复制') }

// ── 预设 ──
const loadPresets = () => { try { presets.value = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { presets.value = [] } }
const savePresetDialog = () => { presetName.value = ''; presetDialogVisible.value = true }
const confirmSavePreset = () => {
  if (!presetName.value.trim()) { ElMessage.warning('请输入名称'); return }
  presets.value.push({
    name: presetName.value.trim(),
    query: queryText.value,
    filters: JSON.parse(JSON.stringify(filters.value)),
    timeRange: timeRange.value
  })
  localStorage.setItem(STORAGE_KEY, JSON.stringify(presets.value))
  presetDialogVisible.value = false
  ElMessage.success('已保存')
}
const loadPreset = (idx) => {
  const p = presets.value[idx]
  if (!p) return
  queryText.value = p.query || ''
  filters.value = JSON.parse(JSON.stringify(p.filters || []))
  if (p.timeRange) timeRange.value = p.timeRange
  page.value = 1
  doQuery()
}
const deletePreset = (idx) => { presets.value.splice(idx, 1); localStorage.setItem(STORAGE_KEY, JSON.stringify(presets.value)) }

onMounted(async () => {
  try { const res = await rawLogs.fields(); fields.value = res.data || [] } catch {}
  loadPresets()
  loadColPrefs()
  doQuery()
})
</script>

<style lang="scss" scoped>
.raw-log-page { padding: 0; }

.page-header {
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;
  h2 { font-size: 18px; font-weight: 600; margin: 0; color: var(--el-text-color-primary); }
}

/* ── 查询栏（Kibana Discover 风格）── */
.discover-bar {
  display: flex;
  gap: 8px;
  align-items: stretch;
  margin-bottom: 10px;
}
.query-input-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
  height: 40px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  transition: border-color 0.15s, box-shadow 0.15s;
  &:focus-within {
    border-color: var(--el-color-primary);
    box-shadow: 0 0 0 2px var(--el-color-primary-light-9);
  }
}
.query-icon { color: var(--el-text-color-secondary); flex-shrink: 0; }
.query-clear {
  color: var(--el-text-color-placeholder); cursor: pointer; flex-shrink: 0;
  &:hover { color: var(--el-text-color-regular); }
}
.query-input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--el-text-color-primary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
  &::placeholder { color: var(--el-text-color-placeholder); font-family: inherit; }
}

.time-picker-btn {
  display: flex; align-items: center; gap: 6px;
  height: 40px;
  padding: 0 14px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  &:hover { border-color: var(--el-color-primary); color: var(--el-color-primary); }
  .caret { color: var(--el-text-color-placeholder); }
}

/* ── 筛选胶囊 ── */
.filter-row {
  display: flex; justify-content: space-between; align-items: center;
  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.pills { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-height: 28px; }
.filter-pill {
  cursor: pointer;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  &.negated { background: var(--el-color-danger-light-9); border-color: var(--el-color-danger-light-5); }
}
.pill-negate {
  display: inline-flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; margin-right: 4px;
  border-radius: 3px;
  background: var(--el-color-primary-light-7);
  color: var(--el-color-primary);
  font-weight: 700; font-size: 11px; line-height: 1;
  &:hover { background: var(--el-color-primary-light-5); }
}
.negated .pill-negate { background: var(--el-color-danger-light-7); color: var(--el-color-danger); }
.pill-field { font-weight: 600; }
.pill-op { margin: 0 4px; color: var(--el-text-color-secondary); }
.pill-value { color: var(--el-text-color-primary); }
.add-filter-btn { border-style: dashed; }
.filter-actions { display: flex; gap: 6px; margin-left: auto; }

/* ── 结果 ──
 * 结果区不再用 el-card，直接贴合 Discover 的一整块结果面板。 */
.result-card {
  border-radius: 8px;
}
.result-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.hits { display: flex; align-items: baseline; gap: 6px; }
.hits strong { font-size: 18px; color: var(--el-text-color-primary); font-variant-numeric: tabular-nums; }
.hits-label { font-size: 13px; color: var(--el-text-color-regular); }
.took {
  margin-left: 10px; font-size: 12px; color: var(--el-text-color-secondary);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.pagination-wrap { display: flex; justify-content: flex-end; margin-top: 16px; }

.detail-kv { display: flex; padding: 6px 0; border-bottom: 1px solid var(--el-border-color-extra-light); }
.detail-key { width: 160px; flex-shrink: 0; font-size: 12px; color: var(--el-text-color-secondary); font-family: monospace; white-space: nowrap; }
.detail-val { flex: 1; font-size: 12px; color: var(--el-text-color-primary); word-break: break-all; font-family: monospace; }
</style>

<style>
/* 下拉菜单里的时间范围高亮（scoped 拿不到 popper） */
.el-dropdown-menu__item.is-active {
  color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
</style>
