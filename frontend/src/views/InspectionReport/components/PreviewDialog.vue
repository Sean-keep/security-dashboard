<template>
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
          <!-- 严重级别 -->
          <div v-for="a in (previewData.addresses || []).filter(x => x.severity === 'critical')" :key="a.ip_address" class="critical-card" style="margin-bottom:8px;">
            <div class="critical-header">
              <el-tag type="danger" effect="dark" size="small">严重</el-tag>
              <span class="critical-ip">{{ a.ip_address }}</span>
              <span class="critical-count">攻击 {{ a.attack_count }} 次</span>
            </div>
            <div v-if="a.handle_suggestion" class="critical-suggestion">
              <span class="suggestion-label">处置结果：</span>{{ a.handle_suggestion }}
            </div>
          </div>
          <!-- 高危及以下 -->
          <el-table :data="(previewData.addresses || []).filter(x => x.severity !== 'critical')" border stripe size="small" max-height="280">
            <el-table-column prop="ip_address" label="IP" min-width="140" />
            <el-table-column label="级别" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="severityType(row.severity)" size="small" effect="plain">{{ severityLabel(row.severity) }}</el-tag>
              </template>
            </el-table-column>
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
                <el-tag v-if="sc.exit_code !== 0" type="danger" size="small" effect="plain">
                  失败（退出码 {{ sc.exit_code }}）
                </el-tag>
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
</template>

<script setup>
import { Monitor } from '@element-plus/icons-vue'
import { useInspectionReport } from '../composables/useInspectionReport'

const {
  previewVisible,
  previewData,
  sectionOrder,
  severityLabel,
  severityType
} = useInspectionReport()
</script>

<style scoped>
.overview { margin-top: 4px; }
.ov-title { font-size: 14px; font-weight: 700; color: #303133; margin-bottom: 8px; }
.ov-text { white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; line-height: 1.7; color: #303133; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; padding: 12px 14px; margin: 0; }

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

.critical-card {
  border: 1px solid #f56c6c; border-left: 4px solid #f56c6c; border-radius: 8px;
  padding: 14px 16px; margin-bottom: 10px; background: #fef0f0;
}
.critical-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.critical-ip { font-weight: 700; font-size: 15px; color: #303133; font-family: 'Courier New', monospace; }
.critical-count { font-size: 13px; color: #f56c6c; font-weight: 600; margin-left: auto; }
.critical-suggestion {
  font-size: 13px; color: #303133; background: #fff; border: 1px solid #e4e7ed;
  border-radius: 6px; padding: 8px 12px; line-height: 1.6;
}
.suggestion-label { font-weight: 600; color: #e6a23c; }
</style>
