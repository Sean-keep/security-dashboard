<template>
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
        <div class="ov-actions">
          <el-button size="small" type="primary" plain :loading="savingTpl" @click="saveSummaryTemplate">保存为默认模板</el-button>
          <span class="ov-hint">保存后，下次进入此页自动套用今日速览、勾选（服务器监控/脚本/接收端口）与板块顺序</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { useInspectionReport } from '../composables/useInspectionReport'

const {
  selectedDate,
  loading,
  currentReport,
  includeAddresses,
  includeMonitoring,
  scriptOptions,
  selectedScriptIds,
  endpointOptions,
  selectedEndpointIds,
  sectionOrder,
  sectionLabels,
  summaryText,
  savingTpl,
  generateReport,
  exportWord,
  exportTxt,
  selectAllScripts,
  clearScripts,
  selectAllEndpoints,
  clearEndpoints,
  endpointName,
  moveEndpointUp,
  moveEndpointDown,
  moveUp,
  moveDown,
  saveSummaryTemplate
} = useInspectionReport()
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
.overview-edit { margin-top: 4px; }
.ov-label { font-size: 13px; font-weight: 600; color: #303133; display: block; margin-bottom: 8px; }
.ov-actions { margin-top: 8px; display: flex; align-items: center; gap: 10px; }
.ov-hint { font-size: 12px; color: #909399; }
</style>
