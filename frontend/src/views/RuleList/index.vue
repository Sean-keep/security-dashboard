<template>
  <div class="rule-list-page">
    <div class="page-header">
      <h2>规则列表</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新建规则</el-button>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-bar">
      <el-form :inline="true" :model="filterForm" size="default">
        <el-form-item label="规则名称">
          <el-input v-model="filterForm.keyword" placeholder="搜索规则名称" clearable style="width:180px" @change="filterChange" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filterForm.is_enabled" placeholder="全部" clearable style="width:130px" @change="filterChange">
            <el-option label="已启用" :value="true" />
            <el-option label="已禁用" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="filterChange">筛选</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 表格 -->
    <el-card shadow="never">
      <template #header>
        <span>共 <strong>{{ total }}</strong> 条规则</span>
      </template>
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
        <el-table-column prop="run_count" label="执行次数" width="90" align="center" />
        <el-table-column prop="last_run" label="上次执行" width="160" />
        <el-table-column prop="is_enabled" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.is_enabled" size="small" @change="toggleEnabled(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="310" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openEdit(row)">编辑</el-button>
            <el-button type="info" link size="small" @click="runPreview(row)">预览</el-button>
            <el-button type="success" link size="small" @click="executeRule(row)">执行</el-button>
            <el-button type="primary" link size="small" @click="openExecutionLog(row)">日志</el-button>
            <el-button type="danger" link size="small" @click="confirmDelete(row)">删除</el-button>
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
          @size-change="loadData"
          @current-change="loadData"
        />
      </div>
    </el-card>

    <!-- 规则编辑弹窗（多阶段可视化） -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="1100px" destroy-on-close class="rule-dialog" top="5vh">
      <el-form ref="ruleFormRef" :model="ruleForm" :rules="ruleFormRules" label-width="100px" size="default">
        <!-- 基本信息 -->
        <el-divider content-position="left">基本信息</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="规则名称" prop="name">
              <el-input v-model="ruleForm.name" placeholder="给规则起个名字，如：检测高频404攻击IP" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="执行方式" prop="schedule_type">
              <el-select v-model="ruleForm.schedule_type" style="width:100%">
                <el-option label="手动执行" value="once" />
                <el-option label="周期执行" value="interval" />
                <el-option label="Cron表达式" value="cron" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <!-- 调度值（周期执行 / Cron表达式） -->
        <el-form-item v-if="ruleForm.schedule_type === 'interval'" label="执行周期" label-width="100">
          <div style="display:flex;align-items:center;gap:8px">
            <span>每</span>
            <el-input-number v-model="scheduleValueObj.value" :min="1" size="default" style="width:110px" />
            <el-select v-model="scheduleValueObj.unit" size="default" style="width:120px">
              <el-option label="分钟" value="minutes" />
              <el-option label="小时" value="hours" />
              <el-option label="天" value="days" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item v-if="ruleForm.schedule_type === 'cron'" label="Cron表达式" label-width="100">
          <el-input v-model="ruleForm.schedule_value" placeholder="如: 0 9 * * * (每天9点)" style="width:300px" size="default" />
          <span style="margin-left:8px;color:#888;font-size:12px">分 时 日 月 周</span>
        </el-form-item>

        <el-form-item label="规则描述">
          <el-input v-model="ruleForm.description" type="textarea" :rows="2" placeholder="描述此规则的检测逻辑和目的" />
        </el-form-item>

        <!-- 多阶段配置 -->
        <el-divider content-position="left">
          <span>查询阶段（多步骤编排）</span>
          <el-button type="primary" size="small" :icon="Plus" style="margin-left:12px" @click="addStage">添加阶段</el-button>
        </el-divider>
        
        <div class="stages-container">
          <div v-for="(stage, stageIdx) in ruleForm.stages" :key="stage.id" class="stage-card">
            <div class="stage-header">
              <div class="stage-title">
                <el-tag type="primary" size="large">阶段 {{ stageIdx + 1 }}</el-tag>
                <el-input v-model="stage.name" placeholder="阶段名称（可选）" style="width:200px;margin-left:8px" />
              </div>
              <el-button type="danger" :icon="Delete" circle size="small" @click="removeStage(stageIdx)" />
            </div>

            <el-row :gutter="16">
              <el-col :span="12">
                <el-form-item label="数据源索引">
                  <el-select v-model="stage.index" placeholder="选择ES索引" filterable allow-create style="width:100%" @change="onStageIndexChange(stage)">
                    <el-option v-for="idx in esIndices" :key="idx.name" :label="idx.name" :value="idx.name" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="12">
                <el-form-item label="时间窗口">
                  <el-input-number v-model="stage.timeWindow.value" :min="1" style="width:120px" />
                  <el-select v-model="stage.timeWindow.unit" style="width:100px;margin-left:8px">
                    <el-option label="分钟" value="minutes" />
                    <el-option label="小时" value="hours" />
                    <el-option label="天" value="days" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <!-- 过滤条件 -->
            <el-form-item label="过滤条件">
              <div class="filters-area">
                <div v-for="(filter, filterIdx) in stage.filters" :key="filterIdx" class="filter-row">
                  <el-select v-model="filter.field" placeholder="字段" filterable style="width:180px">
                    <el-option v-for="(type, f) in getStageFields(stage)" :key="f" :label="f" :value="f" />
                  </el-select>
                  <el-select v-model="filter.operator" style="width:120px">
                    <el-option label="等于" value="equals" />
                    <el-option label="不等于" value="not_equals" />
                    <el-option label="包含" value="contains" />
                    <el-option label="大于" value="gt" />
                    <el-option label="小于" value="lt" />
                    <el-option label="存在" value="exists" />
                  </el-select>
                  <el-input v-model="filter.value" placeholder="值" style="width:200px" />
                  <el-button type="danger" :icon="Delete" circle size="small" @click="stage.filters.splice(filterIdx, 1)" />
                </div>
                <el-button size="small" :icon="Plus" @click="stage.filters.push({field:'', operator:'equals', value:''})">添加条件</el-button>
              </div>
            </el-form-item>

            <!-- 聚合配置 -->
            <el-form-item label="聚合统计">
              <el-checkbox v-model="stage.enableAggregation">启用聚合（分组统计）</el-checkbox>
              <div v-if="stage.enableAggregation" class="aggregation-config">
                <el-row :gutter="12">
                  <el-col :span="8">
                    <el-form-item label="分组字段" label-width="80">
                      <el-select v-model="stage.aggregation.groupBy" multiple filterable placeholder="选择分组字段" style="width:100%">
                        <el-option v-for="(type, f) in getStageFields(stage)" :key="f" :label="f" :value="f" />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="统计指标" label-width="80">
                      <el-select v-model="stage.aggregation.metric" style="width:100%">
                        <el-option label="计数(count)" value="count" />
                        <el-option label="求和(sum)" value="sum" />
                        <el-option label="平均值(avg)" value="avg" />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="别名" label-width="80">
                      <el-input v-model="stage.aggregation.alias" placeholder="如：attack_count" />
                    </el-form-item>
                  </el-col>
                </el-row>
                <el-row :gutter="12">
                  <el-col :span="12">
                    <el-form-item label="阈值过滤" label-width="80">
                      <el-select v-model="stage.aggregation.having.operator" style="width:80px">
                        <el-option label=">" value="gt" />
                        <el-option label=">=" value="gte" />
                        <el-option label="<" value="lt" />
                        <el-option label="<=" value="lte" />
                      </el-select>
                      <el-input-number v-model="stage.aggregation.having.value" :min="0" style="width:120px;margin-left:8px" />
                      <span style="margin-left:8px;color:#888;font-size:12px">只保留满足条件的分组</span>
                    </el-form-item>
                  </el-col>
                </el-row>
              </div>
            </el-form-item>

            <!-- 关联配置（第2+阶段） -->
            <el-form-item v-if="stageIdx > 0" label="关联配置">
              <el-checkbox v-model="stage.enableJoin">启用关联（与前阶段数据关联）</el-checkbox>
              <div v-if="stage.enableJoin" class="join-config">
                <el-row :gutter="12">
                  <el-col :span="8">
                    <el-form-item label="前阶段" label-width="60">
                      <el-select v-model="stage.join.fromStage" style="width:100%">
                        <el-option v-for="(s, i) in ruleForm.stages.slice(0, stageIdx)" :key="s.id" :label="`阶段${i+1}: ${s.name || s.index}`" :value="s.id" />
                      </el-select>
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="关联字段" label-width="80">
                      <el-input v-model="stage.join.remoteField" placeholder="前阶段的关联字段" />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="本地字段" label-width="80">
                      <el-input v-model="stage.join.localField" placeholder="本阶段的匹配字段" />
                    </el-form-item>
                  </el-col>
                </el-row>
              </div>
            </el-form-item>

            <div class="stage-actions">
              <el-button type="primary" size="small" @click="previewStage(stage, stageIdx)">预览此阶段</el-button>
            </div>
          </div>

          <el-empty v-if="!ruleForm.stages.length" description="暂无查询阶段，点击上方按钮添加" />
        </div>

        <!-- 输出映射 -->
        <el-divider content-position="left">输出字段映射</el-divider>
        <div class="output-mapping-area">
          <el-form-item label="最终输出">
            <div class="mapping-list">
              <div v-for="(mapping, field) in ruleForm.outputMapping" :key="field" class="mapping-row">
                <el-input v-model="mapping.outputField" placeholder="输出字段名" style="width:150px" />
                <span style="margin:0 8px">=</span>
                <el-select v-model="mapping.fromStage" placeholder="来源阶段" style="width:150px">
                  <el-option v-for="(s, i) in ruleForm.stages" :key="s.id" :label="`阶段${i+1}`" :value="s.id" />
                </el-select>
                <span style="margin:0 8px">.</span>
                <el-input v-model="mapping.sourceField" placeholder="来源字段" style="width:150px" />
                <el-button type="danger" :icon="Delete" circle size="small" @click="removeMapping(field)" />
              </div>
              <el-button size="small" :icon="Plus" @click="addMapping">添加输出字段</el-button>
            </div>
          </el-form-item>
        </div>

        <!-- 触发动作 -->
        <el-divider content-position="left">触发动作</el-divider>
        <div class="actions-area">
          <el-checkbox v-model="writeMysqlEnabled">将结果写入 MySQL（地址列表）</el-checkbox>
          <div v-if="writeMysqlEnabled" class="action-config">
            <el-row :gutter="12">
              <el-col :span="8">
                <el-form-item label="目标表" label-width="80">
                  <el-select v-model="ruleForm.actionTable" style="width:100%">
                    <el-option label="地址列表" value="addresses" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <el-checkbox v-model="createAlertEnabled" style="margin-top:12px">创建告警（写入告警列表）</el-checkbox>
          <div v-if="createAlertEnabled" class="action-config">
            <el-row :gutter="12">
              <el-col :span="12">
                <el-form-item label="标题模板" label-width="80">
                  <el-input v-model="ruleForm.alertTitleTemplate" placeholder="可选，如：攻击检测 {src_ip}" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-form-item label="内容模板" label-width="80">
              <el-input v-model="ruleForm.alertTemplate" type="textarea" :rows="3" placeholder="支持 {field_name} 和 {stage.field} 语法&#10;如：检测到IP {src_ip} 在 {stage1.count} 次请求中攻击了 {server_name}" />
            </el-form-item>
            <!-- 危险等级条件 -->
            <el-form-item label="危险等级" label-width="80">
              <el-select v-model="ruleForm.severity" style="width:120px">
                <el-option label="低 (low)" value="low" />
                <el-option label="中 (medium)" value="medium" />
                <el-option label="高 (high)" value="high" />
                <el-option label="严重 (critical)" value="critical" />
              </el-select>
              <span style="margin-left:12px;color:#888;font-size:12px">默认等级，满足条件时自动升级</span>
            </el-form-item>
            <el-form-item label="条件升危" label-width="80">
              <div v-for="(cond, idx) in ruleForm.severityConditions" :key="idx" style="display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap">
                <el-input v-model="cond.field" placeholder="字段名" style="width:120px" />
                <el-select v-model="cond.operator" style="width:90px">
                  <el-option label="等于" value="==" />
                  <el-option label="不等于" value="!=" />
                  <el-option label="大于" value=">" />
                  <el-option label="大于等于" value=">=" />
                  <el-option label="小于" value="<" />
                  <el-option label="小于等于" value="<=" />
                  <el-option label="包含" value="contains" />
                </el-select>
                <el-input v-model="cond.value" placeholder="值" style="width:100px" />
                <span style="color:#888">→</span>
                <el-select v-model="cond.severity" style="width:100px">
                  <el-option label="低" value="low" />
                  <el-option label="中" value="medium" />
                  <el-option label="高" value="high" />
                  <el-option label="严重" value="critical" />
                </el-select>
                <el-button type="danger" link size="small" @click="ruleForm.severityConditions.splice(idx, 1)">删除</el-button>
              </div>
              <el-button size="small" @click="ruleForm.severityConditions.push({field:'',operator:'==',value:'',severity:'high'})">+ 添加条件</el-button>
              <span style="margin-left:12px;color:#888;font-size:12px">当条件满足时，告警等级自动升为对应值</span>
            </el-form-item>
          </div>
        </div>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saveLoading" @click="submitRule">保存规则</el-button>
      </template>
    </el-dialog>

    <!-- 执行结果 -->
    <el-dialog v-model="executeDialogVisible" title="执行结果" width="600px" destroy-on-close>
      <div v-if="executeResult" class="execute-result">
        <el-result :icon="executeResult.written > 0 ? 'success' : 'info'" :title="executeResult.msg">
          <template #sub-title>
            <p>查询记录：{{ executeResult.total }} 条</p>
            <p>写入MySQL：{{ executeResult.written }} 条</p>
          </template>
        </el-result>
      </div>
    </el-dialog>

    <!-- 预览弹窗 -->
    <el-dialog v-model="previewDialogVisible" title="ES查询预览" width="900px" destroy-on-close>
      <div v-if="previewLoading" style="text-align:center;padding:40px">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p style="margin-top:12px;color:#888">查询中...</p>
      </div>
      <div v-else-if="previewData.length">
        <el-alert :title="`查询结果：${previewData.length} 条`" type="success" :closable="false" style="margin-bottom:12px" />
        <el-table :data="previewData" :max-height="400" stripe size="small">
          <el-table-column v-for="col in previewColumns" :key="col" :prop="col" :label="col" min-width="120" show-overflow-tooltip />
        </el-table>
      </div>
      <el-empty v-else description="暂无数据" />
      <template #footer>
        <el-button type="primary" @click="previewDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 执行记录弹窗 -->
    <el-dialog v-model="execLogVisible" title="规则执行记录" width="900px" top="10vh">
      <div style="margin-bottom:12px">
        <span style="font-size:14px;color:#606266">规则：<strong>{{ execLogRuleName }}</strong></span>
        <el-button size="small" style="float:right" @click="loadExecutionLogs()" :loading="execLogLoading">刷新</el-button>
      </div>
      <el-table :data="execLogList" stripe size="small" v-loading="execLogLoading">
        <el-table-column prop="executed_at" label="执行时间" width="170" />
        <el-table-column prop="alert_count" label="告警数" width="80" align="center" />
        <el-table-column prop="status" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">{{ row.status === 'success' ? '成功' : '失败' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="执行摘要" min-width="300" show-overflow-tooltip />
        <el-table-column prop="error_message" label="错误信息" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_message" style="color:#F56C6C">{{ row.error_message }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap" style="margin-top:16px">
        <el-pagination
          v-model:current-page="execLogPage"
          :page-size="15"
          :total="execLogTotal"
          layout="total, prev, pager, next"
          @current-change="loadExecutionLogs"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { rules, settings, executionLogs } from '@/api'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Loading } from '@element-plus/icons-vue'

const tableData = ref([])
const total = ref(0)
const dialogVisible = ref(false)
const executeDialogVisible = ref(false)
const previewDialogVisible = ref(false)
const saveLoading = ref(false)
const previewLoading = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const esIndices = ref([{ name: 'security-logs-*' }])
const stageFieldsCache = ref({})  // 缓存各阶段索引的字段
const executeResult = ref(null)
const previewData = ref([])
const previewColumns = ref([])
const writeMysqlEnabled = ref(false)
const createAlertEnabled = ref(false)
const scheduleValueObj = reactive({ value: 5, unit: 'minutes' })

const filterForm = reactive({ keyword: '', is_enabled: '' })
const pagination = reactive({ page: 1, page_size: 20 })

// 多阶段规则表单
const ruleForm = ref({
  name: '',
  description: '',
  schedule_type: 'once',
  schedule_value: '',
  stages: [],  // 多阶段配置
  outputMapping: {},  // 输出映射
  actionTable: 'addresses',
  alertTemplate: '',
  alertTitleTemplate: ''
})

const ruleFormRules = {
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }]
}

const dialogTitle = computed(() => isEdit.value ? '编辑规则' : '新建规则')

const scheduleLabel = (s) => ({ once: '手动', interval: '周期', cron: 'Cron' }[s] || s)

// 获取阶段索引的字段列表（从缓存或ES加载）
const getStageFields = (stage) => {
  const index = stage.index
  if (stageFieldsCache.value[index]) {
    return stageFieldsCache.value[index]
  }
  return {}  // 默认空，在加载阶段索引时填充
}

// 加载规则列表
const loadData = async () => {
  try {
    const params = {
      keyword: filterForm.keyword,
      is_enabled: filterForm.is_enabled === '' ? '' : filterForm.is_enabled,
      page: pagination.page,
      page_size: pagination.page_size
    }
    const res = await rules.list(params)
    tableData.value = res.data.list
    total.value = res.data.total
  } catch (e) {}
}

const filterChange = () => { pagination.page = 1; loadData() }
const resetFilter = () => { Object.assign(filterForm, { keyword: '', is_enabled: '' }); filterChange() }

// 加载ES索引
const loadEsIndices = async () => {
  try {
    const res = await rules.esIndices()
    if (res.data?.length) esIndices.value = res.data
  } catch (e) {
    esIndices.value = [{ name: 'security-logs-*' }]
  }
}

// 加载索引字段
const loadIndexFields = async (index) => {
  if (stageFieldsCache.value[index]) return stageFieldsCache.value[index]
  try {
    const res = await rules.esPreview({ nodes: [], index, limit: 1 })
    const fields = res.data?.fields || {}
    stageFieldsCache.value[index] = fields
    return fields
  } catch (e) {
    const fallback = { src_ip: 'keyword', dest_ip: 'keyword', bytes: 'long', timestamp: 'date' }
    stageFieldsCache.value[index] = fallback
    return fallback
  }
}

// 阶段索引变化时加载字段
const onStageIndexChange = async (stage) => {
  await loadIndexFields(stage.index)
}

// 将后端 stage 格式转换为前端编辑格式
const backendStageToFrontend = (backendStage) => {
  // 从 time_window 对象中提取 value 和 unit
  let timeWindow = { value: 3, unit: 'minutes' }
  if (backendStage.time_window && typeof backendStage.time_window === 'object') {
    const keys = Object.keys(backendStage.time_window)
    if (keys.length > 0) {
      timeWindow = { value: backendStage.time_window[keys[0]], unit: keys[0] }
    }
  }

  // 将后端聚合格式转为前端格式
  let aggregation = { groupBy: [], metric: 'count', alias: 'count', having: { operator: 'gt', value: 0 } }
  let enableAggregation = false
  if (backendStage.aggregation && backendStage.aggregation.group_by) {
    enableAggregation = true
    aggregation = {
      groupBy: Array.isArray(backendStage.aggregation.group_by) ? backendStage.aggregation.group_by : [],
      metric: backendStage.aggregation.metric || 'count',
      alias: backendStage.aggregation.alias || 'count',
      having: backendStage.aggregation.having || { operator: 'gt', value: 0 }
    }
  }

  // 将后端 join 格式转为前端格式
  let join = { fromStage: '', remoteField: '', localField: '' }
  let enableJoin = false
  if (backendStage.join && backendStage.join.from_stage) {
    enableJoin = true
    join = {
      fromStage: backendStage.join.from_stage || '',
      remoteField: backendStage.join.remote_field || '',
      localField: backendStage.join.local_field || ''
    }
  }

  return {
    id: backendStage.id || `stage_${Date.now()}`,
    name: backendStage.name || '',
    index: backendStage.index || '',
    timeWindow,
    filters: Array.isArray(backendStage.filters) ? backendStage.filters : [],
    enableAggregation,
    aggregation,
    enableJoin,
    join
  }
}

// 添加阶段
const addStage = () => {
  const stageId = `stage_${Date.now()}`
  ruleForm.value.stages.push({
    id: stageId,
    name: '',
    index: '',
    timeWindow: { value: 3, unit: 'minutes' },
    filters: [],
    enableAggregation: false,
    aggregation: {
      groupBy: [],
      metric: 'count',
      alias: 'count',
      having: { operator: 'gt', value: 0 }
    },
    enableJoin: false,
    join: {
      fromStage: '',
      remoteField: '',
      localField: ''
    }
  })
}

// 删除阶段
const removeStage = (idx) => {
  ruleForm.value.stages.splice(idx, 1)
}

// 预览单个阶段
const previewStage = async (stage, stageIdx) => {
  if (!stage.index) {
    ElMessage.warning('请先选择数据源索引')
    return
  }

  previewLoading.value = true
  previewDialogVisible.value = true
  previewData.value = []
  previewColumns.value = []

  try {
    // 构建单阶段查询参数
    const stageParams = buildStageParams(stage)
    const res = await rules.esPreview({ stages: [stageParams], limit: 50 })
    
    previewData.value = res.data.preview || []
    if (previewData.value.length) {
      previewColumns.value = Object.keys(previewData.value[0])
    }
  } catch (e) {
    ElMessage.error('预览失败: ' + (e.message || e))
  } finally {
    previewLoading.value = false
  }
}

// 构建阶段参数（用于提交）
const buildStageParams = (stage) => {
  const params = {
    id: stage.id,
    index: stage.index,
    time_window: { [stage.timeWindow.unit]: stage.timeWindow.value },
    filters: stage.filters.filter(f => f.field),
    aggregation: null,
    join: null
  }

  if (stage.enableAggregation && stage.aggregation.groupBy.length) {
    params.aggregation = {
      group_by: stage.aggregation.groupBy,
      metric: stage.aggregation.metric,
      alias: stage.aggregation.alias || 'count',
      having: stage.aggregation.having.value > 0 ? stage.aggregation.having : null
    }
  }

  if (stage.enableJoin && stage.join.fromStage) {
    params.join = {
      from_stage: stage.join.fromStage,
      remote_field: stage.join.remoteField,
      local_field: stage.join.localField
    }
  }

  return params
}

// 添加输出映射
const addMapping = () => {
  const key = `mapping_${Date.now()}`
  ruleForm.value.outputMapping[key] = {
    outputField: '',
    fromStage: '',
    sourceField: ''
  }
}

// 删除输出映射
const removeMapping = (key) => {
  delete ruleForm.value.outputMapping[key]
}

// 打开新建
const openCreate = async () => {
  isEdit.value = false
  editId.value = null
  ruleForm.value = {
    name: '',
    description: '',
    schedule_type: 'once',
    schedule_value: '',
    stages: [],
    outputMapping: {},
    actionTable: 'addresses',
    alertTemplate: '',
    alertTitleTemplate: '',
    severity: 'medium',
    severityConditions: []
  }
  scheduleValueObj.value = 5
  scheduleValueObj.unit = 'minutes'
  writeMysqlEnabled.value = false
  createAlertEnabled.value = false
  severityConditions.value = []
  stageFieldsCache.value = {}
  
  // 获取系统默认ES索引配置
  let defaultIndex = 'security-logs-*'
  try {
    const esCfg = await settings.getEsDefault()
    if (esCfg.data?.default_index) {
      defaultIndex = esCfg.data.default_index
    }
  } catch (e) {}
  
  await loadEsIndices()
  
  // 如果ES索引列表为空，添加默认索引
  if (!esIndices.value.length) {
    esIndices.value = [{ name: defaultIndex }]
  }
  
  // 添加第一个阶段，并设置默认索引
  addStage()
  if (ruleForm.value.stages.length > 0) {
    ruleForm.value.stages[0].index = defaultIndex
    // 预加载该索引的字段
    await loadIndexFields(defaultIndex)
  }
  ruleForm.value.es_index = defaultIndex
  
  dialogVisible.value = true
}

// 打开编辑
const openEdit = async (row) => {
  isEdit.value = true
  editId.value = row.id
  try {
    const res = await rules.get(row.id)
    const data = res.data

    // 解析 schedule_value：interval 用 {value, unit}，cron 用字符串
    let sv = data.schedule_value || ''
    if (data.schedule_type === 'interval') {
      const m = sv.match(/^(\d+)\s*(minutes|hours|days)$/)
      scheduleValueObj.value = m ? parseInt(m[1]) : 5
      scheduleValueObj.unit = m ? m[2] : 'minutes'
    }

    // output_mapping 格式转换：{field: {from_stage, field}} → {key: {outputField, fromStage, sourceField}}
    const outputMapping = {}
    if (data.output_mapping && typeof data.output_mapping === 'object') {
      for (const [outField, cfg] of Object.entries(data.output_mapping)) {
        const key = `mapping_${Date.now()}_${outField}`
        outputMapping[key] = {
          outputField: outField,
          fromStage: cfg.from_stage || '',
          sourceField: cfg.field || ''
        }
      }
    }

    // Parse actions for alert template + severity
    let alertTemplate = ''
    let alertTitleTemplate = ''
    let severity = 'medium'
    let severityConditions = []
    if (data.actions && data.actions.length) {
      for (const act of data.actions) {
        if (act.type === 'create_alert') {
          alertTemplate = act.template || ''
          alertTitleTemplate = act.title_template || ''
          severity = act.severity || 'medium'
          severityConditions = act.severity_conditions || []
        }
      }
    }

    ruleForm.value = {
      name: data.name || '',
      description: data.description || '',
      schedule_type: data.schedule_type || 'once',
      schedule_value: data.schedule_type === 'cron' ? sv : '',
      stages: (data.stages || []).map(backendStageToFrontend),
      outputMapping,
      actionTable: 'addresses',
      alertTemplate,
      alertTitleTemplate,
      severity,
      severityConditions
    }
    writeMysqlEnabled.value = !!(data.actions && data.actions.some(a => a.type === 'write_mysql'))
    createAlertEnabled.value = !!(data.actions && data.actions.some(a => a.type === 'create_alert'))
    stageFieldsCache.value = {}
    await loadEsIndices()
    for (const stage of ruleForm.value.stages) {
      if (stage.index) await loadIndexFields(stage.index)
    }
    dialogVisible.value = true
  } catch (e) {}
}

// 提交规则
const submitRule = async () => {
  try {
    await ruleFormRef.value.validate()
    saveLoading.value = true

    // 构建提交数据
    const stages = ruleForm.value.stages.map(buildStageParams)
    
    // 构建输出映射
    const outputMapping = {}
    for (const key in ruleForm.value.outputMapping) {
      const m = ruleForm.value.outputMapping[key]
      if (m.outputField && m.fromStage && m.sourceField) {
        outputMapping[m.outputField] = {
          from_stage: m.fromStage,
          field: m.sourceField
        }
      }
    }

    // schedule_value：interval 时拼接为字符串
    let scheduleValue = ruleForm.value.schedule_value
    if (ruleForm.value.schedule_type === 'interval') {
      scheduleValue = `${scheduleValueObj.value} ${scheduleValueObj.unit}`
    }

    const payload = {
      name: ruleForm.value.name,
      description: ruleForm.value.description,
      schedule_type: ruleForm.value.schedule_type,
      schedule_value: scheduleValue,
      stages,
      output_mapping: outputMapping,
      es_index: ruleForm.value.es_index,
      actions: []
    }

    if (writeMysqlEnabled.value) {
      payload.actions.push({
        type: 'write_mysql',
        table: ruleForm.value.actionTable,
        mapping: {}
      })
    }

    if (createAlertEnabled.value) {
      const alertAction = { type: 'create_alert', mapping: {} }
      if (ruleForm.value.alertTemplate) alertAction.template = ruleForm.value.alertTemplate
      if (ruleForm.value.alertTitleTemplate) alertAction.title_template = ruleForm.value.alertTitleTemplate
      // 危险等级条件
      alertAction.severity = ruleForm.value.severity || 'medium'
      if (ruleForm.value.severityConditions && ruleForm.value.severityConditions.length) {
        alertAction.severity_conditions = ruleForm.value.severityConditions.filter(c => c.field && c.operator && c.value !== undefined && c.severity)
      }
      payload.actions.push(alertAction)
    }

    if (isEdit.value) {
      await rules.update(editId.value, payload)
      ElMessage.success('规则更新成功')
    } else {
      await rules.create(payload)
      ElMessage.success('规则创建成功')
    }
    dialogVisible.value = false
    loadData()
  } catch (e) {
    if (e.message) ElMessage.error(e.message)
  } finally {
    saveLoading.value = false
  }
}

const toggleEnabled = async (row) => {
  try {
    await rules.update(row.id, { is_enabled: row.is_enabled })
    ElMessage.success(row.is_enabled ? '规则已启用' : '规则已禁用')
  } catch (e) {}
}

const runPreview = async (row) => {
  try {
    const res = await rules.run(row.id)
    previewData.value = res.data.preview || []
    previewColumns.value = previewData.value.length ? Object.keys(previewData.value[0]) : []
    previewDialogVisible.value = true
  } catch (e) {}
}

const executeRule = async (row) => {
  try {
    await ElMessageBox.confirm('确认执行此规则？将查询ES并写入MySQL。', '执行确认', { type: 'info' })
    const res = await rules.execute(row.id)
    executeResult.value = res.data
    executeResult.value.msg = res.msg
    executeDialogVisible.value = true
    loadData()
  } catch (e) {}
}

const confirmDelete = (row) => {
  ElMessageBox.confirm(`确定删除规则「${row.name}」？`, '确认', { type: 'warning' })
    .then(async () => { await rules.delete(row.id); ElMessage.success('删除成功'); loadData() })
    .catch(() => {})
}

// ── 规则执行记录 ──
const execLogVisible = ref(false)
const execLogRuleName = ref('')
const execLogRuleId = ref(null)
const execLogList = ref([])
const execLogTotal = ref(0)
const execLogPage = ref(1)
const execLogLoading = ref(false)

const openExecutionLog = (row) => {
  execLogRuleName.value = row.name
  execLogRuleId.value = row.id
  execLogPage.value = 1
  execLogVisible.value = true
  loadExecutionLogs()
}

const loadExecutionLogs = async () => {
  execLogLoading.value = true
  try {
    const r = await executionLogs.list({ rule_id: execLogRuleId.value, page: execLogPage.value })
    execLogList.value = r.data?.list || r.data?.items || []
    execLogTotal.value = r.data?.total || 0
  } catch (e) {
    execLogList.value = []
  } finally {
    execLogLoading.value = false
  }
}

const ruleFormRef = ref()

onMounted(loadData)
</script>

<style lang="scss" scoped>
.rule-list-page { }
.page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; h2 { margin:0; font-size:18px; } }
.filter-bar { margin-bottom: 16px; }
.rule-name { font-weight: 600; color: #409EFF; }
.pagination-wrap { display:flex; justify-content:flex-end; margin-top:16px; }

.rule-dialog :deep(.el-dialog__body) { padding: 12px 24px 8px; max-height: 70vh; overflow-y: auto; }

.stages-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 8px;
}

.stage-card {
  background: #f7f8fa;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 16px;
  transition: box-shadow 0.2s;
  &:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
}

.stage-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #e0e0e0;
}

.stage-title {
  display: flex;
  align-items: center;
}

.filters-area {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.aggregation-config, .join-config {
  margin-top: 8px;
  background: #fff;
  border-radius: 6px;
  padding: 12px;
}

.stage-actions {
  margin-top: 12px;
  text-align: right;
}

.output-mapping-area {
  background: #f7f8fa;
  border-radius: 8px;
  padding: 12px 16px;
}

.mapping-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mapping-row {
  display: flex;
  align-items: center;
}

.actions-area {
  background: #f7f8fa;
  border-radius: 8px;
  padding: 12px 16px;
}

.action-config {
  margin-top: 12px;
  background: #fff;
  border-radius: 6px;
  padding: 8px;
}

.execute-result { }
</style>
