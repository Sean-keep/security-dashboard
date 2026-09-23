<template>
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

        <!-- 严重级别：单独卡片展示 -->
        <div v-if="criticalAddresses.length" class="critical-section">
          <div class="critical-title">⚠️ 严重攻击地址（{{ criticalAddresses.length }} 条）</div>
          <div v-for="a in criticalAddresses" :key="a.ip_address" class="critical-card">
            <div class="critical-header">
              <el-tag type="danger" effect="dark" size="small">严重</el-tag>
              <span class="critical-ip">{{ a.ip_address }}</span>
              <span v-if="a.country" class="critical-country">{{ a.country }}</span>
              <span class="critical-count">攻击 {{ a.attack_count }} 次</span>
            </div>
            <div class="critical-meta">
              <span v-if="a.domain">域名: {{ a.domain }}</span>
              <span>时间: {{ a.start_time }} ~ {{ a.end_time }}</span>
              <span>持续: {{ a.duration }}s</span>
            </div>
            <div v-if="a.handle_suggestion" class="critical-suggestion">
              <span class="suggestion-label">处置结果：</span>{{ a.handle_suggestion }}
            </div>
          </div>
        </div>

        <!-- 高危及以下：原有表格 -->
        <el-table :data="normalAddresses" border stripe size="small" max-height="460">
          <el-table-column type="index" label="#" width="48" />
          <el-table-column prop="ip_address" label="IP 地址" min-width="150" />
          <el-table-column label="严重级别" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="severityType(row.severity)" size="small" effect="plain">
                {{ severityLabel(row.severity) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="country" label="国家/地区" width="160" show-overflow-tooltip />
          <el-table-column prop="domain" label="关联域名" min-width="170" show-overflow-tooltip />
          <el-table-column prop="start_time" label="起始时间" width="180" show-overflow-tooltip />
          <el-table-column prop="end_time" label="结束时间" width="180" show-overflow-tooltip />
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
              <el-tag v-if="sc.exit_code !== 0" type="danger" size="small" effect="plain">
                失败（退出码 {{ sc.exit_code }}）
              </el-tag>
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
          <div v-for="(it, ii) in currentReport.ingested" :key="(it.endpoint_name || '') + '-' + (it.sender_name || '') + '-' + ii" class="script-block">
            <div class="script-head">
              <span class="script-name">{{ it.endpoint_name }}<template v-if="it.sender_name"> · {{ it.sender_name }}</template></span>
              <span class="script-type">{{ it.received_at }}</span>
            </div>
            <pre class="script-out" v-if="it.payload">{{ it.payload }}</pre>
          </div>
        </div>
      </el-card>
    </template>
  </template>
</template>

<script setup>
import { Monitor } from '@element-plus/icons-vue'
import { useInspectionReport } from '../composables/useInspectionReport'

const {
  currentReport,
  loading,
  sectionOrder,
  criticalAddresses,
  normalAddresses,
  severityLabel,
  severityType
} = useInspectionReport()
</script>

<style scoped>
.mb-16 { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; gap: 10px; }
.card-title { font-weight: 600; font-size: 13px; }

.overview { margin-top: 4px; }
.ov-title { font-size: 14px; font-weight: 700; color: var(--el-text-color-primary); margin-bottom: 8px; }
.ov-text { white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; line-height: 1.7; color: var(--el-text-color-primary); background: var(--el-fill-color-light); border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 12px 14px; margin: 0; }

.server-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); gap: 16px; margin-top: 8px; }
.server-card { border: 1px solid var(--el-border-color-light); border-radius: 10px; padding: 18px 20px; background: var(--el-fill-color-light); }
.node-info { display: flex; align-items: center; gap: 6px; margin-bottom: 14px; min-width: 0; }
.node-icon { color: var(--el-color-primary); flex-shrink: 0; }
.node-alias { font-weight: 700; font-size: 14px; color: var(--el-text-color-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 200px; }
.node-addr { font-size: 12px; color: var(--el-text-color-secondary); font-family: 'Courier New', monospace; flex-shrink: 0; }
.metric-rows { display: flex; flex-direction: column; gap: 10px; }
.metric-line { display: flex; align-items: center; gap: 12px; font-size: 13px; }
.ml-label { width: 88px; color: var(--el-text-color-regular); font-weight: 500; flex-shrink: 0; }
.ml-val { color: var(--el-text-color-primary); font-family: 'Courier New', monospace; }

.script-list { display: flex; flex-direction: column; gap: 14px; margin-top: 8px; }
.script-block { border: 1px solid var(--el-border-color-lighter); border-radius: 8px; padding: 12px 14px; background: var(--el-fill-color-light); }
.script-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.script-name { font-weight: 600; font-size: 14px; color: var(--el-text-color-primary); }
.script-type { font-size: 12px; color: var(--el-text-color-secondary); }
.script-out { margin: 0; padding: 10px 12px; background: var(--code-bg); color: var(--code-fg); border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 320px; overflow: auto; }
.script-err { margin: 8px 0 0; padding: 10px 12px; background: var(--code-bg); color: var(--code-fg); border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-all; max-height: 200px; overflow: auto; }

.critical-section { margin-bottom: 16px; }
.critical-title { font-size: 14px; font-weight: 700; color: var(--el-color-danger); margin-bottom: 12px; }
.critical-card {
  border: 1px solid var(--el-color-danger); border-left: 4px solid var(--el-color-danger); border-radius: 8px;
  padding: 14px 16px; margin-bottom: 10px; background: var(--el-color-danger-light-9);
}
.critical-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.critical-ip { font-weight: 700; font-size: 15px; color: var(--el-text-color-primary); font-family: 'Courier New', monospace; }
.critical-country { font-size: 12px; color: var(--el-text-color-secondary); }
.critical-count { font-size: 13px; color: var(--el-color-danger); font-weight: 600; margin-left: auto; }
.critical-meta { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--el-text-color-regular); margin-bottom: 8px; }
.critical-suggestion {
  font-size: 13px; color: var(--el-text-color-primary); background: var(--el-bg-color); border: 1px solid var(--el-border-color-light);
  border-radius: 6px; padding: 8px 12px; line-height: 1.6;
}
.suggestion-label { font-weight: 600; color: var(--el-color-warning); }
</style>
