<template>
  <div class="address-list-page">
    <div class="page-header">
      <h2>攻击地址列表</h2>
      <el-button type="primary" :icon="Plus" @click="openCreate">新增地址</el-button>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-bar">
      <el-form :inline="true" :model="filterForm" size="default">
        <el-form-item label="关键词">
          <el-input v-model="filterForm.keyword" placeholder="IP/域名" clearable style="width:180px" @change="filterChange" />
        </el-form-item>
        <el-form-item label="时间范围">
          <el-select v-model="timePreset" size="default" style="width:145px" @change="onTimePresetChange">
            <el-option label="最近 1 小时" value="1h" />
            <el-option label="最近 6 小时" value="6h" />
            <el-option label="今日" value="today" />
            <el-option label="最近 1 天" value="1d" />
            <el-option label="最近 7 天" value="7d" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="filterChange">筛选</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 表格 -->
    <AddressTable
      :table-data="tableData"
      :total="total"
      :pagination="pagination"
      :multiple-selection="multipleSelection"
      :country-loading-map="countryLoadingMap"
      @selection-change="onSelectionChange"
      @sort-change="onSortChange"
      @block-one="blockOne"
      @open-edit="openEdit"
      @confirm-delete="confirmDelete"
      @open-block-config="openBlockConfig"
      @block-selected="blockSelected"
      @batch-lookup-country="batchLookupCountry"
      @export-csv="exportCsv"
      @batch-delete="batchDelete"
      @load="loadData"
    />

    <!-- 新增/编辑对话框 -->
    <AddressFormDialog />

    <!-- 配置封堵参数 -->
    <BlockConfigPanel />

    <!-- 封禁执行结果 -->
    <BlockRunDialog />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useAddresses } from './composables/useAddresses'
import AddressTable from './components/AddressTable.vue'
import AddressFormDialog from './components/AddressFormDialog.vue'
import BlockConfigPanel from './components/BlockConfigPanel.vue'
import BlockRunDialog from './components/BlockRunDialog.vue'

const {
  tableData,
  total,
  pagination,
  multipleSelection,
  countryLoadingMap,
  filterForm,
  timePreset,
  filterChange,
  onTimePresetChange,
  resetFilter,
  onSelectionChange,
  onSortChange,
  openCreate,
  openEdit,
  confirmDelete,
  blockOne,
  blockSelected,
  batchLookupCountry,
  batchDelete,
  exportCsv,
  openBlockConfig,
  loadData
} = useAddresses()

onMounted(loadData)
</script>

<style lang="scss" scoped>
.address-list-page { }
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; h2 { margin: 0; font-size: 18px; } }
.filter-bar { margin-bottom: 16px; }
</style>
