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
      <el-table
        :data="endpoints"
        border
        stripe
        size="small"
        v-loading="loading"
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
                      <el-button size="small" type="text" style="color:#f56c6c;margin-left:auto" @click="deleteLog(item, row)">
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
            <el-button size="small" type="text" @click.stop="copy(baseUrl + '/api/remote/ingest/' + row.name)">复制</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="text" @click.stop="openEdit(row)">编辑</el-button>
            <el-button size="small" type="text" style="color:#f56c6c" @click.stop="removeEndpoint(row)">删除</el-button>
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { remoteApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowRight } from '@element-plus/icons-vue'

const endpoints = ref([])
const loading = ref(false)
const baseUrl = window.location.origin
const tableRef = ref(null)

const showCreate = ref(false)
const form = reactive({ name: '', description: '' })

const showEdit = ref(false)
const editForm = reactive({ id: null, name: '', description: '' })

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
  const res = await remoteApi.updateEndpoint(editForm.id, editForm.name.trim(), editForm.description.trim())
  if (res.code === 0) {
    ElMessage.success('已保存')
    showEdit.value = false
    loadEndpoints()
  } else {
    ElMessage.error(res.msg || '保存失败')
  }
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

:deep(.el-table .expanded-row td) { background: #f5f7fa !important; }
:deep(.el-table td.el-table__cell) { cursor: pointer; }

.expand-icon {
  display: flex;
  align-items: center;
  transition: transform 0.2s;
  color: #c0c4cc;
  cursor: pointer;
}
.expand-icon.expanded { transform: rotate(90deg); color: #409EFF; }

/* 隐藏原生展开箭头（用自定义箭头代替） */
:deep(.el-table__expand-icon) { display: none; }

.expand-panel {
  padding: 12px 16px;
  background: #fafafa;
}

.expand-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.expand-title { font-size: 13px; color: #606266; font-weight: 500; }

.expand-empty { color: #909399; font-size: 13px; padding: 8px 0; text-align: center; }

.log-list { display: flex; flex-direction: column; gap: 8px; }
.log-item { border: 1px solid #e4e7ed; border-radius: 4px; overflow: hidden; }
.log-head {
  background: #f5f7fa;
  padding: 5px 12px;
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #909399;
  align-items: center;
}
.log-payload {
  margin: 0;
  padding: 10px 12px;
  background: #1e1e1e;
  color: #d4d4d4;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 280px;
  overflow: auto;
}
.expand-pager { margin-top: 10px; justify-content: flex-end; }
</style>
