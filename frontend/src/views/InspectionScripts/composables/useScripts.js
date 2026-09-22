import { ref } from 'vue'
import { inspectApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'

// ── module-level state (single owner shared across the page) ──
const scripts = ref([])
const selectedScripts = ref([])
const execResults = ref([])

const loadScripts = async () => {
  const res = await inspectApi.listScripts()
  scripts.value = res.data || []
}

const createScript = async (data) => {
  await inspectApi.createScript(data)
}

const updateScript = async (id, data) => {
  await inspectApi.updateScript(id, data)
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

const clearExecResults = () => {
  execResults.value = []
}

export function useScripts() {
  return {
    scripts,
    selectedScripts,
    execResults,
    loadScripts,
    createScript,
    updateScript,
    removeScript,
    runSelectedScripts,
    clearExecResults
  }
}
