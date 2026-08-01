import request from './request'

// ── 认证 ──
export const auth = {
  login: (data) => request.post('/auth/login', data),
  me: () => request.get('/auth/me'),
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
  esIndices: () => request.get('/rules/es-indices')
}

// ── 告警列表 ──
export const alerts = {
  list: (params) => request.get('/alerts', { params }),
  stats: () => request.get('/alerts/stats'),
  get: (id) => request.get(`/alerts/${id}`),
  update: (id, data) => request.put(`/alerts/${id}`, data),
  delete: (id) => request.delete(`/alerts/${id}`),
  batchUpdate: (ids, status) => request.post('/alerts/batch-update', { ids, status }),
  batchDelete: (ids) => request.post('/alerts/batch-delete', { ids })
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
export const inspectApi = {
  // Scripts
  listScripts: () => request.get('/inspect/scripts'),
  createScript: (data) => request.post('/inspect/scripts', data),
  updateScript: (id, data) => request.put(`/inspect/scripts/${id}`, data),
  deleteScript: (id) => request.delete(`/inspect/scripts/${id}`),
  executeScripts: (ids) => request.post('/inspect/scripts/execute', { script_ids: ids }),
  executeAdhoc: (type, script) => request.post('/inspect/execute', { type, script }),
  // Traffic
  traffic: (params) => request.post('/inspect/traffic', params),
  // Grafana
  grafanaMetrics: (params) => request.get('/inspect/grafana-metrics', { params }),
  // VirusTotal
  lookupCountry: (ips) => request.post('/inspect/lookup-country', ips),
  // Pip 包管理
  listPipPackages: () => request.get('/inspect/pip-packages'),
  installPip: (pkg) => request.post('/inspect/pip-install', { package: pkg }),
  uninstallPip: (pkg) => request.post('/inspect/pip-uninstall', { package: pkg }),
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
export const reports = {
  inspection: (params) => request.get('/reports/inspection', { params }),
}

// 宸℃鎶ュ憡绠＄悊
export const reportMgmt = {
  list: (params) => request.get('/reports', { params }),
  get: (id) => request.get(`/reports/${id}`),
  delete: (id) => request.delete(`/reports/${id}`),
  generate: (params) => request.get('/reports/inspection', { params }),
}


// ── 规则执行记录 ──
export const executionLogs = {
  list: (params) => request.get('/execution-logs', { params }),
  get: (id) => request.get(`/execution-logs/${id}`),
}

// ── 首页概览 ──
export const getDashboardStats = () => Promise.all([
  request.get('/addresses', { params: { page_size: 1 } }),
  request.get('/rules', { params: { page_size: 10 } }),
  alerts.stats()
]).then(([addrRes, ruleRes, alertRes]) => ({
  addressCount: addrRes.data.total,
  ruleCount: ruleRes.data.total,
  alertStats: alertRes.data
}))

// ── 远程接收接口（被动推送） ──
export const remoteApi = {
  listEndpoints: () => request.get('/remote/endpoints'),
  createEndpoint: (name, description) => request.post('/remote/endpoints', { name, description }),
  updateEndpoint: (id, description) => request.put(`/remote/endpoints/${id}`, { description }),
  deleteEndpoint: (id) => request.delete(`/remote/endpoints/${id}`),
  listLogs: (id, params) => request.get(`/remote/endpoints/${id}/logs`, { params }),
  clearLogs: (id) => request.delete(`/remote/endpoints/${id}/logs`),
  deleteLog: (id) => request.delete(`/remote/logs/${id}`),
}
