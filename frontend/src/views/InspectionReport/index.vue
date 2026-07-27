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
          <div class="script-pick" v-if="scriptOptions.length">
            <span class="sp-label">勾选脚本:</span>
            <el-checkbox-group v-model="selectedScriptIds" size="small">
              <el-checkbox v-for="sc in scriptOptions" :key="sc.id" :label="sc.id" border>{{ sc.name }}</el-checkbox>
            </el-checkbox-group>
            <span class="sp-hint" v-if="!selectedScriptIds.length">未勾选则不执行脚本</span>
          </div>
        </el-card>

        <el-empty v-if="!currentReport && !loading" description="请选择日期后点击「生成巡检报告」" />

        <template v-if="currentReport">
          <!-- 汇总 -->
          <el-card shadow="never" class="mb-16">
            <template #header>
              <div class="card-header">
                <span class="card-title">巡检报告 · {{ currentReport.report_date }}</span>
                <span class="card-sub">生成时间：{{ currentReport.generated_at }}</span>
              </div>
            </template>
            <div class="summary">
              <div class="summary-item">
                <div class="s-val">{{ currentReport.address_count }}</div>
                <div class="s-label">当日攻击地址</div>
              </div>
              <div class="summary-item">
                <div class="s-val">{{ (currentReport.servers || []).length }}</div>
                <div class="s-label">监控服务器</div>
              </div>
              <div class="summary-item">
                <div class="s-val">{{ currentReport.script_count }}</div>
                <div class="s-label">脚本执行</div>
              </div>
              <div class="summary-item">
                <div class="s-val" :class="currentReport.monitoring_connected ? 'ok' : 'bad'">
                  {{ currentReport.monitoring_connected ? '已连接' : '未连接' }}
                </div>
                <div class="s-label">Grafana/Prometheus</div>
              </div>
            </div>
            <el-alert v-if="!currentReport.monitoring_connected && currentReport.monitoring_error"
              type="warning" :closable="false" show-icon :title="currentReport.monitoring_error" style="margin-top:12px" />
          </el-card>

          <!-- 攻击地址 -->
          <el-card shadow="never" class="mb-16">
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

          <!-- 服务器监控（仅数字） -->
          <el-card shadow="never" class="mb-16" v-if="(currentReport.servers || []).length">
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

          <!-- 脚本执行结果 -->
          <el-card shadow="never" v-if="(currentReport.scripts || []).length">
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
            <el-table-column prop="report_date" label="报告日期" width="130" />
            <el-table-column prop="generated_at" label="生成时间" width="170" />
            <el-table-column prop="address_count" label="攻击地址" width="100" align="right" />
            <el-table-column prop="script_count" label="脚本数" width="90" align="right" />
            <el-table-column prop="created_by" label="生成人" width="100" />
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <el-button size="small" type="primary" plain @click="previewReport(row)">预览</el-button>
                <el-button size="small" @click="exportReport(row, 'word')">导出 Word</el-button>
                <el-button size="small" @click="exportReport(row, 'txt')">导出 TXT</el-button>
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
        <div class="summary summary-dlg">
          <div class="summary-item"><div class="s-val">{{ previewData.address_count }}</div><div class="s-label">当日攻击地址</div></div>
          <div class="summary-item"><div class="s-val">{{ (previewData.servers || []).length }}</div><div class="s-label">监控服务器</div></div>
          <div class="summary-item"><div class="s-val">{{ previewData.script_count }}</div><div class="s-label">脚本执行</div></div>
          <div class="summary-item">
            <div class="s-val" :class="previewData.monitoring_connected ? 'ok' : 'bad'">{{ previewData.monitoring_connected ? '已连接' : '未连接' }}</div>
            <div class="s-label">Grafana/Prometheus</div>
          </div>
        </div>

        <el-divider content-position="left">攻击地址</el-divider>
        <el-table :data="previewData.addresses || []" border stripe size="small" max-height="280">
          <el-table-column prop="ip_address" label="IP" min-width="140" />
          <el-table-column prop="country" label="国家" width="130" show-overflow-tooltip />
          <el-table-column prop="domain" label="域名" min-width="160" show-overflow-tooltip />
          <el-table-column prop="start_time" label="起始时间" width="165" />
          <el-table-column prop="attack_count" label="次数" width="90" align="right" />
        </el-table>

        <template v-if="(previewData.servers || []).length">
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

        <template v-if="(previewData.scripts || []).length">
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
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { reports, reportMgmt } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Monitor, Refresh } from '@element-plus/icons-vue'

// ── Tab 状态 ──
const activeTab = ref('generate')

// ── 生成报告 ──
const selectedDate = ref(formatToday())
const loading = ref(false)
const currentReport = ref(null)
const scriptOptions = ref([])
const selectedScriptIds = ref([])

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
})

const generateReport = async () => {
  loading.value = true
  try {
    const params = { date: selectedDate.value }
    if (selectedScriptIds.value.length) params.script_ids = selectedScriptIds.value.join(',')
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
  L.push(`当日攻击地址: ${r.address_count} ｜ 监控服务器: ${(r.servers || []).length} ｜ 脚本执行: ${r.script_count} ｜ 监控: ${r.monitoring_connected ? '已连接' : '未连接'}`)
  L.push('───────────────────────────────────────────────')
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
  L.push('【脚本执行结果】')
  if (!(r.scripts || []).length) L.push('（未勾选脚本，未执行）')
  ;(r.scripts || []).forEach((sc, i) => {
    L.push(`${i + 1}. ${sc.name} [${sc.script_type}] 退出码 ${sc.exit_code}`)
    if (sc.stdout) L.push('   ' + sc.stdout.replace(/\n/g, '\n   '))
    if (sc.stderr) L.push('   错误: ' + sc.stderr.replace(/\n/g, '\n   '))
  })
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
  L.push(`<p>当日攻击地址：${r.address_count} ｜ 监控服务器：${(r.servers || []).length} ｜ 脚本执行：${r.script_count} ｜ 监控：${r.monitoring_connected ? '已连接' : '未连接'}</p>`)
  L.push('<h3>攻击地址</h3>')
  ;(r.addresses || []).forEach((a, i) => {
    const country = a.country ? `（${a.country}）` : ''
    L.push(`<p><b>${i + 1}. 攻击地址:</b> ${a.ip_address}${country}<br/>`)
    L.push(`攻击时间: ${a.start_time} ~ ${a.end_time}<br/>`)
    L.push(`持续时间: ${a.duration} 秒<br/>`)
    L.push(`攻击次数: ${a.attack_count}<br/>`)
    L.push(`攻击域名: ${a.domain || '-'}</p>`)
  })
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
  L.push('<h3>脚本执行结果</h3>')
  if (!(r.scripts || []).length) L.push('<p>（未勾选脚本，未执行）</p>')
  ;(r.scripts || []).forEach((sc, i) => {
    L.push(`<p><b>${i + 1}. ${sc.name}</b> [${sc.script_type}] 退出码 ${sc.exit_code}<br/>`)
    if (sc.stdout) L.push(`<pre>${sc.stdout.replace(/</g, '&lt;')}</pre>`)
    if (sc.stderr) L.push(`<pre>错误: ${sc.stderr.replace(/</g, '&lt;')}</pre>`)
    L.push('</p>')
  })
  L.push('</body></html>')
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
.script-pick { display: flex; align-items: flex-start; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
.sp-label { font-size: 13px; color: #606266; flex-shrink: 0; line-height: 32px; }
.sp-hint { font-size: 12px; color: #c0c4cc; line-height: 32px; }
.card-header { display: flex; align-items: center; gap: 10px; }
.card-title { font-weight: 600; font-size: 15px; }

.summary { display: flex; gap: 32px; }
.summary-dlg { margin-bottom: 0; }
.summary-item { text-align: center; }
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
