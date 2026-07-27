<template>
  <div class="inspection-container">
    <div class="page-header">
      <h2>日常巡检</h2>
    </div>
    <el-tabs v-model="activeTab" class="inspection-tabs">
      
      <!-- Tab 1: 脚本执行 -->
      <el-tab-pane label="脚本执行" name="scripts">
        <div class="tab-content">
          <!-- 脚本列表 + 新增 -->
          <div class="section-header">
            <span class="section-title">脚本清单</span>
            <el-button type="primary" size="small" @click="showScriptDialog = true">+ 新增脚本</el-button>
          </div>
          
          <el-table :data="scripts" border stripe size="small" class="script-table">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column prop="name" label="脚本名称" min-width="150" />
            <el-table-column prop="script_type" label="类型" width="80">
              <template #default="{ row }">
                <el-tag size="small">{{ row.script_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
            <el-table-column label="操作" width="200" fixed="right">
              <template #default="{ row }">
                <el-checkbox v-model="selectedScripts" :value="row.id" style="margin-right:8px">选中</el-checkbox>
                <el-button size="small" type="text" @click="editScript(row)">编辑</el-button>
                <el-button size="small" type="text" style="color:#f56c6c" @click="removeScript(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          
          <div v-if="selectedScripts.length > 0" class="exec-section">
            <el-button type="success" @click="runSelectedScripts">▶ 执行选中脚本 ({{ selectedScripts.length }} 个)</el-button>
          </div>
          
          <!-- 执行结果 -->
          <div v-if="execResults.length > 0" class="results-section">
            <div class="section-title">执行结果</div>
            <div v-for="r in execResults" :key="r.id" class="result-item">
              <div class="result-header">
                <strong>{{ r.name }}</strong>
                <el-tag :type="r.exit_code === 0 ? 'success' : 'danger'" size="small" style="margin-left:8px">
                  exit: {{ r.exit_code }}
                </el-tag>
              </div>
              <pre class="result-output">{{ r.stdout || r.stderr || '(无输出)' }}</pre>
            </div>
          </div>
          
          <!-- 快速执行（单脚本） -->
          <div class="section-header" style="margin-top:24px">
            <span class="section-title">快速执行</span>
          </div>
          <div class="adhoc-section">
            <el-select v-model="adhocType" size="small" style="width:100px;margin-right:8px">
              <el-option value="python" label="Python" />
              <el-option value="shell" label="Shell" />
            </el-select>
            <el-input v-model="adhocScript" size="small" type="textarea" :rows="4" 
              placeholder="输入代码，按 Enter 执行" style="flex:1" />
            <el-button type="primary" size="small" @click="runAdhoc" style="margin-left:8px">执行</el-button>
          </div>
          <div v-if="adhocResult" class="adhoc-result">
            <pre>{{ adhocResult.stdout || adhocResult.stderr }}</pre>
          </div>
        </div>
      </el-tab-pane>
      
      <!-- Tab 2: 流量巡检 -->
      <el-tab-pane label="流量巡检" name="traffic">
        <div class="tab-content">
          <div class="filter-row">
            <span>时间窗口：</span>
            <el-input-number v-model="trafficParams.window_minutes" :min="1" :max="1440" size="small" style="width:120px" />
            <span style="margin-left:16px">分组字段：</span>
            <el-select v-model="trafficParams.group_by_field" size="small" style="width:180px">
              <el-option value="domain" label="domain" />
              <el-option value="src_ip.keyword" label="src_ip (IP)" />
              <el-option value="request_uri.keyword" label="request_uri" />
              <el-option value="user_agent.keyword" label="user_agent" />
            </el-select>
            <el-button type="primary" size="small" @click="runTraffic" style="margin-left:16px">查询</el-button>
          </div>
          
          <div v-if="trafficResult" class="traffic-result">
            <div class="traffic-summary">
              共 {{ trafficResult.total }} 条日志（最近 {{ trafficResult.window_minutes }} 分钟）
            </div>
            <el-table :data="trafficResult.domains" border stripe size="small">
              <el-table-column prop="key" label="字段值" min-width="200" show-overflow-tooltip />
              <el-table-column prop="count" label="出现次数" width="120" sortable />
              <el-table-column prop="unique_uris" label="唯一URI数" width="120" />
            </el-table>
          </div>
        </div>
      </el-tab-pane>
      
      <!-- Tab 3: 系统指标 -->
      <el-tab-pane label="系统指标" name="metrics">
        <div class="tab-content">
          <el-button type="primary" @click="loadMetrics" :loading="metricsLoading">刷新指标</el-button>
          <div v-if="metricsData && !metricsData.connected" class="info-tip">
            无法连接到 Grafana 服务器，请检查系统设置中的 Grafana 配置
          </div>
          <div v-else-if="metricsData" class="metrics-grid">
            <div class="metric-card">
              <div class="metric-title">CPU 利用率</div>
              <div class="metric-value">{{ metricsData.cpu?.avg ?? '-' }}%</div>
              <div class="metric-sub">峰值: {{ metricsData.cpu?.peak ?? '-' }}%</div>
            </div>
            <div class="metric-card">
              <div class="metric-title">内存使用率</div>
              <div class="metric-value">{{ metricsData.memory?.avg ?? '-' }}%</div>
              <div class="metric-sub">峰值: {{ metricsData.memory?.peak ?? '-' }}%</div>
            </div>
            <div class="metric-card">
              <div class="metric-title">磁盘使用率</div>
              <div class="metric-value">{{ metricsData.disk?.avg ?? '-' }}%</div>
              <div class="metric-sub">峰值: {{ metricsData.disk?.peak ?? '-' }}%</div>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>
    
    <!-- 脚本编辑对话框 -->
    <el-dialog v-model="showScriptDialog" :title="editingScript ? '编辑脚本' : '新增脚本'" width="600px">
      <el-form :model="scriptForm" label-width="80px">
        <el-form-item label="脚本名称">
          <el-input v-model="scriptForm.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="scriptForm.script_type" style="width:100%">
            <el-option value="python" label="Python" />
            <el-option value="shell" label="Shell" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="scriptForm.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="代码内容">
          <el-input v-model="scriptForm.content" type="textarea" :rows="8" 
            placeholder="import json&#10;print('Hello')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showScriptDialog = false">取消</el-button>
        <el-button type="primary" @click="saveScript">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { inspectApi } from '@/api'
import { ElMessage } from 'element-plus'

const route = useRoute()
const activeTab = ref(route.query.tab || 'scripts')

// Sync tab from URL changes (when sidebar sub-menu is clicked)
watch(() => route.query.tab, (tab) => {
  if (tab && ['scripts', 'traffic', 'metrics'].includes(tab)) {
    activeTab.value = tab
  }
})

// Scripts
const scripts = ref([])
const selectedScripts = ref([])
const execResults = ref([])
const showScriptDialog = ref(false)
const editingScript = ref(null)
const scriptForm = reactive({ name: '', script_type: 'python', description: '', content: '' })

// Adhoc
const adhocType = ref('python')
const adhocScript = ref('')
const adhocResult = ref(null)

// Traffic
const trafficParams = reactive({ window_minutes: 30, group_by_field: 'domain' })
const trafficResult = ref(null)

// Metrics
const metricsLoading = ref(false)
const metricsData = ref(null)

async function loadScripts() {
  const res = await inspectApi.listScripts()
  scripts.value = res.data || []
}

async function saveScript() {
  if (!scriptForm.name || !scriptForm.content) {
    ElMessage.warning('名称和代码不能为空')
    return
  }
  if (editingScript.value) {
    await inspectApi.updateScript(editingScript.value.id, scriptForm)
    ElMessage.success('脚本已更新')
  } else {
    await inspectApi.createScript(scriptForm)
    ElMessage.success('脚本已创建')
  }
  showScriptDialog.value = false
  editingScript.value = null
  Object.assign(scriptForm, { name: '', script_type: 'python', description: '', content: '' })
  loadScripts()
}

function editScript(row) {
  editingScript.value = row
  Object.assign(scriptForm, { name: row.name, script_type: row.script_type, description: row.description, content: row.content })
  showScriptDialog.value = true
}

async function removeScript(id) {
  await inspectApi.deleteScript(id)
  ElMessage.success('已删除')
  loadScripts()
}

async function runSelectedScripts() {
  const res = await inspectApi.executeScripts(selectedScripts.value)
  execResults.value = res.data?.results || []
}

async function runAdhoc() {
  if (!adhocScript.value.trim()) return
  const res = await inspectApi.executeAdhoc(adhocType.value, adhocScript.value)
  adhocResult.value = res.data || {}
}

async function runTraffic() {
  const res = await inspectApi.traffic(trafficParams)
  trafficResult.value = res.data || null
}

async function loadMetrics() {
  metricsLoading.value = true
  try {
    const res = await inspectApi.grafanaMetrics()
    metricsData.value = res.data || null
  } finally {
    metricsLoading.value = false
  }
}

onMounted(() => {
  loadScripts()
  loadMetrics()
})
</script>

<style scoped>
.inspection-container { padding: 20px; }
.page-header { margin-bottom: 16px; }
.page-header h2 { margin: 0; font-size: 18px; font-weight: 600; }
.inspection-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
.tab-content { min-height: 400px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.script-table { margin-bottom: 16px; }
.exec-section { margin: 12px 0; }
.results-section { margin-top: 16px; }
.result-item { margin-bottom: 12px; border: 1px solid #e4e7ed; border-radius: 4px; overflow: hidden; }
.result-header { background: #f5f7fa; padding: 8px 12px; display: flex; align-items: center; }
.result-output { margin: 0; padding: 8px 12px; background: #1e1e1e; color: #d4d4d4; font-size: 12px; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-all; }
.adhoc-section { display: flex; gap: 8px; align-items: flex-start; }
.adhoc-result { margin-top: 12px; }
.adhoc-result pre { margin: 0; padding: 12px; background: #1e1e1e; color: #d4d4d4; font-size: 12px; border-radius: 4px; white-space: pre-wrap; max-height: 300px; overflow: auto; }
.filter-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 16px; }
.traffic-result { margin-top: 12px; }
.traffic-summary { margin-bottom: 8px; color: #606266; font-size: 13px; }
.info-tip { margin-top: 16px; padding: 12px; background: #fdf6ec; border-radius: 4px; color: #e6a23c; font-size: 13px; }
.metrics-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 20px; }
.metric-card { background: #f5f7fa; border-radius: 8px; padding: 20px; text-align: center; }
.metric-title { font-size: 13px; color: #909399; margin-bottom: 8px; }
.metric-value { font-size: 28px; font-weight: 700; color: #303133; }
.metric-sub { font-size: 12px; color: #909399; margin-top: 4px; }
</style>
