<template>
  <div class="dashboard" v-loading="loading">
    <div class="page-header">
      <h2>安全巡检概览</h2>
      <div class="header-actions">
        <el-button :icon="Refresh" text @click="loadData" size="small">刷新</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stat-cards">
      <el-col :span="6">
        <div class="stat-card stat-primary" :class="{ 'stat-error': errors.addressCount }">
          <div class="stat-icon"><el-icon><Location /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ errors.addressCount ? '—' : stats.addressCount }}</div>
            <div class="stat-label">攻击地址总数</div>
            <div v-if="errors.addressCount" class="stat-error-msg" :title="errors.addressCount">加载失败</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card stat-success" :class="{ 'stat-error': errors.ruleCount }">
          <div class="stat-icon"><el-icon><Connection /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ errors.ruleCount ? '—' : stats.ruleCount }}</div>
            <div class="stat-label">检测规则数</div>
            <div v-if="errors.ruleCount" class="stat-error-msg" :title="errors.ruleCount">加载失败</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card stat-danger" :class="{ 'stat-error': errors.alertStats }">
          <div class="stat-icon"><el-icon><Bell /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ errors.alertStats ? '—' : (stats.alertStats?.total || 0) }}</div>
            <div class="stat-label">告警总数</div>
            <div v-if="errors.alertStats" class="stat-error-msg" :title="errors.alertStats">加载失败</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card stat-warning" :class="{ 'stat-error': errors.alertStats }">
          <div class="stat-icon"><el-icon><Warning /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ errors.alertStats ? '—' : (stats.alertStats?.critical || 0) }}</div>
            <div class="stat-label">严重告警</div>
            <div v-if="errors.alertStats" class="stat-error-msg" :title="errors.alertStats">加载失败</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 趋势 + 实时统计 -->
    <el-row :gutter="20" class="overview-row">
      <el-col :span="16">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-title">告警趋势（近7天）</div>
          </template>
          <el-empty v-if="!loading && !trend.length" description="暂无趋势数据" :image-size="80" />
          <div v-show="trend.length" ref="trendChartRef" class="chart-container"></div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover" class="summary-card">
          <template #header>
            <div class="card-title">实时统计</div>
          </template>
          <div class="summary-list">
            <div class="summary-item">
              <span class="label">今日新增告警</span>
              <span class="value danger">{{ stats.alertStats?.today || 0 }}</span>
            </div>
            <el-divider style="margin: 12px 0" />
            <div class="summary-item">
              <span class="label">高危告警</span>
              <span class="value warning">{{ stats.alertStats?.high || 0 }}</span>
            </div>
            <el-divider style="margin: 12px 0" />
            <div class="summary-item">
              <span class="label">待处理告警</span>
              <span class="value primary">{{ stats.alertStats?.pending || 0 }}</span>
            </div>
            <el-divider style="margin: 12px 0" />
            <div class="summary-item">
              <span class="label">累计登录次数</span>
              <span class="value">{{ userStore.userInfo.login_count || '-' }}</span>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近告警 -->
    <el-card shadow="hover" class="recent-alerts">
      <template #header>
        <div class="card-title">最近告警</div>
      </template>
      <el-empty v-if="!loading && !recentAlerts.length" description="暂无告警" :image-size="80" />
      <el-table v-else :data="recentAlerts" stripe size="small">
        <el-table-column prop="title" label="告警标题" min-width="160" />
        <el-table-column prop="content" label="告警内容" min-width="220" show-overflow-tooltip />
        <el-table-column prop="severity" label="级别" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="severityType(row.severity)" size="small">{{ row.severity }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="时间" width="180" show-overflow-tooltip />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { getDashboardStats, alerts } from '@/api'
import { useUserStore } from '@/store/user'
import * as echarts from 'echarts'

const userStore = useUserStore()
const loading = ref(false)
const stats = ref({ addressCount: 0, ruleCount: 0, alertStats: {} })
const errors = ref({})
const recentAlerts = ref([])
const trend = ref([])
const trendChartRef = ref()
let trendChart = null
let resizeHandler = null

const severityType = (s) => ({ critical: 'danger', high: 'warning', medium: 'info', low: 'success' }[s] || '')
const statusType = (s) => ({ pending: 'warning', confirmed: 'primary', resolved: 'success', false_positive: 'info' }[s] || '')

// ECharts canvas 需要字面量色值，不能用 CSS 变量。运行时解析 Element Plus primary。
const resolvePrimaryColor = () => {
  const raw = window.getComputedStyle(document.documentElement).getPropertyValue('--el-color-primary').trim()
  return raw || '#409EFF'
}
// #rrggbb / #rgb → rgba()，用于 areaStyle 渐变
const hexToRgba = (hex, alpha) => {
  let h = String(hex || '').replace('#', '')
  if (h.length === 3) h = h.split('').map(c => c + c).join('')
  if (h.length !== 6) return `rgba(64,158,255,${alpha})`
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

const loadData = async () => {
  loading.value = true
  errors.value = {}
  try {
    const data = await getDashboardStats()
    stats.value = data
    errors.value = data.errors || {}
    trend.value = data.trend || []
    await nextTick()
    renderTrendChart(trend.value)
  } catch (e) {
    errors.value = { addressCount: e?.message || '加载失败', ruleCount: e?.message || '加载失败', alertStats: e?.message || '加载失败' }
    trend.value = []
    disposeTrendChart()
  }
  try {
    // 已按 created_at desc 排序，不再限制为今日（安静日会空白）
    const res = await alerts.list({ page_size: 10, sort_field: 'created_at', sort_order: 'desc' })
    recentAlerts.value = res.data.list || []
  } catch (e) {
    /* 最近告警卡片失败不影响统计卡片 */
  } finally {
    loading.value = false
  }
}

const disposeTrendChart = () => {
  if (trendChart) {
    trendChart.dispose()
    trendChart = null
  }
}

const renderTrendChart = (trendData) => {
  if (!trendChartRef.value) return
  if (!trendData || !trendData.length) {
    disposeTrendChart()
    return
  }
  // 与 InspectionMetrics 一致：dispose 后再 init，避免 loadData 反复 init 泄漏实例
  disposeTrendChart()
  trendChart = echarts.init(trendChartRef.value)
  const primary = resolvePrimaryColor()
  const option = {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: trendData.map(t => String(t.date || '').slice(5)),
      axisLine: { lineStyle: { color: '#ddd' } }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f0f0f0' } }
    },
    series: [{
      data: trendData.map(t => t.count),
      type: 'line',
      smooth: true,
      areaStyle: {
        color: {
          type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: hexToRgba(primary, 0.4) },
            { offset: 1, color: hexToRgba(primary, 0.05) }
          ]
        }
      },
      lineStyle: { color: primary, width: 2 },
      itemStyle: { color: primary }
    }]
  }
  trendChart.setOption(option)
}

const onResize = () => { trendChart && trendChart.resize() }

onMounted(() => {
  resizeHandler = onResize
  window.addEventListener('resize', resizeHandler)
  loadData()
})

onUnmounted(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  disposeTrendChart()
})
</script>

<style lang="scss" scoped>
.dashboard { }

.header-actions { display: flex; align-items: center; gap: 8px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  h2 { margin: 0; font-size: 18px; color: var(--el-text-color-primary); }
}

.stat-cards { margin-bottom: 20px; }

.stat-card {
  background: var(--el-bg-color);
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
  border-left: 4px solid;
  &.stat-primary { border-color: var(--el-color-primary); .stat-icon { background: var(--el-color-primary-light-9); color: var(--el-color-primary); } }
  &.stat-success { border-color: var(--el-color-success); .stat-icon { background: var(--el-color-success-light-9); color: var(--el-color-success); } }
  &.stat-danger { border-color: var(--el-color-danger); .stat-icon { background: var(--el-color-danger-light-9); color: var(--el-color-danger); } }
  &.stat-warning { border-color: var(--el-color-warning); .stat-icon { background: var(--el-color-warning-light-9); color: var(--el-color-warning); } }
  &.stat-error { opacity: 0.75; }
}

.stat-icon {
  width: 52px; height: 52px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  :deep(.el-icon) { font-size: 26px; }
}

.stat-value { font-size: 28px; font-weight: 700; color: var(--el-text-color-primary); line-height: 1; }
.stat-label { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; }
.stat-error-msg { font-size: 12px; color: var(--el-color-danger); margin-top: 4px; }

.overview-row { margin-bottom: 20px; }

.chart-card { }
.chart-container { height: 260px; }

.card-title {
  font-size: 15px; font-weight: 600; color: var(--el-text-color-primary);
}

.summary-list { padding: 4px 0; }
.summary-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0;
  .label { font-size: 14px; color: var(--el-text-color-regular); }
  .value { font-size: 22px; font-weight: 700; &.danger { color: var(--el-color-danger); } &.warning { color: var(--el-color-warning); } &.primary { color: var(--el-color-primary); } }
}
</style>
