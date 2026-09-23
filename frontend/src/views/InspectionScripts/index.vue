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
    <ScriptTable
      @edit="editScript"
      @delete="removeScript"
      @run-selected="runSelectedScripts"
    />

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
    <ScriptEditorDialog ref="editorRef" @saved="loadScripts" />

    <!-- 执行与依赖对话框 -->
    <ToolDialog ref="toolRef" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Lightning, Plus, Document } from '@element-plus/icons-vue'
import ScriptTable from './components/ScriptTable.vue'
import ScriptEditorDialog from './components/ScriptEditorDialog.vue'
import ToolDialog from './components/ToolDialog.vue'
import { useScripts } from './composables/useScripts'


const {
  scripts,
  execResults,
  loadScripts,
  removeScript,
  runSelectedScripts
} = useScripts()

const editorRef = ref()
const toolRef = ref()

const openCreate = () => editorRef.value.openCreate()
const editScript = (row) => editorRef.value.editScript(row)
const openToolDialog = () => toolRef.value.openToolDialog()

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
  color: var(--el-text-color-primary);
}

.script-count {
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.action-right {
  display: flex;
  gap: 12px;
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
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  overflow: hidden;
}

.result-item:last-child {
  margin-bottom: 0;
}

.result-header {
  background: var(--el-fill-color-light);
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
  background: var(--code-bg);
  color: var(--code-fg);
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
