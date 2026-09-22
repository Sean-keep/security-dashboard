<template>
  <!-- ══ 登录日志 ══ -->
  <el-card shadow="never" class="mb-16">
    <template #header>
      <div class="card-header">
        <span class="card-title">日志中心</span>
        <div class="header-right">
          <el-select v-model="logTypeFilter" size="small" style="width:130px" @change="logPage=1;loadLogs()">
            <el-option label="全部日志" value="" />
            <el-option label="登录日志" value="login" />
            <el-option label="操作日志" value="operation" />
          </el-select>
        </div>
      </div>
    </template>
    <el-table :data="logList" stripe size="small">
      <el-table-column prop="created_at" label="时间" width="170" />
      <el-table-column prop="log_type" label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.log_type === 'login' ? 'primary' : 'warning'" size="small">
            {{ row.log_type === 'login' ? '登录' : '操作' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="username" label="用户名" width="120" />
      <el-table-column prop="action" label="操作" min-width="180" show-overflow-tooltip />
      <el-table-column prop="target" label="对象" width="150" show-overflow-tooltip />
      <el-table-column prop="ip_address" label="IP地址" width="140" />
      <el-table-column prop="status" label="结果" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'success' ? 'success' : 'danger'" size="small">
            {{ row.status === 'success' ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="detail" label="详情" min-width="160" show-overflow-tooltip />
    </el-table>
    <div class="pagination-wrap">
      <el-pagination
        v-model:current-page="logPage"
        :page-size="20"
        :total="logTotal"
        layout="total, prev, pager, next"
        @current-change="loadLogs"
      />
    </div>
  </el-card>
</template>

<script setup>
import { useSystemSettings } from '../composables/useSystemSettings'

const {
  logList,
  logTotal,
  logPage,
  logTypeFilter,
  loadLogs
} = useSystemSettings()
</script>

<style lang="scss" scoped>
.mb-16 { margin-bottom: 16px; }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
