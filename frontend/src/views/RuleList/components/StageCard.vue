<template>
  <div class="stage-card">
    <div class="stage-header">
      <div class="stage-title">
        <el-tag type="primary" size="large">阶段 {{ stageIdx + 1 }}</el-tag>
        <el-input v-model="stage.name" placeholder="阶段名称（可选）" style="width:200px;margin-left:8px" />
      </div>
      <el-button type="danger" :icon="Delete" circle size="small" @click="emit('remove')" />
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
        <filter-tree
          v-model="stage.filters"
          :fields="getStageFields(stage)"
        />
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
                <el-option v-for="(s, i) in priorStages" :key="s.id" :label="`阶段${i+1}: ${s.name || s.index}`" :value="s.id" />
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
      <el-button type="primary" size="small" @click="emit('preview')">预览此阶段</el-button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import FilterTree from '@/components/FilterTree.vue'
import { useRules } from '../composables/useRules'

const props = defineProps({
  stage: { type: Object, required: true },
  stageIdx: { type: Number, required: true },
  stages: { type: Array, required: true },
  esIndices: { type: Array, default: () => [] }
})

const emit = defineEmits(['remove', 'preview'])

const { getStageFields, onStageIndexChange } = useRules()

const priorStages = computed(() => props.stages.slice(0, props.stageIdx))
</script>

<style lang="scss" scoped>
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
</style>
