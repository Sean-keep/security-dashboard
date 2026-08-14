<template>
  <div class="page-container">

    <el-tabs v-model="activeTab" class="report-tabs">

      <!-- ════════════════════ Tab 1: 生成报告 ════════════════════ -->
      <el-tab-pane label="生成报告" name="generate">
        <el-card shadow="never" class="mb-16">
          <div class="toolbar">
            <el-date-picker
              v-model="selectedDate"
              type="date"
              placeholder="选择日期"
              value-format="YYYY-MM-DD"
              size="default"
              style="width: 180px"
            />
            <el-button type="primary" :loading="loading" @click="generateReport">生成巡检报告</el-button>
            <el-button :disabled="!currentReport" @click="exportWord">导出 Word</el-button>
            <el-button :disabled="!currentReport" @click="exportTxt">导出 TXT</el-button>
          </div>
          <!-- 数据来源勾选 -->
          <div class="pick-panel">
            <div class="pick-checks">
              <el-checkbox v-model="includeAddresses">包含当日攻击地址</el-checkbox>
              <el-checkbox v-model="includeMonitoring">包含服务器监控</el-checkbox>
            </div>
            <el-divider class="pick-div" />
            <div class="pick-row" v-if="scriptOptions.length">
              <div class="pick-head">
                <span class="pick-title">执行脚本</span>
                <div class="pick-actions">
                  <el-button link type="primary" size="small" @click="selectAllScripts">全选</el-button>
                  <el-button link size="small" @click="clearScripts">清空</el-button>
                </div>
              </div>
              <div class="pick-box">
                <el-checkbox-group v-model="selectedScriptIds" size="small">
                  <el-checkbox v-for="sc in scriptOptions" :key="sc.id" :label="sc.id" border>{{ sc.name }}</el-checkbox>
                </el-checkbox-group>
              </div>
              <span class="pick-hint" v-if="!selectedScriptIds.length">未勾选则不执行脚本</span>
            </div>
            <div class="pick-row" v-if="endpointOptions.length">
              <div class="pick-head">
                <span class="pick-title">整合接收端口</span>
                <div class="pick-actions">
                  <el-button link type="primary" size="small" @click="selectAllEndpoints">全选</el-button>
                  <el-button link size="small" @click="clearEndpoints">清空</el-button>
                </div>
              </div>
              <div class="pick-box">
                <el-checkbox-group v-model="selectedEndpointIds" size="small">
                  <el-checkbox v-for="ep in endpointOptions" :key="ep.id" :label="ep.id" border>{{ ep.name }}</el-checkbox>
                </el-checkbox-group>
              </div>
              <span class="pick-hint" v-if="!selectedEndpointIds.length">未勾选则不整合接收数据</span>
            </div>
            <div class="order-box" v-if="selectedEndpointIds.length">
              <div class="order-title">接收端口顺序（上下调整，决定报告中接口排列）</div>
              <div v-for="(eid, idx) in selectedEndpointIds" :key="eid" class="order-item">
                <span class="order-name">{{ endpointName(eid) }}</span>
                <div class="order-btns">
                  <el-button size="small" :disabled="idx === 0" text bg @click="moveEndpointUp(idx)">↑ 上移</el-button>
                  <el-button size="small" :disabled="idx === selectedEndpointIds.length - 1" text bg @click="moveEndpointDown(idx)">↓ 下移</el-button>
                </div>
              </div>
            </div>
            <el-divider class="pick-div" />
            <div class="order-box">
              <div class="order-title">报告板块顺序（从上到下）</div>
              <div v-for="(key, idx) in sectionOrder" :key="key" class="order-item">
                <span class="order-name">{{ sectionLabels[key] }}</span>
                <div class="order-btns">
                  <el-button size="small" :disabled="idx === 0" text bg @click="moveUp(idx)">↑ 上移</el-button>
                  <el-button size="small" :disabled="idx === sectionOrder.length - 1" text bg @click="moveDown(idx)">↓ 下移</el-button>
                </div>
              </div>
            </div>
            <el-divider class="pick-div" />
            <div class="overview-edit">
              <span class="ov-label">今日速览（总结性说明，生成报告时填写）：</span>
              <el-input v-model="summaryText" type="textarea" :rows="4"
                placeholder="如：1、无可用性问题，ospay线上服务器内存使用率峰值超过80%&#10;2、nginx日志发现7个ip攻击行为，无入侵成功迹象..." />
            </div>
          </div>
        </el-card>

        <el-empty v-if="!currentReport && !loading" description="请选择日期后点击「生成巡检报告」" />

        <template v-if="currentReport">
          <!-- 今日速览 -->
          <el-card shadow="never" class="mb-16" v-if="currentReport">
            <template #header>
              <div class="card-header">
                <span class="card-title">巡检报告 · {{ currentReport.report_date }}</span>
                <span class="card-sub">生成时间：{{ currentReport.generated_at }}</span>
              </div>
            </template>
            <div class="overview">
              <div class="ov-title">今日速览</div>
              <pre class="ov-text">{{ currentReport.summary_text || '（未填写今日速览）' }}</pre>
            </div>
          </el-card>

          <!-- 各板块按可排序顺序渲染 -->
          <template v-for="key in sectionOrder" :key="key">
            <el-card shadow="never" class="mb-16" v-if="key === 'addresses' && currentReport.addresses !== null">
              <template #header>
                <div class="card-header">
                  <span class="card-title">当日攻击地址（按攻击次数排序）</span>
                  <span class="card-sub">{{ (currentReport.addresses || []).length }} 条</span>
                </div>
              </template>
              <el-table :data="currentReport.addresses || []" border stripe size="small" max-height="460">
                <el-table-column type="index" label="#" width="48" />
                <el-table-column prop="ip_address" label="IP 地址" min-width="150" />
                <el-table-column prop="country" label="国家/地区" width="160" show-overflow-tooltip />
                <el-table-column prop="domain" label="关联域名" min-width="170" show-overflow-tooltip />
                <el-table-column prop="start_time" label="起始时间" width="170" />
                <el-table-column prop="end_time" label="结束时间" width="170" />
                <el-table-column prop="duration" label="持续(s)" width="100" align="right" />
                <el-table-column prop="attack_count" label="攻击次数" width="110" align="right" sortable />
              </el-table>
            </el-card>

            <el-card shadow="never" class="mb-16" v-if="key === 'monitoring' && currentReport.servers !== null">
              <template #header>
                <div class="card-header">
                  <span class="card-title">服务器监控</span>
                  <span class="card-sub">24 小时</span>
                </div>
              </template>
              <div class="server-list">
                <div v-for="s in currentReport.servers" :key="s.instance" class="server-card">
                  <div class="node-info">
                    <el-icon class="node-icon"><Monitor /></el-icon>
                    <span class="node-alias" v-if="s.alias">{{ s.alias }}</span>
                    <span class="node-addr" :class="{ 'has-alias': s.alias }">{{ s.instance }}</span>
                  </div>
                  <div class="metric-rows">
                    <div class="metric-line"><span class="ml-label">CPU</span><span class="ml-val">均值 {{ s.cpu?.avg ?? '-' }}% ｜ 峰值 {{ s.cpu?.peak ?? '-' }}%</span></div>
                    <div class="metric-line"><span class="ml-label">内存</span><span class="ml-val">均值 {{ s.memory?.avg ?? '-' }}% ｜ 峰值 {{ s.memory?.peak ?? '-' }}%</span></div>
                    <div class="metric-line" v-for="dk in (s.disks || [])" :key="dk.mountpoint">
                      <span class="ml-label">{{ dk.mountpoint === '/' ? '磁盘（/）' : '磁盘（' + dk.mountpoint + '）' }}</span>
                      <span class="ml-val">均值 {{ dk.avg ?? '-' }}% ｜ 峰值 {{ dk.peak ?? '-' }}%</span>
                    </div>
                  </div>
                </div>
              </div>
            </el-card>

            <el-card shadow="never" class="mb-16" v-if="key === 'scripts' && currentReport.scripts?.length">
              <template #header>
                <div class="card-header">
                  <span class="card-title">脚本执行结果</span>
                  <span class="card-sub">{{ currentReport.script_count }} 个已执行脚本</span>
                </div>
              </template>
              <div class="script-list">
                <div v-for="sc in currentReport.scripts" :key="sc.id" class="script-block">
                  <div class="script-head">
                    <span class="script-name">{{ sc.name }}</span>
                    <el-tag :type="sc.exit_code === 0 ? 'success' : 'danger'" size="small" effect="plain">
                      {{ sc.exit_code === 0 ? '成功' : '失败' }}（退出码 {{ sc.exit_code }}）
                    </el-tag>
                    <span class="script-type">{{ sc.script_type }}</span>
                  </div>
                  <pre class="script-out" v-if="sc.stdout">{{ sc.stdout }}</pre>
                  <pre class="script-err" v-if="sc.stderr">{{ sc.stderr }}</pre>
                </div>
              </div>
            </el-card>

            <el-card shadow="never" class="mb-16" v-if="key === 'ingested' && currentReport.ingested?.length">
              <template #header>
                <div class="card-header">
                  <span class="card-title">接收数据（最近一条）</span>
                  <span class="card-sub">{{ currentReport.ingested.length }} 个端口</span>
                </div>
              </template>
              <div class="script-list">
                <div v-for="it in currentReport.ingested" :key="it.endpoint_name" class="script-block">
                  <div class="script-head">
                    <span class="script-name">{{ it.endpoint_name }}</span>
                    <span class="script-type">{{ it.received_at }}</span>
                  </div>
                  <pre class="script-out" v-if="it.payload">{{ it.payload }}</pre>
                </div>
              </div>
            </el-card>
          </template>
        </template>
      </el-tab-pane>

      <!-- ════════════════════ Tab 2: 报告列表 ════════════════════ -->
      <el-tab-pane label="报告列表" name="list">
        <el-card shadow="never" class="mb-16">
          <template #header>
            <div class="toolbar">
              <span class="card-title">历史巡检报告</span>
              <el-button size="small" :loading="refreshing" @click="loadReports">
                <el-icon><Refresh /></el-icon> 刷新
              </el-button>
            </div>
          </template>

          <el-table :data="reportList" v-loading="refreshing" border stripe size="small">
            <el-table-column prop="id" label="ID" width="70" align="center" />
            <el-table-column prop="report_date" label="报告日期" width="140" />
            <el-table-column prop="generated_at" label="生成时间" width="180" />
            <el-table-column prop="address_count" label="攻击地址" width="110" align="right" />
            <el-table-column prop="script_count" label="脚本数" width="100" align="right" />
            <el-table-column prop="created_by" label="生成人" width="120" />
            <el-table-column label="操作">
              <template #default="{ row }">
                <el-button size="small" type="primary" plain @click="previewReport(row)">预览</el-button>
                <el-button size="small" @click="exportReport(row, 'word')">Word</el-button>
                <el-button size="small" @click="exportReport(row, 'txt')">TXT</el-button>
                <el-button size="small" type="danger" plain @click="removeReport(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-pagination
            v-if="reportTotal > 0"
            background
            layout="prev, pager, next, total"
            :total="reportTotal"
            :page-size="reportPageSize"
            :current-page="reportPage"
            @current-change="onPageChange"
            style="margin-top:16px;justify-content:center"
          />
        </el-card>
      </el-tab-pane>

    </el-tabs>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewVisible" title="报告预览" width="900px" destroy-on-close>
      <template v-if="previewData">
        <div class="overview" v-if="previewData">
          <div class="ov-title">今日速览</div>
          <pre class="ov-text">{{ previewData.summary_text || '（未填写今日速览）' }}</pre>
        </div>

        <template v-for="key in sectionOrder" :key="key">
          <template v-if="key === 'addresses' && previewData.addresses !== null">
            <el-divider content-position="left">攻击地址</el-divider>
            <el-table :data="previewData.addresses || []" border stripe size="small" max-height="280">
              <el-table-column prop="ip_address" label="IP" min-width="140" />
              <el-table-column prop="country" label="国家" width="130" show-overflow-tooltip />
              <el-table-column prop="domain" label="域名" min-width="160" show-overflow-tooltip />
              <el-table-column prop="start_time" label="起始时间" width="165" />
              <el-table-column prop="attack_count" label="次数" width="90" align="right" />
            </el-table>
          </template>

          <template v-if="key === 'monitoring' && previewData.servers !== null">
            <el-divider content-position="left">服务器监控</el-divider>
            <div class="server-list">
              <div v-for="s in previewData.servers" :key="s.instance" class="server-card">
                <div class="node-info">
                  <el-icon class="node-icon"><Monitor /></el-icon>
                  <span class="node-alias" v-if="s.alias">{{ s.alias }}</span>
                  <span class="node-addr">{{ s.instance }}</span>
                </div>
                <div class="metric-rows">
                  <div class="metric-line"><span class="ml-label">CPU</span><span class="ml-val">均值 {{ s.cpu?.avg ?? '-' }}% ｜ 峰值 {{ s.cpu?.peak ?? '-' }}%</span></div>
                  <div class="metric-line"><span class="ml-label">内存</span><span class="ml-val">均值 {{ s.memory?.avg ?? '-' }}% ｜ 峰值 {{ s.memory?.peak ?? '-' }}%</span></div>
                  <div class="metric-line" v-for="dk in (s.disks || [])" :key="dk.mountpoint">
                    <span class="ml-label">{{ dk.mountpoint === '/' ? '磁盘（/）' : '磁盘（' + dk.mountpoint + '）' }}</span>
                    <span class="ml-val">均值 {{ dk.avg ?? '-' }}% ｜ 峰值 {{ dk.peak ?? '-' }}%</span>
                  </div>
                </div>
              </div>
            </div>
          </template>

          <template v-if="key === 'scripts' && previewData.scripts?.length">
            <el-divider content-position="left">脚本执行结果</el-divider>
            <div class="script-list">
              <div v-for="sc in previewData.scripts" :key="sc.id" class="script-block">
                <div class="script-head">
                  <span class="script-name">{{ sc.name }}</span>
                  <el-tag :type="sc.exit_code === 0 ? 'success' : 'danger'" size="small" effect="plain">
                    {{ sc.exit_code === 0 ? '成功' : '失败' }}（退出码 {{ sc.exit_code }}）
                  </el-tag>
                  <span class="script-type">{{ sc.script_type }}</span>
                </div>
                <pre class="script-out" v-if="sc.stdout">{{ sc.stdout }}</pre>
                <pre class="script-err" v-if="sc.stderr">{{ sc.stderr }}</pre>
              </div>
            </div>
          </template>

          <template v-if="key === 'ingested' && previewData.ingested?.length">
            <el-divider content-position="left">接收数据（最近一条）</el-divider>
            <div class="script-list">
              <div v-for="it in previewData.ingested" :key="it.endpoint_name" class="script-block">
                <div class="script-head">
                  <span class="script-name">{{ it.endpoint_name }}</span>
                  <span class="script-type">{{ it.received_at }}</span>
                </div>
                <pre class="script-out" v-if="it.payload">{{ it.payload }}</pre>
              </div>
            </div>
          </template>
        </template>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { reports, reportMgmt, remoteApi } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Monitor, Refresh } from '@element-plus/icons-vue'

// ── Tab 状态 ──
const activeTab = ref('generate')

// ── 生成报告 ──
const selectedDate = ref(formatToday())
const includeAddresses = ref(true)
const includeMonitoring = ref(true)
const loading = ref(false)
const currentReport = ref(null)
const DEFAULT_SUMMARY = `1、无可用性问题，ospay线上服务器内存使用率峰值超过80%
2、nginx日志发现7个ip攻击行为，无入侵成功迹象
3、代理IP剩余流量:1116.17GB，预计还可以使用111天（预计每天消耗10G）
4、短信网关余额：304.72372，预计还可以使用30天（预计每天消耗10）`
const summaryText = ref(DEFAULT_SUMMARY)
const scriptOptions = ref([])
const selectedScriptIds = ref([])
const endpointOptions = ref([])
const selectedEndpointIds = ref([])

// ── 全选 / 清空 ──
const selectAllScripts = () => { selectedScriptIds.value = scriptOptions.value.map(s => s.id) }
const clearScripts = () => { selectedScriptIds.value = [] }
const selectAllEndpoints = () => { selectedEndpointIds.value = endpointOptions.value.map(ep => ep.id) }
const clearEndpoints = () => { selectedEndpointIds.value = [] }
const endpointName = (id) => {
  const ep = endpointOptions.value.find(e => e.id === id)
  return ep ? ep.name : ('#' + id)
}
const moveEndpointUp = (idx) => {
  if (idx > 0) {
    const a = selectedEndpointIds.value
    ;[a[idx - 1], a[idx]] = [a[idx], a[idx - 1]]
  }
}
const moveEndpointDown = (idx) => {
  if (idx < selectedEndpointIds.value.length - 1) {
    const a = selectedEndpointIds.value
    ;[a[idx + 1], a[idx]] = [a[idx], a[idx + 1]]
  }
}

// ── 报告板块顺序（可上下调整） ──
const SECTION_KEYS = ['addresses', 'monitoring', 'scripts', 'ingested']
const sectionLabels = { addresses: '当日攻击地址', monitoring: '服务器监控', scripts: '脚本执行结果', ingested: '接收数据（最近一条）' }
const sectionOrder = ref([...SECTION_KEYS])
const STORAGE_ORDER = 'report_section_order'
const moveUp = (idx) => { if (idx > 0) { const a = sectionOrder.value; [a[idx - 1], a[idx]] = [a[idx], a[idx - 1]] } }
const moveDown = (idx) => { if (idx < sectionOrder.value.length - 1) { const a = sectionOrder.value; [a[idx + 1], a[idx]] = [a[idx], a[idx + 1]] } }
function restoreOrder() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_ORDER) || '[]')
    if (Array.isArray(saved) && saved.length === SECTION_KEYS.length && saved.every(k => SECTION_KEYS.includes(k))) {
      sectionOrder.value = saved
    }
  } catch (e) {}
}
watch(sectionOrder, (v) => { localStorage.setItem(STORAGE_ORDER, JSON.stringify(v)) }, { deep: true })

// ── 勾选状态持久化（默认恢复上次生成报告的勾选） ──
const STORAGE_SCRIPTS = 'report_selected_scripts'
const STORAGE_ENDPOINTS = 'report_selected_endpoints'

function restoreSelection() {
  try {
    const savedScripts = JSON.parse(localStorage.getItem(STORAGE_SCRIPTS) || '[]')
    if (Array.isArray(savedScripts) && scriptOptions.value.length) {
      const validIds = new Set(scriptOptions.value.map(s => s.id))
      selectedScriptIds.value = savedScripts.filter(id => validIds.has(id))
    }
  } catch (e) {}
  try {
    const savedEndpoints = JSON.parse(localStorage.getItem(STORAGE_ENDPOINTS) || '[]')
    if (Array.isArray(savedEndpoints) && endpointOptions.value.length) {
      const validIds = new Set(endpointOptions.value.map(ep => ep.id))
      selectedEndpointIds.value = savedEndpoints.filter(id => validIds.has(id))
    }
  } catch (e) {}
}

watch(selectedScriptIds, (v) => {
  localStorage.setItem(STORAGE_SCRIPTS, JSON.stringify(v))
}, { deep: true })
watch(selectedEndpointIds, (v) => {
  localStorage.setItem(STORAGE_ENDPOINTS, JSON.stringify(v))
}, { deep: true })

function formatToday() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

onMounted(async () => {
  try {
    const res = await reportMgmt.list({ page: 1, page_size: 1 })
    // just a connectivity check
  } catch (e) {}
  try {
    const r = await reportMgmt.list({ page: 1, page_size: 1 })
    const scriptsRes = await import('@/api').then(m => m.inspectApi?.listScripts())
    if (scriptsRes) {
      scriptOptions.value = scriptsRes.data || []
    } else {
      const sr = await (await import('@/api')).inspectApi.listScripts()
      scriptOptions.value = sr.data || []
    }
  } catch (e) {
    scriptOptions.value = []
  }
  try {
    const er = await remoteApi.listEndpoints()
    endpointOptions.value = er.data || []
  } catch (e) {
    endpointOptions.value = []
  }
  // 选项加载完成后，恢复上次勾选与板块顺序
  restoreSelection()
  restoreOrder()
})

const generateReport = async () => {
  loading.value = true
  try {
    const params = { date: selectedDate.value }
    if (!includeAddresses.value) params.include_addresses = '0'
    if (!includeMonitoring.value) params.include_monitoring = '0'
    if (selectedScriptIds.value.length) params.script_ids = selectedScriptIds.value.join(',')
    if (selectedEndpointIds.value.length) params.endpoint_ids = selectedEndpointIds.value.join(',')
    params.summary_text = summaryText.value
    const res = await reports.inspection(params)
    currentReport.value = res.data || null
    if (currentReport.value) ElMessage.success('报告已生成并保存')
  } catch (e) {
    ElMessage.error('生成巡检报告失败')
  } finally {
    loading.value = false
  }
}

// ── 报告列表 ──
const reportList = ref([])
const reportTotal = ref(0)
const reportPage = ref(1)
const reportPageSize = ref(10)
const refreshing = ref(false)

const loadReports = async () => {
  refreshing.value = true
  try {
    const res = await reportMgmt.list({ page: reportPage.value, page_size: reportPageSize.value })
    reportList.value = res.data?.items || []
    reportTotal.value = res.data?.total || 0
  } catch (e) {
    ElMessage.error('加载报告列表失败')
  } finally {
    refreshing.value = false
  }
}
loadReports()

const onPageChange = (p) => {
  reportPage.value = p
  loadReports()
}

// ── 预览 ──
const previewVisible = ref(false)
const previewData = ref(null)

const previewReport = async (row) => {
  try {
    const res = await reportMgmt.get(row.id)
    previewData.value = res.data || null
    previewVisible.value = true
  } catch (e) {
    ElMessage.error('加载报告详情失败')
  }
}

// ── 导出（复用同一份数据） ──
const downloadFile = (content, filename, mime) => {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const buildText = (data) => {
  const r = data
  const L = []
  L.push('═══════════════════════════════════════════════')
  L.push(`        安全巡检报告 · ${r.report_date}`)
  L.push('═══════════════════════════════════════════════')
  L.push(`生成时间: ${r.generated_at}`)
  if (r.summary_text) {
    L.push('')
    L.push('【今日速览】')
    L.push(r.summary_text)
    L.push('───────────────────────────────────────────────')
  }
  const txtParts = []
  if (r.addresses !== null) txtParts.push(`当日攻击地址: ${r.address_count}`)
  if (r.servers !== null) txtParts.push(`监控服务器: ${(r.servers || []).length}`)
  if (r.script_count > 0) txtParts.push(`脚本执行: ${r.script_count}`)
  if (r.servers !== null) txtParts.push(`监控: ${r.monitoring_connected ? '已连接' : '未连接'}`)
  if (txtParts.length) L.push(txtParts.join(' ｜ '))
  L.push('───────────────────────────────────────────────')
  for (const key of sectionOrder.value) {
    if (key === 'addresses' && r.addresses && r.addresses.length) {
      L.push('【攻击地址】')
      ;(r.addresses || []).forEach((a, i) => {
        const country = a.country ? `（${a.country}）` : ''
        L.push(`${i + 1}. 攻击地址: ${a.ip_address}${country}`)
        L.push(`   攻击时间: ${a.start_time} ~ ${a.end_time}`)
        L.push(`   持续时间: ${a.duration} 秒`)
        L.push(`   攻击次数: ${a.attack_count}`)
        L.push(`   攻击域名: ${a.domain || '-'}`)
      })
      L.push('───────────────────────────────────────────────')
    } else if (key === 'monitoring' && r.servers && r.servers.length) {
      L.push('【服务器监控】')
      ;(r.servers || []).forEach((s, i) => {
        L.push(`${i + 1}. ${s.alias || ''} ${s.instance}`)
        L.push(`   CPU 均值 ${s.cpu?.avg ?? '-'}% / 峰值 ${s.cpu?.peak ?? '-'}%`)
        L.push(`   内存 均值 ${s.memory?.avg ?? '-'}% / 峰值 ${s.memory?.peak ?? '-'}%`)
        ;(s.disks || []).forEach((dk) => {
          L.push(`   磁盘 ${dk.mountpoint} 均值 ${dk.avg ?? '-'}% / 峰值 ${dk.peak ?? '-'}%`)
        })
      })
      L.push('───────────────────────────────────────────────')
    } else if (key === 'scripts' && r.scripts && r.scripts.length) {
      L.push('【脚本执行结果】')
      ;(r.scripts || []).forEach((sc, i) => {
        L.push(`${i + 1}. ${sc.name} [${sc.script_type}] 退出码 ${sc.exit_code}`)
        if (sc.stdout) L.push('   ' + sc.stdout.replace(/\n/g, '\n   '))
        if (sc.stderr) L.push('   错误: ' + sc.stderr.replace(/\n/g, '\n   '))
      })
      L.push('───────────────────────────────────────────────')
    } else if (key === 'ingested' && r.ingested && r.ingested.length) {
      L.push('【接收数据（最近一条）】')
      ;(r.ingested || []).forEach((it, i) => {
        L.push(`${i + 1}. 端口: ${it.endpoint_name} ｜ 接收时间: ${it.received_at}`)
        if (it.payload) L.push('   ' + it.payload.replace(/\n/g, '\n   '))
      })
    }
  }
  L.push('═══════════════════════════════════════════════')
  return L.join('\n')
}

const buildHtml = (data) => {
  const r = data
  const L = []
  L.push('<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">')
  L.push('<head><meta charset="utf-8"><title>巡检报告</title></head><body>')
  L.push(`<h2>安全巡检报告 · ${r.report_date}</h2>`)
  L.push(`<p>生成时间：${r.generated_at}</p>`)
  if (r.summary_text) {
    L.push('<h3>今日速览</h3>')
    L.push(`<pre>${r.summary_text.replace(/</g, '&lt;')}</pre>`)
  }
  const htmlParts = []
  if (r.addresses !== null) htmlParts.push(`当日攻击地址：${r.address_count}`)
  if (r.servers !== null) htmlParts.push(`监控服务器：${(r.servers || []).length}`)
  if (r.script_count > 0) htmlParts.push(`脚本执行：${r.script_count}`)
  if (r.servers !== null) htmlParts.push(`监控：${r.monitoring_connected ? '已连接' : '未连接'}`)
  if (htmlParts.length) L.push(`<p>${htmlParts.join(' ｜ ')}</p>`)
  for (const key of sectionOrder.value) {
    if (key === 'addresses' && r.addresses && r.addresses.length) {
      L.push('<h3>攻击地址</h3>')
      ;(r.addresses || []).forEach((a, i) => {
        const country = a.country ? `（${a.country}）` : ''
        L.push(`<p><b>${i + 1}. 攻击地址:</b> ${a.ip_address}${country}<br/>`)
        L.push(`攻击时间: ${a.start_time} ~ ${a.end_time}<br/>`)
        L.push(`持续时间: ${a.duration} 秒<br/>`)
        L.push(`攻击次数: ${a.attack_count}<br/>`)
        L.push(`攻击域名: ${a.domain || '-'}</p>`)
      })
    } else if (key === 'monitoring' && r.servers && r.servers.length) {
      L.push('<h3>服务器监控</h3>')
      ;(r.servers || []).forEach((s, i) => {
        L.push(`<p><b>${i + 1}. ${s.alias || ''} ${s.instance}</b><br/>`)
        L.push(`CPU 均值 ${s.cpu?.avg ?? '-'}% / 峰值 ${s.cpu?.peak ?? '-'}%<br/>`)
        L.push(`内存 均值 ${s.memory?.avg ?? '-'}% / 峰值 ${s.memory?.peak ?? '-'}%<br/>`)
        ;(s.disks || []).forEach((dk) => {
          L.push(`磁盘 ${dk.mountpoint} 均值 ${dk.avg ?? '-'}% / 峰值 ${dk.peak ?? '-'}%<br/>`)
        })
        L.push('</p>')
      })
    } else if (key === 'scripts' && r.scripts && r.scripts.length) {
      L.push('<h3>脚本执行结果</h3>')
      ;(r.scripts || []).forEach((sc, i) => {
        L.push(`<p><b>${i + 1}. ${sc.name}</b> [${sc.script_type}] 退出码 ${sc.exit_code}<br/>`)
        if (sc.stdout) L.push(`<pre>${sc.stdout.replace(/</g, '&lt;')}</pre>`)
        if (sc.stderr) L.push(`<pre>错误: ${sc.stderr.replace(/</g, '&lt;')}</pre>`)
        L.push('</p>')
      })
    } else if (key === 'ingested' && r.ingested && r.ingested.length) {
      L.push('<h3>接收数据（最近一条）</h3>')
      ;(r.ingested || []).forEach((it, i) => {
        L.push(`<p><b>${i + 1}. ${it.endpoint_name}</b> ｜ 接收时间: ${it.received_at}<br/>`)
        if (it.payload) L.push(`<pre>${it.payload.replace(/</g, '&lt;')}</pre>`)
        L.push('</p>')
      })
    }
  }
  L.push('<\/' + 'body><\/' + 'html>')
  return L.join('')
}

// 当前报告导出（生成报告 Tab）
const exportWord = () => {
  if (!currentReport.value) return
  downloadFile(buildHtml(currentReport.value), `巡检报告_${currentReport.value.report_date}.doc`, 'application/msword')
}
const exportTxt = () => {
  if (!currentReport.value) return
  downloadFile(buildText(currentReport.value), `巡检报告_${currentReport.value.report_date}.txt`, 'text/plain;charset=utf-8')
}

// 报告列表导出（先拉详情再导）
const exportReport = async (row, fmt) => {
  try {
    const res = await reportMgmt.get(row.id)
    const data = res.data
    if (!data) return
    if (fmt === 'word') {
      downloadFile(buildHtml(data), `巡检报告_${data.report_date}.doc`, 'application/msword')
    } else {
      downloadFile(buildText(data), `巡检报告_${data.report_date}.txt`, 'text/plain;charset=utf-8')
    }
  } catch (e) {
    ElMessage.error('导出失败')
  }
}

// 删除
const removeReport = (row) => {
  ElMessageBox.confirm(`确认删除 ${row.report_date} 的巡检报告？`, '删除确认', { type: 'warning' })
    .then(async () => {
      try {
        await reportMgmt.delete(row.id)
        ElMessage.success('报告已删除')
        loadReports()
      } catch (e) {
        ElMessage.error('删除失败')
      }
    })
    .catch(() => {})
}
</script>

<style scoped>
.mb-16 { margin-bottom: 16px; }
.toolbar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.pick-panel { margin-top: 14px; border: 1px solid #ebeef5; border-radius: 8px; padding: 14px 16px; background: #fafafa; }
.pick-row { margin-bottom: 18px; }
.pick-row:last-child { margin-bottom: 0; }
.pick-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.pick-title { font-size: 13px; font-weight: 600; color: #303133; }
.pick-actions { display: flex; gap: 2px; }
.pick-box { max-height: 168px; overflow-y: auto; padding: 4px 2px; border: 1px solid #f0f0f0; border-radius: 6px; background: #fff; }
.pick-box :deep(.el-checkbox-group) { display: flex; flex-wrap: wrap; gap: 8px; }
.pick-box :deep(.el-checkbox) { margin-right: 0; margin-bottom: 0; }
.pick-hint { font-size: 12px; color: #c0c4cc; margin-top: 8px; display: block; }
.pick-checks { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; }
.pick-div { margin: 14px 0; }
.order-box { border-top: 1px dashed #e4e7ed; padding-top: 4px; }
.order-title { font-size: 12px; color: #909399; margin-bottom: 8px; }
.order-item { display: flex; align-items: center; justify-content: space-between; padding: 5px 10px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; margin-bottom: 6px; }
.order-name { font-size: 13px; color: #303133; }
.order-btns { display: flex; gap: 4px; }
.card-header { display: flex; align-items: center; gap: 10px; }
.card-title { font-weight: 600; font-size: 15px; }

.summary { display: flex; gap: 32px; }
.summary-dlg { margin-bottom: 0; }
.summary-item { text-align: center; }
.overview { margin-top: 4px; }
.ov-title { font-size: 14px; font-weight: 700; color: #303133; margin-bottom: 8px; }
.ov-text { white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; line-height: 1.7; color: #303133; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; padding: 12px 14px; margin: 0; }
.overview-edit { margin-top: 4px; }
.ov-label { font-size: 13px; font-weight: 600; color: #303133; display: block; margin-bottom: 8px; }
.s-val { font-size: 24px; font-weight: 700; color: #303133; }
.s-val.ok { color: #67c23a; }
.s-val.bad { color: #f56c6c; }
.s-label { font-size: 12px; color: #909399; margin-top: 4px; }

.server-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 16px; margin-top: 8px; }
.server-card { border: 1px solid #e4e7ed; border-radius: 10px; padding: 18px 20px; background: #fafafa; }
.node-info { display: flex; align-items: center; gap: 6px; margin-bottom: 14px; min-width: 0; }
.node-icon { color: #409EFF; flex-shrink: 0; }
.node-alias { font-weight: 700; font-size: 14px; color: #303133; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }
.node-addr { font-size: 12px; color: #909399; font-family: 'Courier New', monospace; flex-shrink: 0; }
.metric-rows { display: flex; flex-direction: column; gap: 10px; }
.metric-line { display: flex; align-items: center; gap: 12px; font-size: 13px; }
.ml-label { width: 88px; color: #606266; font-weight: 500; flex-shrink: 0; }
.ml-val { color: #303133; font-family: 'Courier New', monospace; }

.script-list { display: flex; flex-direction: column; gap: 14px; margin-top: 8px; }
.script-block { border: 1px solid #ebeef5; border-radius: 8px; padding: 12px 14px; background: #fcfcfc; }
.script-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.script-name { font-weight: 600; font-size: 14px; color: #303133; }
.script-type { font-size: 12px; color: #909399; }
.script-out { margin: 0; padding: 10px 12px; background: #0c1021; color: #d6e2ff; border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 320px; overflow: auto; }
.script-err { margin: 8px 0 0; padding: 10px 12px; background: #2b0d0d; color: #ffb4b4; border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow: auto; }

.report-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
</style>
