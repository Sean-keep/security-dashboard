<template>
  <div class="page-container">

    <!-- ══ 用户管理 ══ -->
    <el-card shadow="never" class="mb-16" v-if="activeNav === 'users'">
      <template #header>
        <div class="card-header">
          <span class="card-title">用户列表</span>
          <el-button type="primary" size="small" @click="openUserDialog(null)" :disabled="!userStore.isAdmin">
            + 新增用户
          </el-button>
        </div>
      </template>
      <el-table :data="users" stripe size="small">
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="nickname" label="昵称" min-width="100" />
        <el-table-column prop="role" label="角色" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'primary'" size="small">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="login_count" label="登录次数" width="90" align="center" />
        <el-table-column prop="last_login" label="最后登录" width="160" />
        <el-table-column prop="created_at" label="创建时间" width="160" />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openUserDialog(row)">编辑</el-button>
            <el-button type="danger" link size="small"
              :disabled="row.id === userStore.userInfo.id || !userStore.isAdmin"
              @click="deleteUser(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ══ 连接设置（预览列表模式） ══ -->
    <div v-if="activeNav === 'connection'">

      <!-- ES -->
      <el-card shadow="never" class="mb-16">
        <template #header>
          <div class="card-header">
            <span class="card-title">Elasticsearch</span>
            <div class="header-right">
              <el-tag :type="esTestResult?.connected ? 'success' : esTestResult ? 'danger' : 'info'" size="small">
                {{ esTestResult ? (esTestResult.connected ? '已连接' : '未连接') : '未测试' }}
              </el-tag>
              <el-button v-if="!editingEs" type="primary" link size="small" @click="startEditEs">编辑</el-button>
              <template v-else>
                <el-button type="default" size="small" @click="cancelEditEs">取消</el-button>
                <el-button type="primary" size="small" :loading="esSaving" @click="saveEs">保存</el-button>
              </template>
            </div>
          </div>
        </template>
        <!-- 预览模式 -->
        <div v-if="!editingEs" class="conn-preview">
          <div class="preview-row"><span class="preview-label">主机</span><span class="preview-val mono">{{ esForm.es_scheme }}://{{ esForm.es_host || '未配置' }}:{{ esForm.es_port }}</span></div>
          <div class="preview-row"><span class="preview-label">默认索引</span><span class="preview-val mono">{{ esForm.es_index || '未配置' }}</span></div>
          <div class="preview-row"><span class="preview-label">用户名</span><span class="preview-val">{{ esForm.es_user || '-' }}</span></div>
          <div class="preview-row"><span class="preview-label">忽略证书</span><span class="preview-val">{{ esForm.es_verify_certs === 'false' ? '是' : '否' }}</span></div>
        </div>
        <!-- 编辑模式 -->
        <el-form v-else :model="esForm" label-width="100px" size="default">
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="主机地址"><el-input v-model="esForm.es_host" placeholder="35.241.110.62" /></el-form-item></el-col>
            <el-col :span="4"><el-form-item label="协议"><el-select v-model="esForm.es_scheme" style="width:100%"><el-option label="HTTPS" value="https" /><el-option label="HTTP" value="http" /></el-select></el-form-item></el-col>
            <el-col :span="4"><el-form-item label="端口"><el-input-number v-model="esForm.es_port" :min="1" :max="65535" style="width:100%" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="默认索引"><el-input v-model="esForm.es_index" placeholder="security-logs-*" /></el-form-item></el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="用户名"><el-input v-model="esForm.es_user" placeholder="elastic" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="密码"><el-input v-model="esForm.es_password" type="password" show-password placeholder="密码" /></el-form-item></el-col>
            <el-col :span="4"><el-form-item label="忽略证书"><el-switch v-model="esForm.es_verify_certs" active-value="false" inactive-value="true" /></el-form-item></el-col>
          </el-row>
        </el-form>
        <div v-if="editingEs" class="card-footer">
          <el-button size="small" :loading="esTesting" @click="testEs">测试连接</el-button>
          <span v-if="esTestResult" class="test-msg" :class="esTestResult.connected ? 'ok' : 'fail'">{{ esTestResult.connected ? `连接成功 (${esTestResult.latency_ms ?? '?'}ms)` : `失败: ${esTestResult.error}` }}</span>
        </div>
      </el-card>

      <!-- MySQL -->
      <el-card shadow="never" class="mb-16">
        <template #header>
          <div class="card-header">
            <span class="card-title">MySQL</span>
            <div class="header-right">
              <el-tag :type="mysqlTestResult?.connected ? 'success' : mysqlTestResult ? 'danger' : 'info'" size="small">
                {{ mysqlTestResult ? (mysqlTestResult.connected ? '已连接' : '未连接') : '未测试' }}
              </el-tag>
              <el-button v-if="!editingMysql" type="primary" link size="small" @click="startEditMysql">编辑</el-button>
              <template v-else>
                <el-button type="default" size="small" @click="cancelEditMysql">取消</el-button>
                <el-button type="primary" size="small" :loading="mysqlSaving" @click="saveMysql">保存</el-button>
              </template>
            </div>
          </div>
        </template>
        <div v-if="!editingMysql" class="conn-preview">
          <div class="preview-row"><span class="preview-label">主机</span><span class="preview-val mono">{{ mysqlForm.mysql_host || '未配置' }}:{{ mysqlForm.mysql_port }}</span></div>
          <div class="preview-row"><span class="preview-label">数据库</span><span class="preview-val mono">{{ mysqlForm.mysql_database || '未配置' }}</span></div>
          <div class="preview-row"><span class="preview-label">用户名</span><span class="preview-val">{{ mysqlForm.mysql_user || '-' }}</span></div>
        </div>
        <el-form v-else :model="mysqlForm" label-width="100px" size="default">
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="主机地址"><el-input v-model="mysqlForm.mysql_host" placeholder="localhost" /></el-form-item></el-col>
            <el-col :span="4"><el-form-item label="端口"><el-input-number v-model="mysqlForm.mysql_port" :min="1" :max="65535" style="width:100%" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="数据库名"><el-input v-model="mysqlForm.mysql_database" placeholder="security_dashboard" /></el-form-item></el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8"><el-form-item label="用户名"><el-input v-model="mysqlForm.mysql_user" placeholder="root" /></el-form-item></el-col>
            <el-col :span="8"><el-form-item label="密码"><el-input v-model="mysqlForm.mysql_password" type="password" show-password placeholder="密码" /></el-form-item></el-col>
          </el-row>
        </el-form>
        <div v-if="editingMysql" class="card-footer">
          <el-button size="small" :loading="mysqlTesting" @click="testMysql">测试连接</el-button>
          <span v-if="mysqlTestResult" class="test-msg" :class="mysqlTestResult.connected ? 'ok' : 'fail'">{{ mysqlTestResult.connected ? `连接成功 (${mysqlTestResult.latency_ms ?? '?'}ms)` : `失败: ${mysqlTestResult.error}` }}</span>
        </div>
      </el-card>

      <!-- Grafana -->
      <el-card shadow="never" class="mb-16">
        <template #header>
          <div class="card-header">
            <span class="card-title">Grafana</span>
            <div class="header-right">
              <el-tag :type="grafanaTestResult?.connected ? 'success' : grafanaTestResult ? 'danger' : 'info'" size="small">
                {{ grafanaTestResult ? (grafanaTestResult.connected ? '已连接' : '未连接') : '未测试' }}
              </el-tag>
              <el-button v-if="!editingGrafana" type="primary" link size="small" @click="startEditGrafana">编辑</el-button>
              <template v-else>
                <el-button type="default" size="small" @click="cancelEditGrafana">取消</el-button>
                <el-button type="primary" size="small" :loading="grafanaSaving" @click="saveGrafana">保存</el-button>
              </template>
            </div>
          </div>
        </template>
        <div v-if="!editingGrafana" class="conn-preview">
          <div class="preview-row"><span class="preview-label">服务地址</span><span class="preview-val mono">{{ grafanaForm.grafana_url || '未配置' }}</span></div>
          <div class="preview-row"><span class="preview-label">认证方式</span><span class="preview-val">{{ grafanaForm.grafana_auth_mode === 'apikey' ? 'API Key' : '用户名+密码' }}</span></div>
          <div v-if="grafanaForm.grafana_auth_mode === 'apikey'" class="preview-row"><span class="preview-label">API Key</span><span class="preview-val">{{ grafanaForm.grafana_api_key ? '********' : '-' }}</span></div>
        </div>
        <el-form v-else :model="grafanaForm" label-width="100px" size="default">
          <el-form-item label="服务地址"><el-input v-model="grafanaForm.grafana_url" placeholder="http://localhost:3000" /></el-form-item>
          <el-form-item label="认证方式">
            <el-radio-group v-model="grafanaForm.grafana_auth_mode" size="default">
              <el-radio value="apikey">API Key（推荐）</el-radio>
              <el-radio value="basic">用户名 + 密码</el-radio>
            </el-radio-group>
          </el-form-item>
          <template v-if="grafanaForm.grafana_auth_mode === 'apikey'">
            <el-form-item label="API Key"><el-input v-model="grafanaForm.grafana_api_key" placeholder="Grafana API Key" type="password" show-password /></el-form-item>
          </template>
          <template v-else>
            <el-row :gutter="16">
              <el-col :span="8"><el-form-item label="用户名"><el-input v-model="grafanaForm.grafana_user" placeholder="Grafana 用户名" /></el-form-item></el-col>
              <el-col :span="8"><el-form-item label="密码"><el-input v-model="grafanaForm.grafana_password" type="password" show-password placeholder="Grafana 密码" /></el-form-item></el-col>
            </el-row>
          </template>
        </el-form>
        <div v-if="editingGrafana" class="card-footer">
          <el-button size="small" :loading="grafanaTesting" @click="testGrafana">测试连接</el-button>
          <span v-if="grafanaTestResult" class="test-msg" :class="grafanaTestResult.connected ? 'ok' : 'fail'">
            {{ grafanaTestResult.connected
              ? `连接成功${grafanaTestResult.version ? ` (v${grafanaTestResult.version})` : ''}`
              : `失败: ${grafanaTestResult.stage === 'auth_invalid' ? 'Token无效（请检查Key是否过期）' : grafanaTestResult.stage === 'auth_forbidden' ? '代理/CDN拦截（建议直接IP访问）' : (grafanaTestResult.error || '连接失败')}` }}
          </span>
        </div>
      </el-card>

    </div><!-- /connection -->

    <!-- ══ 安全设置 ══ -->
    <el-card shadow="never" class="mb-16" v-if="activeNav === 'security'">
      <template #header>
        <div class="card-header">
          <span class="card-title">登录安全策略</span>
        </div>
      </template>
      <el-form :model="securityForm" label-width="140px" size="default" style="max-width:560px">
        <el-form-item label="登录最大尝试次数">
          <el-input-number v-model="securityForm.login_max_attempts" :min="1" :max="20" />
          <span class="form-hint">连续失败超过此次数后，账户被临时锁定</span>
        </el-form-item>
        <el-form-item label="登录锁定时长">
          <el-input-number v-model="securityForm.login_lockout_minutes" :min="1" :max="1440" />
          <span class="form-hint">锁定后等待多少分钟自动解除（分钟）</span>
        </el-form-item>
      </el-form>
      <div class="card-footer">
        <el-button type="primary" size="small" :loading="securitySaving" @click="saveSecurity">保存策略</el-button>
        <span v-if="securitySaved" class="test-msg ok">保存成功</span>
      </div>
    </el-card>

    <!-- ══ 登录日志 ══ -->
    <el-card shadow="never" class="mb-16" v-if="activeNav === 'logs'">
      <template #header>
        <div class="card-header">
          <span class="card-title">日志中心</span>
          <div class="header-right">
            <el-select v-model="logTypeFilter" size="small" style="width:130px" @change="logPage=1;loadLogs()">
              <el-option label="全部日志" value="" />
              <el-option label="登录日志" value="login" />
              <el-option label="操作日志" value="operation" />
            </el-select>
          </div>
        </div>
      </template>
      <el-table :data="logList" stripe size="small">
        <el-table-column prop="created_at" label="时间" width="170" />
        <el-table-column prop="log_type" label="类型" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.log_type === 'login' ? 'primary' : 'warning'" size="small">
              {{ row.log_type === 'login' ? '登录' : '操作' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户名" width="120" />
        <el-table-column prop="action" label="操作" min-width="180" show-overflow-tooltip />
        <el-table-column prop="target" label="对象" width="150" show-overflow-tooltip />
        <el-table-column prop="ip_address" label="IP地址" width="140" />
        <el-table-column prop="status" label="结果" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
              {{ row.status === 'success' ? '成功' : '失败' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" min-width="160" show-overflow-tooltip />
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="logPage"
          :page-size="20"
          :total="logTotal"
          layout="total, prev, pager, next"
          @current-change="loadLogs"
        />
      </div>
    </el-card>

  </div><!-- /page-container -->

  <!-- 用户编辑弹窗 -->
  <el-dialog v-model="userDialogVisible" :title="isUserEdit ? '编辑用户' : '新增用户'" width="460px" destroy-on-close>
    <el-form ref="userFormRef" :model="userForm" :rules="userRules" label-width="90px" size="default">
      <el-form-item label="用户名" prop="username">
        <el-input v-model="userForm.username" :disabled="isUserEdit" placeholder="登录用户名" />
      </el-form-item>
      <el-form-item :label="isUserEdit ? '新密码' : '密码'" :prop="isUserEdit ? '' : 'password'">
        <el-input v-model="userForm.password" type="password" show-password :placeholder="isUserEdit ? '留空则不修改' : '请输入密码'" />
      </el-form-item>
      <el-form-item label="昵称" prop="nickname">
        <el-input v-model="userForm.nickname" placeholder="显示名称" />
      </el-form-item>
      <el-form-item label="角色" prop="role">
        <el-select v-model="userForm.role" style="width:100%">
          <el-option label="管理员" value="admin" />
          <el-option label="操作员" value="operator" />
          <el-option label="查看者" value="viewer" />
        </el-select>
      </el-form-item>
      <el-form-item label="启用状态">
        <el-switch v-model="userForm.is_active" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="userDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="userSaveLoading" @click="submitUser">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { settings } from '@/api'
import { useUserStore } from '@/store/user'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

// ── 导航 ──
const validTabs = ['users', 'connection', 'security', 'logs']
const activeNav = computed(() => {
  const seg = route.path.split('/').pop()
  return validTabs.includes(seg) ? seg : 'users'
})

// ── 用户管理 ──
const users = ref([])
const userDialogVisible = ref(false)
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

const roleLabel = (r) => ({ admin: '管理员', operator: '操作员', viewer: '查看者' }[r] || r)

const loadUsers = async () => {
  try { users.value = (await settings.users()).data } catch (e) { ElMessage.error('加载用户失败') }
}

const openUserDialog = (row) => {
  if (row) {
    isUserEdit.value = true; editUserId.value = row.id
    userForm.value = { username: row.username, password: '', nickname: row.nickname, role: row.role, is_active: row.is_active }
  } else {
    isUserEdit.value = false; editUserId.value = null
    userForm.value = { username: '', password: '', nickname: '', role: 'operator', is_active: true }
  }
  userDialogVisible.value = true
}

const submitUser = async () => {
  try {
    await userFormRef.value.validate()
  } catch (_) {
    return  // 表单验证失败，el-form 自动显示字段错误
  }
  userSaveLoading.value = true
  try {
    const payload = { ...userForm.value }
    if (isUserEdit.value) {
      if (!payload.password) delete payload.password
      await settings.updateUser(editUserId.value, payload)
      ElMessage.success('用户更新成功')
    } else {
      await settings.createUser(payload)
      ElMessage.success('用户创建成功')
    }
    userDialogVisible.value = false
    loadUsers()
  } catch (e) {
    // axios 拦截器已经 showMessage 了，这里仅作兜底
    console.error('submitUser error:', e)
  } finally {
    userSaveLoading.value = false
  }
}

const deleteUser = (row) => {
  ElMessageBox.confirm(`确定删除用户「${row.username}」？`, '确认', { type: 'warning' })
    .then(async () => { await settings.deleteUser(row.id); ElMessage.success('删除成功'); loadUsers() })
    .catch(() => {})
}

// ── 连接配置 ──
const esForm = reactive({ es_host: '', es_port: 9200, es_scheme: 'https', es_verify_certs: 'false', es_user: '', es_password: '', es_index: 'security-logs-*' })
const mysqlForm = reactive({ mysql_host: '', mysql_port: 3306, mysql_user: '', mysql_password: '', mysql_database: '' })
const grafanaForm = reactive({ grafana_url: '', grafana_auth_mode: 'apikey', grafana_api_key: '', grafana_user: '', grafana_password: '' })

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
    Object.values(groups).forEach(arr => arr.forEach(item => { flat[item.key] = item.value }))

    if (flat.es_host !== undefined) esForm.es_host = flat.es_host
    if (flat.es_port !== undefined) esForm.es_port = parseInt(flat.es_port)
    if (flat.es_scheme !== undefined) esForm.es_scheme = flat.es_scheme
    if (flat.es_verify_certs !== undefined) esForm.es_verify_certs = flat.es_verify_certs
    if (flat.es_user !== undefined) esForm.es_user = flat.es_user
    if (flat.es_password !== undefined) esForm.es_password = flat.es_password
    if (flat.es_index !== undefined) esForm.es_index = flat.es_index

    if (flat.mysql_host !== undefined) mysqlForm.mysql_host = flat.mysql_host
    if (flat.mysql_port !== undefined) mysqlForm.mysql_port = parseInt(flat.mysql_port)
    if (flat.mysql_user !== undefined) mysqlForm.mysql_user = flat.mysql_user
    if (flat.mysql_password !== undefined) mysqlForm.mysql_password = flat.mysql_password
    if (flat.mysql_database !== undefined) mysqlForm.mysql_database = flat.mysql_database

    if (flat.grafana_url !== undefined) grafanaForm.grafana_url = flat.grafana_url
    if (flat.grafana_auth_mode !== undefined) grafanaForm.grafana_auth_mode = flat.grafana_auth_mode
    if (flat.grafana_api_key !== undefined) grafanaForm.grafana_api_key = flat.grafana_api_key
    if (flat.grafana_user !== undefined) grafanaForm.grafana_user = flat.grafana_user
    if (flat.grafana_password !== undefined) grafanaForm.grafana_password = flat.grafana_password

    if (flat.login_max_attempts !== undefined) securityForm.login_max_attempts = parseInt(flat.login_max_attempts)
    if (flat.login_lockout_minutes !== undefined) securityForm.login_lockout_minutes = parseInt(flat.login_lockout_minutes)
  } catch (e) {}
}

const saveEs = async () => {
  esSaving.value = true
  try {
    await settings.saveConfig({ es_host: esForm.es_host, es_port: String(esForm.es_port), es_scheme: esForm.es_scheme, es_verify_certs: esForm.es_verify_certs, es_user: esForm.es_user, es_password: esForm.es_password, es_index: esForm.es_index })
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
  try { await settings.saveConfig({ mysql_host: mysqlForm.mysql_host, mysql_port: String(mysqlForm.mysql_port), mysql_user: mysqlForm.mysql_user, mysql_password: mysqlForm.mysql_password, mysql_database: mysqlForm.mysql_database }); ElMessage.success('MySQL 配置已保存'); editingMysql.value = false }
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
  try { await settings.saveConfig({ grafana_url: grafanaForm.grafana_url, grafana_auth_mode: grafanaForm.grafana_auth_mode, grafana_api_key: grafanaForm.grafana_api_key, grafana_user: grafanaForm.grafana_user, grafana_password: grafanaForm.grafana_password }); ElMessage.success('Grafana 配置已保存'); editingGrafana.value = false }
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

onMounted(() => { loadUsers(); loadConfig(); loadLogs() })
</script>

<style lang="scss" scoped>
.page-container { }

.mb-16 { margin-bottom: 16px; }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.conn-preview {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px 24px;
}
.preview-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.preview-label {
  font-size: 13px;
  color: #909399;
  min-width: 56px;
  flex-shrink: 0;
}
.preview-val {
  font-size: 13px;
  color: #303133;
  word-break: break-all;
}
.preview-val.mono {
  font-family: 'Courier New', monospace;
  color: #409EFF;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 12px;
  border-top: 1px solid #f0f0f0;
}

.test-msg {
  font-size: 13px;
  margin-left: 4px;
  &.ok { color: #67c23a; }
  &.fail { color: #f56c6c; }
}

.form-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
