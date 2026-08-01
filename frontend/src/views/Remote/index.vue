<template>
  <div class="remote-container">
    <div class="page-header">
      <h2>远程孤岛执行</h2>
      <span class="tip">目标服务器不可直连，请生成采集器脚本拷贝到目标机运行，结果自动回传</span>
    </div>

    <!-- 主机管理 -->
    <el-card class="section" shadow="never">
      <div class="section-header">
        <span class="section-title">远程主机</span>
        <el-button type="primary" size="small" @click="showHostDialog = true">+ 新增主机</el-button>
      </div>
      <el-table :data="hosts" border stripe size="small" v-loading="hostsLoading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="alias" label="别名" min-width="140" />
        <el-table-column prop="token" label="Token" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="token">{{ row.token }}</code>
            <el-button size="small" type="text" @click="copy(row.token)">复制</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="last_seen" label="最近活跃" width="170" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="text" @click="resetToken(row)">重置Token</el-button>
            <el-button size="small" type="text" style="color:#f56c6c" @click="removeHost(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 生成采集器 -->
    <el-card class="section" shadow="never">
      <div class="section-header">
        <span class="section-title">生成采集器</span>
        <span class="sub-tip">生成脚本 → 拷贝到目标服务器执行 → 结果自动回传</span>
      </div>
      <el-form :inline="true" size="small" class="gen-form">
        <el-form-item label="主机">
          <el-select v-model="genForm.host_id" style="width:150px" placeholder="选择主机">
            <el-option v-for="h in hosts" :key="h.id" :value="h.id" :label="h.alias" />
          </el-select>
        </el-form-item>
        <el-form-item label="脚本">
          <el-select v-model="genForm.script_id" style="width:200px" placeholder="选择脚本" :loading="scriptsLoading">
            <el-option v-for="s in scripts" :key="s.id" :value="s.id" :label="s.name" />
          </el-select>
        </el-form-item>
        <el-form-item label="语言">
          <el-select v-model="genForm.lang" style="width:100px">
            <el-option value="python" label="Python" />
            <el-option value="shell" label="Shell" />
          </el-select>
        </el-form-item>
        <el-form-item label="上报地址">
          <el-input v-model="genForm.callback" style="width:260px" placeholder="孤岛可访问的后端地址" />
        </el-form-item>
        <el-button type="primary" size="small" @click="genCollector" :disabled="!genForm.host_id || !genForm.script_id">
          生成并下载
        </el-button>
      </el-form>
    </el-card>

    <!-- 执行结果 -->
    <el-card class="section" shadow="never">
      <div class="section-header">
        <span class="section-title">执行结果</span>
        <el-button size="small" @click="loadExecutions">刷新</el-button>
      </div>
      <el-table :data="executions" border stripe size="small" v-loading="execLoading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="host_alias" label="主机" width="140" />
        <el-table-column prop="script_name" label="脚本" min-width="160" />
        <el-table-column prop="exit_code" label="退出码" width="90">
          <template #default="{ row }">
            <el-tag :type="row.exit_code === 0 ? 'success' : 'danger'" size="small">{{ row.exit_code }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="received_at" label="接收时间" width="170" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="text" @click="viewDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-if="execTotal > execPageSize"
        class="pager"
        layout="total, prev, pager, next"
        :total="execTotal"
        :page-size="execPageSize"
        :current-page="execPage"
        @current-change="onPageChange"
      />
    </el-card>

    <!-- 新增主机 -->
    <el-dialog v-model="showHostDialog" title="新增主机" width="400px">
      <el-input v-model="hostAlias" placeholder="请输入主机别名" />
      <template #footer>
        <el-button @click="showHostDialog = false">取消</el-button>
        <el-button type="primary" @click="addHost">确定</el-button>
      </template>
    </el-dialog>

    <!-- 详情 -->
    <el-dialog v-model="showDetail" title="执行详情" width="720px">
      <div v-if="detail">
        <div class="detail-meta">
          <span>主机：{{ detail.host_alias }}</span>
          <span>脚本：{{ detail.script_name || '-' }}</span>
          <span>退出码：{{ detail.exit_code }}</span>
          <span>接收：{{ detail.received_at }}</span>
        </div>
        <div class="detail-block">
          <div class="block-label">STDOUT</div>
          <pre class="output">{{ detail.stdout || '(空)' }}</pre>
        </div>
        <div class="detail-block" v-if="detail.stderr">
          <div class="block-label">STDERR</div>
          <pre class="output err">{{ detail.stderr }}</pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { remoteApi, inspectApi } from '@/api'
import { ElMessage } from 'element-plus'

const hosts = ref([])
const hostsLoading = ref(false)
const scripts = ref([])
const scriptsLoading = ref(false)
const executions = ref([])
const execLoading = ref(false)
const execPage = ref(1)
const execPageSize = ref(20)
const execTotal = ref(0)

const showHostDialog = ref(false)
const hostAlias = ref('')
const showDetail = ref(false)
const detail = ref(null)

const genForm = reactive({
  host_id: null,
  script_id: null,
  lang: 'python',
  callback: window.location.origin
})

async function loadHosts() {
  hostsLoading.value = true
  try {
    const res = await remoteApi.listHosts()
    hosts.value = res.data || []
  } finally {
    hostsLoading.value = false
  }
}

async function loadScripts() {
  scriptsLoading.value = true
  try {
    const res = await inspectApi.listScripts()
    scripts.value = res.data || []
  } finally {
    scriptsLoading.value = false
  }
}

async function loadExecutions() {
  execLoading.value = true
  try {
    const res = await remoteApi.listExecutions({ page: execPage.value, page_size: execPageSize.value })
    executions.value = res.data?.items || []
    execTotal.value = res.data?.total || 0
  } finally {
    execLoading.value = false
  }
}

async function addHost() {
  if (!hostAlias.value.trim()) {
    ElMessage.warning('别名不能为空')
    return
  }
  const res = await remoteApi.createHost(hostAlias.value.trim())
  if (res.code === 0 || res.code === 200) {
    ElMessage.success('主机已创建，请复制 Token')
    showHostDialog.value = false
    hostAlias.value = ''
    loadHosts()
  } else {
    ElMessage.error(res.msg || '创建失败')
  }
}

async function resetToken(row) {
  const res = await remoteApi.resetToken(row.id)
  if (res.code === 0 || res.code === 200) {
    ElMessage.success('Token 已重置，新 Token：' + res.data.token)
    loadHosts()
  } else {
    ElMessage.error(res.msg || '重置失败')
  }
}

async function removeHost(row) {
  await remoteApi.deleteHost(row.id)
  ElMessage.success('已删除')
  loadHosts()
}

async function genCollector() {
  const res = await remoteApi.generateCollector(genForm.script_id, genForm.host_id, genForm.callback, genForm.lang)
  if (res.code === 0 || res.code === 200) {
    const content = res.data.content
    const filename = res.data.filename || 'collector.py'
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('采集器已下载，拷贝到目标服务器执行即可')
  } else {
    ElMessage.error(res.msg || '生成失败')
  }
}

async function viewDetail(row) {
  const res = await remoteApi.getExecution(row.id)
  if (res.code === 0 || res.code === 200) {
    detail.value = res.data
    showDetail.value = true
  } else {
    ElMessage.error(res.msg || '获取失败')
  }
}

function copy(text) {
  navigator.clipboard?.writeText(text).then(() => ElMessage.success('已复制'))
}

function onPageChange(p) {
  execPage.value = p
  loadExecutions()
}

onMounted(() => {
  loadHosts()
  loadScripts()
  loadExecutions()
})
</script>

<style scoped>
.remote-container { padding: 20px; }
.page-header { margin-bottom: 16px; display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
.page-header h2 { margin: 0; font-size: 18px; font-weight: 600; }
.tip { font-size: 12px; color: #909399; }
.section { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.sub-tip { font-size: 12px; color: #909399; }
.token { font-family: monospace; font-size: 12px; word-break: break-all; }
.gen-form { flex-wrap: wrap; }
.pager { margin-top: 12px; justify-content: flex-end; }
.detail-meta { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; font-size: 13px; color: #606266; }
.detail-block { margin-bottom: 12px; }
.block-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.output { margin: 0; padding: 12px; background: #1e1e1e; color: #d4d4d4; font-size: 12px; border-radius: 4px; white-space: pre-wrap; max-height: 320px; overflow: auto; word-break: break-all; }
.output.err { background: #2a1e1e; }
</style>
