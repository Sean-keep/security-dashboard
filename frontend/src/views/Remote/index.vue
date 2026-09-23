<template>
  <div class="remote-container">
    <div class="page-header">
      <h2>远程接收接口</h2>
      <span class="tip">源端 POST 即存，无需 token · 发送方按特征归类，可绑定起名 · 日报勾选接口取最近一条</span>
    </div>

    <!-- 发送方：接收端认人。特征是提示不是凭证，绑定只是起名字 -->
    <el-card class="section" shadow="never">
      <div class="section-header">
        <span class="section-title">发送方</span>
        <span class="tip">共 {{ senders.length }} 个 · 待绑定 {{ pendingCount }} 个</span>
        <el-button size="small" style="margin-left:auto" @click="loadSenders">刷新</el-button>
      </div>
      <el-table :data="senders" border stripe size="small" v-loading="sendersLoading" class="nowrap-table">
        <el-table-column prop="status" label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'bound'" type="success" size="small">已绑定</el-tag>
            <el-tag v-else-if="row.status === 'rejected'" type="danger" size="small">已拒收</el-tag>
            <el-tag v-else type="warning" size="small">待绑定</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="display_name" label="名称" min-width="110" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.display_name">{{ row.display_name }}</span>
            <span v-else class="muted">未命名</span>
          </template>
        </el-table-column>
        <el-table-column prop="endpoint_name" label="接口" width="110" show-overflow-tooltip>
          <template #default="{ row }"><code class="name">{{ row.endpoint_name }}</code></template>
        </el-table-column>
        <el-table-column prop="src_ip" label="源 IP" width="130" show-overflow-tooltip />
        <el-table-column prop="user_agent" label="User-Agent" min-width="140" show-overflow-tooltip />
        <el-table-column prop="payload_shape" label="载荷形状" min-width="140" show-overflow-tooltip />
        <el-table-column prop="send_count" label="次数" width="70" sortable />
        <el-table-column prop="last_seen_at" label="最近接收" width="180" show-overflow-tooltip />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <div class="ops">
              <el-button v-if="row.status !== 'bound'" size="small" type="text" style="color:var(--el-color-success)" @click.stop="bindSender(row)">绑定</el-button>
              <el-button v-if="row.status !== 'rejected'" size="small" type="text" style="color:var(--el-color-danger)" @click.stop="rejectSender(row)">拒收</el-button>
              <el-dropdown trigger="click" @command="(c) => onSenderOp(c, row)">
                <el-button size="small" type="text" @click.stop>更多</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item v-if="row.status === 'bound'" command="unbind">解绑</el-dropdown-item>
                    <el-dropdown-item command="sample">样例载荷</el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!sendersLoading && senders.length === 0" description="暂无发送方，源端推一次数据后会出现在这里" />
    </el-card>

    <el-card class="section" shadow="never">
      <div class="section-header">
        <span class="section-title">接收接口</span>
        <el-button type="primary" size="small" @click="showCreate = true">+ 新增接口</el-button>
      </div>
      <el-table
        :data="endpoints"
        border
        stripe
        size="small"
        v-loading="loading"
        class="nowrap-table"
        :row-class-name="rowClass"
        @row-click="onRowClick"
        @expand-change="onExpandChange"
        ref="tableRef"
        row-key="id"
      >
        <!-- 原生展开列（隐藏自带箭头，用左侧自定义箭头指示） -->
        <el-table-column type="expand" width="1">
          <template #default="{ row }">
            <div class="expand-panel">
              <div class="expand-toolbar">
                <span class="expand-title">接收数据（共 {{ row.count }} 条）</span>
                <el-button
                  v-if="row.count > 0"
                  size="small"
                  type="danger"
                  plain
                  @click="clearLogs(row)"
                >清空全部</el-button>
              </div>

              <!-- 加载该接口数据 -->
              <div v-loading="expandLoading[row.id]">
                <div v-if="(expandData[row.id] || []).length === 0" class="expand-empty">
                  暂无接收数据
                </div>
                <div v-else class="log-list">
                  <div v-for="(item, idx) in expandData[row.id] || []" :key="item.id" class="log-item">
                    <div class="log-head">
                      <span>#{{ idx + 1 }}</span>
                      <span>{{ item.received_at }}</span>
                      <el-tag v-if="item.sender_name" size="small" :type="item.sender_status === 'bound' ? 'success' : (item.sender_status === 'rejected' ? 'danger' : 'warning')">
                        {{ item.sender_name }}
                      </el-tag>
                      <el-button size="small" type="text" style="color:var(--el-color-danger);margin-left:auto" @click="deleteLog(item, row)">
                        删除
                      </el-button>
                    </div>
                    <pre class="log-payload">{{ pretty(item.payload) }}</pre>
                  </div>
                </div>

                <!-- 分页 -->
                <el-pagination
                  v-if="expandTotal[row.id] > expandPageSize"
                  class="expand-pager"
                  layout="total, prev, pager, next"
                  :total="expandTotal[row.id] || 0"
                  :page-size="expandPageSize"
                  :current-page="expandPage[row.id] || 1"
                  @current-change="(p) => onExpandPage(row.id, p)"
                />
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column width="48">
          <template #default="{ row }">
            <el-icon class="expand-icon" :class="{ expanded: expandedRow === row.id }">
              <ArrowRight />
            </el-icon>
          </template>
        </el-table-column>
        <el-table-column type="index" label="序号" width="60" />
        <el-table-column prop="name" label="接口名称" min-width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="name">{{ row.name }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="150" show-overflow-tooltip />
        <el-table-column prop="count" label="接收数" width="80" sortable />
        <el-table-column prop="created_at" label="创建时间" width="180" show-overflow-tooltip />
        <el-table-column label="Token" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.has_token" type="success" size="small">已设置</el-tag>
            <el-tag v-else type="info" size="small">无</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="接收地址" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <div class="ops">
              <code class="url">{{ baseUrl }}/api/remote/ingest/{{ row.name }}</code>
              <el-button size="small" type="text" @click.stop="copy(baseUrl + '/api/remote/ingest/' + row.name)">复制</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <div class="ops">
              <el-button size="small" type="text" @click.stop="openEdit(row)">编辑</el-button>
              <el-button size="small" type="text" @click.stop="rotateToken(row)">Token</el-button>
              <el-button size="small" type="text" style="color:var(--el-color-danger)" @click.stop="removeEndpoint(row)">删除</el-button>
            </div>
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

    <!-- Token 展示（仅创建 / 重置后显示一次） -->
    <el-dialog v-model="showToken" title="Ingest Token" width="520px" :close-on-click-modal="false">
      <el-alert type="warning" :closable="false" show-icon style="margin-bottom:12px">
        Token 仅在此展示一次，关闭后无法再次查看，请立即复制保存。源端请求需携带请求头
        <code>X-Ingest-Token: &lt;token&gt;</code>
      </el-alert>
      <div class="token-row">
        <code class="token-value">{{ tokenValue }}</code>
        <el-button type="primary" size="small" @click="copy(tokenValue)">复制</el-button>
      </div>
      <template #footer>
        <el-button type="primary" @click="showToken = false">我已保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑接口 -->
    <el-dialog v-model="showEdit" title="编辑接收接口" width="460px">
      <el-form label-width="80px">
        <el-form-item label="接口名称">
          <el-input v-model="editForm.name" placeholder="字母/数字/下划线/横线，1-64位" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="editForm.description" type="textarea" :rows="2" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 发送方样例载荷 -->
    <el-dialog v-model="showSample" :title="'样例载荷 — ' + (sampleSender?.display_name || sampleSender?.src_ip || '')" width="640px">
      <pre class="log-payload">{{ pretty(samplePayload) }}</pre>
      <template #footer>
        <el-button type="primary" @click="showSample = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { remoteApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight } from '@element-plus/icons-vue'

const endpoints = ref([])
const loading = ref(false)
const baseUrl = window.location.origin
const tableRef = ref(null)

// 发送方（接收端认人）
const senders = ref([])
const sendersLoading = ref(false)
const pendingCount = computed(() => senders.value.filter(s => s.status === 'pending').length)
const showSample = ref(false)
const samplePayload = ref('')
const sampleSender = ref(null)

const showCreate = ref(false)
const form = reactive({ name: '', description: '' })

const showEdit = ref(false)
const editForm = reactive({ id: null, name: '', description: '' })

// Token 一次性展示
const showToken = ref(false)
const tokenValue = ref('')

// 展开状态
const expandedRow = ref(null)
const expandData = reactive({})    // endpoint_id → log list
const expandLoading = reactive({})  // endpoint_id → bool
const expandPage = reactive({})     // endpoint_id → page number
const expandTotal = reactive({})     // endpoint_id → total
const expandPageSize = 20

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
  // 拦截器保证 code === 200 才会 resolve
  const res = await remoteApi.createEndpoint(form.name.trim(), form.description.trim())
  ElMessage.success('接口已创建')
  showCreate.value = false
  form.name = ''
  form.description = ''
  loadEndpoints()
  // token 仅展示一次
  const tok = res.data?.token
  if (tok) {
    tokenValue.value = tok
    showToken.value = true
  }
}

async function rotateToken(row) {
  await ElMessageBox.confirm(
    `确定重置接口「${row.name}」的 Token？旧 Token 将立即失效，源端需同步更换。`,
    '确认重置 Token',
    { type: 'warning', confirmButtonText: '重置', cancelButtonText: '取消' }
  )
  const res = await remoteApi.rotateToken(row.id)
  const tok = res.data?.token
  if (tok) {
    tokenValue.value = tok
    showToken.value = true
  }
  loadEndpoints()
}

async function openEdit(row) {
  editForm.id = row.id
  editForm.name = row.name
  editForm.description = row.description || ''
  showEdit.value = true
}

async function saveEdit() {
  if (!editForm.name.trim()) {
    ElMessage.warning('接口名称不能为空')
    return
  }
  if (!/^[A-Za-z0-9_-]{1,64}$/.test(editForm.name.trim())) {
    ElMessage.warning('名称只能包含字母、数字、下划线和横线（1-64位）')
    return
  }
  await remoteApi.updateEndpoint(editForm.id, editForm.name.trim(), editForm.description.trim())
  ElMessage.success('已保存')
  showEdit.value = false
  loadEndpoints()
}

async function removeEndpoint(row) {
  await ElMessageBox.confirm(
    `确定删除接口「${row.name}」及其全部 ${row.count} 条接收数据？`,
    '确认删除',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
  )
  await remoteApi.deleteEndpoint(row.id)
  ElMessage.success('已删除')
  if (expandedRow.value === row.id) expandedRow.value = null
  loadEndpoints()
}

async function clearLogs(row) {
  await ElMessageBox.confirm(
    `确定清空接口「${row.name}」的全部 ${row.count} 条接收数据？`,
    '确认清空',
    { type: 'warning', confirmButtonText: '清空', cancelButtonText: '取消' }
  )
  await remoteApi.clearLogs(row.id)
  ElMessage.success('已清空')
  if (expandedRow.value === row.id) {
    delete expandData[row.id]
    delete expandLoading[row.id]
  }
  loadEndpoints()
}

async function deleteLog(item, row) {
  await ElMessageBox.confirm('确定删除该条接收数据？', '确认删除', {
    type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消'
  })
  await remoteApi.deleteLog(item.id)
  ElMessage.success('已删除')
  // 刷新当前页
  await loadLogsFor(row.id)
  loadEndpoints()  // 更新 count
}

async function onRowClick(row) {
  const expanded = expandedRow.value !== row.id
  if (expanded) {
    expandedRow.value = row.id
    await loadLogsFor(row.id)
    tableRef.value?.toggleRowExpansion(row, true)
  } else {
    expandedRow.value = null
    tableRef.value?.toggleRowExpansion(row, false)
  }
}

async function onExpandChange(row, expanded) {
  // 同步状态：无论是点击行还是点击原生展开按钮触发
  if (expanded) {
    expandedRow.value = row.id
    await loadLogsFor(row.id)
  } else {
    if (expandedRow.value === row.id) {
      expandedRow.value = null
    }
  }
}

async function loadLogsFor(endpointId) {
  expandLoading[endpointId] = true
  try {
    const page = expandPage[endpointId] || 1
    const res = await remoteApi.listLogs(endpointId, { page, page_size: expandPageSize })
    expandData[endpointId] = res.data?.items || []
    expandTotal[endpointId] = res.data?.total || 0
  } finally {
    expandLoading[endpointId] = false
  }
}

async function onExpandPage(endpointId, p) {
  expandPage[endpointId] = p
  await loadLogsFor(endpointId)
}

function rowClass({ row }) {
  return expandedRow.value === row.id ? 'expanded-row' : ''
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

async function loadSenders() {
  sendersLoading.value = true
  try {
    const res = await remoteApi.listSenders()
    senders.value = res.data?.items || []
  } finally {
    sendersLoading.value = false
  }
}

async function bindSender(row) {
  let name = row.display_name || row.src_ip || ''
  try {
    const r = await ElMessageBox.prompt(
      '起个名字，方便日报里认人（留空则用源 IP）。',
      '绑定发送方',
      { inputValue: name, confirmButtonText: '绑定', cancelButtonText: '取消' }
    )
    name = (r.value || '').trim()
  } catch {
    return
  }
  await remoteApi.bindSender(row.id, name)
  ElMessage.success('已绑定')
  loadSenders()
}

async function unbindSender(row) {
  await ElMessageBox.confirm(
    `确定解绑「${row.display_name || row.src_ip}」？名字会清掉，数据照旧。`,
    '确认解绑',
    { type: 'warning', confirmButtonText: '解绑', cancelButtonText: '取消' }
  )
  await remoteApi.unbindSender(row.id)
  ElMessage.success('已退回待绑定')
  loadSenders()
}

async function rejectSender(row) {
  await ElMessageBox.confirm(
    `确定拒收「${row.display_name || row.src_ip}」？只是标记，数据照收照进日报。`,
    '确认拒收',
    { type: 'warning', confirmButtonText: '拒收', cancelButtonText: '取消' }
  )
  await remoteApi.rejectSender(row.id)
  ElMessage.success('已拒收')
  loadSenders()
}

async function deleteSender(row) {
  await ElMessageBox.confirm(
    `确定删除发送方「${row.display_name || row.src_ip}」的识别记录？它推过的数据会保留。`,
    '确认删除',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
  )
  await remoteApi.deleteSender(row.id)
  ElMessage.success('已删除')
  loadSenders()
}

function openSample(row) {
  sampleSender.value = row
  samplePayload.value = row.sample_payload || ''
  showSample.value = true
}

function onSenderOp(cmd, row) {
  if (cmd === 'unbind') return unbindSender(row)
  if (cmd === 'sample') return openSample(row)
  if (cmd === 'delete') return deleteSender(row)
}

onMounted(() => {
  loadEndpoints()
  loadSenders()
})
</script>

<style scoped>
.remote-container { padding: 20px; }
/* 头部一行放得下就一行，放不下省略号 —— 不换行 */
.page-header { margin-bottom: 16px; display: flex; align-items: baseline; gap: 12px; min-width: 0; }
.page-header h2 { margin: 0; font-size: 18px; font-weight: 600; flex: none; }
.page-header .tip { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tip { font-size: 12px; color: var(--el-text-color-secondary); }
.section { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-weight: 600; font-size: 14px; color: var(--el-text-color-primary); flex: none; }
.name { font-family: monospace; font-size: 13px; color: var(--el-color-primary); }
.muted { color: var(--el-text-color-secondary); }
.url { font-family: monospace; font-size: 12px; color: var(--el-text-color-regular); }

/* 表格单元格一律不换行，长内容省略号 + tooltip */
.nowrap-table :deep(.el-table__cell .cell) {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nowrap-table :deep(.el-table__cell .el-tooltip) { max-width: 100%; }

/* 操作列一行放齐，靠 dropdown 收下不常用的 */
.ops {
  display: flex;
  align-items: center;
  gap: 2px;
  white-space: nowrap;
}
.ops :deep(.el-button) { padding: 0 4px; }
.ops :deep(.el-button + .el-button) { margin-left: 0; }
.ops .url {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

:deep(.el-table .expanded-row td) { background: var(--el-fill-color-light) !important; }
:deep(.el-table td.el-table__cell) { cursor: pointer; }

.expand-icon {
  display: flex;
  align-items: center;
  transition: transform 0.2s;
  color: var(--el-text-color-placeholder);
  cursor: pointer;
}
.expand-icon.expanded { transform: rotate(90deg); color: var(--el-color-primary); }

/* 隐藏原生展开箭头（用自定义箭头代替） */
:deep(.el-table__expand-icon) { display: none; }

.expand-panel {
  padding: 12px 16px;
  background: var(--el-fill-color-light);
}

.expand-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.expand-title { font-size: 13px; color: var(--el-text-color-regular); font-weight: 500; }

.expand-empty { color: var(--el-text-color-secondary); font-size: 13px; padding: 8px 0; text-align: center; }

.log-list { display: flex; flex-direction: column; gap: 8px; }
.log-item { border: 1px solid var(--el-border-color-light); border-radius: 4px; overflow: hidden; }
.log-head {
  background: var(--el-fill-color-light);
  padding: 5px 12px;
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  align-items: center;
}
.log-payload {
  margin: 0;
  padding: 10px 12px;
  background: var(--code-bg);
  color: var(--code-fg);
  font-size: 12px;
  /* 不换行：长行横向滚动，保住 JSON 的缩进结构 */
  white-space: pre;
  max-height: 280px;
  overflow: auto;
}
.expand-pager { margin-top: 10px; justify-content: flex-end; }

.token-row {
  display: flex;
  align-items: center;
  gap: 12px;
}
.token-value {
  flex: 1;
  min-width: 0;
  font-family: monospace;
  font-size: 13px;
  white-space: nowrap;
  overflow-x: auto;
  background: var(--el-fill-color-light);
  padding: 8px 12px;
  border-radius: 4px;
  color: var(--el-text-color-primary);
}
</style>
