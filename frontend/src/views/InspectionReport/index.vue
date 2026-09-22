<template>
  <div class="page-container">

    <el-tabs v-model="activeTab" class="report-tabs">

      <!-- ════════════════════ Tab 1: 生成报告 ════════════════════ -->
      <el-tab-pane label="生成报告" name="generate">
        <ReportConfig />
        <ReportPreview />
      </el-tab-pane>

      <!-- ════════════════════ Tab 2: 报告列表 ════════════════════ -->
      <el-tab-pane label="报告列表" name="list">
        <ReportList
          :report-list="reportList"
          :report-total="reportTotal"
          :report-page="reportPage"
          :report-page-size="reportPageSize"
          :refreshing="refreshing"
          @refresh="loadReports"
          @page-change="onPageChange"
          @preview="previewReport"
          @export="exportReport"
          @remove="removeReport"
        />
      </el-tab-pane>

    </el-tabs>

    <PreviewDialog />

  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import ReportConfig from './components/ReportConfig.vue'
import ReportPreview from './components/ReportPreview.vue'
import ReportList from './components/ReportList.vue'
import PreviewDialog from './components/PreviewDialog.vue'
import { useInspectionReport } from './composables/useInspectionReport'

const {
  activeTab,
  reportList,
  reportTotal,
  reportPage,
  reportPageSize,
  refreshing,
  loadReports,
  onPageChange,
  previewReport,
  exportReport,
  removeReport,
  initPage
} = useInspectionReport()

loadReports()
onMounted(initPage)
</script>

<style scoped>
.report-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }

.summary { display: flex; gap: 32px; }
.summary-dlg { margin-bottom: 0; }
.summary-item { text-align: center; }
.s-val { font-size: 24px; font-weight: 700; color: #303133; }
.s-val.ok { color: #67c23a; }
.s-val.bad { color: #f56c6c; }
.s-label { font-size: 12px; color: #909399; margin-top: 4px; }
</style>
