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
      <RuleTable
        :table-data="tableData"
        :total="total"
        :pagination="pagination"
        @edit="openEdit"
        @preview="runPreview"
        @execute="executeRule"
        @log="openExecutionLog"
        @delete="confirmDelete"
        @toggle="toggleEnabled"
        @load="loadData"
      />
    </el-card>

    <!-- 规则编辑弹窗（多阶段可视化） -->
    <RuleFormDialog ref="formDialogRef" @saved="loadData" />

    <!-- 执行结果 -->
    <ExecResultDialog v-model="executeDialogVisible" :result="executeResult" />

    <!-- 预览弹窗 -->
    <EsPreviewDialog
      v-model="previewDialogVisible"
      :loading="previewLoading"
      :data="previewData"
      :columns="previewColumns"
    />

    <!-- 执行记录弹窗 -->
    <ExecLogDialog ref="execLogRef" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import RuleTable from './components/RuleTable.vue'
import RuleFormDialog from './components/RuleFormDialog.vue'
import EsPreviewDialog from './components/EsPreviewDialog.vue'
import ExecResultDialog from './components/ExecResultDialog.vue'
import ExecLogDialog from './components/ExecLogDialog.vue'
import { useRules } from './composables/useRules'

const {
  tableData,
  total,
  filterForm,
  pagination,
  previewDialogVisible,
  previewLoading,
  previewData,
  previewColumns,
  executeDialogVisible,
  executeResult,
  loadData,
  filterChange,
  resetFilter,
  toggleEnabled,
  runPreview,
  executeRule,
  confirmDelete
} = useRules()

const formDialogRef = ref()
const execLogRef = ref()

const openCreate = () => formDialogRef.value.openCreate()
const openEdit = (row) => formDialogRef.value.openEdit(row)
const openExecutionLog = (row) => execLogRef.value.open(row)

onMounted(loadData)
</script>

<style lang="scss" scoped>
.rule-list-page { }
.page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; h2 { margin:0; font-size:18px; } }
.filter-bar { margin-bottom: 16px; }
</style>
