<template>
  <el-dialog v-model="visible" title="规则执行记录" width="900px" top="10vh">
    <div style="margin-bottom:12px">
      <span style="font-size:14px;color:#606266">规则：<strong>{{ ruleName }}</strong></span>
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
</template>

<script setup>
import { ref } from 'vue'
import { executionLogs } from '@/api'

const visible = ref(false)
const ruleName = ref('')
const ruleId = ref(null)
const execLogList = ref([])
const execLogTotal = ref(0)
const execLogPage = ref(1)
const execLogLoading = ref(false)

const open = (row) => {
  ruleName.value = row.name
  ruleId.value = row.id
  execLogPage.value = 1
  visible.value = true
  loadExecutionLogs()
}

const loadExecutionLogs = async () => {
  execLogLoading.value = true
  try {
    const r = await executionLogs.list({ rule_id: ruleId.value, page: execLogPage.value })
    execLogList.value = r.data?.list || r.data?.items || []
    execLogTotal.value = r.data?.total || 0
  } catch (e) {
    execLogList.value = []
  } finally {
    execLogLoading.value = false
  }
}

defineExpose({ open })
</script>

<style lang="scss" scoped>
.pagination-wrap { display:flex; justify-content:flex-end; margin-top:16px; }
</style>
