import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { addresses, inspectApi } from '@/api'
import { useAddressesStore } from '@/store/addresses'
import { ElMessage, ElMessageBox } from 'element-plus'

// ── 模块级国家缓存（跨组件实例持久，避免重复查询 ipinfo.io） ──
const _countryCache = {}

const formRules = {
  ip_address: [{ required: true, message: '请输入攻击地址', trigger: 'blur' }]
}

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

export function useAddresses() {
  const store = useAddressesStore()
  // refs（storeToRefs 保持返回形状：调用方拿到的仍是 ref，模板自动解包不变）
  const {
    tableRef, tableData, total, multipleSelection, loading, error,
    dialogVisible, saveLoading, isEdit, editId, formRef,
    timePreset, form, countryQueryLoading,
    blockConfigVisible, blockResultVisible, blockRunning, blockResults, scriptOptions
  } = storeToRefs(store)
  // reactive 对象按引用返回（与原先模块级 reactive 行为一致）
  const filterForm = store.filterForm
  const pagination = store.pagination
  const sortMeta = store.sortMeta
  const countryLoadingMap = store.countryLoadingMap
  const blockConfig = store.blockConfig

  const dialogTitle = computed(() => isEdit.value ? '编辑地址' : '新增地址')

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

  // 通过 ipinfo.io 自动填充国家信息（带缓存）
  const autoFillCountries = async () => {
    // 1. 先从缓存填充已有数据
    tableData.value.forEach(row => {
      if (!row.country && _countryCache[row.ip_address]) {
        row.country = _countryCache[row.ip_address]
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
        }
      })
    } catch (e) {
      console.error('国家信息查询失败', e)
    } finally {
      ips.forEach(ip => { delete countryLoadingMap[ip] })
    }
  }

  // 组装列表查询参数（loadData / exportCsv 共用，保证筛选与排序口径一致）
  const buildListParams = () => {
    const params = {
      keyword: filterForm.keyword,
      ...buildDateRange(),
      ...sortMeta
    }
    if (filterForm.severity) params.severity = filterForm.severity
    if (filterForm.status) params.status = filterForm.status
    return params
  }

  const loadData = async () => {
    // 每次加载前清空勾选，避免批量操作打到已不展示的行
    multipleSelection.value = []
    loading.value = true
    error.value = null
    try {
      const params = {
        ...buildListParams(),
        page: pagination.page,
        page_size: pagination.page_size
      }
      const res = await addresses.list(params)
      tableData.value = res.data.list
      total.value = res.data.total
      // 国家列自动补齐（fire-and-forget，不阻塞列表渲染）
      autoFillCountries().catch(() => {})
    } catch (e) {
      error.value = e?.message || e?.response?.data?.msg || '地址列表加载失败'
    } finally {
      loading.value = false
    }
  }

  const filterChange = () => { pagination.page = 1; loadData() }
  const onTimePresetChange = () => { pagination.page = 1; loadData() }

  const resetFilter = () => {
    Object.assign(filterForm, { keyword: '', severity: '', status: '' })
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


  // ── 封禁功能（调用脚本执行中的封堵脚本） ──
  const BLOCK_CONFIG_KEY = 'block_config'

  const openBlockConfig = async () => {
    try {
      const res = await inspectApi.listScripts()
      scriptOptions.value = (res.data || []).filter(s => s.is_active !== false)
    } catch (e) { scriptOptions.value = [] }
    try {
      const saved = JSON.parse(localStorage.getItem(BLOCK_CONFIG_KEY) || '{}')
      blockConfig.scriptId = saved.scriptId ?? null
      blockConfig.paramsTemplate = saved.paramsTemplate || ''
    } catch (e) {}
    blockConfigVisible.value = true
  }

  const saveBlockConfig = () => {
    if (!blockConfig.scriptId) { ElMessage.warning('请选择封堵脚本'); return }
    localStorage.setItem(BLOCK_CONFIG_KEY, JSON.stringify({ ...blockConfig }))
    ElMessage.success('封堵参数已保存')
    blockConfigVisible.value = false
  }

  // 解析参数模板：每行 KEY=VALUE，值中 {ip} 替换为当前 IP
  const parseBlockTemplate = (tpl, ip) => {
    const env = {}
    String(tpl || '').split('\n').forEach(line => {
      line = line.trim()
      if (!line || line.startsWith('#')) return
      const idx = line.indexOf('=')
      if (idx <= 0) return
      const key = line.slice(0, idx).trim()
      const val = line.slice(idx + 1).trim().replace(/\{ip\}/g, ip)
      if (key) env[key] = val
    })
    return env
  }

  const doBlock = async (rows) => {
    let config
    try { config = JSON.parse(localStorage.getItem(BLOCK_CONFIG_KEY) || '{}') } catch (e) { config = {} }
    if (!config.scriptId) {
      ElMessage.warning('请先点击「配置封堵参数」选择封堵脚本')
      return
    }
    const ips = rows.map(r => r.ip_address)
    await ElMessageBox.confirm(
      `将对 ${ips.length} 个地址执行封堵脚本：\n${ips.join('\n')}`,
      '确认封禁', { type: 'warning', confirmButtonText: '执行封禁', cancelButtonText: '取消' }
    )
    blockResults.value = []
    blockResultVisible.value = true
    blockRunning.value = true
    try {
      const targets = rows.map(r => ({
        ip: r.ip_address,
        env: parseBlockTemplate(config.paramsTemplate, r.ip_address)
      }))
      const res = await inspectApi.blockByScript(config.scriptId, targets)
      const results = res.data?.results || []
      blockResults.value = results
      // 执行成功的地址更新状态为已封禁
      const okIps = new Set(results.filter(r => r.exit_code === 0).map(r => r.ip))
      if (okIps.size) {
        await Promise.all(
          rows.filter(r => okIps.has(r.ip_address)).map(r => addresses.update(r.id, { status: 'blocked' }))
        )
      }
      ElMessage.success(`封禁执行完成：成功 ${okIps.size} / ${rows.length}`)
      loadData()
    } catch (e) {
      if (e === 'cancel' || e === 'close') return
      ElMessage.error('封禁执行失败：' + (e?.response?.data?.msg || e?.message || '未知错误'))
    } finally {
      blockRunning.value = false
    }
  }

  const blockOne = (row) => { doBlock([row]).catch(() => {}) }
  const blockSelected = () => {
    if (!multipleSelection.value.length) return
    doBlock(multipleSelection.value).catch(() => {})
  }


  // ── 导出 CSV ──
  const exportCsv = async () => {
    try {
      // 与列表同源的筛选 + 排序（不再读 filterForm 上不存在的 sort_* 字段）
      const params = { ...buildListParams(), page: 1, page_size: 100000 }

      const res = await addresses.exportCsv(params)
      // 创建下载链接
      const blob = new Blob([res], { type: 'text/csv;charset=utf-8;' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      // 服务端 Content-Disposition 文件名优先，回退到客户端生成
      a.download = res.filename || `addresses_${new Date().toISOString().slice(0,10)}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      ElMessage.success('导出成功')
    } catch (e) {
      ElMessage.error('导出失败：' + (e.message || '未知错误'))
    }
  }

  return {
    // table state
    tableRef,
    tableData,
    total,
    multipleSelection,
    loading,
    error,
    pagination,
    sortMeta,
    countryLoadingMap,
    // filter state
    filterForm,
    timePreset,
    // form / dialog state
    dialogVisible,
    saveLoading,
    isEdit,
    editId,
    formRef,
    form,
    formRules,
    dialogTitle,
    countryQueryLoading,
    // block state
    BLOCK_CONFIG_KEY,
    blockConfigVisible,
    blockResultVisible,
    blockRunning,
    blockResults,
    scriptOptions,
    blockConfig,
    // helpers
    severityTag,
    statusTag,
    statusLabel,
    formatDuration,
    buildDateRange,
    parseBlockTemplate,
    // list actions
    loadData,
    autoFillCountries,
    filterChange,
    onTimePresetChange,
    resetFilter,
    onSelectionChange,
    onSortChange,
    // form actions
    openCreate,
    openEdit,
    queryCountryForForm,
    submitForm,
    // row actions
    confirmDelete,
    batchDelete,
    batchLookupCountry,
    // block actions
    openBlockConfig,
    saveBlockConfig,
    doBlock,
    blockOne,
    blockSelected,
    // export
    exportCsv
  }
}
