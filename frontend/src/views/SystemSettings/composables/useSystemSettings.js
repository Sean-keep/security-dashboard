import { ref, reactive } from 'vue'
import { settings } from '@/api'
import { useUserStore } from '@/store/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { roleLabel } from '@/config/roles'

// ── 用户管理（账号钥匙 / 授权钥匙分开） ──
const users = ref([])
const accountDialogVisible = ref(false)
const roleDialogVisible = ref(false)
const isUserEdit = ref(false)
const editUserId = ref(null)
const userSaveLoading = ref(false)
const userFormRef = ref()
const userForm = ref({ username: '', password: '', nickname: '', role: 'operator', is_active: true })
const userRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, message: '密码至少6位', trigger: 'blur' }],
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }]
}

const roleTarget = ref(null)
const roleForm = ref({ role: 'operator' })

const loadUsers = async () => {
  try { users.value = (await settings.users()).data || [] } catch (e) { /* 无权时静默；UserPanel 有提示 */ }
}

// 账号资料：昵称 / 密码 / 启用。**不含角色** —— 那是授权的活。
const openAccountDialog = (row) => {
  if (row) {
    isUserEdit.value = true; editUserId.value = row.id
    userForm.value = { username: row.username, password: '', nickname: row.nickname, is_active: row.is_active }
  } else {
    isUserEdit.value = false; editUserId.value = null
    userForm.value = { username: '', password: '', nickname: '', role: 'operator', is_active: true }
  }
  accountDialogVisible.value = true
}

const submitAccount = async () => {
  try {
    await userFormRef.value.validate()
  } catch (_) {
    return  // 表单验证失败，el-form 自动显示字段错误
  }
  userSaveLoading.value = true
  try {
    if (isUserEdit.value) {
      const payload = {
        nickname: userForm.value.nickname,
        is_active: userForm.value.is_active,
      }
      if (userForm.value.password) payload.password = userForm.value.password
      await settings.updateUser(editUserId.value, payload)
      ElMessage.success('账号更新成功')
    } else {
      await settings.createUser({ ...userForm.value })
      ElMessage.success('用户创建成功')
    }
    accountDialogVisible.value = false
    loadUsers()
  } catch (e) {
    // axios 拦截器已经 showMessage 了，这里仅作兜底
    console.error('submitAccount error:', e)
  } finally {
    userSaveLoading.value = false
  }
}

// 授权：只改角色。安全管理员的钥匙，系统管理员也开不了这扇门。
const openRoleDialog = (row) => {
  roleTarget.value = row
  roleForm.value = { role: row.role }
  roleDialogVisible.value = true
}

const submitRole = async () => {
  if (!roleTarget.value) return
  userSaveLoading.value = true
  try {
    await settings.updateUserRole(roleTarget.value.id, roleForm.value.role)
    ElMessage.success('角色已更新')
    roleDialogVisible.value = false
    loadUsers()
  } catch (e) {
    console.error('submitRole error:', e)
  } finally {
    userSaveLoading.value = false
  }
}

const deleteUser = (row) => {
  ElMessageBox.confirm(`确定删除用户「${row.username}」？`, '确认', { type: 'warning' })
    .then(async () => {
      await settings.deleteUser(row.id)
      ElMessage.success('删除成功')
      loadUsers()
    })
    .catch(() => {})
}

// ── 连接配置 ──
const esForm = reactive({ es_host: '', es_port: 9200, es_scheme: 'https', es_verify_certs: 'false', es_user: '', es_password: '', es_index: 'security-logs-*' })
const mysqlForm = reactive({ mysql_host: '', mysql_port: 3306, mysql_user: '', mysql_password: '', mysql_database: '' })
const grafanaForm = reactive({ grafana_url: '', grafana_auth_mode: 'apikey', grafana_api_key: '', grafana_user: '', grafana_password: '' })
// 后端对 secret 键脱敏为 ""，另给 secret_set 布尔。UI 用它显示「已配置，留空保持不变」，
// 绝不伪造 ******** 当作值；保存时空字符串=保持原值（后端约定）。
const secretSet = reactive({ es_password: false, mysql_password: false, grafana_api_key: false, grafana_password: false })

const esSaving = ref(false), esTesting = ref(false), esTestResult = ref(null)
const mysqlSaving = ref(false), mysqlTesting = ref(false), mysqlTestResult = ref(null)
const grafanaSaving = ref(false), grafanaTesting = ref(false), grafanaTestResult = ref(null)

// 连接编辑状态（预览 → 编辑模式切换）
const editingEs = ref(false), editingMysql = ref(false), editingGrafana = ref(false)
// 缓存原始值（取消时恢复）
const esBackup = ref({}), mysqlBackup = ref({}), grafanaBackup = ref({})

const startEditEs = () => { esBackup.value = { ...esForm }; editingEs.value = true }
const cancelEditEs = () => { Object.assign(esForm, esBackup.value); editingEs.value = false }
const startEditMysql = () => { mysqlBackup.value = { ...mysqlForm }; editingMysql.value = true }
const cancelEditMysql = () => { Object.assign(mysqlForm, mysqlBackup.value); editingMysql.value = false }
const startEditGrafana = () => { grafanaBackup.value = { ...grafanaForm }; editingGrafana.value = true }
const cancelEditGrafana = () => { Object.assign(grafanaForm, grafanaBackup.value); editingGrafana.value = false }

const loadConfig = async () => {
  try {
    const res = await settings.getConfig()
    const groups = res.data || {}
    const flat = {}
    const flags = {}
    Object.values(groups).forEach(arr => arr.forEach(item => {
      flat[item.key] = item.value
      if (item.secret_set !== undefined) flags[item.key] = !!item.secret_set
    }))
    // es-default 顶层 password_set 兼容
    if (res.data?.password_set !== undefined) flags.es_password = !!res.data.password_set

    if (flat.es_host !== undefined) esForm.es_host = flat.es_host
    if (flat.es_port !== undefined) esForm.es_port = parseInt(flat.es_port)
    if (flat.es_scheme !== undefined) esForm.es_scheme = flat.es_scheme
    if (flat.es_verify_certs !== undefined) esForm.es_verify_certs = flat.es_verify_certs
    if (flat.es_user !== undefined) esForm.es_user = flat.es_user
    // secret 值后端恒为 ""；只记录是否已配置，不把伪造值塞进表单
    esForm.es_password = ''
    secretSet.es_password = flags.es_password ?? false
    if (flat.es_index !== undefined) esForm.es_index = flat.es_index

    if (flat.mysql_host !== undefined) mysqlForm.mysql_host = flat.mysql_host
    if (flat.mysql_port !== undefined) mysqlForm.mysql_port = parseInt(flat.mysql_port)
    if (flat.mysql_user !== undefined) mysqlForm.mysql_user = flat.mysql_user
    mysqlForm.mysql_password = ''
    secretSet.mysql_password = flags.mysql_password ?? false
    if (flat.mysql_database !== undefined) mysqlForm.mysql_database = flat.mysql_database

    if (flat.grafana_url !== undefined) grafanaForm.grafana_url = flat.grafana_url
    if (flat.grafana_auth_mode !== undefined) grafanaForm.grafana_auth_mode = flat.grafana_auth_mode
    grafanaForm.grafana_api_key = ''
    secretSet.grafana_api_key = flags.grafana_api_key ?? false
    if (flat.grafana_user !== undefined) grafanaForm.grafana_user = flat.grafana_user
    grafanaForm.grafana_password = ''
    secretSet.grafana_password = flags.grafana_password ?? false

    if (flat.login_max_attempts !== undefined) securityForm.login_max_attempts = parseInt(flat.login_max_attempts)
    if (flat.login_lockout_minutes !== undefined) securityForm.login_lockout_minutes = parseInt(flat.login_lockout_minutes)
  } catch (e) {}
}

// secret 字段 placeholder：已配置且当前为空时提示「留空保持不变」
const secretPlaceholder = (key, fallback) => (secretSet[key] ? '已配置，留空保持不变' : fallback)

const saveEs = async () => {
  esSaving.value = true
  try {
    await settings.saveConfig({ es_host: esForm.es_host, es_port: String(esForm.es_port), es_scheme: esForm.es_scheme, es_verify_certs: esForm.es_verify_certs, es_user: esForm.es_user, es_password: esForm.es_password, es_index: esForm.es_index })
    if (esForm.es_password) secretSet.es_password = true
    esForm.es_password = ''  // 保存后立刻丢弃手输的明文，不留表单内存
    ElMessage.success('ES 配置已保存')
    editingEs.value = false  // 保存后跳转回预览模式
  } catch (e) { ElMessage.error('保存失败') }
  finally { esSaving.value = false }
}
const testEs = async () => {
  esTesting.value = true; esTestResult.value = null
  try { const r = await settings.testEs(); esTestResult.value = r.data } catch (e) { esTestResult.value = { connected: false, error: e?.response?.data?.msg || '请求失败' } }
  finally { esTesting.value = false }
}

const saveMysql = async () => {
  mysqlSaving.value = true
  try {
    await settings.saveConfig({ mysql_host: mysqlForm.mysql_host, mysql_port: String(mysqlForm.mysql_port), mysql_user: mysqlForm.mysql_user, mysql_password: mysqlForm.mysql_password, mysql_database: mysqlForm.mysql_database })
    if (mysqlForm.mysql_password) secretSet.mysql_password = true
    mysqlForm.mysql_password = ''
    ElMessage.success('MySQL 配置已保存')
    editingMysql.value = false
  }
  catch (e) { ElMessage.error('保存失败') }
  finally { mysqlSaving.value = false }
}
const testMysql = async () => {
  mysqlTesting.value = true; mysqlTestResult.value = null
  try { const r = await settings.testMysql(); mysqlTestResult.value = r.data } catch (e) { mysqlTestResult.value = { connected: false, error: e?.response?.data?.msg || '请求失败' } }
  finally { mysqlTesting.value = false }
}

const saveGrafana = async () => {
  grafanaSaving.value = true
  try {
    await settings.saveConfig({ grafana_url: grafanaForm.grafana_url, grafana_auth_mode: grafanaForm.grafana_auth_mode, grafana_api_key: grafanaForm.grafana_api_key, grafana_user: grafanaForm.grafana_user, grafana_password: grafanaForm.grafana_password })
    if (grafanaForm.grafana_api_key) secretSet.grafana_api_key = true
    if (grafanaForm.grafana_password) secretSet.grafana_password = true
    grafanaForm.grafana_api_key = ''
    grafanaForm.grafana_password = ''
    ElMessage.success('Grafana 配置已保存')
    editingGrafana.value = false
  }
  catch (e) { ElMessage.error('保存失败') }
  finally { grafanaSaving.value = false }
}
const testGrafana = async () => {
  grafanaTesting.value = true; grafanaTestResult.value = null
  try { const r = await settings.testGrafana(); grafanaTestResult.value = r.data } catch (e) { grafanaTestResult.value = { connected: false, error: e?.response?.data?.msg || '请求失败' } }
  finally { grafanaTesting.value = false }
}

// ── 安全设置 ──
const securityForm = reactive({ login_max_attempts: 5, login_lockout_minutes: 15 })
const securitySaving = ref(false)
const securitySaved = ref(false)

const saveSecurity = async () => {
  securitySaving.value = true; securitySaved.value = false
  try {
    await settings.saveConfig({ login_max_attempts: String(securityForm.login_max_attempts), login_lockout_minutes: String(securityForm.login_lockout_minutes) })
    securitySaved.value = true
    setTimeout(() => { securitySaved.value = false }, 2500)
  } catch (e) { ElMessage.error('保存失败') }
  finally { securitySaving.value = false }
}

// ── 日志中心 ──
const logList = ref([]), logTotal = ref(0), logPage = ref(1), logTypeFilter = ref('')
const loadLogs = async () => {
  try {
    const params = { page: logPage.value }
    if (logTypeFilter.value) params.log_type = logTypeFilter.value
    const r = await settings.logs(params)
    logList.value = r.data.list || r.data.items || []
    logTotal.value = r.data.total || 0
  } catch (e) {}
}

export function useSystemSettings() {
  const userStore = useUserStore()

  return {
    userStore,
    // users
    users,
    accountDialogVisible,
    roleDialogVisible,
    isUserEdit,
    editUserId,
    userSaveLoading,
    userFormRef,
    userForm,
    userRules,
    roleTarget,
    roleForm,
    roleLabel,
    loadUsers,
    openAccountDialog,
    openRoleDialog,
    submitAccount,
    submitRole,
    deleteUser,
    // connection
    esForm,
    mysqlForm,
    grafanaForm,
    secretSet,
    secretPlaceholder,
    esSaving,
    esTesting,
    esTestResult,
    mysqlSaving,
    mysqlTesting,
    mysqlTestResult,
    grafanaSaving,
    grafanaTesting,
    grafanaTestResult,
    editingEs,
    editingMysql,
    editingGrafana,
    startEditEs,
    cancelEditEs,
    startEditMysql,
    cancelEditMysql,
    startEditGrafana,
    cancelEditGrafana,
    loadConfig,
    saveEs,
    testEs,
    saveMysql,
    testMysql,
    saveGrafana,
    testGrafana,
    // security
    securityForm,
    securitySaving,
    securitySaved,
    saveSecurity,
    // logs
    logList,
    logTotal,
    logPage,
    logTypeFilter,
    loadLogs
  }
}
