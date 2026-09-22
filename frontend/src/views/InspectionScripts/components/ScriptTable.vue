<template>
  <el-card shadow="never" class="main-card">
    <el-table :data="scripts" border stripe>
      <el-table-column type="index" label="序号" width="70" align="center" />
      <el-table-column prop="name" label="脚本名称" min-width="180">
        <template #default="{ row }">
          <div class="script-name">
            <el-icon class="script-icon" :class="row.script_type">
              <Document />
            </el-icon>
            <span>{{ row.name }}</span>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="script_type" label="类型" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="row.script_type === 'python' ? 'success' : 'info'" size="small">
            {{ row.script_type === 'python' ? 'Python' : 'Shell' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="250" show-overflow-tooltip />
      <el-table-column label="操作" width="250" fixed="right" align="center">
        <template #default="{ row }">
          <div class="table-actions">
            <el-checkbox v-model="selectedScripts" :value="row.id">选中</el-checkbox>
            <el-button type="primary" link size="small" @click="emit('edit', row)">
              <el-icon><Edit /></el-icon> 编辑
            </el-button>
            <el-button type="danger" link size="small" @click="emit('delete', row.id)">
              <el-icon><Delete /></el-icon> 删除
            </el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- 执行选中脚本 -->
    <div v-if="selectedScripts.length > 0" class="exec-bar">
      <el-button type="success" size="large" @click="emit('run-selected')">
        <el-icon><VideoPlay /></el-icon>
        执行选中脚本 ({{ selectedScripts.length }} 个)
      </el-button>
    </div>
  </el-card>
</template>

<script setup>
import { Document, Edit, Delete, VideoPlay } from '@element-plus/icons-vue'
import { useScripts } from '../composables/useScripts'

const { scripts, selectedScripts } = useScripts()

const emit = defineEmits(['edit', 'delete', 'run-selected'])
</script>

<style scoped>
/* 主卡片 */
.main-card {
  margin-bottom: 20px;
}

.script-name {
  display: flex;
  align-items: center;
  gap: 8px;
}

.script-icon {
  font-size: 18px;
}

.script-icon.python {
  color: #3572A5;
}

.script-icon.shell {
  color: #89e051;
}

.table-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.exec-bar {
  padding: 16px;
  margin-top: 16px;
  background: #f0f9eb;
  border-radius: 8px;
  display: flex;
  justify-content: center;
}
</style>
