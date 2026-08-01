<template>
  <div class="remote-container">
    <div class="page-header">
      <h2>远程接收接口</h2>
      <span class="tip">定义多个接收接口（各带名称），源端只需往对应接口 POST 数据即自动存储</span>
    </div>

    <el-card class="section" shadow="never">
      <div class="section-header">
        <span class="section-title">接收接口</span>
        <el-button type="primary" size="small" @click="showCreate = true">+ 新增接口</el-button>
      </div>
      <el-table :data="endpoints" border stripe size="small" v-loading="loading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="接口名称" min-width="160">
          <template #default="{ row }">
            <code class="name">{{ row.name }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip />
        <el-table-column prop="count" label="接收数" width="90" sortable />
        <el-table-column prop="created_at" label="创建时间" width="170" />
        <el-table-column label="接收地址" min-width="280">
          <template #default="{ row }">
            <code class="url">{{ baseUrl }}/api/remote/ingest/{{ row.name }}</code>
            <el-button size="small" type="text" @click="copy(baseUrl + '/api/remote/ingest/' + row.name)">复制</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="text" @click="viewLogs(row)">查看数据</el-button>
            <el-button size="small" type="text" style="color:#f56c6c" @click="remove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && endpoints.length === 0" description="暂无接收接口，点击右上角新增" />
    </el-card>

    <!-- 新增接口 -->
    <el-dialog v-model="showCreate" title="新增接收接口" width="460px">
      <el-form label-width="80px">
        <el-form-item label="接口名称">
          <el-input v-model="form.name" placeholder="如 server-a-logs（字母/数字/下划线/横线）" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="create">确定</el-button>
      </template>
    </el-dialog>

    <!-- 数据查看 -->
    <el-dialog v-model="showLogs" :title="'接收数据 - ' + (current.name || '')" width="760px">
      <div class="logs-meta">
        <span>接口：<code>{{ current.name }}</code></span>
        <span>共 {{ logTotal }} 条</span>
        <el-button size="small" @click="loadLogs">刷新</el-button>
      </div>
      <div v-loading="logsLoading" class="logs-list">
        <div v-for="item in logs" :key="item.id" class="log-item">
          <div class="log-head">
            <span>#{{ item.id }}</span>
            <span>{{ item.received_at }}</span>
          </div>
          <pre class="log-payload">{{ pretty(item.payload) }}</pre>
        </div>
        <el-empty v-if="!logsLoading && logs.length === 0" description="该接口暂无接收数据" />
      </div>
      <el-pagination
        v-if="logTotal > logPageSize"
        class="pager"
        layout="total, prev, pager, next"
        :total="logTotal"
        :page-size="logPageSize"
        :current-page="logPage"
        @current-change="onLogPage"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { remoteApi } from '@/api'
import { ElMessage } from 'element-plus'

const endpoints = ref([])
const loading = ref(false)
const baseUrl = window.location.origin

const showCreate = ref(false)
const form = reactive({ name: '', description: '' })

const showLogs = ref(false)
const current = ref({})
const logs = ref([])
const logsLoading = ref(false)
const logPage = ref(1)
const logPageSize = ref(20)
const logTotal = ref(0)

async function loadEndpoints() {
  loading.value = true
  try {
    const res = await remoteApi.listEndpoints()
    endpoints.value = res.data || []
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!form.name.trim()) {
    ElMessage.warning('接口名称不能为空')
    return
  }
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(form.name.trim())) {
    ElMessage.warning('名称只能包含字母、数字、下划线和横线（1-64位）')
    return
  }
  const res = await remoteApi.createEndpoint(form.name.trim(), form.description.trim())
  if (res.code === 0) {
    ElMessage.success('接口已创建')
    showCreate.value = false
    form.name = ''
    form.description = ''
    loadEndpoints()
  } else {
    ElMessage.error(res.msg || '创建失败')
  }
}

async function remove(row) {
  await remoteApi.deleteEndpoint(row.id)
  ElMessage.success('已删除')
  loadEndpoints()
}

async function viewLogs(row) {
  current.value = row
  logPage.value = 1
  showLogs.value = true
  await loadLogs()
}

async function loadLogs() {
  if (!current.value.id) return
  logsLoading.value = true
  try {
    const res = await remoteApi.listLogs(current.value.id, { page: logPage.value, page_size: logPageSize.value })
    logs.value = res.data?.items || []
    logTotal.value = res.data?.total || 0
  } finally {
    logsLoading.value = false
  }
}

function onLogPage(p) {
  logPage.value = p
  loadLogs()
}

function pretty(payload) {
  if (!payload) return '(空)'
  try {
    return JSON.stringify(JSON.parse(payload), null, 2)
  } catch (e) {
    return payload
  }
}

function copy(text) {
  navigator.clipboard?.writeText(text).then(() => ElMessage.success('已复制'))
}

onMounted(() => {
  loadEndpoints()
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
.name { font-family: monospace; font-size: 13px; color: #409EFF; }
.url { font-family: monospace; font-size: 12px; word-break: break-all; color: #606266; }
.logs-meta { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; font-size: 13px; color: #606266; }
.logs-list { max-height: 460px; overflow: auto; }
.log-item { margin-bottom: 12px; border: 1px solid #e4e7ed; border-radius: 4px; overflow: hidden; }
.log-head { background: #f5f7fa; padding: 6px 12px; display: flex; gap: 16px; font-size: 12px; color: #909399; }
.log-payload { margin: 0; padding: 12px; background: #1e1e1e; color: #d4d4d4; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 320px; overflow: auto; }
.pager { margin-top: 12px; justify-content: flex-end; }
</style>
