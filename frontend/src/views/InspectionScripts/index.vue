<template>
  <div class="page-container">
    <!-- 脚本管理卡片 -->
    <el-card shadow="never" class="mb-16">
      <template #header>
        <div class="card-header">
          <span class="card-title">脚本清单</span>
          <div style="display:flex;gap:8px">
            <el-button type="primary" size="small" @click="openToolDialog">⚡ 执行与依赖</el-button>
            <el-button type="primary" size="small" @click="openCreate">+ 新增脚本</el-button>
          </div>
        </div>
      </template>
      <el-table :data="scripts" border stripe size="small">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="脚本名称" min-width="160" />
        <el-table-column prop="script_type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.script_type === 'python' ? 'success' : 'info'">{{ row.script_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-checkbox v-model="selectedScripts" :value="row.id" style="margin-right:8px">选中</el-checkbox>
            <el-button size="small" type="text" @click="editScript(row)">编辑</el-button>
            <el-button size="small" type="text" style="color:#f56c6c" @click="removeScript(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div v-if="selectedScripts.length > 0" class="exec-bar">
        <el-button type="success" @click="runSelectedScripts">▶ 执行选中脚本 ({{ selectedScripts.length }} 个)</el-button>
      </div>
    </el-card>

    <!-- 执行结果 -->
    <el-card v-if="execResults.length > 0" shadow="never" class="mt-16">
      <template #header>
        <span class="card-title">执行结果</span>
      </template>
      <div v-for="r in execResults" :key="r.id" class="result-item">
        <div class="result-header">
          <strong>{{ r.name }}</strong>
          <el-tag :type="r.exit_code === 0 ? 'success' : 'danger'" size="small" style="margin-left:8px">
            exit: {{ r.exit_code ?? '?' }}
          </el-tag>
        </div>
        <pre class="result-output">{{ r.stdout || r.stderr || '(无输出)' }}</pre>
      </div>
    </el-card>

    <!-- 脚本编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑脚本' : '新增脚本'" width="600px" destroy-on-close>
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="80px">
        <el-form-item label="脚本名称" prop="name">
          <el-input v-model="form.name" placeholder="输入脚本名称" />
        </el-form-item>
        <el-form-item label="类型" prop="script_type">
          <el-select v-model="form.script_type" style="width:100%">
            <el-option value="python" label="Python" />
            <el-option value="shell" label="Shell" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="描述脚本功能" />
        </el-form-item>
        <el-form-item label="代码内容" prop="content">
          <el-input v-model="form.content" type="textarea" :rows="10"
            placeholder="import json&#10;print('Hello')" style="font-family:'Courier New',monospace" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saveLoading" @click="submitForm">保存</el-button>
      </template>
    </el-dialog>

    <!-- 执行与依赖对话框 -->
    <el-dialog v-model="toolDialogVisible" title="⚡ 执行与依赖" width="720px" destroy-on-close>
      <el-tabs v-model="toolTab">
        <!-- 快速执行 -->
        <el-tab-pane label="快速执行" name="adhoc">
          <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:12px">
            <el-select v-model="adhocType" size="small" style="width:100px;flex-shrink:0">
              <el-option value="python" label="Python" />
              <el-option value="shell" label="Shell" />
            </el-select>
            <el-input v-model="adhocScript" size="small" type="textarea" :rows="5"
              placeholder="输入代码，点击执行" style="flex:1;font-family:'Courier New',monospace" />
            <el-button type="primary" size="small" @click="runAdhoc" :loading="adhocLoading" style="flex-shrink:0;margin-left:8px">执行</el-button>
          </div>
          <div v-if="adhocResult" class="adhoc-result">
            <pre>{{ adhocResult.stdout || adhocResult.stderr || '(无输出)' }}</pre>
          </div>
        </el-tab-pane>
        <!-- 依赖管理 -->
        <el-tab-pane label="依赖管理" name="pip">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
            <el-input v-model="pipInstallName" size="small" placeholder="包名，如：requests 或 requests==2.28.0" style="flex:1" />
            <el-button type="primary" size="small" @click="installPipPackage" :loading="pipInstalling">安装</el-button>
            <el-button size="small" @click="loadPipPackages" :loading="pipLoading">刷新</el-button>
          </div>
          <div v-if="pipResult.msg" class="pip-msg" :class="pipResult.ok ? 'pip-ok' : 'pip-err'">{{ pipResult.msg }}</div>
          <div v-if="pipPackages.length" class="pip-list">
            <div class="pip-item" v-for="pkg in pipPackages" :key="pkg.name">
              <span class="pip-name">{{ pkg.name }}</span>
              <span class="pip-version">{{ pkg.version }}</span>
              <el-button size="small" type="danger" link @click="uninstallPipPackage(pkg.name)">卸载</el-button>
            </div>
          </div>
          <el-empty v-else-if="!pipLoading" description="点击刷新加载已安装的包" :image-size="60" />
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
  // Load pip packages in background
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
.page-container { }
.mb-16 { margin-bottom: 16px; }
.mt-16 { margin-top: 16px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-title { font-weight: 600; font-size: 15px; }
.exec-bar { padding: 12px 0 0; }
.adhoc-row { display: flex; align-items: flex-start; gap: 8px; }
.adhoc-result { margin-top: 12px; }
.adhoc-result pre {
  margin: 0; padding: 12px; background: #1e1e1e; color: #d4d4d4;
  font-size: 12px; border-radius: 4px; white-space: pre-wrap;
  max-height: 300px; overflow: auto;
}
.result-item { margin-bottom: 12px; border: 1px solid #e4e7ed; border-radius: 6px; overflow: hidden; }
.result-header { background: #f5f7fa; padding: 8px 12px; display: flex; align-items: center; }
.result-output {
  margin: 0; padding: 12px; background: #1e1e1e; color: #d4d4d4;
  font-size: 12px; max-height: 200px; overflow: auto;
  white-space: pre-wrap; word-break: break-all;
}

/* Pip 管理 */
.pip-install-row { display: flex; align-items: center; margin-bottom: 10px; }
.pip-msg { padding: 6px 12px; border-radius: 4px; font-size: 13px; margin-bottom: 10px; }
.pip-ok { background: #f0f9eb; color: #67c23a; }
.pip-err { background: #fef0f0; color: #f56c6c; }
.pip-list { max-height: 260px; overflow-y: auto; border: 1px solid #ebeef5; border-radius: 4px; }
.pip-item { display: flex; align-items: center; padding: 5px 12px; border-bottom: 1px solid #f0f0f0; font-size: 13px; }
.pip-item:last-child { border-bottom: none; }
.pip-item:hover { background: #f5f7fa; }
.pip-name { flex: 1; font-family: 'Courier New', monospace; color: #303133; }
.pip-version { color: #909399; font-size: 12px; margin-right: 8px; flex-shrink: 0; }
</style>
