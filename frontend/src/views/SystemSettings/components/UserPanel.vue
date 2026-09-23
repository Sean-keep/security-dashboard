<template>
  <!-- ══ 用户管理 ══ -->
  <el-card shadow="never" class="mb-16">
      <template #header>
        <div class="card-header">
          <span class="card-title">用户列表</span>
          <el-button type="primary" size="small" @click="openUserDialog(null)" :disabled="!userStore.isAdmin">
            + 新增用户
          </el-button>
        </div>
      </template>
      <el-table :data="users" stripe size="small">
        <el-table-column prop="username" label="用户名" min-width="120" />
        <el-table-column prop="nickname" label="昵称" min-width="100" />
        <el-table-column prop="role" label="角色" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'primary'" size="small">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="login_count" label="登录次数" width="90" align="center" />
        <el-table-column prop="last_login" label="最后登录" width="160" />
        <el-table-column prop="created_at" label="创建时间" width="160" />
        <el-table-column label="操作" width="130" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="openUserDialog(row)">编辑</el-button>
            <el-button type="danger" link size="small"
              :disabled="row.id === userStore.userInfo.id || !userStore.isAdmin"
              @click="deleteUser(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 用户编辑弹窗 -->
    <el-dialog v-model="userDialogVisible" :title="isUserEdit ? '编辑用户' : '新增用户'" width="460px" destroy-on-close>
      <el-form ref="userFormRef" :model="userForm" :rules="userRules" label-width="90px" size="default">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="userForm.username" :disabled="isUserEdit" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item :label="isUserEdit ? '新密码' : '密码'" :prop="isUserEdit ? '' : 'password'">
          <el-input v-model="userForm.password" type="password" show-password :placeholder="isUserEdit ? '留空则不修改' : '请输入密码'" />
        </el-form-item>
        <el-form-item label="昵称" prop="nickname">
          <el-input v-model="userForm.nickname" placeholder="显示名称" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="userForm.role" style="width:100%">
            <el-option label="管理员" value="admin" />
            <el-option label="操作员" value="operator" />
            <el-option label="查看者" value="viewer" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="userForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="userDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="userSaveLoading" @click="submitUser">保存</el-button>
      </template>
    </el-dialog>
</template>

<script setup>
import { useSystemSettings } from '../composables/useSystemSettings'

const {
  userStore,
  users,
  userDialogVisible,
  isUserEdit,
  userSaveLoading,
  userFormRef,
  userForm,
  userRules,
  roleLabel,
  openUserDialog,
  submitUser,
  deleteUser
} = useSystemSettings()
</script>

<style lang="scss" scoped>
.mb-16 { margin-bottom: 16px; }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
</style>
