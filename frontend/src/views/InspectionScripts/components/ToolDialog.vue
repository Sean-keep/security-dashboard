<template>
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
        <PipPanel
          :packages="pipPackages"
          :loading="pipLoading"
          :installing="pipInstalling"
          :install-name="pipInstallName"
          :result="pipResult"
          @update:install-name="pipInstallName = $event"
          @install="installPipPackage"
          @refresh="loadPipPackages"
          @uninstall="uninstallPipPackage"
        />
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { inspectApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { VideoPlay } from '@element-plus/icons-vue'
import PipPanel from './PipPanel.vue'

// 执行与依赖弹框
const toolDialogVisible = ref(false)
const toolTab = ref('adhoc')

const adhocType = ref('python')
const adhocScript = ref('')
const adhocResult = ref(null)
const adhocLoading = ref(false)

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

const runAdhoc = async () => {
  if (!adhocScript.value.trim()) return
  adhocLoading.value = true
  adhocResult.value = null
  try {
    const res = await inspectApi.executeAdhoc(adhocType.value, adhocScript.value)
    adhocResult.value = res.data || {}
  } catch (e) { ElMessage.error('执行失败') } finally { adhocLoading.value = false }
}

const openToolDialog = () => {
  toolDialogVisible.value = true
  toolTab.value = 'adhoc'
  adhocScript.value = ''
  adhocResult.value = null
  if (!pipPackages.value.length) loadPipPackages()
}

defineExpose({ openToolDialog })
</script>

<style scoped>
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
</style>
