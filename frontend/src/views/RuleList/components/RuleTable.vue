<template>
  <el-table :data="tableData" stripe>
    <el-table-column prop="name" label="规则名称" min-width="160">
      <template #default="{ row }">
        <span class="rule-name">{{ row.name }}</span>
      </template>
    </el-table-column>
    <el-table-column prop="es_index" label="ES索引" min-width="160" show-overflow-tooltip />
    <el-table-column prop="schedule_type" label="执行方式" width="100" align="center">
      <template #default="{ row }">
        <el-tag size="small">{{ scheduleLabel(row.schedule_type) }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="schedule_value" label="调度值" width="130" show-overflow-tooltip />
    <el-table-column label="告警趋势" width="150" align="center">
      <template #default="{ row }">
        <el-tooltip placement="top" :show-after="100">
          <template #content>
            <div class="trend-tooltip">
              <div v-for="item in row.alert_trend" :key="item.date" class="trend-item">
                <span>{{ item.date }}</span>
                <span class="count">{{ item.count }} 条</span>
              </div>
            </div>
          </template>
          <svg class="trend-chart" viewBox="0 0 100 40" preserveAspectRatio="none">
            <path
              v-if="row.alert_trend?.length"
              :d="getTrendPath(row.alert_trend)"
              fill="none"
              stroke="var(--el-color-primary)"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
            <path
              v-if="row.alert_trend?.length"
              :d="getTrendArea(row.alert_trend)"
              fill="var(--el-color-primary)"
              fill-opacity="0.1"
            />
          </svg>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column prop="last_run" label="上次执行" width="180" show-overflow-tooltip />
    <el-table-column prop="is_enabled" label="状态" width="80" align="center">
      <template #default="{ row }">
        <el-switch v-model="row.is_enabled" size="small" @change="emit('toggle', row)" />
      </template>
    </el-table-column>
    <el-table-column label="操作" width="310" fixed="right">
      <template #default="{ row }">
        <el-button type="primary" link size="small" @click="emit('edit', row)">编辑</el-button>
        <el-button type="info" link size="small" @click="emit('preview', row)">预览</el-button>
        <el-button type="success" link size="small" @click="emit('execute', row)">执行</el-button>
        <el-button type="primary" link size="small" @click="emit('log', row)">日志</el-button>
        <el-button type="danger" link size="small" @click="emit('delete', row)">删除</el-button>
      </template>
    </el-table-column>
  </el-table>

  <div class="pagination-wrap">
    <el-pagination
      v-model:current-page="pagination.page"
      v-model:page-size="pagination.page_size"
      :total="total"
      :page-sizes="[10, 20, 50]"
      layout="total, sizes, prev, pager, next"
      @size-change="emit('load')"
      @current-change="emit('load')"
    />
  </div>
</template>

<script setup>
defineProps({
  tableData: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  pagination: { type: Object, required: true }
})

const emit = defineEmits(['edit', 'preview', 'execute', 'log', 'delete', 'toggle', 'load'])

const scheduleLabel = (s) => ({ once: '手动', interval: '周期', cron: 'Cron' }[s] || s)

// 计算趋势图路径
const getTrendPath = (trend) => {
  if (!trend?.length) return ''
  const max = Math.max(...trend.map(t => t.count), 1)
  const points = trend.map((t, i) => {
    const x = (i / (trend.length - 1)) * 100
    const y = 40 - (t.count / max) * 35
    return `${x},${y}`
  })
  return `M${points.join(' L')}`
}

// 计算趋势图填充区域
const getTrendArea = (trend) => {
  if (!trend?.length) return ''
  const max = Math.max(...trend.map(t => t.count), 1)
  const points = trend.map((t, i) => {
    const x = (i / (trend.length - 1)) * 100
    const y = 40 - (t.count / max) * 35
    return `${x},${y}`
  })
  return `M0,40 L${points.join(' L')} L100,40 Z`
}
</script>

<style lang="scss" scoped>
.rule-name { font-weight: 600; color: var(--el-color-primary); }
.pagination-wrap { display:flex; justify-content:flex-end; margin-top:16px; }

.trend-chart {
  width: 100px;
  height: 30px;
  cursor: pointer;
}

.trend-tooltip {
  min-width: 120px;
}

.trend-item {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 2px 0;
  font-size: 12px;
}

.trend-item .count {
  font-weight: 600;
  color: var(--el-color-primary);
}
</style>
