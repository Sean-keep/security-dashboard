<template>
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
          <el-form-item label="规则类型" prop="rule_type">
            <el-select v-model="ruleForm.rule_type" style="width:100%">
              <el-option label="ES 日志规则" value="logs" />
              <el-option label="指标阈值规则" value="metric" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="16" v-if="!isMetric">
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
      <!-- 指标规则不问调度：固定每 60 秒，只问「持续多久」 -->
      <el-form-item v-else label="检查间隔" label-width="100">
        <span class="metric-fixed-schedule">固定每 60 秒检查一次（服务端强制），只需在下方填写「持续多久」</span>
      </el-form-item>
      <!-- 调度值（周期执行 / Cron表达式） -->
      <el-form-item v-if="!isMetric && ruleForm.schedule_type === 'interval'" label="执行周期" label-width="100">
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
      <el-form-item v-if="!isMetric && ruleForm.schedule_type === 'cron'" label="Cron表达式" label-width="100">
        <el-input v-model="ruleForm.schedule_value" placeholder="如: 0 9 * * * (每天9点)" style="width:300px" size="default" />
        <span style="margin-left:8px;color:var(--el-text-color-secondary);font-size:12px">分 时 日 月 周</span>
      </el-form-item>
      <!-- 调度预览：和保存校验走同一条后端路径，边打字边回显 -->
      <el-form-item v-if="!isMetric && ruleForm.schedule_type !== 'once'" label="排期预览" label-width="100">
        <div class="schedule-preview" :class="previewClass">
          <template v-if="previewLoading">计算中…</template>
          <template v-else-if="preview.error">
            <span class="preview-error">✕ {{ preview.error }}</span>
          </template>
          <template v-else-if="preview.next_runs?.length">
            <div class="preview-ok">✓ 合法，下次执行：</div>
            <div v-for="(t, i) in preview.next_runs" :key="i" class="preview-run">{{ i + 1 }}. {{ t }}</div>
          </template>
          <template v-else>填写调度参数后显示下次执行时间</template>
        </div>
      </el-form-item>
      <el-form-item v-else-if="!isMetric" label="排期预览" label-width="100">
        <div class="schedule-preview">手动执行，保存后需要点「执行」才会跑</div>
      </el-form-item>

      <el-form-item label="规则描述">
        <el-input v-model="ruleForm.description" type="textarea" :rows="2" placeholder="描述此规则的检测逻辑和目的" />
      </el-form-item>

      <!-- 指标阈值（只对指标规则显示） -->
      <template v-if="isMetric">
        <el-divider content-position="left">指标阈值</el-divider>
        <div class="metric-area">
          <el-form-item label="PromQL" label-width="100">
            <el-input
              v-model="ruleForm.metric.promql"
              type="textarea"
              :rows="3"
              class="metric-promql"
              placeholder="如：rate(node_cpu_seconds_total{mode!=&quot;idle&quot;}[5m]) * 100"
            />
            <div class="metric-hint">
              可用变量：
              <span class="promql-code">{instance}</span>
              <span class="promql-code">{value}</span>
              <span class="promql-code">{threshold}</span>
              <span class="promql-code">{operator}</span>
              <span class="promql-code">{promql}</span>
              <span class="promql-code">{sustain_minutes}</span>
              <span class="promql-code">{series}</span>
            </div>
            <div class="metric-hint">
              ⚠️ 标题模板里不要放 <span class="promql-code">{value}</span> ——
              标题参与告警去重的指纹，带上数值会让「持续告警」每分钟都算新告警。数值放内容模板。
            </div>
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="14">
              <el-form-item label="条件" label-width="100">
                <div style="display:flex;align-items:center;gap:8px">
                  <span>当值</span>
                  <el-select v-model="ruleForm.metric.operator" style="width:90px">
                    <el-option label=">" value=">" />
                    <el-option label=">=" value=">=" />
                    <el-option label="<" value="<" />
                    <el-option label="<=" value="<=" />
                    <el-option label="等于" value="==" />
                  </el-select>
                  <el-input-number v-model="ruleForm.metric.threshold" :precision="4" style="width:140px" />
                </div>
              </el-form-item>
            </el-col>
            <el-col :span="10">
              <el-form-item label="持续多久" label-width="100">
                <div style="display:flex;align-items:center;gap:8px">
                  <el-input-number v-model="ruleForm.metric.sustain_minutes" :min="1" :max="1440" style="width:120px" />
                  <span>分钟</span>
                </div>
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label=" " label-width="100">
            <el-button size="small" :loading="promqlTesting" @click="testPromql">测试 PromQL</el-button>
            <span style="margin-left:12px;color:var(--el-text-color-secondary);font-size:12px">
              立即查一次，回显命中的序列和当前值。不落库、不推进持续计时。
            </span>
          </el-form-item>
          <div v-if="promqlResult" class="promql-result" :class="promqlResult.error ? 'is-error' : ''">
            <template v-if="promqlResult.error">✕ {{ promqlResult.error }}</template>
            <template v-else>
              ✓ 命中 {{ promqlResult.total }} 条序列
              <div v-for="(s, i) in promqlResult.series" :key="i" class="promql-series">
                {{ s.identity || '(无 instance 标签)' }} = {{ s.value }}
              </div>
            </template>
          </div>
        </div>
      </template>

      <!-- 多阶段配置（只对日志规则显示） -->
      <template v-if="!isMetric">
        <el-divider content-position="left">
          <span>查询阶段（多步骤编排）</span>
          <el-button type="primary" size="small" :icon="Plus" style="margin-left:12px" @click="addStage">添加阶段</el-button>
        </el-divider>

        <div class="stages-container">
          <StageCard
            v-for="(stage, stageIdx) in ruleForm.stages"
            :key="stage.id"
            :stage="stage"
            :stage-idx="stageIdx"
            :stages="ruleForm.stages"
            :es-indices="esIndices"
            @remove="removeStage(stageIdx)"
            @preview="previewStage(stage, stageIdx)"
          />

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
      </template>

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
            <span style="margin-left:12px;color:var(--el-text-color-secondary);font-size:12px">默认等级，满足条件时自动升级</span>
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
              <span style="color:var(--el-text-color-secondary)">→</span>
              <el-select v-model="cond.severity" style="width:100px">
                <el-option label="低" value="low" />
                <el-option label="中" value="medium" />
                <el-option label="高" value="high" />
                <el-option label="严重" value="critical" />
              </el-select>
              <el-button type="danger" link size="small" @click="ruleForm.severityConditions.splice(idx, 1)">删除</el-button>
            </div>
            <el-button size="small" @click="ruleForm.severityConditions.push({field:'',operator:'==',value:'',severity:'high'})">+ 添加条件</el-button>
            <span style="margin-left:12px;color:var(--el-text-color-secondary);font-size:12px">当条件满足时，告警等级自动升为对应值</span>
          </el-form-item>
        </div>

        <el-checkbox v-model="telegramEnabled" style="margin-top:12px">推送到 Telegram</el-checkbox>
        <div v-if="telegramEnabled" class="action-config">
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="Bot Token" label-width="80">
                <el-input
                  v-model="ruleForm.tgBotToken"
                  type="password"
                  show-password
                  :placeholder="ruleForm.tgTokenSet ? '已配置，留空保持不变' : '123456:ABC-DEF...'"
                />
              </el-form-item>
            </el-col>
            <el-col :span="10">
              <el-form-item label="Chat ID" label-width="80">
                <el-input v-model="ruleForm.tgChatId" placeholder="-1001234567890 或用户 ID" />
              </el-form-item>
            </el-col>
            <el-col :span="2" style="display:flex;align-items:center">
              <el-button size="small" :loading="tgTesting" @click="testTelegram">测试</el-button>
            </el-col>
          </el-row>
          <el-form-item label="标题模板" label-width="80">
            <el-input v-model="ruleForm.tgTitleTemplate" placeholder="可选，留空则用「告警: 规则名」" />
          </el-form-item>
          <el-form-item label="消息模板" label-width="80">
            <el-input
              v-model="ruleForm.tgTemplate"
              type="textarea"
              :rows="3"
              placeholder="可选，留空则用默认告警文案。&#10;支持 {field_name} 和 {stage.field} 语法，与「创建告警」的内容模板一致"
            />
          </el-form-item>
          <div class="tg-hint">
            Bot Token 只保存在服务端，接口不会回传明文；编辑时留空表示保持原值。
            单次执行最多推送 20 条，避免刷屏触发 Telegram 限流。
          </div>
        </div>
      </div>
    </el-form>

    <template #footer>
      <el-button @click="dialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="saveLoading" @click="submitRule">保存规则</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import StageCard from './StageCard.vue'
import { useRules } from '../composables/useRules'
import { rules as rulesApi, schedulePreview } from '@/api'

const emit = defineEmits(['saved'])

const {
  esIndices,
  stageFieldsCache,
  loadEsIndices,
  loadIndexFields,
  backendStageToFrontend,
  buildStageParams,
  previewStage: previewStageAction,
  getDefaultIndex,
  createRule,
  updateRule,
  getRule
} = useRules()

const dialogVisible = ref(false)
const saveLoading = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const writeMysqlEnabled = ref(false)
const createAlertEnabled = ref(false)
const telegramEnabled = ref(false)
const tgTesting = ref(false)
const promqlTesting = ref(false)
const promqlResult = ref(null)
const scheduleValueObj = reactive({ value: 5, unit: 'minutes' })
const ruleFormRef = ref()

// 多阶段规则表单
const ruleForm = ref({
  name: '',
  description: '',
  rule_type: 'logs',
  metric: { promql: '', operator: '>', threshold: 80, sustain_minutes: 5 },
  schedule_type: 'once',
  schedule_value: '',
  stages: [],  // 多阶段配置
  outputMapping: {},  // 输出映射
  actionTable: 'addresses',
  alertTemplate: '',
  alertTitleTemplate: '',
  // Telegram 推送。tgTokenSet 只反映服务端「是否已配置」，明文 token 不会回传。
  tgBotToken: '',
  tgChatId: '',
  tgTitleTemplate: '',
  tgTemplate: '',
  tgTokenSet: false
})

const isMetric = computed(() => ruleForm.value.rule_type === 'metric')

const ruleFormRules = {
  name: [{ required: true, message: '请输入规则名称', trigger: 'blur' }]
}

const dialogTitle = computed(() => isEdit.value ? '编辑规则' : '新建规则')

// ── 调度参数实时预览 ──
// 和保存校验走同一条后端路径（rule_runner.parse_schedule），避免「打字时说合法、
// 存进去却不合法」。debounce 是为了别在每个键上打一次接口。
const preview = ref({ valid: true, error: null, next_runs: [] })
const previewLoading = ref(false)
let previewTimer = null

const currentScheduleValue = computed(() => {
  if (ruleForm.value.schedule_type === 'interval') {
    return `${scheduleValueObj.value} ${scheduleValueObj.unit}`
  }
  return ruleForm.value.schedule_value || ''
})

const previewClass = computed(() => ({
  'is-error': !!preview.value.error,
  'is-ok': preview.value.valid && preview.value.next_runs?.length
}))

const refreshPreview = async () => {
  const stype = ruleForm.value.schedule_type
  const svalue = currentScheduleValue.value
  if (stype === 'once') {
    preview.value = { valid: true, error: null, next_runs: [] }
    return
  }
  if (!svalue || !svalue.trim()) {
    preview.value = { valid: false, error: '执行周期不能为空', next_runs: [] }
    return
  }
  previewLoading.value = true
  try {
    const res = await schedulePreview(stype, svalue, 3)
    preview.value = res.data || { valid: false, error: '预览失败', next_runs: [] }
  } catch (e) {
    preview.value = { valid: false, error: e.message || '预览失败', next_runs: [] }
  } finally {
    previewLoading.value = false
  }
}

watch(
  [
    () => ruleForm.value.schedule_type,
    () => ruleForm.value.schedule_value,
    () => scheduleValueObj.value,
    () => scheduleValueObj.unit,
  ],
  () => {
    clearTimeout(previewTimer)
    previewTimer = setTimeout(refreshPreview, 350)
  }
)

// 添加阶段
const addStage = () => {
  const stageId = `stage_${Date.now()}`
  ruleForm.value.stages.push({
    id: stageId,
    name: '',
    index: '',
    timeWindow: { value: 3, unit: 'minutes' },
    filters: { logic: null, filters: [] },
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
const previewStage = (stage) => {
  previewStageAction(stage)
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
    rule_type: 'logs',
    metric: { promql: '', operator: '>', threshold: 80, sustain_minutes: 5 },
    schedule_type: 'once',
    schedule_value: '',
    stages: [],
    outputMapping: {},
    actionTable: 'addresses',
    alertTemplate: '',
    alertTitleTemplate: '',
    severity: 'medium',
    severityConditions: [],
    tgBotToken: '',
    tgChatId: '',
    tgTitleTemplate: '',
    tgTemplate: '',
    tgTokenSet: false
  }
  scheduleValueObj.value = 5
  scheduleValueObj.unit = 'minutes'
  writeMysqlEnabled.value = false
  createAlertEnabled.value = false
  telegramEnabled.value = false
  promqlResult.value = null
  stageFieldsCache.value = {}

  // 获取系统默认ES索引配置
  const defaultIndex = await getDefaultIndex()

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
  refreshPreview()
}

// 打开编辑
const openEdit = async (row) => {
  isEdit.value = true
  editId.value = row.id
  try {
    const res = await getRule(row.id)
    const data = res.data
    const ruleType = data.source_type === 'metric' ? 'metric' : 'logs'

    // 解析 schedule_value：interval 用 {value, unit}，cron 用字符串。
    // 指标规则的 "60 seconds" 不在这个正则里（服务端强制，界面上也不显示），
    // 所以只对日志规则解析。
    let sv = data.schedule_value || ''
    if (ruleType === 'logs' && data.schedule_type === 'interval') {
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

    // Parse actions for alert template + severity + telegram
    let alertTemplate = ''
    let alertTitleTemplate = ''
    let severity = 'medium'
    let severityConditions = []
    let tgBotToken = ''
    let tgChatId = ''
    let tgTitleTemplate = ''
    let tgTemplate = ''
    let tgTokenSet = false
    if (data.actions && data.actions.length) {
      for (const act of data.actions) {
        if (act.type === 'create_alert') {
          alertTemplate = act.template || ''
          alertTitleTemplate = act.title_template || ''
          severity = act.severity || 'medium'
          severityConditions = act.severity_conditions || []
        }
        if (act.type === 'telegram') {
          // 服务端已脱敏：只会回传 bot_token_set，不会回传明文 token
          tgBotToken = ''
          tgChatId = act.chat_id || ''
          tgTitleTemplate = act.title_template || ''
          tgTemplate = act.template || ''
          tgTokenSet = !!act.bot_token_set
        }
      }
    }

    ruleForm.value = {
      name: data.name || '',
      description: data.description || '',
      rule_type: ruleType,
      metric: {
        promql: data.metric?.promql || '',
        operator: data.metric?.operator || '>',
        threshold: data.metric?.threshold ?? 80,
        sustain_minutes: data.metric?.sustain_minutes ?? 5
      },
      schedule_type: data.schedule_type || 'once',
      schedule_value: ruleType === 'logs' && data.schedule_type === 'cron' ? sv : '',
      stages: ruleType === 'metric' ? [] : (data.stages || []).map(backendStageToFrontend),
      outputMapping: ruleType === 'metric' ? {} : outputMapping,
      actionTable: 'addresses',
      alertTemplate,
      alertTitleTemplate,
      severity,
      severityConditions,
      tgBotToken,
      tgChatId,
      tgTitleTemplate,
      tgTemplate,
      tgTokenSet
    }
    writeMysqlEnabled.value = !!(data.actions && data.actions.some(a => a.type === 'write_mysql'))
    createAlertEnabled.value = !!(data.actions && data.actions.some(a => a.type === 'create_alert'))
    telegramEnabled.value = !!(data.actions && data.actions.some(a => a.type === 'telegram'))
    stageFieldsCache.value = {}
    promqlResult.value = null
    // 指标规则不查 ES，别去拉索引列表和字段
    if (ruleType === 'logs') {
      await loadEsIndices()
      for (const stage of ruleForm.value.stages) {
        if (stage.index) await loadIndexFields(stage.index)
      }
    }
    dialogVisible.value = true
    refreshPreview()
  } catch (e) {}
}

// 连通性测试：用当前表单凭据发一条，不落库
const testTelegram = async () => {
  tgTesting.value = true
  try {
    await rulesApi.telegramTest({
      bot_token: ruleForm.value.tgBotToken,
      chat_id: ruleForm.value.tgChatId,
      // 编辑时 token 留空则让服务端用已保存的那把
      rule_id: isEdit.value ? editId.value : null
    })
    ElMessage.success('测试消息已发送，请查看 Telegram')
  } catch (e) {
    // 拦截器已把业务错误转成 reject
    ElMessage.error(e.message || '测试失败')
  } finally {
    tgTesting.value = false
  }
}

// PromQL 连通性测试：立即查一次，只读（不推进持续计时）
const testPromql = async () => {
  const promql = (ruleForm.value.metric?.promql || '').trim()
  if (!promql) {
    ElMessage.warning('请先填写 PromQL 表达式')
    return
  }
  promqlTesting.value = true
  promqlResult.value = null
  try {
    const res = await rulesApi.promqlTest({ promql })
    promqlResult.value = res.data || { total: 0, series: [] }
    ElMessage.success(`查询成功，命中 ${promqlResult.value.total} 条序列`)
  } catch (e) {
    // 拦截器已经弹过错误了，这里只把文案留在结果区供对照
    promqlResult.value = { error: e.message || '查询失败' }
  } finally {
    promqlTesting.value = false
  }
}

// 提交规则
const submitRule = async () => {
  try {
    await ruleFormRef.value.validate()
    saveLoading.value = true

    const asMetric = isMetric.value

    if (asMetric) {
      const m = ruleForm.value.metric || {}
      if (!(m.promql || '').trim()) {
        ElMessage.error('请填写 PromQL 表达式')
        return
      }
      if (!(m.sustain_minutes >= 1)) {
        ElMessage.error('持续时长至少 1 分钟')
        return
      }
    }

    // 构建提交数据（指标规则不查 ES，阶段/映射一律空）
    const stages = asMetric ? [] : ruleForm.value.stages.map(buildStageParams)

    // 构建输出映射
    const outputMapping = {}
    if (!asMetric) {
      for (const key in ruleForm.value.outputMapping) {
        const m = ruleForm.value.outputMapping[key]
        if (m.outputField && m.fromStage && m.sourceField) {
          outputMapping[m.outputField] = {
            from_stage: m.fromStage,
            field: m.sourceField
          }
        }
      }
    }

    // schedule_value：interval 时拼接为字符串。
    // 指标规则由服务端强制成 interval/60 seconds，这里也如实送上去保持一致。
    let scheduleType = ruleForm.value.schedule_type
    let scheduleValue = ruleForm.value.schedule_value
    if (asMetric) {
      scheduleType = 'interval'
      scheduleValue = '60 seconds'
    } else if (scheduleType === 'interval') {
      scheduleValue = `${scheduleValueObj.value} ${scheduleValueObj.unit}`
    }

    // 提交前再校验一次。预览那条路是实时的，但用户可能在红字的情况下硬存 ——
    // 后端也会拒（400），这里先拦一层给个更早的反馈。
    if (!asMetric && scheduleType !== 'once') {
      const pv = await schedulePreview(scheduleType, scheduleValue, 1).catch(() => null)
      const d = pv?.data
      if (d && d.valid === false) {
        ElMessage.error(d.error || '调度参数不合法')
        saveLoading.value = false
        return
      }
    }

    const payload = {
      name: ruleForm.value.name,
      description: ruleForm.value.description,
      source_type: asMetric ? 'metric' : 'logs',
      schedule_type: scheduleType,
      schedule_value: scheduleValue,
      stages,
      output_mapping: outputMapping,
      es_index: asMetric ? '' : ruleForm.value.es_index,
      actions: []
    }
    if (asMetric) {
      payload.metric = {
        promql: ruleForm.value.metric.promql.trim(),
        operator: ruleForm.value.metric.operator,
        threshold: ruleForm.value.metric.threshold,
        sustain_minutes: ruleForm.value.metric.sustain_minutes
      }
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

    if (telegramEnabled.value) {
      const tgAction = {
        type: 'telegram',
        chat_id: ruleForm.value.tgChatId,
        severity: ruleForm.value.severity || 'medium'
      }
      // 留空 = 保持原值（服务端 _merge_telegram_secret 处理），所以这里总是上送字段
      tgAction.bot_token = ruleForm.value.tgBotToken
      if (ruleForm.value.tgTemplate) tgAction.template = ruleForm.value.tgTemplate
      if (ruleForm.value.tgTitleTemplate) tgAction.title_template = ruleForm.value.tgTitleTemplate
      payload.actions.push(tgAction)
    }

    if (isEdit.value) {
      await updateRule(editId.value, payload)
      ElMessage.success('规则更新成功')
    } else {
      await createRule(payload)
      ElMessage.success('规则创建成功')
    }
    dialogVisible.value = false
    emit('saved')
  } catch (e) {
    if (e.message) ElMessage.error(e.message)
  } finally {
    saveLoading.value = false
  }
}

defineExpose({ openCreate, openEdit })
</script>

<style lang="scss" scoped>
.rule-dialog :deep(.el-dialog__body) { padding: 12px 24px 8px; max-height: 70vh; overflow-y: auto; }

.stages-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 8px;
}

.output-mapping-area {
  background: var(--el-fill-color-light);
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
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 12px 16px;
}

.action-config {
  margin-top: 12px;
  background: var(--el-bg-color);
  border-radius: 6px;
  padding: 8px;
}

.tg-hint {
  margin: 4px 0 0 80px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-secondary);
}

.metric-area {
  background: var(--el-fill-color-light);
  border-radius: 8px;
  padding: 12px 16px;
}

.metric-fixed-schedule {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.metric-hint {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--el-text-color-secondary);
}

// PromQL 片段用代码色，和巡检指标页的 .promql-code 同一套 token
.metric-hint .promql-code,
.promql-code {
  display: inline-block;
  padding: 0 6px;
  margin: 0 2px;
  border-radius: 4px;
  font-family: var(--el-font-family-mono, monospace);
  font-size: 12px;
  background: var(--code-inline-bg);
  color: var(--code-inline-fg);
}

.metric-promql :deep(textarea) {
  font-family: var(--el-font-family-mono, monospace);
  font-size: 12px;
}

.promql-result {
  margin-left: 100px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--el-bg-color);
  font-size: 12px;
  line-height: 1.8;
  color: var(--el-color-success);

  &.is-error { color: var(--el-color-danger); }

  .promql-series {
    font-family: var(--el-font-family-mono, monospace);
    color: var(--el-text-color-regular);
  }
}

.schedule-preview {
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-secondary);

  &.is-error { color: var(--el-color-danger); }
  .preview-ok { color: var(--el-color-success); }
  .preview-error { color: var(--el-color-danger); }
  .preview-run {
    font-family: var(--el-font-family-mono, monospace);
    color: var(--el-text-color-regular);
  }
}
</style>
