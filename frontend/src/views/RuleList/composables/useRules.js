import { ref, reactive } from 'vue'
import { rules, settings } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

// ── module-level state (single owner shared across the page) ──
const tableData = ref([])
const total = ref(0)
const filterForm = reactive({ keyword: '', is_enabled: '' })
const pagination = reactive({ page: 1, page_size: 20 })

const executeDialogVisible = ref(false)
const executeResult = ref(null)

const previewDialogVisible = ref(false)
const previewLoading = ref(false)
const previewData = ref([])
const previewColumns = ref([])

const esIndices = ref([{ name: 'security-logs-*' }])
const stageFieldsCache = ref({})  // 缓存各阶段索引的字段

// 加载规则列表
const loadData = async () => {
  try {
    const params = {
      keyword: filterForm.keyword,
      is_enabled: filterForm.is_enabled === '' ? '' : filterForm.is_enabled,
      page: pagination.page,
      page_size: pagination.page_size
    }
    const res = await rules.list(params)
    tableData.value = res.data.list
    total.value = res.data.total
  } catch (e) {}
}

const filterChange = () => { pagination.page = 1; loadData() }
const resetFilter = () => { Object.assign(filterForm, { keyword: '', is_enabled: '' }); filterChange() }

// 加载ES索引
const loadEsIndices = async () => {
  try {
    const res = await rules.esIndices()
    if (res.data?.length) esIndices.value = res.data
  } catch (e) {
    esIndices.value = [{ name: 'security-logs-*' }]
  }
}

// 加载索引字段
const loadIndexFields = async (index) => {
  if (stageFieldsCache.value[index]) return stageFieldsCache.value[index]
  try {
    const res = await rules.esPreview({ nodes: [], index, limit: 1 })
    const fields = res.data?.fields || {}
    stageFieldsCache.value[index] = fields
    return fields
  } catch (e) {
    const fallback = { src_ip: 'keyword', dest_ip: 'keyword', bytes: 'long', timestamp: 'date' }
    stageFieldsCache.value[index] = fallback
    return fallback
  }
}

// 获取阶段索引的字段列表（从缓存或ES加载）
const getStageFields = (stage) => {
  const index = stage.index
  if (stageFieldsCache.value[index]) {
    return stageFieldsCache.value[index]
  }
  return {}  // 默认空，在加载阶段索引时填充
}

// 阶段索引变化时加载字段
const onStageIndexChange = async (stage) => {
  await loadIndexFields(stage.index)
}

// 将后端 stage 格式转换为前端编辑格式
const backendStageToFrontend = (backendStage) => {
  // 从 time_window 对象中提取 value 和 unit
  let timeWindow = { value: 3, unit: 'minutes' }
  if (backendStage.time_window && typeof backendStage.time_window === 'object') {
    const keys = Object.keys(backendStage.time_window)
    if (keys.length > 0) {
      timeWindow = { value: backendStage.time_window[keys[0]], unit: keys[0] }
    }
  }

  // 将后端聚合格式转为前端格式
  let aggregation = { groupBy: [], metric: 'count', alias: 'count', having: { operator: 'gt', value: 0 } }
  let enableAggregation = false
  if (backendStage.aggregation && backendStage.aggregation.group_by) {
    enableAggregation = true
    aggregation = {
      groupBy: Array.isArray(backendStage.aggregation.group_by) ? backendStage.aggregation.group_by : [],
      metric: backendStage.aggregation.metric || 'count',
      alias: backendStage.aggregation.alias || 'count',
      having: backendStage.aggregation.having || { operator: 'gt', value: 0 }
    }
  }

  // 将后端 join 格式转为前端格式
  let join = { fromStage: '', remoteField: '', localField: '' }
  let enableJoin = false
  if (backendStage.join && backendStage.join.from_stage) {
    enableJoin = true
    join = {
      fromStage: backendStage.join.from_stage || '',
      remoteField: backendStage.join.remote_field || '',
      localField: backendStage.join.local_field || ''
    }
  }

  // 处理过滤条件格式（兼容旧格式数组和新格式树形结构）
  let filters = { logic: null, filters: [] }
  if (backendStage.filters) {
    if (Array.isArray(backendStage.filters)) {
      // 旧格式：数组，转换为新格式
      filters = { logic: 'and', filters: backendStage.filters }
    } else if (typeof backendStage.filters === 'object' && backendStage.filters.logic) {
      // 新格式：树形结构
      filters = backendStage.filters
    }
  }

  return {
    id: backendStage.id || `stage_${Date.now()}`,
    name: backendStage.name || '',
    index: backendStage.index || '',
    timeWindow,
    filters,
    enableAggregation,
    aggregation,
    enableJoin,
    join
  }
}

// 清理过滤条件树，移除空条件
const cleanFilterTree = (node) => {
  if (!node || !node.logic || !Array.isArray(node.filters)) {
    return node
  }

  const cleanedFilters = []
  for (const filter of node.filters) {
    // 简单条件（有 field 字段）
    if (filter.field !== undefined) {
      // 只保留有字段名的条件
      if (filter.field) {
        cleanedFilters.push(filter)
      }
    }
    // 逻辑组（有 logic 字段）
    else if (filter.logic && Array.isArray(filter.filters)) {
      const cleanedGroup = cleanFilterTree(filter)
      // 只保留非空的条件组
      if (cleanedGroup.filters.length > 0) {
        cleanedFilters.push(cleanedGroup)
      }
    }
  }

  return {
    logic: node.logic,
    filters: cleanedFilters
  }
}

// 构建阶段参数（用于提交）
const buildStageParams = (stage) => {
  // 处理过滤条件（新格式：树形结构）
  let filters = stage.filters
  // 如果是新格式对象，需要清理空的条件
  if (filters && typeof filters === 'object' && filters.logic) {
    filters = cleanFilterTree(filters)
  }

  const params = {
    id: stage.id,
    index: stage.index,
    time_window: { [stage.timeWindow.unit]: stage.timeWindow.value },
    filters: filters,
    aggregation: null,
    join: null
  }

  if (stage.enableAggregation && stage.aggregation.groupBy.length) {
    params.aggregation = {
      group_by: stage.aggregation.groupBy,
      metric: stage.aggregation.metric,
      alias: stage.aggregation.alias || 'count',
      having: stage.aggregation.having
    }
  }

  if (stage.enableJoin && stage.join.fromStage) {
    params.join = {
      from_stage: stage.join.fromStage,
      remote_field: stage.join.remoteField,
      local_field: stage.join.localField
    }
  }

  return params
}

// 预览单个阶段
const previewStage = async (stage) => {
  if (!stage.index) {
    ElMessage.warning('请先选择数据源索引')
    return
  }

  previewLoading.value = true
  previewDialogVisible.value = true
  previewData.value = []
  previewColumns.value = []

  try {
    // 构建单阶段查询参数
    const stageParams = buildStageParams(stage)
    const res = await rules.esPreview({ stages: [stageParams], limit: 50 })

    previewData.value = res.data.preview || []
    if (previewData.value.length) {
      previewColumns.value = Object.keys(previewData.value[0])
    }
  } catch (e) {
    ElMessage.error('预览失败: ' + (e.message || e))
  } finally {
    previewLoading.value = false
  }
}

// 获取系统默认ES索引配置
const getDefaultIndex = async () => {
  let defaultIndex = 'security-logs-*'
  try {
    const esCfg = await settings.getEsDefault()
    if (esCfg.data?.default_index) {
      defaultIndex = esCfg.data.default_index
    }
  } catch (e) {}
  return defaultIndex
}

const createRule = (payload) => rules.create(payload)
const updateRule = (id, payload) => rules.update(id, payload)
const getRule = (id) => rules.get(id)

const toggleEnabled = async (row) => {
  try {
    await rules.update(row.id, { is_enabled: row.is_enabled })
    ElMessage.success(row.is_enabled ? '规则已启用' : '规则已禁用')
  } catch (e) {}
}

const runPreview = async (row) => {
  try {
    const res = await rules.run(row.id)
    previewData.value = res.data.preview || []
    previewColumns.value = previewData.value.length ? Object.keys(previewData.value[0]) : []
    previewDialogVisible.value = true
  } catch (e) {}
}

const executeRule = async (row) => {
  try {
    await ElMessageBox.confirm('确认执行此规则？将查询ES并写入MySQL。', '执行确认', { type: 'info' })
    const res = await rules.execute(row.id)
    executeResult.value = res.data
    executeResult.value.msg = res.msg
    executeDialogVisible.value = true
    loadData()
  } catch (e) {}
}

const confirmDelete = (row) => {
  ElMessageBox.confirm(`确定删除规则「${row.name}」？`, '确认', { type: 'warning' })
    .then(async () => { await rules.delete(row.id); ElMessage.success('删除成功'); loadData() })
    .catch(() => {})
}

export function useRules() {
  return {
    // list state
    tableData,
    total,
    filterForm,
    pagination,
    // preview state
    previewDialogVisible,
    previewLoading,
    previewData,
    previewColumns,
    // execute result state
    executeDialogVisible,
    executeResult,
    // ES meta
    esIndices,
    stageFieldsCache,
    // list actions
    loadData,
    filterChange,
    resetFilter,
    // CRUD helpers
    createRule,
    updateRule,
    getRule,
    getDefaultIndex,
    // row actions
    toggleEnabled,
    runPreview,
    executeRule,
    confirmDelete,
    // ES / stage helpers
    loadEsIndices,
    loadIndexFields,
    getStageFields,
    onStageIndexChange,
    backendStageToFrontend,
    cleanFilterTree,
    buildStageParams,
    previewStage
  }
}
