import request from './request'

// ── 认证 ──
export const auth = {
  login: (data) => request.post('/auth/login', data),
  me: () => request.get('/auth/me'),
  refresh: () => request.post('/auth/refresh'),
  logout: () => request.post('/auth/logout'),
  changePassword: (data) => request.post('/auth/change-password', data)
}

// ── 地址列表 ──
export const addresses = {
  list: (params) => request.get('/addresses', { params }),
  create: (data) => request.post('/addresses', data),
  update: (id, data) => request.put(`/addresses/${id}`, data),
  delete: (id) => request.delete(`/addresses/${id}`),
  batchDelete: (ids) => request.post('/addresses/batch-delete', { ids }),
  batchLookupCountry: (ids) => request.post('/addresses/batch-lookup-country', { ids }),
  migrateCountries: () => request.post('/addresses/migrate-countries'),
  exportCsv: (params) => request.get('/addresses/export', { params, responseType: 'blob' }),
}

// ── 规则列表 ──
export const rules = {
  list: (params) => request.get('/rules', { params }),
  create: (data) => request.post('/rules', data),
  get: (id) => request.get(`/rules/${id}`),
  update: (id, data) => request.put(`/rules/${id}`, data),
  delete: (id) => request.delete(`/rules/${id}`),
  run: (id) => request.post(`/rules/${id}/run`),
  execute: (id) => request.post(`/rules/${id}/execute`),
  esPreview: (data) => request.post('/rules/es-preview', data),
  esIndices: () => request.get('/rules/es-indices'),
  // TG 推送连通性测试（不落库，只用表单里当前填写的凭据发一条测试消息）
  telegramTest: (data) => request.post('/rules/telegram-test', data)
}

// ── 告警列表 ──
export const alerts = {
  list: (params) => request.get('/alerts', { params }),
  stats: () => request.get('/alerts/stats'),
  get: (id) => request.get(`/alerts/${id}`),
  update: (id, data) => request.put(`/alerts/${id}`, data),
  delete: (id) => request.delete(`/alerts/${id}`),
  batchUpdate: (ids, status) => request.post('/alerts/batch-update', { ids, status }),
  batchDelete: (ids) => request.post('/alerts/batch-delete', { ids }),
  // 服务端 CSV 导出。拦截器对 responseType==='blob' 直接返回 Blob，不做信封解包。
  exportCsv: (params) => request.get('/alerts/export', { params, responseType: 'blob' })
}

// ── 系统设置 ──
export const settings = {
  users: () => request.get('/settings/users'),
  createUser: (data) => request.post('/settings/users', data),
  updateUser: (id, data) => request.put(`/settings/users/${id}`, data),
  deleteUser: (id) => request.delete(`/settings/users/${id}`),
  getConfig: () => request.get('/settings/config'),
  saveConfig: (updates) => request.put('/settings/config', { updates }),
  loginLogs: (params) => request.get('/settings/login-logs', { params }),
  getEsDefault: () => request.get('/settings/es-default'),
  // 连接测试
  testEs: () => request.get('/settings/test-es'),
  testMysql: () => request.get('/settings/test-mysql'),
  testPrometheus: () => request.get('/settings/test-prometheus'),
  testGrafana: () => request.get('/settings/test-grafana'),
  // 日志中心
  logs: (params) => request.get('/logs', { params }),
  createLog: (data) => request.post('/logs', data),
}

// ── Inspect API ──
// 长耗时操作单独放宽超时：服务端允许 pip install 120s，报告生成可能更久
export const inspectApi = {
  // Scripts
  listScripts: () => request.get('/inspect/scripts'),
  createScript: (data) => request.post('/inspect/scripts', data),
  updateScript: (id, data) => request.put(`/inspect/scripts/${id}`, data),
  deleteScript: (id) => request.delete(`/inspect/scripts/${id}`),
  // 脚本执行可能跑批处理，放宽到 90s
  executeScripts: (ids, extraEnv) => request.post('/inspect/scripts/execute', { script_ids: ids, extra_env: extraEnv || {} }, { timeout: 90000 }),
  blockByScript: (scriptId, targets) => request.post('/inspect/block', { script_id: scriptId, targets }, { timeout: 90000 }),
  executeAdhoc: (type, script) => request.post('/inspect/execute', { type, script }, { timeout: 90000 }),
  // 脚本执行历史（后端新增；未就绪时 404）
  listScriptRuns: (scriptId, params) => request.get(`/inspect/scripts/${scriptId}/runs`, { params }),
  // Traffic
  traffic: (params) => request.post('/inspect/traffic', params),
  // Grafana
  grafanaMetrics: (params) => request.get('/inspect/grafana-metrics', { params }),
  // VirusTotal
  lookupCountry: (ips) => request.post('/inspect/lookup-country', ips),
  // Pip 包管理（服务端允许 120s，客户端给 180s 兜底）
  listPipPackages: () => request.get('/inspect/pip-packages'),
  installPip: (pkg) => request.post('/inspect/pip-install', { package: pkg }, { timeout: 180000 }),
  uninstallPip: (pkg) => request.post('/inspect/pip-uninstall', { package: pkg }, { timeout: 180000 }),
  // 自定义指标
  listCustomMetrics: () => request.get('/inspect/custom-metrics'),
  createCustomMetric: (data) => request.post('/inspect/custom-metrics', data),
  updateCustomMetric: (id, data) => request.put(`/inspect/custom-metrics/${id}`, data),
  deleteCustomMetric: (id) => request.delete(`/inspect/custom-metrics/${id}`),
  // 服务器别名
  getServerAliases: () => request.get('/inspect/server-aliases'),
  setServerAliases: (aliases) => request.put('/inspect/server-aliases', aliases),
}

// ── 巡检报告 ──
// 报告生成 = 多脚本 + Prometheus 拉取，远超 30s 默认超时
export const reports = {
  inspection: (params) => request.get('/reports/inspection', { params, timeout: 180000 }),
  getSummaryTemplate: () => request.get('/reports/summary-template'),
  saveSummaryTemplate: (template, config) => request.put('/reports/summary-template', { template, config }),
}

// 巡检报告管理
export const reportMgmt = {
  list: (params) => request.get('/reports', { params }),
  get: (id) => request.get(`/reports/${id}`),
  delete: (id) => request.delete(`/reports/${id}`),
  generate: (params) => request.get('/reports/inspection', { params, timeout: 180000 }),
}


// ── 规则执行记录 ──
export const executionLogs = {
  list: (params) => request.get('/execution-logs', { params }),
  get: (id) => request.get(`/execution-logs/${id}`),
}

// ── 调度器 ──
export const scheduler = {
  status: () => request.get('/scheduler/status'),
}

// ── 首页概览 ──
// 优先走后端聚合接口 GET /dashboard/stats；404 时退回 3 端点拼装（Promise.allSettled，
// 单卡失败不影响其它卡，并返回 per-source 错误信息供 UI 展示）。
export const getDashboardStats = async () => {
  try {
    const res = await request.get('/dashboard/stats')
    const d = res.data || {}
    return {
      addressCount: d.address_count ?? 0,
      ruleCount: d.rule_count ?? 0,
      alertStats: d.alert || {},
      trend: d.trend || [],
      errors: {}
    }
  } catch (e) {
    // 仅在新端点不存在时回退；其它错误继续抛出
    const status = e?.response?.status
    const msg = String(e?.message || '')
    const is404 = status === 404 || msg.includes('404') || msg.includes('Not Found')
    if (!is404) throw e
  }

  // page_size=10：规则列表历史上下限是 ge=10，1 会被 422 拒掉，回退路径就哑了
  const [addrRes, ruleRes, alertRes] = await Promise.allSettled([
    request.get('/addresses', { params: { page_size: 10 } }),
    request.get('/rules', { params: { page_size: 10 } }),
    alerts.stats()
  ])
  const errors = {}
  const pickErr = (r, key) => {
    if (r.status === 'rejected') errors[key] = r.reason?.message || '加载失败'
  }
  pickErr(addrRes, 'addressCount')
  pickErr(ruleRes, 'ruleCount')
  pickErr(alertRes, 'alertStats')
  const alertData = alertRes.status === 'fulfilled' ? (alertRes.value.data || {}) : {}
  return {
    addressCount: addrRes.status === 'fulfilled' ? (addrRes.value.data?.total ?? 0) : 0,
    ruleCount: ruleRes.status === 'fulfilled' ? (ruleRes.value.data?.total ?? 0) : 0,
    alertStats: alertData,
    trend: alertData.trend || [],
    errors
  }
}

// ── 远程接收接口（被动推送） ──
export const remoteApi = {
  listEndpoints: () => request.get('/remote/endpoints'),
  createEndpoint: (name, description) => request.post('/remote/endpoints', { name, description }),
  updateEndpoint: (id, name, description) => request.put(`/remote/endpoints/${id}`, { name, description }),
  deleteEndpoint: (id) => request.delete(`/remote/endpoints/${id}`),
  rotateToken: (id) => request.post(`/remote/endpoints/${id}/rotate-token`),
  listLogs: (id, params) => request.get(`/remote/endpoints/${id}/logs`, { params }),
  clearLogs: (id) => request.delete(`/remote/endpoints/${id}/logs`),
  deleteLog: (id) => request.delete(`/remote/logs/${id}`),
  // 发送方：第一包特征聚出来的人，手动绑定后才进日报
  listSenders: (params) => request.get('/remote/senders', { params }),
  bindSender: (id, displayName) => request.post(`/remote/senders/${id}/bind`, { display_name: displayName }),
  rejectSender: (id) => request.post(`/remote/senders/${id}/reject`),
  unbindSender: (id) => request.post(`/remote/senders/${id}/unbind`),
  deleteSender: (id) => request.delete(`/remote/senders/${id}`),
}

// ── 原始日志查询 ──
export const rawLogs = {
  query: (params) => request.post('/raw-logs/query', params),
  fields: () => request.get('/raw-logs/fields'),
}
