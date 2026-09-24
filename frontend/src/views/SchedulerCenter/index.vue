<template>
  <div class="scheduler-center">
    <!-- 健康条 -->
    <el-card class="health-card" shadow="never">
      <div class="health-row">
        <div class="health-main">
          <span class="status-dot" :class="health.running ? 'online' : 'offline'"></span>
          <span class="health-title">
            {{ health.running ? '调度器运行中' : '调度器已停止' }}
          </span>
          <el-tag v-if="health.healthy" type="success" size="small" effect="plain">健康</el-tag>
          <el-tag v-else type="danger" size="small" effect="plain">有 {{ health.problems?.length || 0 }} 个问题</el-tag>
        </div>
        <el-button size="small" :loading="loading" @click="refresh">刷新</el-button>
      </div>

      <div class="health-meta">
        <span>心跳：{{ health.heartbeat_at || '—' }}
          <template v-if="health.heartbeat_age_seconds != null">（{{ relTime(health.heartbeat_age_seconds) }}）</template>
        </span>
        <span>最近跑完：<template v-if="health.last_activity_age_seconds != null">{{ relTime(health.last_activity_age_seconds) }}</template><template v-else>—</template></span>
        <span>任务数：{{ health.job_count ?? '—' }}</span>
        <span>连续失败最多：{{ health.consecutive_failures_max ?? 0 }}</span>
        <span>超时未调度：{{ health.stale_rules ?? 0 }}</span>
      </div>

      <div class="health-counts">
        <div class="count-item">
          <div class="count-num ok">{{ health.counts_24h?.success ?? 0 }}</div>
          <div class="count-label">24h 成功</div>
        </div>
        <div class="count-item">
          <div class="count-num err">{{ health.counts_24h?.error ?? 0 }}</div>
          <div class="count-label">24h 失败</div>
        </div>
        <div class="count-item">
          <div class="count-num warn">{{ health.counts_24h?.missed ?? 0 }}</div>
          <div class="count-label">24h 漏跑</div>
        </div>
      </div>

      <div v-if="health.problems?.length" class="problem-list">
        <div v-for="(p, i) in health.problems" :key="i" class="problem-item">⚠ {{ p }}</div>
      </div>
    </el-card>

    <!-- 任务表 -->
    <el-card class="block-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>调度任务</span>
          <span class="card-hint">含内置的每日数据保留清理</span>
        </div>
      </template>
      <el-table :data="jobs" stripe size="small" v-loading="loading">
        <el-table-column prop="name" label="任务" min-width="180" show-overflow-tooltip />
        <el-table-column prop="schedule" label="调度" width="150" show-overflow-tooltip />
        <el-table-column label="下次执行" width="180">
          <template #default="{ row }">
            <span v-if="row.stale" class="stale">{{ row.next_run || '—' }}</span>
            <span v-else>{{ row.next_run || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上次执行" width="220">
          <template #default="{ row }">
            <div class="run-cell">
              <span>{{ row.last_run || '—' }}</span>
              <el-tag
                v-if="row.last_status"
                :type="statusType(row.last_status)"
                size="small"
                effect="plain"
              >{{ statusLabel(row.last_status) }}</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms" label="耗时" width="90" align="right">
          <template #default="{ row }">
            <span v-if="row.duration_ms">{{ (row.duration_ms / 1000).toFixed(2) }}s</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="consecutive_failures" label="连败" width="70" align="center">
          <template #default="{ row }">
            <span :class="{ 'stale': (row.consecutive_failures || 0) >= 3 }">{{ row.consecutive_failures || 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.rule_id"
              type="primary"
              link
              size="small"
              :loading="runningId === row.rule_id"
              @click="runNow(row)"
            >立即执行</el-button>
            <span v-else class="muted">内置</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 近 24h 执行时间线 -->
    <el-card class="block-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>近 24h 执行时间线</span>
          <span class="card-hint">只列最近 80 条</span>
        </div>
      </template>
      <el-timeline v-if="timeline.length">
        <el-timeline-item
          v-for="item in timeline"
          :key="item.id"
          :timestamp="item.executed_at"
          :type="statusType(item.status)"
          placement="top"
        >
          <div class="timeline-row">
            <el-tag :type="statusType(item.status)" size="small" effect="plain">{{ statusLabel(item.status) }}</el-tag>
            <span class="timeline-name">{{ item.rule_name || `规则 #${item.rule_id}` }}</span>
            <span class="timeline-meta">
              告警 {{ item.alert_count || 0 }}
              <template v-if="item.duration_ms">｜{{ (item.duration_ms / 1000).toFixed(2) }}s</template>
              <template v-if="item.triggered_by">｜{{ item.triggered_by === 'manual' ? '手动' : '定时' }}</template>
            </span>
          </div>
          <div v-if="item.error_message" class="timeline-err">{{ item.error_message }}</div>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="近 24h 没有执行记录" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { scheduler, executionLogs, rules as rulesApi } from '@/api'

const loading = ref(false)
const runningId = ref(null)
const health = ref({
  running: false,
  healthy: false,
  problems: [],
  counts_24h: {},
  heartbeat_at: null,
  heartbeat_age_seconds: null,
  last_activity_at: null,
  last_activity_age_seconds: null,
  job_count: 0,
  stale_rules: 0,
  consecutive_failures_max: 0,
})
const jobs = ref([])
const timeline = ref([])
let timer = null

const statusType = (s) => (s === 'success' ? 'success' : s === 'missed' ? 'warning' : 'danger')
const statusLabel = (s) => ({ success: '成功', error: '失败', missed: '漏跑' }[s] || s)
const relTime = (secs) => {
  const s = Number(secs) || 0
  if (s < 60) return `${s} 秒前`
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  return `${Math.floor(s / 86400)} 天前`
}

const refresh = async () => {
  loading.value = true
  try {
    const [hRes, sRes, lRes] = await Promise.all([
      scheduler.health(),
      scheduler.status(),
      executionLogs.list({ page: 1, page_size: 80 }),
    ])
    health.value = hRes.data || health.value
    jobs.value = sRes.data?.jobs || []
    timeline.value = lRes.data?.list || lRes.data?.items || []
  } catch (e) {
    ElMessage.error(e.message || '加载调度状态失败')
  } finally {
    loading.value = false
  }
}

const runNow = async (row) => {
  runningId.value = row.rule_id
  try {
    const res = await rulesApi.execute(row.rule_id)
    ElMessage.success(res.msg || '执行完成')
    refresh()
  } catch (e) {
    ElMessage.error(e.message || '执行失败')
  } finally {
    runningId.value = null
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 30000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })
</script>

<style lang="scss" scoped>
.scheduler-center {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.health-card,
.block-card {
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}

.card-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  font-weight: 600;
}
.card-hint {
  font-weight: 400;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.health-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.health-main {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
}
.health-title { color: var(--el-text-color-primary); }

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  &.online { background: var(--el-color-success); box-shadow: 0 0 4px var(--el-color-success-light-5); }
  &.offline { background: var(--el-color-danger); box-shadow: 0 0 4px var(--el-color-danger-light-5); }
}

.health-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin: 12px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.health-counts {
  display: flex;
  gap: 32px;
  padding: 12px 0;
  border-top: 1px solid var(--el-border-color-lighter);
}
.count-item { text-align: center; }
.count-num {
  font-size: 22px;
  font-weight: 700;
  &.ok { color: var(--el-color-success); }
  &.err { color: var(--el-color-danger); }
  &.warn { color: var(--el-color-warning); }
}
.count-label {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.problem-list {
  margin-top: 8px;
  padding-top: 10px;
  border-top: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.problem-item {
  font-size: 13px;
  color: var(--el-color-danger);
}

.run-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.stale { color: var(--el-color-danger); }
.muted { color: var(--el-text-color-secondary); }

.timeline-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.timeline-name { font-weight: 600; }
.timeline-meta {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.timeline-err {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-color-danger);
  word-break: break-all;
}
</style>
