<template>
  <div class="dashboard">
    <div class="page-header">
      <h2>安全巡检概览</h2>
      <div class="header-actions">
        <el-button :icon="Refresh" text @click="loadData" size="small">刷新</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="20" class="stat-cards">
      <el-col :span="6">
        <div class="stat-card stat-primary">
          <div class="stat-icon"><el-icon><Location /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.addressCount }}</div>
            <div class="stat-label">攻击地址总数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card stat-success">
          <div class="stat-icon"><el-icon><Connection /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.ruleCount }}</div>
            <div class="stat-label">检测规则数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card stat-danger">
          <div class="stat-icon"><el-icon><Bell /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.alertStats?.total || 0 }}</div>
            <div class="stat-label">告警总数</div>
          </div>
        </div>
      </el-col>
      <el-col :span="6">
        <div class="stat-card stat-warning">
          <div class="stat-icon"><el-icon><Warning /></el-icon></div>
          <div class="stat-info">
            <div class="stat-value">{{ stats.alertStats?.critical || 0 }}</div>
            <div class="stat-label">严重告警</div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 今日概览 + 趋势 -->
    <el-row :gutter="20" class="overview-row">
      <el-col :span="16">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-title">告警趋势（近7天）</div>
          </template>
          <div ref="trendChartRef" class="chart-container"></div>
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

    <!-- 最新告警 -->
    <el-card shadow="hover" class="recent-alerts">
      <template #header>
        <div class="card-title">最新告警</div>
      </template>
      <el-table :data="recentAlerts" stripe size="small">
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
        <el-table-column prop="created_at" label="时间" width="160" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { getDashboardStats, alerts } from '@/api'
import { useUserStore } from '@/store/user'
import * as echarts from 'echarts'

const userStore = useUserStore()
const stats = ref({ addressCount: 0, ruleCount: 0, alertStats: {} })
const recentAlerts = ref([])
const trendChartRef = ref()
// 仪表盘时间范围固定为今日 (Asia/Shanghai)
const getDateRange = () => {
  const now = new Date()
  const cst = new Date(now.getTime() + 8 * 3600 * 1000)
  const today = cst.toISOString().slice(0, 10)  // 'YYYY-MM-DD'
  const nowCST = cst.toISOString().slice(0, 19).replace('T', ' ')
  return { date_from: today + ' 00:00:00', date_to: nowCST }
}

const severityType = (s) => ({ critical: 'danger', high: 'warning', medium: 'info', low: 'success' }[s] || '')
const statusType = (s) => ({ pending: 'warning', confirmed: 'primary', resolved: 'success', false_positive: 'info' }[s] || '')

const loadData = async () => {
  try {
    const data = await getDashboardStats()
    stats.value = data
    // 渲染图表
    await nextTick()
    renderTrendChart(data.alertStats?.trend || [])
  } catch (e) {
    // ignore
  }
  try {
    const range = getDateRange()
    const res = await alerts.list({ page_size: 10, sort_field: 'created_at', sort_order: 'desc', ...range })
    recentAlerts.value = res.data.list
  } catch (e) {}
}

const renderTrendChart = (trend) => {
  if (!trendChartRef.value) return
  const chart = echarts.init(trendChartRef.value)
  const option = {
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: trend.map(t => t.date.slice(5)),
      axisLine: { lineStyle: { color: '#ddd' } }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      splitLine: { lineStyle: { color: '#f0f0f0' } }
    },
    series: [{
      data: trend.map(t => t.count),
      type: 'line',
      smooth: true,
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [{ offset: 0, color: 'rgba(64,158,255,0.4)' }, { offset: 1, color: 'rgba(64,158,255,0.05)' }] } },
      lineStyle: { color: '#409EFF', width: 2 },
      itemStyle: { color: '#409EFF' }
    }]
  }
  chart.setOption(option)
}

onMounted(loadData)
</script>

<style lang="scss" scoped>
.dashboard { }

.header-actions { display: flex; align-items: center; gap: 8px; }

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  h2 { margin: 0; font-size: 18px; color: #333; }
}

.stat-cards { margin-bottom: 20px; }

.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.06);
  border-left: 4px solid;
  &.stat-primary { border-color: #409EFF; .stat-icon { background: rgba(64,158,255,0.1); color: #409EFF; } }
  &.stat-success { border-color: #67c23a; .stat-icon { background: rgba(103,194,58,0.1); color: #67c23a; } }
  &.stat-danger { border-color: #f56c6c; .stat-icon { background: rgba(245,108,108,0.1); color: #f56c6c; } }
  &.stat-warning { border-color: #e6a23c; .stat-icon { background: rgba(230,162,60,0.1); color: #e6a23c; } }
}

.stat-icon {
  width: 52px; height: 52px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  :deep(.el-icon) { font-size: 26px; }
}

.stat-value { font-size: 28px; font-weight: 700; color: #1a1a2e; line-height: 1; }
.stat-label { font-size: 13px; color: #888; margin-top: 4px; }

.overview-row { margin-bottom: 20px; }

.chart-card { }
.chart-container { height: 260px; }

.card-title {
  font-size: 15px; font-weight: 600; color: #333;
}

.summary-list { padding: 4px 0; }
.summary-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0;
  .label { font-size: 14px; color: #666; }
  .value { font-size: 22px; font-weight: 700; &.danger { color: #f56c6c; } &.warning { color: #e6a23c; } &.primary { color: #409EFF; } }
}
</style>
