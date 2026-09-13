<template>
  <div class="page-container">
    <!-- 顶部操作栏 -->
    <div class="action-bar">
      <div class="action-left">
        <h2 class="page-title">脚本管理</h2>
        <span class="script-count">共 {{ scripts.length }} 个脚本</span>
      </div>
      <div class="action-right">
        <el-button type="primary" @click="openToolDialog">
          <el-icon><Lightning /></el-icon> 执行与依赖
        </el-button>
        <el-button type="success" @click="openCreate">
          <el-icon><Plus /></el-icon> 新增脚本
        </el-button>
      </div>
    </div>

    <!-- 脚本列表 -->
    <el-card shadow="never" class="main-card">
      <el-table :data="scripts" border stripe>
        <el-table-column type="index" label="序号" width="70" align="center" />
        <el-table-column prop="name" label="脚本名称" min-width="180">
          <template #default="{ row }">
            <div class="script-name">
              <el-icon class="script-icon" :class="row.script_type">
                <Document />
              </el-icon>
              <span>{{ row.name }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="script_type" label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.script_type === 'python' ? 'success' : 'info'" size="small">
              {{ row.script_type === 'python' ? 'Python' : 'Shell' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="250" show-overflow-tooltip />
        <el-table-column label="操作" width="250" fixed="right" align="center">
          <template #default="{ row }">
            <div class="table-actions">
              <el-checkbox v-model="selectedScripts" :value="row.id">选中</el-checkbox>
              <el-button type="primary" link size="small" @click="editScript(row)">
                <el-icon><Edit /></el-icon> 编辑
              </el-button>
              <el-button type="danger" link size="small" @click="removeScript(row.id)">
                <el-icon><Delete /></el-icon> 删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- 执行选中脚本 -->
      <div v-if="selectedScripts.length > 0" class="exec-bar">
        <el-button type="success" size="large" @click="runSelectedScripts">
          <el-icon><VideoPlay /></el-icon>
          执行选中脚本 ({{ selectedScripts.length }} 个)
        </el-button>
      </div>
    </el-card>

    <!-- 执行结果 -->
    <el-card v-if="execResults.length > 0" shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">执行结果</span>
          <el-button text size="small" @click="execResults = []">清空结果</el-button>
        </div>
      </template>
      <div v-for="r in execResults" :key="r.id" class="result-item">
        <div class="result-header">
          <div class="result-title">
            <el-icon><Document /></el-icon>
            <strong>{{ r.name }}</strong>
          </div>
          <el-tag :type="r.exit_code === 0 ? 'success' : 'danger'" size="small">
            {{ r.exit_code === 0 ? '成功' : '失败' }} (exit: {{ r.exit_code ?? '?' }})
          </el-tag>
        </div>
        <div class="result-body">
          <pre class="code-block"><code>{{ r.stdout || r.stderr || '(无输出)' }}</code></pre>
        </div>
      </div>
    </el-card>

    <!-- 脚本编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑脚本' : '新增脚本'"
      width="80%"
      top="5vh"
      destroy-on-close
      class="script-dialog"
    >
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="100px">
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="脚本名称" prop="name">
              <el-input v-model="form.name" placeholder="输入脚本名称" size="large" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="脚本类型" prop="script_type">
              <el-select v-model="form.script_type" style="width:100%" size="large">
                <el-option value="python" label="Python" />
                <el-option value="shell" label="Shell" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="脚本描述">
          <el-input v-model="form.description" placeholder="描述脚本功能" size="large" />
        </el-form-item>
        <el-form-item label="代码内容" prop="content">
          <div class="code-editor-wrapper">
            <div class="code-toolbar">
              <span class="code-lang">{{ form.script_type === 'python' ? 'Python' : 'Shell' }}</span>
              <el-button text size="small" @click="formatCode">格式化</el-button>
            </div>
            <el-input
              v-model="form.content"
              type="textarea"
              :rows="20"
              placeholder="# 在此编写代码..."
              class="code-textarea"
            />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="large" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" size="large" :loading="saveLoading" @click="submitForm">
          <el-icon><Check /></el-icon> 保存脚本
        </el-button>
      </template>
    </el-dialog>

    <!-- 执行与依赖对话框 -->
    <el-dialog
      v-model="toolDialogVisible"
      title="执行与依赖管理"
      width="85%"
      top="3vh"
      destroy-on-close
      class="tool-dialog"
    >
      <el-tabs v-model="toolTab" class="tool-tabs">
        <!-- 快速执行 -->
        <el-tab-pane label="快速执行" name="adhoc">
          <div class="adhoc-container">
            <div class="adhoc-editor">
              <div class="editor-header">
                <el-select v-model="adhocType" style="width:150px" size="large">
                  <el-option value="python" label="Python" />
                  <el-option value="shell" label="Shell" />
                </el-select>
                <el-button
                  type="primary"
                  size="large"
                  @click="runAdhoc"
                  :loading="adhocLoading"
                >
                  <el-icon><VideoPlay /></el-icon> 执行代码
                </el-button>
              </div>
              <div class="code-editor-wrapper large">
                <div class="code-toolbar">
                  <span class="code-lang">{{ adhocType === 'python' ? 'Python' : 'Shell' }}</span>
                  <span class="code-hint">Ctrl+Enter 执行</span>
                </div>
                <el-input
                  v-model="adhocScript"
                  type="textarea"
                  :rows="16"
                  placeholder="# 在此输入代码，点击执行按钮或按 Ctrl+Enter 执行&#10;&#10;import platform&#10;print(f'Python: {platform.python_version()}')&#10;print(f'OS: {platform.system()} {platform.release()}')"
                  class="code-textarea"
                  @keydown.ctrl.enter="runAdhoc"
                />
              </div>
            </div>
            <div class="adhoc-output" v-if="adhocResult">
              <div class="output-header">
                <span>执行结果</span>
                <el-tag :type="adhocResult.exit_code === 0 ? 'success' : 'danger'" size="small">
                  {{ adhocResult.exit_code === 0 ? '成功' : '失败' }}
                </el-tag>
              </div>
              <pre class="code-block"><code>{{ adhocResult.stdout || adhocResult.stderr || '(无输出)' }}</code></pre>
            </div>
          </div>
        </el-tab-pane>

        <!-- 依赖管理 -->
        <el-tab-pane label="依赖管理" name="pip">
          <div class="pip-container">
            <div class="pip-header">
              <div class="pip-search">
                <el-input
                  v-model="pipInstallName"
                  placeholder="输入包名，如：requests 或 requests==2.28.0"
                  size="large"
                  clearable
                >
                  <template #prepend>包名</template>
                </el-input>
              </div>
              <div class="pip-actions">
                <el-button type="primary" size="large" @click="installPipPackage" :loading="pipInstalling">
                  <el-icon><Download /></el-icon> 安装
                </el-button>
                <el-button size="large" @click="loadPipPackages" :loading="pipLoading">
                  <el-icon><Refresh /></el-icon> 刷新列表
                </el-button>
              </div>
            </div>

            <div v-if="pipResult.msg" class="pip-msg" :class="pipResult.ok ? 'pip-ok' : 'pip-err'">
              <el-icon>{{ pipResult.ok ? 'CircleCheck' : 'CircleClose' }}</el-icon>
              {{ pipResult.msg }}
            </div>

            <div class="pip-list-container">
              <div class="pip-list-header">
                <span>已安装的包 ({{ pipPackages.length }})</span>
              </div>
              <div v-if="pipPackages.length" class="pip-list">
                <div class="pip-item" v-for="pkg in pipPackages" :key="pkg.name">
                  <div class="pip-info">
                    <span class="pip-name">{{ pkg.name }}</span>
                    <span class="pip-version">v{{ pkg.version }}</span>
                  </div>
                  <el-button type="danger" link size="small" @click="uninstallPipPackage(pkg.name)">
                    <el-icon><Delete /></el-icon> 卸载
                  </el-button>
                </div>
              </div>
              <el-empty v-else-if="!pipLoading" description="点击刷新加载已安装的包" :image-size="80" />
              <div v-else class="pip-loading">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>加载中...</span>
              </div>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { inspectApi } from '@/api'
import { useUserStore } from '@/store/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Lightning, Plus, Edit, Delete, Document, VideoPlay,
  Check, Download, Refresh, Loading, CircleCheck, CircleClose
} from '@element-plus/icons-vue'

const userStore = useUserStore()

const scripts = ref([])
const selectedScripts = ref([])
const execResults = ref([])
const dialogVisible = ref(false)
const saveLoading = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref()
const form = reactive({ name: '', script_type: 'python', description: '', content: '' })
const formRules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  content: [{ required: true, message: '请输入代码内容', trigger: 'blur' }]
}

const adhocType = ref('python')
const adhocScript = ref('')
const adhocResult = ref(null)
const adhocLoading = ref(false)

// 执行与依赖弹框
const toolDialogVisible = ref(false)
const toolTab = ref('adhoc')
const openToolDialog = () => {
  toolDialogVisible.value = true
  toolTab.value = 'adhoc'
  adhocScript.value = ''
  adhocResult.value = null
  if (!pipPackages.value.length) loadPipPackages()
}

// Pip 管理
const pipPackages = ref([])
const pipLoading = ref(false)
const pipInstalling = ref(false)
const pipInstallName = ref('')
const pipResult = reactive({ ok: false, msg: '' })

const loadPipPackages = async () => {
  pipLoading.value = true
  pipResult.msg = ''
  try {
    const res = await inspectApi.listPipPackages()
    pipPackages.value = res.data || []
  } catch (e) { ElMessage.error('获取包列表失败') }
  finally { pipLoading.value = false }
}

const installPipPackage = async () => {
  const pkg = pipInstallName.value.trim()
  if (!pkg) { ElMessage.warning('请输入包名'); return }
  pipInstalling.value = true
  pipResult.msg = ''
  try {
    const res = await inspectApi.installPip(pkg)
    pipResult.ok = true
    pipResult.msg = res.msg || '安装成功'
    pipInstallName.value = ''
    loadPipPackages()
  } catch (e) {
    pipResult.ok = false
    pipResult.msg = e.message || '安装失败'
  } finally { pipInstalling.value = false }
}

const uninstallPipPackage = (name) => {
  ElMessageBox.confirm(`确定卸载 Python 包「${name}」？`, '确认卸载', { type: 'warning' })
    .then(async () => {
      pipResult.msg = ''
      try {
        const res = await inspectApi.uninstallPip(name)
        pipResult.ok = true
        pipResult.msg = res.msg || '卸载成功'
        loadPipPackages()
      } catch (e) {
        pipResult.ok = false
        pipResult.msg = e.message || '卸载失败'
      }
    }).catch(() => {})
}

const loadScripts = async () => {
  const res = await inspectApi.listScripts()
  scripts.value = res.data || []
}

const openCreate = () => {
  isEdit.value = false; editingId.value = null
  Object.assign(form, { name: '', script_type: 'python', description: '', content: '' })
  dialogVisible.value = true
}

const editScript = (row) => {
  isEdit.value = true; editingId.value = row.id
  Object.assign(form, { name: row.name, script_type: row.script_type, description: row.description, content: row.content })
  dialogVisible.value = true
}

const formatCode = () => {
  // 简单的代码格式化提示
  ElMessage.info('代码格式化功能开发中')
}

const submitForm = async () => {
  try {
    await formRef.value.validate()
    saveLoading.value = true
    if (isEdit.value) {
      await inspectApi.updateScript(editingId.value, form)
      ElMessage.success('脚本已更新')
    } else {
      await inspectApi.createScript(form)
      ElMessage.success('脚本已创建')
    }
    dialogVisible.value = false
    loadScripts()
  } catch (e) {} finally { saveLoading.value = false }
}

const removeScript = (id) => {
  ElMessageBox.confirm('确定删除此脚本？', '确认', { type: 'warning' })
    .then(async () => { await inspectApi.deleteScript(id); ElMessage.success('已删除'); loadScripts() })
    .catch(() => {})
}

const runSelectedScripts = async () => {
  const res = await inspectApi.executeScripts(selectedScripts.value)
  execResults.value = res.data?.results || []
}

const runAdhoc = async () => {
  if (!adhocScript.value.trim()) return
  adhocLoading.value = true
  adhocResult.value = null
  try {
    const res = await inspectApi.executeAdhoc(adhocType.value, adhocScript.value)
    adhocResult.value = res.data || {}
  } catch (e) { ElMessage.error('执行失败') } finally { adhocLoading.value = false }
}

onMounted(loadScripts)
</script>

<style scoped>
.page-container {
  padding: 20px;
  min-height: calc(100vh - 60px);
}

/* 顶部操作栏 */
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.action-left {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.script-count {
  font-size: 14px;
  color: #909399;
}

.action-right {
  display: flex;
  gap: 12px;
}

/* 主卡片 */
.main-card {
  margin-bottom: 20px;
}

.script-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.script-icon {
  font-size: 18px;
}

.script-icon.python {
  color: #3572A5;
}

.script-icon.shell {
  color: #89e051;
}

.table-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.exec-bar {
  padding: 16px;
  margin-top: 16px;
  background: #f0f9eb;
  border-radius: 8px;
  display: flex;
  justify-content: center;
}

/* 执行结果 */
.result-card {
  margin-top: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 600;
  font-size: 16px;
}

.result-item {
  margin-bottom: 16px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}

.result-item:last-child {
  margin-bottom: 0;
}

.result-header {
  background: #f5f7fa;
  padding: 12px 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.result-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
}

.result-body {
  padding: 0;
}

/* 代码块样式 */
.code-block {
  margin: 0;
  padding: 16px;
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  overflow-x: auto;
  max-height: 400px;
  overflow-y: auto;
}

.code-block code {
  font-family: inherit;
}

/* 代码编辑器 */
.code-editor-wrapper {
  width: 100%;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  overflow: hidden;
}

.code-editor-wrapper.large {
  border-width: 2px;
}

.code-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}

.code-lang {
  font-size: 13px;
  font-weight: 600;
  color: #409eff;
}

.code-hint {
  font-size: 12px;
  color: #909399;
}

.code-textarea :deep(.el-textarea__inner) {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-size: 14px;
  line-height: 1.6;
  padding: 16px;
  border: none;
  border-radius: 0;
  resize: none;
}

.code-textarea :deep(.el-textarea__inner):focus {
  box-shadow: none;
}

/* 脚本编辑对话框 */
.script-dialog :deep(.el-dialog__body) {
  padding: 20px 24px;
}

/* 执行与依赖对话框 */
.tool-dialog :deep(.el-dialog__body) {
  padding: 0;
}

.tool-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 20px;
  background: #f5f7fa;
}

.tool-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}

/* 快速执行 */
.adhoc-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px;
}

.adhoc-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.adhoc-output {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}

.output-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: #f5f7fa;
  font-weight: 600;
}

/* 依赖管理 */
.pip-container {
  padding: 20px;
}

.pip-header {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}

.pip-search {
  flex: 1;
}

.pip-actions {
  display: flex;
  gap: 12px;
  flex-shrink: 0;
}

.pip-msg {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 14px;
}

.pip-msg .el-icon {
  font-size: 18px;
}

.pip-ok {
  background: #f0f9eb;
  color: #67c23a;
}

.pip-err {
  background: #fef0f0;
  color: #f56c6c;
}

.pip-list-container {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}

.pip-list-header {
  padding: 12px 16px;
  background: #f5f7fa;
  font-weight: 600;
  font-size: 14px;
  border-bottom: 1px solid #e4e7ed;
}

.pip-list {
  max-height: 500px;
  overflow-y: auto;
}

.pip-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  transition: background 0.2s;
}

.pip-item:last-child {
  border-bottom: none;
}

.pip-item:hover {
  background: #f5f7fa;
}

.pip-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pip-name {
  font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
  font-weight: 600;
  color: #303133;
}

.pip-version {
  color: #909399;
  font-size: 13px;
}

.pip-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: #909399;
}

.pip-loading .el-icon {
  font-size: 20px;
}
</style>
