<template>
  <div class="filter-tree">
    <!-- 初始状态：只有添加按钮 -->
    <div v-if="!modelValue.logic" class="init-buttons">
      <el-button size="small" type="primary" plain @click="initAsCondition">
        <el-icon><Plus /></el-icon> 添加条件
      </el-button>
      <el-button size="small" type="warning" plain @click="initAsGroup">
        <el-icon><FolderAdd /></el-icon> 添加条件组
      </el-button>
    </div>

    <!-- 已初始化：显示条件组 -->
    <div v-else class="condition-group" :class="`logic-${modelValue.logic}`">
      <!-- 组头部 -->
      <div class="group-header">
        <el-select
          v-model="modelValue.logic"
          size="small"
          class="logic-select"
          @change="onLogicChange"
        >
          <el-option label="且 (AND)" value="and" />
          <el-option label="或 (OR)" value="or" />
          <el-option label="非 (NOT)" value="not" />
        </el-select>

        <div class="header-actions">
          <el-button
            type="danger"
            text
            size="small"
            @click="handleDelete"
          >
            <el-icon><Delete /></el-icon>
            {{ isRoot ? '清空' : '删除此组' }}
          </el-button>
        </div>
      </div>

      <!-- 条件列表 -->
      <div class="conditions-list">
        <div
          v-for="(filter, idx) in modelValue.filters"
          :key="idx"
          class="condition-item"
        >
          <!-- 简单条件 -->
          <div v-if="filter.field !== undefined" class="condition-row">
            <el-select
              v-model="filter.field"
              placeholder="选择字段"
              filterable
              size="small"
              class="field-select"
            >
              <el-option
                v-for="(type, f) in fields"
                :key="f"
                :label="f"
                :value="f"
              >
                <span style="float: left">{{ f }}</span>
                <span style="float: right; color: #8492a6; font-size: 12px">{{ type }}</span>
              </el-option>
            </el-select>

            <el-select v-model="filter.operator" size="small" class="operator-select">
              <el-option label="等于" value="equals" />
              <el-option label="不等于" value="not_equals" />
              <el-option label="大于" value="gt" />
              <el-option label="大于等于" value="gte" />
              <el-option label="小于" value="lt" />
              <el-option label="小于等于" value="lte" />
              <el-option label="包含" value="contains" />
              <el-option label="不包含" value="not_contains" />
              <el-option label="存在" value="exists" />
              <el-option label="不存在" value="not_exists" />
            </el-select>

            <template v-if="!['exists', 'not_exists'].includes(filter.operator)">
              <el-input
                v-model="filter.value"
                placeholder="值"
                size="small"
                class="value-input"
              />
            </template>

            <el-button
              type="danger"
              :icon="Delete"
              circle
              size="small"
              @click="removeItem(idx)"
            />
          </div>

          <!-- 嵌套条件组 -->
          <div v-else class="nested-group">
            <filter-tree
              v-model="modelValue.filters[idx]"
              :fields="fields"
              :is-root="false"
              @remove="removeItem(idx)"
            />
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="!modelValue.filters?.length" class="empty-hint">
          请点击下方按钮添加条件
        </div>
      </div>

      <!-- 添加按钮 -->
      <div class="group-footer">
        <el-button size="small" type="primary" plain @click="addCondition">
          <el-icon><Plus /></el-icon> 添加条件
        </el-button>
        <el-button size="small" type="warning" plain @click="addConditionGroup">
          <el-icon><FolderAdd /></el-icon> 添加条件组
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Plus, Delete, FolderAdd } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: {
    type: Object,
    default: () => ({ logic: null, filters: [] })
  },
  fields: {
    type: Object,
    default: () => ({})
  },
  isRoot: {
    type: Boolean,
    default: true
  }
})

const emit = defineEmits(['update:modelValue', 'remove'])

const onLogicChange = (val) => {
  emit('update:modelValue', { ...props.modelValue, logic: val })
}

// 处理删除/清空
const handleDelete = () => {
  if (props.isRoot) {
    // 根节点：清空重置
    emit('update:modelValue', { logic: null, filters: [] })
  } else {
    // 嵌套节点：通知父组件删除
    emit('remove')
  }
}

// 初始化为条件
const initAsCondition = () => {
  emit('update:modelValue', {
    logic: 'and',
    filters: [{ field: '', operator: 'equals', value: '' }]
  })
}

// 初始化为条件组
const initAsGroup = () => {
  emit('update:modelValue', {
    logic: 'and',
    filters: [{ logic: 'and', filters: [] }]
  })
}

// 添加条件
const addCondition = () => {
  emit('update:modelValue', {
    ...props.modelValue,
    filters: [...props.modelValue.filters, { field: '', operator: 'equals', value: '' }]
  })
}

// 添加条件组
const addConditionGroup = () => {
  emit('update:modelValue', {
    ...props.modelValue,
    filters: [...props.modelValue.filters, { logic: 'and', filters: [] }]
  })
}

// 删除项
const removeItem = (idx) => {
  const newFilters = [...props.modelValue.filters]
  newFilters.splice(idx, 1)
  // 如果删除后为空，且是根节点，重置状态
  if (newFilters.length === 0 && props.isRoot) {
    emit('update:modelValue', { logic: null, filters: [] })
  } else {
    emit('update:modelValue', { ...props.modelValue, filters: newFilters })
  }
}
</script>

<style scoped>
.filter-tree {
  width: 100%;
}

/* 初始按钮 */
.init-buttons {
  display: flex;
  gap: 8px;
  padding: 16px;
  background: #fafafa;
  border: 2px dashed #dcdfe6;
  border-radius: 8px;
  justify-content: center;
}

/* 条件组容器 */
.condition-group {
  border: 2px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}

.condition-group.logic-and { border-color: #409eff; }
.condition-group.logic-or { border-color: #e6a23c; }
.condition-group.logic-not { border-color: #f56c6c; }

/* 组头部 */
.group-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}

.logic-and .group-header { background: #ecf5ff; border-bottom-color: #b3d8ff; }
.logic-or .group-header { background: #fdf6ec; border-bottom-color: #f5dab1; }
.logic-not .group-header { background: #fef0f0; border-bottom-color: #fbc4c4; }

.logic-select {
  width: 120px;
}

.header-actions {
  margin-left: auto;
}

/* 条件列表 */
.conditions-list {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* 条件行 */
.condition-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
}

.condition-row:hover {
  border-color: #c0c4cc;
}

.field-select { width: 180px; }
.operator-select { width: 120px; }
.value-input { flex: 1; min-width: 150px; }

/* 嵌套组 */
.nested-group {
  margin-top: 4px;
}

/* 空状态 */
.empty-hint {
  text-align: center;
  color: #c0c4cc;
  padding: 12px;
  font-size: 13px;
}

/* 底部按钮 */
.group-footer {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  background: #fafafa;
  border-top: 1px solid #ebeef5;
}

.logic-and .group-footer { background: #f0f9ff; }
.logic-or .group-footer { background: #fdf6ec; }
.logic-not .group-footer { background: #fef0f0; }
</style>
