import { ref, computed, watch } from 'vue'
import { reports, reportMgmt, remoteApi, inspectApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

// ── module-level state (single owner shared across the page) ──

// ── Tab 状态 ──
const activeTab = ref('generate')

// ── 生成报告 ──
const selectedDate = ref(formatToday())
const includeAddresses = ref(true)
const includeMonitoring = ref(true)
const loading = ref(false)
const currentReport = ref(null)
const DEFAULT_SUMMARY = `【今日速览模板】
1、<可用性结论，例：无可用性问题 / XX服务器XX资源使用率峰值XX%>
2、<安全事件结论，例：nginx日志发现X个IP攻击行为，无入侵成功迹象>
3、<资源余量1，例：XX服务剩余流量：XXX，预计可用XX天>
4、<资源余量2，例：XX网关余额：XXX，预计可用XX天>`
const summaryText = ref(DEFAULT_SUMMARY)
const savingTpl = ref(false)

// ── 攻击地址按严重级别分组 ──
const criticalAddresses = computed(() =>
  (currentReport.value?.addresses || []).filter(a => a.severity === 'critical')
)
const normalAddresses = computed(() =>
  (currentReport.value?.addresses || []).filter(a => a.severity !== 'critical')
)
const severityLabel = (s) => ({ critical: '严重', high: '高危', medium: '中危', low: '低危' }[s] || s)
const severityType = (s) => ({ critical: 'danger', high: 'warning', medium: '', low: 'info' }[s] || '')

const scriptOptions = ref([])
const selectedScriptIds = ref([])
const endpointOptions = ref([])
const selectedEndpointIds = ref([])

// ── 报告板块顺序（可上下调整） ──
const SECTION_KEYS = ['addresses', 'monitoring', 'scripts', 'ingested']
const sectionLabels = { addresses: '当日攻击地址', monitoring: '服务器监控', scripts: '脚本执行结果', ingested: '接收数据（最近一条）' }
const sectionOrder = ref([...SECTION_KEYS])
const STORAGE_ORDER = 'report_section_order'

// ── 勾选状态持久化（默认恢复上次生成报告的勾选） ──
const STORAGE_SCRIPTS = 'report_selected_scripts'
const STORAGE_ENDPOINTS = 'report_selected_endpoints'

// ── 报告列表 ──
const reportList = ref([])
const reportTotal = ref(0)
const reportPage = ref(1)
const reportPageSize = ref(10)
const refreshing = ref(false)

// ── 预览 ──
const previewVisible = ref(false)
const previewData = ref(null)

// ── 今日速览默认模板（后端 system_config 持久化，保存完整页面配置） ──
const applyTemplate = (tpl) => {
  if (!tpl) return
  // 今日速览
  if (tpl.template) summaryText.value = tpl.template
  const cfg = tpl.config || {}
  // 勾选：服务器监控 / 攻击地址
  if (typeof cfg.include_addresses === 'boolean') includeAddresses.value = cfg.include_addresses
  if (typeof cfg.include_monitoring === 'boolean') includeMonitoring.value = cfg.include_monitoring
  // 勾选：脚本（需选项已加载，过滤不存在的）
  if (Array.isArray(cfg.script_ids) && scriptOptions.value.length) {
    const valid = new Set(scriptOptions.value.map(s => s.id))
    selectedScriptIds.value = cfg.script_ids.filter(id => valid.has(id))
  }
  // 勾选 + 顺序：接收端口（需选项已加载）
  if (Array.isArray(cfg.endpoint_ids) && endpointOptions.value.length) {
    const valid = new Set(endpointOptions.value.map(ep => ep.id))
    const merged = cfg.endpoint_ids.filter(id => valid.has(id))
    // 补上模板没勾但存在的新端口？不补，保持模板顺序的严格子集
    selectedEndpointIds.value = merged
  }
  // 板块顺序
  if (Array.isArray(cfg.section_order) && cfg.section_order.length === SECTION_KEYS.length
      && cfg.section_order.every(k => SECTION_KEYS.includes(k))) {
    sectionOrder.value = [...cfg.section_order]
  }
}

const loadSummaryTemplate = async () => {
  try {
    const res = await reports.getSummaryTemplate()
    applyTemplate(res.data)
  } catch (e) { /* 加载失败时用前端内置默认值 */ }
}

const saveSummaryTemplate = async () => {
  const tpl = String(summaryText.value || '').trim()
  if (!tpl) {
    ElMessage.warning('模板不能为空')
    return
  }
  const cfg = {
    include_addresses: includeAddresses.value,
    include_monitoring: includeMonitoring.value,
    script_ids: selectedScriptIds.value.slice(),
    endpoint_ids: selectedEndpointIds.value.slice(),
    section_order: sectionOrder.value.slice()
  }
  savingTpl.value = true
  try {
    await reports.saveSummaryTemplate(tpl, cfg)
    ElMessage.success('默认模板已保存（含今日速览、勾选与顺序）')
  } catch (e) {
    ElMessage.error('保存模板失败: ' + (e.message || '未知错误'))
  } finally {
    savingTpl.value = false
  }
}

// ── 全选 / 清空 ──
const selectAllScripts = () => { selectedScriptIds.value = scriptOptions.value.map(s => s.id) }
const clearScripts = () => { selectedScriptIds.value = [] }
const selectAllEndpoints = () => { selectedEndpointIds.value = endpointOptions.value.map(ep => ep.id) }
const clearEndpoints = () => { selectedEndpointIds.value = [] }
const endpointName = (id) => {
  const ep = endpointOptions.value.find(e => e.id === id)
  return ep ? ep.name : ('#' + id)
}
const moveEndpointUp = (idx) => {
  if (idx > 0) {
    const a = selectedEndpointIds.value
    ;[a[idx - 1], a[idx]] = [a[idx], a[idx - 1]]
  }
}
const moveEndpointDown = (idx) => {
  if (idx < selectedEndpointIds.value.length - 1) {
    const a = selectedEndpointIds.value
    ;[a[idx + 1], a[idx]] = [a[idx], a[idx + 1]]
  }
}

const moveUp = (idx) => { if (idx > 0) { const a = sectionOrder.value; [a[idx - 1], a[idx]] = [a[idx], a[idx - 1]] } }
const moveDown = (idx) => { if (idx < sectionOrder.value.length - 1) { const a = sectionOrder.value; [a[idx + 1], a[idx]] = [a[idx], a[idx + 1]] } }

function restoreOrder() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_ORDER) || '[]')
    if (Array.isArray(saved) && saved.length === SECTION_KEYS.length && saved.every(k => SECTION_KEYS.includes(k))) {
      sectionOrder.value = saved
    }
  } catch (e) {}
}
watch(sectionOrder, (v) => { localStorage.setItem(STORAGE_ORDER, JSON.stringify(v)) }, { deep: true })

function restoreSelection() {
  try {
    const savedScripts = JSON.parse(localStorage.getItem(STORAGE_SCRIPTS) || '[]')
    if (Array.isArray(savedScripts) && scriptOptions.value.length) {
      const validIds = new Set(scriptOptions.value.map(s => s.id))
      selectedScriptIds.value = savedScripts.filter(id => validIds.has(id))
    }
  } catch (e) {}
  try {
    const savedEndpoints = JSON.parse(localStorage.getItem(STORAGE_ENDPOINTS) || '[]')
    if (Array.isArray(savedEndpoints) && endpointOptions.value.length) {
      const validIds = new Set(endpointOptions.value.map(ep => ep.id))
      selectedEndpointIds.value = savedEndpoints.filter(id => validIds.has(id))
    }
  } catch (e) {}
}

watch(selectedScriptIds, (v) => {
  localStorage.setItem(STORAGE_SCRIPTS, JSON.stringify(v))
}, { deep: true })
watch(selectedEndpointIds, (v) => {
  localStorage.setItem(STORAGE_ENDPOINTS, JSON.stringify(v))
}, { deep: true })

function formatToday() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

const generateReport = async () => {
  loading.value = true
  try {
    const params = { date: selectedDate.value }
    if (!includeAddresses.value) params.include_addresses = '0'
    if (!includeMonitoring.value) params.include_monitoring = '0'
    if (selectedScriptIds.value.length) params.script_ids = selectedScriptIds.value.join(',')
    if (selectedEndpointIds.value.length) params.endpoint_ids = selectedEndpointIds.value.join(',')
    params.summary_text = summaryText.value
    // 生成时把板块顺序固化进报告 content 快照，导出读报告行而不是当时的 UI 状态
    params.section_order = sectionOrder.value.join(',')
    const res = await reports.inspection(params)
    currentReport.value = res.data || null
    if (currentReport.value) {
      // 后端尚未持久化 content.section_order 时本地补写，保证本条导出顺序正确
      if (!currentReport.value.content) currentReport.value.content = {}
      if (!Array.isArray(currentReport.value.content.section_order)) {
        currentReport.value.content.section_order = [...sectionOrder.value]
      }
      ElMessage.success('报告已生成并保存')
    }
  } catch (e) {
    ElMessage.error('生成巡检报告失败')
  } finally {
    loading.value = false
  }
}

const loadReports = async () => {
  refreshing.value = true
  try {
    const res = await reportMgmt.list({ page: reportPage.value, page_size: reportPageSize.value })
    reportList.value = res.data?.items || []
    reportTotal.value = res.data?.total || 0
  } catch (e) {
    ElMessage.error('加载报告列表失败')
  } finally {
    refreshing.value = false
  }
}

const onPageChange = (p) => {
  reportPage.value = p
  loadReports()
}

const previewReport = async (row) => {
  try {
    const res = await reportMgmt.get(row.id)
    previewData.value = res.data || null
    previewVisible.value = true
  } catch (e) {
    ElMessage.error('加载报告详情失败')
  }
}

// ── 导出（复用同一份数据） ──
// HTML 转义：导出 Word/HTML 落盘文档，alert.handle_suggestion 等字段可被污染，
// 必须对所有插值转义，防导出文件内嵌 XSS。
const esc = (s) => String(s ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

const downloadFile = (content, filename, mime) => {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// 板块顺序：优先报告 content 快照（生成时固化），缺失时回退当前 UI 状态
const resolveSectionOrder = (r) => {
  const snap = r?.content?.section_order
  if (Array.isArray(snap) && snap.length === SECTION_KEYS.length && snap.every(k => SECTION_KEYS.includes(k))) {
    return snap
  }
  return sectionOrder.value
}

// 板块描述符：buildText / buildHtml 共用同一份布局逻辑，避免两处 ~80% 重复导致行为漂移
const SECTIONS = {
  addresses: {
    title: '攻击地址',
    hasData: (r) => !!(r.addresses && r.addresses.length),
    renderText: (r) => {
      const L = []
      const critical = r.addresses.filter(a => a.severity === 'critical')
      const normal = r.addresses.filter(a => a.severity !== 'critical')
      if (critical.length) {
        L.push('【⚠️ 严重攻击地址】')
        critical.forEach((a, i) => {
          const country = a.country ? `（${esc(a.country)}）` : ''
          L.push(`${i + 1}. 攻击地址: ${esc(a.ip_address)}${country}`)
          L.push(`   攻击时间: ${esc(a.start_time)} ~ ${esc(a.end_time)}`)
          L.push(`   攻击次数: ${esc(a.attack_count)}`)
          L.push(`   攻击域名: ${esc(a.domain) || '-'}`)
          if (a.handle_suggestion) L.push(`   处置结果: ${esc(a.handle_suggestion)}`)
        })
        L.push('')
      }
      if (normal.length) {
        L.push('【攻击地址】')
        normal.forEach((a, i) => {
          const country = a.country ? `（${esc(a.country)}）` : ''
          const lvl = { high: '高危', medium: '中危', low: '低危' }[a.severity] || ''
          L.push(`${i + 1}. 攻击地址: ${esc(a.ip_address)}${country} [${esc(lvl)}]`)
          L.push(`   攻击时间: ${esc(a.start_time)} ~ ${esc(a.end_time)}`)
          L.push(`   持续时间: ${esc(a.duration)} 秒`)
          L.push(`   攻击次数: ${esc(a.attack_count)}`)
          L.push(`   攻击域名: ${esc(a.domain) || '-'}`)
        })
      }
      return L
    },
    renderHtml: (r) => {
      const L = []
      const critical = r.addresses.filter(a => a.severity === 'critical')
      const normal = r.addresses.filter(a => a.severity !== 'critical')
      if (critical.length) {
        L.push('<h3 style="color:#f56c6c;">⚠️ 严重攻击地址</h3>')
        critical.forEach((a, i) => {
          const country = a.country ? `（${esc(a.country)}）` : ''
          L.push(`<p style="border-left:3px solid #f56c6c;padding-left:10px;">`)
          L.push(`<b>${i + 1}. ${esc(a.ip_address)}</b>${country}<br/>`)
          L.push(`攻击时间: ${esc(a.start_time)} ~ ${esc(a.end_time)} ｜ 次数: ${esc(a.attack_count)}<br/>`)
          L.push(`域名: ${esc(a.domain) || '-'}`)
          if (a.handle_suggestion) L.push(`<br/><b style="color:#e6a23c;">处置结果：</b>${esc(a.handle_suggestion)}`)
          L.push(`</p>`)
        })
      }
      if (normal.length) {
        L.push('<h3>攻击地址</h3>')
        normal.forEach((a, i) => {
          const country = a.country ? `（${esc(a.country)}）` : ''
          const lvl = { high: '高危', medium: '中危', low: '低危' }[a.severity] || ''
          L.push(`<p><b>${i + 1}. 攻击地址:</b> ${esc(a.ip_address)}${country} [${esc(lvl)}]<br/>`)
          L.push(`攻击时间: ${esc(a.start_time)} ~ ${esc(a.end_time)}<br/>`)
          L.push(`持续时间: ${esc(a.duration)} 秒<br/>`)
          L.push(`攻击次数: ${esc(a.attack_count)}<br/>`)
          L.push(`攻击域名: ${esc(a.domain) || '-'}</p>`)
        })
      }
      return L
    }
  },
  monitoring: {
    title: '服务器监控',
    hasData: (r) => !!(r.servers && r.servers.length),
    renderText: (r) => {
      const L = []
      L.push('【服务器监控】')
      r.servers.forEach((s, i) => {
        L.push(`${i + 1}. ${esc(s.alias) || ''} ${esc(s.instance)}`)
        L.push(`   CPU 均值 ${esc(s.cpu?.avg ?? '-')}% / 峰值 ${esc(s.cpu?.peak ?? '-')}%`)
        L.push(`   内存 均值 ${esc(s.memory?.avg ?? '-')}% / 峰值 ${esc(s.memory?.peak ?? '-')}%`)
        ;(s.disks || []).forEach((dk) => {
          L.push(`   磁盘 ${esc(dk.mountpoint)} 均值 ${esc(dk.avg ?? '-')}% / 峰值 ${esc(dk.peak ?? '-')}%`)
        })
      })
      return L
    },
    renderHtml: (r) => {
      const L = []
      L.push('<h3>服务器监控</h3>')
      r.servers.forEach((s, i) => {
        L.push(`<p><b>${i + 1}. ${esc(s.alias) || ''} ${esc(s.instance)}</b><br/>`)
        L.push(`CPU 均值 ${esc(s.cpu?.avg ?? '-')}% / 峰值 ${esc(s.cpu?.peak ?? '-')}%<br/>`)
        L.push(`内存 均值 ${esc(s.memory?.avg ?? '-')}% / 峰值 ${esc(s.memory?.peak ?? '-')}%<br/>`)
        ;(s.disks || []).forEach((dk) => {
          L.push(`磁盘 ${esc(dk.mountpoint)} 均值 ${esc(dk.avg ?? '-')}% / 峰值 ${esc(dk.peak ?? '-')}%<br/>`)
        })
        L.push('</p>')
      })
      return L
    }
  },
  scripts: {
    title: '脚本执行结果',
    hasData: (r) => !!(r.scripts && r.scripts.length),
    renderText: (r) => {
      const L = []
      L.push('【脚本执行结果】')
      r.scripts.forEach((sc, i) => {
        const status = sc.exit_code === 0 ? '' : ` [失败, 退出码 ${esc(sc.exit_code)}]`
        L.push(`${i + 1}. ${esc(sc.name)}${status}`)
        if (sc.stdout) L.push('   ' + esc(sc.stdout).replace(/\n/g, '\n   '))
        if (sc.stderr) L.push('   错误: ' + esc(sc.stderr).replace(/\n/g, '\n   '))
      })
      return L
    },
    renderHtml: (r) => {
      const L = []
      L.push('<h3>脚本执行结果</h3>')
      r.scripts.forEach((sc, i) => {
        const status = sc.exit_code === 0 ? '' : ` <span style="color:#f56c6c;">[失败, 退出码 ${esc(sc.exit_code)}]</span>`
        L.push(`<p><b>${i + 1}. ${esc(sc.name)}</b>${status}<br/>`)
        if (sc.stdout) L.push(`<pre>${esc(sc.stdout)}</pre>`)
        if (sc.stderr) L.push(`<pre>错误: ${esc(sc.stderr)}</pre>`)
        L.push('</p>')
      })
      return L
    }
  },
  ingested: {
    title: '接收数据（最近一条）',
    hasData: (r) => !!(r.ingested && r.ingested.length),
    renderText: (r) => {
      const L = []
      L.push('【接收数据（最近一条）】')
      r.ingested.forEach((it, i) => {
        const who = it.sender_name ? ` ｜ 发送方: ${esc(it.sender_name)}` : ''
        L.push(`${i + 1}. 端口: ${esc(it.endpoint_name)}${who} ｜ 接收时间: ${esc(it.received_at)}`)
        if (it.payload) L.push('   ' + esc(it.payload).replace(/\n/g, '\n   '))
      })
      return L
    },
    renderHtml: (r) => {
      const L = []
      L.push('<h3>接收数据（最近一条）</h3>')
      r.ingested.forEach((it, i) => {
        const who = it.sender_name ? ` ｜ 发送方: ${esc(it.sender_name)}` : ''
        L.push(`<p><b>${i + 1}. ${esc(it.endpoint_name)}</b>${who} ｜ 接收时间: ${esc(it.received_at)}<br/>`)
        if (it.payload) L.push(`<pre>${esc(it.payload)}</pre>`)
        L.push('</p>')
      })
      return L
    }
  }
}

const buildText = (data) => {
  const r = data
  const L = []
  L.push('═══════════════════════════════════════════════')
  L.push(`        安全巡检报告 · ${esc(r.report_date)}`)
  L.push('═══════════════════════════════════════════════')
  L.push(`生成时间: ${esc(r.generated_at)}`)
  if (r.summary_text) {
    L.push('')
    L.push('【今日速览】')
    L.push(esc(r.summary_text))
    L.push('───────────────────────────────────────────────')
  }
  const txtParts = []
  if (r.addresses !== null) txtParts.push(`当日攻击地址: ${esc(r.address_count)}`)
  if (r.servers !== null) txtParts.push(`监控服务器: ${esc((r.servers || []).length)}`)
  if (r.script_count > 0) txtParts.push(`脚本执行: ${esc(r.script_count)}`)
  if (r.servers !== null) txtParts.push(`监控: ${r.monitoring_connected ? '已连接' : '未连接'}`)
  if (txtParts.length) L.push(txtParts.join(' ｜ '))
  L.push('───────────────────────────────────────────────')
  for (const key of resolveSectionOrder(r)) {
    const sec = SECTIONS[key]
    if (sec && sec.hasData(r)) {
      L.push(...sec.renderText(r))
      L.push('───────────────────────────────────────────────')
    }
  }
  L.push('═══════════════════════════════════════════════')
  return L.join('\n')
}

const buildHtml = (data) => {
  const r = data
  const L = []
  L.push('<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:word" xmlns="http://www.w3.org/TR/REC-html40">')
  L.push('<head><meta charset="utf-8"><title>巡检报告</title></head><body>')
  L.push(`<h2>安全巡检报告 · ${esc(r.report_date)}</h2>`)
  L.push(`<p>生成时间：${esc(r.generated_at)}</p>`)
  if (r.summary_text) {
    L.push('<h3>今日速览</h3>')
    L.push(`<pre>${esc(r.summary_text)}</pre>`)
  }
  const htmlParts = []
  if (r.addresses !== null) htmlParts.push(`当日攻击地址：${esc(r.address_count)}`)
  if (r.servers !== null) htmlParts.push(`监控服务器：${esc((r.servers || []).length)}`)
  if (r.script_count > 0) htmlParts.push(`脚本执行：${esc(r.script_count)}`)
  if (r.servers !== null) htmlParts.push(`监控：${r.monitoring_connected ? '已连接' : '未连接'}`)
  if (htmlParts.length) L.push(`<p>${htmlParts.join(' ｜ ')}</p>`)
  for (const key of resolveSectionOrder(r)) {
    const sec = SECTIONS[key]
    if (sec && sec.hasData(r)) {
      L.push(...sec.renderHtml(r))
    }
  }
  L.push('</' + 'body></' + 'html>')
  return L.join('')
}

// 当前报告导出（生成报告 Tab）
const exportWord = () => {
  if (!currentReport.value) return
  downloadFile(buildHtml(currentReport.value), `巡检报告_${currentReport.value.report_date}.doc`, 'application/msword')
}
const exportTxt = () => {
  if (!currentReport.value) return
  downloadFile(buildText(currentReport.value), `巡检报告_${currentReport.value.report_date}.txt`, 'text/plain;charset=utf-8')
}

// 报告列表导出（先拉详情再导）
const exportReport = async (row, fmt) => {
  try {
    const res = await reportMgmt.get(row.id)
    const data = res.data
    if (!data) return
    if (fmt === 'word') {
      downloadFile(buildHtml(data), `巡检报告_${data.report_date}.doc`, 'application/msword')
    } else {
      downloadFile(buildText(data), `巡检报告_${data.report_date}.txt`, 'text/plain;charset=utf-8')
    }
  } catch (e) {
    ElMessage.error('导出失败')
  }
}

// 删除
const removeReport = (row) => {
  ElMessageBox.confirm(`确认删除 ${row.report_date} 的巡检报告？`, '删除确认', { type: 'warning' })
    .then(async () => {
      try {
        await reportMgmt.delete(row.id)
        ElMessage.success('报告已删除')
        loadReports()
      } catch (e) {
        ElMessage.error('删除失败')
      }
    })
    .catch(() => {})
}

// 页面初始化：加载脚本/端口选项 → 恢复本地勾选与顺序 → 应用后端默认模板
const initPage = async () => {
  try {
    await reportMgmt.list({ page: 1, page_size: 1 })
    const scriptsRes = await inspectApi.listScripts()
    scriptOptions.value = scriptsRes.data || []
  } catch (e) {
    scriptOptions.value = []
  }
  try {
    const er = await remoteApi.listEndpoints()
    endpointOptions.value = er.data || []
  } catch (e) {
    endpointOptions.value = []
  }
  // 选项加载完成后：恢复上次勾选与板块顺序，再应用后端默认模板（模板优先）
  restoreSelection()
  restoreOrder()
  // 优先加载后端保存的完整默认模板（含今日速览、勾选、顺序）
  await loadSummaryTemplate()
}

export function useInspectionReport() {
  return {
    // tab
    activeTab,
    // generate state
    selectedDate,
    includeAddresses,
    includeMonitoring,
    loading,
    currentReport,
    summaryText,
    savingTpl,
    // address grouping / severity helpers
    criticalAddresses,
    normalAddresses,
    severityLabel,
    severityType,
    // template
    applyTemplate,
    loadSummaryTemplate,
    saveSummaryTemplate,
    // script / endpoint picks
    scriptOptions,
    selectedScriptIds,
    endpointOptions,
    selectedEndpointIds,
    selectAllScripts,
    clearScripts,
    selectAllEndpoints,
    clearEndpoints,
    endpointName,
    moveEndpointUp,
    moveEndpointDown,
    // section order
    SECTION_KEYS,
    sectionLabels,
    sectionOrder,
    moveUp,
    moveDown,
    restoreOrder,
    restoreSelection,
    // generate / list / preview / export
    generateReport,
    reportList,
    reportTotal,
    reportPage,
    reportPageSize,
    refreshing,
    loadReports,
    onPageChange,
    previewVisible,
    previewData,
    previewReport,
    exportWord,
    exportTxt,
    exportReport,
    removeReport,
    initPage
  }
}
