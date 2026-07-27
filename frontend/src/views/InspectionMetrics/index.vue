<template>
  <div class="page-container">

    <!-- ══ 系统监控 ══ -->
    <el-card shadow="never" class="mb-16">
      <template #header>
        <div class="card-header">
          <span class="card-title">系统监控</span>
          <span class="card-sub" v-if="metrics && metrics.time_range">{{ metrics.time_range }}</span>
          <div class="time-range-btns">
            <el-select v-model="timePreset" size="small" style="width:145px" @change="loadMetrics">
              <el-option label="最近 1 小时" value="1h" />
              <el-option label="最近 6 小时" value="6h" />
              <el-option label="今日" value="today" />
              <el-option label="最近 1 天" value="1d" />
              <el-option label="最近 7 天" value="7d" />
            </el-select>
          </div>
          <el-button type="primary" :loading="loading" @click="loadMetrics" size="small">刷新</el-button>
        </div>
      </template>

      <el-alert v-if="!grafanaConnected" type="warning" :closable="false" show-icon style="margin-bottom:16px">
        无法连接到 Grafana，请检查系统设置中的连接配置
      </el-alert>
      <el-alert v-if="grafanaConnected && !serverList.length && !loading" type="info" :closable="false" show-icon style="margin-bottom:16px">
        暂未获取到服务器指标数据，请确认 Prometheus 已采集 node_exporter 数据
      </el-alert>

      <!-- Grafana 面板嵌入区 -->
      <div v-if="grafanaUrl" class="grafana-panel">
        <div class="panel-header">
          <span class="panel-title">Grafana 面板</span>
          <el-button size="small" @click="showPanelInput = !showPanelInput">{{ showPanelInput ? '收起' : '嵌入面板' }}</el-button>
        </div>
        <div v-if="showPanelInput" class="panel-input-row">
          <el-input v-model="panelEmbedUrl" placeholder="粘贴 Grafana 面板分享链接（/d/xxx/...）后回车" @keyup.enter="applyPanelUrl" size="small" style="max-width:500px" />
          <el-button size="small" type="primary" @click="applyPanelUrl">加载</el-button>
        </div>
        <iframe v-if="panelEmbedUrl" :src="panelEmbedUrl + '?kiosk=tv&hide-header=true&hide-controls=true'" class="grafana-iframe" frameborder="0" />
        <el-alert v-else type="info" :closable="false" show-icon>在系统设置中配置 Grafana URL 后可在此嵌入面板</el-alert>
      </div>

      <!-- 服务器节点卡片 -->
      <div v-if="serverList.length" class="server-list">
        <div v-for="s in serverList" :key="s.instance" class="server-card">

          <!-- 卡片标题栏 -->
          <div class="card-head">
            <div class="node-info">
              <el-icon class="node-icon"><Monitor /></el-icon>
              <span class="node-alias" v-if="s.alias && !aliasEditing[s.instance]">{{ s.alias }}</span>
              <span class="node-addr" :class="{'has-alias': s.alias}">{{ s.instance }}</span>
            </div>
            <el-button
              v-if="isAdmin"
              type="primary"
              link
              size="small"
              @click="startEditAlias(s.instance, s.alias || '')"
            >
              {{ s.alias ? '改别名' : '+ 别名' }}
            </el-button>
          </div>

          <!-- 别名编辑区 -->
          <div v-if="aliasEditing[s.instance]" class="alias-edit">
            <el-input
              v-model="aliasEditing[s.instance]"
              size="small"
              :placeholder="'给 ' + s.instance + ' 设别名'"
              @keyup.enter="saveAlias(s.instance)"
              style="max-width: 260px"
            />
            <el-button type="primary" size="small" @click="saveAlias(s.instance)">保存</el-button>
            <el-button size="small" @click="delete aliasEditing[s.instance]">取消</el-button>
          </div>

          <!-- 指标行 -->
          <div class="metric-rows">
            <!-- CPU -->
            <div class="metric-row">
              <div class="mr-header">
                <span class="mr-label">CPU</span>
                <span class="mr-stat">
                  <el-tag type="info" size="small" effect="plain">均值 {{ s.cpu?.avg ?? '-' }}%</el-tag>
                  <el-tag :type="peakType(s.cpu?.peak)" size="small" effect="plain">峰值 {{ s.cpu?.peak ?? '-' }}%</el-tag>
                </span>
              </div>
              <div :ref="el => registerChartRef(el, s.instance + '_cpu', s.cpu_series)" :data-key="s.instance + '_cpu'" class="chart-container"></div>
            </div>

            <!-- 内存 -->
            <div class="metric-row">
              <div class="mr-header">
                <span class="mr-label">内存</span>
                <span class="mr-stat">
                  <el-tag type="info" size="small" effect="plain">均值 {{ s.memory?.avg ?? '-' }}%</el-tag>
                  <el-tag :type="peakType(s.memory?.peak)" size="small" effect="plain">峰值 {{ s.memory?.peak ?? '-' }}%</el-tag>
                </span>
              </div>
              <div :ref="el => registerChartRef(el, s.instance + '_mem', s.memory_series)" :data-key="s.instance + '_mem'" class="chart-container"></div>
            </div>

            <!-- 磁盘（按挂载点） -->
            <template v-for="dk in (s.disks || [])" :key="dk.mountpoint">
              <div class="metric-row disk-row">
                <div class="mr-header">
                  <span class="mr-label">{{ dk.mountpoint === '/' ? '磁盘（/）' : '磁盘（/data/logs）' }}</span>
                  <span class="mr-stat">
                    <el-tag type="info" size="small" effect="plain">均值 {{ dk.avg ?? '-' }}%</el-tag>
                    <el-tag :type="peakType(dk.peak)" size="small" effect="plain">峰值 {{ dk.peak ?? '-' }}%</el-tag>
                  </span>
                </div>
                <div :ref="el => registerChartRef(el, s.instance + '_disk', s.disk_series)" :data-key="s.instance + '_disk'" class="chart-container"></div>
              </div>
            </template>
          </div>
        </div>
      </div>

      <!-- 骨架屏 -->
      <div v-if="loading" class="server-list">
        <div v-for="i in 2" :key="i" class="server-card skeleton-card">
          <el-skeleton :rows="5" animated />
        </div>
      </div>
    </el-card>

    <!-- ══ 自定义监控（已隐藏，无数据） ══ -->
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive, nextTick } from 'vue'
import { inspectApi } from '@/api'
import { useUserStore } from '@/store/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Monitor } from '@element-plus/icons-vue'
import * as echarts from 'echarts'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

// Ensure role is loaded (handles stale localStorage from old login sessions)
if (!userStore.isAdmin && userStore.isLoggedIn) {
  import('@/api/request').then(({ default: request }) => {
    request.get('/auth/me').then(res => {
      if (res.data?.role) {
        userStore.userInfo = res.data
        localStorage.setItem('userInfo', JSON.stringify(res.data))
      }
    }).catch(() => {})
  })
}

const loading = ref(false)
const metrics = ref(null)
const customMetrics = ref([])
const aliasEditing = reactive({})   // { instance: aliasStr }
const timePreset = ref('1h')

// ECharts chart instances
const chartInstances = {}
const trendDialogVisible = ref(false)
const trendMetric = ref(null)
const trendChartRef = ref(null)

// Grafana panel embedding
const grafanaUrl = computed(() => metrics.value?.grafana_url || '')
const showPanelInput = ref(false)
const panelEmbedUrl = ref('')
const applyPanelUrl = () => { if (panelEmbedUrl.value) showPanelInput.value = true }

// registerChart: initialize an ECharts instance on a container element
const registerChartRef = (el, key, series) => {
  if (!el || !series?.length) return
  if (chartInstances[key]) {
    chartInstances[key].dispose()
    delete chartInstances[key]
  }
  const chart = echarts.init(el)
  chart.setOption({
    grid: { top: 4, bottom: 4, left: 4, right: 4, containLabel: false },
    xAxis: { type: 'time', show: false },
    yAxis: { type: 'value', max: 100, show: false },
    series: [{
      data: series.map(p => [p.timestamp * 1000, p.value]),
      type: 'line', smooth: true, symbol: 'none',
      lineStyle: { width: 2 },
      areaStyle: { opacity: 0.2 }
    }],
    tooltip: { trigger: 'axis', formatter: p => `${p[0].value[1].toFixed(1)}%` }
  })
  chartInstances[key] = chart
}

// ── 自定义监控（已移除，保留空变量避免引用报错）

const grafanaConnected = computed(() => metrics.value?.connected !== false)
const serverList = computed(() => metrics.value?.servers || [])

const peakType = (v) => {
  if (v === null || v === undefined) return 'info'
  if (v >= 90) return 'danger'
  if (v >= 70) return 'warning'
  return 'success'
}
const cpuColor  = (v) => (v >= 90 ? '#f56c6c' : v >= 70 ? '#e6a23c' : '#67c23a')
const memColor  = (v) => (v >= 90 ? '#f56c6c' : v >= 80 ? '#e6a23c' : '#67c23a')
const diskColor = (v) => (v >= 95 ? '#f56c6c' : v >= 85 ? '#e6a23c' : '#67c23a')

// 打开趋势图弹窗
const openTrendDialog = (row) => {
  trendMetric.value = row
  trendDialogVisible.value = true
  nextTick(() => {
    if (trendChartRef.value && row.series_data?.length) {
      const chart = echarts.init(trendChartRef.value)
      chart.setOption({
        title: { text: row.name, textStyle: { fontSize: 14 } },
        tooltip: { trigger: 'axis' },
        grid: { top: 40, bottom: 30, left: 50, right: 20 },
        xAxis: { type: 'time' },
        yAxis: { type: 'value', name: row.unit || '' },
        series: [{
          data: row.series_data.map(p => [p.timestamp * 1000, p.value]),
          type: 'line', smooth: true, symbol: 'none'
        }]
      })
    }
  })
}

const loadMetrics = async () => {
  loading.value = true
  try {
    const res = await inspectApi.grafanaMetrics({ time_range: timePreset.value })
    metrics.value = res.data || null
    customMetrics.value = []
  } catch (e) {
    metrics.value = { connected: false }
    ElMessage.error('获取指标失败')
  } finally {
    loading.value = false
  }
  // 注册 ECharts 图表（在 DOM 更新后执行）
  nextTick(() => {
    for (const s of serverList.value) {
      if (s.cpu_series?.length) {
        const el = document.querySelector(`[data-key="${s.instance}_cpu"]`)
        registerChartRef(el, s.instance + '_cpu', s.cpu_series)
      }
      if (s.memory_series?.length) {
        const el = document.querySelector(`[data-key="${s.instance}_mem"]`)
        registerChartRef(el, s.instance + '_mem', s.memory_series)
      }
      if (s.disk_series?.length) {
        const el = document.querySelector(`[data-key="${s.instance}_disk"]`)
        registerChartRef(el, s.instance + '_disk', s.disk_series)
      }
    }
  })
}

// ── 别名编辑 ──
const startEditAlias = (instance, currentAlias) => {
  aliasEditing[instance] = currentAlias
}

const saveAlias = async (instance) => {
  const alias = (aliasEditing[instance] || '').trim()
  // 合并到当前 aliases
  const current = {}
  for (const s of serverList.value) {
    if (s.alias) current[s.instance] = s.alias
  }
  if (alias) {
    current[instance] = alias
  } else {
    delete current[instance]
  }
  try {
    await inspectApi.setServerAliases(current)
    ElMessage.success('别名已保存')
    delete aliasEditing[instance]
    // 刷新数据
    await loadMetrics()
  } catch (e) {
    console.error(e)
  }
}

// ── 自定义指标 ──
const openMetricDialog = (row) => {
  metricEditId.value = row ? row.id : null
  metricForm.value = row
    ? { name: row.name, description: row.description, promql: row.promql, unit: row.unit || '' }
    : { name: '', description: '', promql: '', unit: '' }
  metricDialogVisible.value = true
}

const submitMetric = async () => {
  try { await metricFormRef.value.validate() } catch (_) { return }
  metricSaving.value = true
  try {
    if (metricEditId.value) {
      await inspectApi.updateCustomMetric(metricEditId.value, { ...metricForm.value })
      ElMessage.success('监控更新成功')
    } else {
      await inspectApi.createCustomMetric({ ...metricForm.value })
      ElMessage.success('监控创建成功')
    }
    metricDialogVisible.value = false
    loadMetrics()
  } catch (e) {
    console.error(e)
  } finally {
    metricSaving.value = false
  }
}

const deleteMetric = (row) => {
  ElMessageBox.confirm(`确定删除监控「${row.name}」？`, '确认', { type: 'warning' })
    .then(async () => {
      try {
        await inspectApi.deleteCustomMetric(row.id)
        ElMessage.success('删除成功')
        loadMetrics()
      } catch (e) { console.error(e) }
    }).catch(() => {})
}

onMounted(loadMetrics)
</script>

<style scoped>
.mb-16 { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; gap: 10px; }
.card-title { font-weight: 600; font-size: 15px; }
.card-sub { font-size: 12px; color: #909399; font-weight: normal; }

/* 服务器卡片 */
.server-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(440px, 1fr));
  gap: 16px;
}
.server-card {
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  padding: 18px 20px 14px;
  background: #fafafa;
  transition: box-shadow 0.2s;
}
.server-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); }

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.node-info {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.node-icon { color: #409EFF; flex-shrink: 0; }
.node-alias {
  font-weight: 700;
  font-size: 14px;
  color: #303133;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 200px;
}
.node-addr {
  font-size: 12px;
  color: #909399;
  font-family: 'Courier New', monospace;
  flex-shrink: 0;
}
.node-addr.has-alias {
  font-size: 11px;
  color: #c0c4cc;
}

.alias-edit {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #ecf5ff;
  border-radius: 6px;
}

.metric-rows { display: flex; flex-direction: column; gap: 14px; }
.metric-row { }
.disk-row { }
.mr-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.mr-label { font-size: 13px; color: #606266; font-weight: 500; }
.mr-stat { display: flex; gap: 6px; align-items: center; }

/* ECharts 图表容器 */
.chart-container { height: 60px; width: 100%; margin-bottom: 4px; }

/* Grafana 面板嵌入 */
.grafana-panel { margin-bottom: 16px; border: 1px solid #e4e7ed; border-radius: 8px; padding: 12px 16px; background: #f5f7fa; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.panel-title { font-weight: 600; font-size: 14px; }
.panel-input-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.grafana-iframe { width: 100%; height: 340px; border-radius: 6px; border: 1px solid #dcdfe6; }

/* 自定义监控 */
.promql-code {
  font-family: 'Courier New', monospace;
  font-size: 12px;
  color: #c7254e;
  background: #fdf2f5;
  padding: 2px 6px;
  border-radius: 4px;
  word-break: break-all;
}
.metric-val { display: flex; flex-direction: column; gap: 1px; margin-right: 8px; }
.val-host { font-size: 10px; color: #909399; }
.val-num { font-size: 13px; font-weight: 600; color: #303133; font-family: 'Courier New', monospace; }
.val-more { font-size: 11px; color: #909399; vertical-align: middle; }
.empty-text { color: #909399; }

.skeleton-card { min-height: 200px; }
</style>
