<template>
  <!-- ══ 用户管理（三权分立） ══
       账号钥匙（manage_accounts）与授权钥匙（manage_authz）在界面上也是分开的：
       建号/删号/禁用/重置密码归系统管理员，改角色归安全管理员。两边互不越界。 -->
  <el-card shadow="never" class="mb-16">
    <template #header>
      <div class="card-header">
        <span class="card-title">用户列表</span>
        <div class="toolbar">
          <el-input
            v-model="keyword"
            placeholder="搜用户名 / 昵称"
            clearable
            size="small"
            class="search"
            @input="filterLocal"
          />
          <el-select v-model="roleFilter" clearable placeholder="全部角色" size="small" class="role-filter">
            <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
          <el-button
            type="primary"
            size="small"
            :disabled="!canManageAccounts"
            @click="openAccountDialog(null)"
          >+ 新增用户</el-button>
        </div>
      </div>
    </template>

    <el-alert v-if="!canManageAccounts && !canManageAuthz" type="info" :closable="false" class="mb-16">
      当前角色无权管理用户。系统管理员管账号，安全管理员管角色，两者互不越界。
    </el-alert>

    <el-table :data="visibleUsers" stripe size="small">
      <el-table-column prop="username" label="用户名" min-width="120" />
      <el-table-column prop="nickname" label="昵称" min-width="100" />
      <el-table-column prop="role" label="角色" width="120" align="center">
        <template #default="{ row }">
          <el-tag :type="roleTag(row.role)" size="small">{{ roleLabel(row.role) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '禁用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="login_count" label="登录次数" width="90" align="center" />
      <el-table-column prop="last_login" label="最后登录" width="180" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <div class="ops">
            <el-button
              type="primary" link size="small"
              :disabled="!canManageAccounts"
              @click="openAccountDialog(row)"
            >编辑</el-button>
            <el-button
              type="warning" link size="small"
              :disabled="!canManageAuthz || row.id === userStore.userInfo.id"
              @click="openRoleDialog(row)"
            >改角色</el-button>
            <el-button
              type="danger" link size="small"
              :disabled="!canManageAccounts || row.id === userStore.userInfo.id"
              @click="deleteUser(row)"
            >删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <div class="legend">
      <span><b>编辑</b> = 昵称 / 密码 / 启用（系统管理员）</span>
      <span><b>改角色</b> = 授权（安全管理员）</span>
    </div>
  </el-card>

  <!-- 账号资料弹窗（不含角色） -->
  <el-dialog v-model="accountDialogVisible" :title="isUserEdit ? '编辑账号' : '新增用户'" width="460px" destroy-on-close>
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
      <!-- 初始任命只在建号时出现；编辑里没有这一项，改角色走另一个弹窗 -->
      <el-form-item v-if="!isUserEdit" label="初始角色" prop="role">
        <el-select v-model="userForm.role" style="width:100%">
          <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
        </el-select>
        <div class="form-hint">建号时的任命。之后再改角色属于「授权」，归安全管理员。</div>
      </el-form-item>
      <el-form-item label="启用状态">
        <el-switch v-model="userForm.is_active" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="accountDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="userSaveLoading" @click="submitAccount">保存</el-button>
    </template>
  </el-dialog>

  <!-- 授权弹窗（只改角色） -->
  <el-dialog v-model="roleDialogVisible" title="授权 · 修改角色" width="460px" destroy-on-close>
    <div class="authz-target">
      <span class="at-label">用户</span>
      <el-tag size="small">{{ roleTarget?.nickname || roleTarget?.username }}</el-tag>
      <span class="at-arrow">→</span>
      <el-tag size="small" :type="roleTag(roleTarget?.role)">{{ roleLabel(roleTarget?.role) }}</el-tag>
    </div>

    <el-form label-width="90px" size="default" class="mt-16">
      <el-form-item label="新角色">
        <el-radio-group v-model="roleForm.role" class="role-radio">
          <el-radio v-for="r in ROLE_OPTIONS" :key="r.value" :value="r.value" border class="role-radio-item">
            <div class="rr">
              <div class="rr-title">
                <el-tag :type="roleTag(r.value)" size="small" effect="plain">{{ r.label }}</el-tag>
              </div>
              <div class="rr-desc">{{ r.description }}</div>
            </div>
          </el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <el-alert type="warning" :closable="false" class="mt-16">
      账号管理 / 授权 / 审计 三权互斥。改完后请确认「三权在任」里没有空缺 ——
      最后一个在任系统管理员不能被降权，否则没人能再建号。
    </el-alert>

    <template #footer>
      <el-button @click="roleDialogVisible = false">取消</el-button>
      <el-button type="warning" :loading="userSaveLoading" @click="submitRole">确认授权</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useSystemSettings } from '../composables/useSystemSettings'
import { ROLE_OPTIONS, roleLabel, roleTag } from '@/config/roles'

const {
  userStore,
  users,
  accountDialogVisible,
  roleDialogVisible,
  isUserEdit,
  userSaveLoading,
  userFormRef,
  userForm,
  userRules,
  roleTarget,
  roleForm,
  loadUsers,
  openAccountDialog,
  openRoleDialog,
  submitAccount,
  submitRole,
  deleteUser,
} = useSystemSettings()

const canManageAccounts = computed(() => userStore.hasPerm('manage_accounts'))
const canManageAuthz = computed(() => userStore.hasPerm('manage_authz'))

const keyword = ref('')
const roleFilter = ref('')
const visibleUsers = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return (users.value || []).filter(u => {
    if (roleFilter.value && u.role !== roleFilter.value) return false
    if (!kw) return true
    return String(u.username || '').toLowerCase().includes(kw)
        || String(u.nickname || '').toLowerCase().includes(kw)
  })
})

// 过滤是本地的 —— 用户量就那么点，不值得一次往返
const filterLocal = () => {}

watch([canManageAccounts, canManageAuthz], () => {
  if (canManageAccounts.value || canManageAuthz.value) loadUsers()
}, { immediate: true })
</script>

<style lang="scss" scoped>
.mb-16 { margin-bottom: 16px; }
.mt-16 { margin-top: 16px; }

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.card-title { font-size: 15px; font-weight: 600; color: var(--el-text-color-primary); }

.toolbar { display: flex; align-items: center; gap: 8px; }
.search { width: 180px; }
.role-filter { width: 130px; }

.ops { display: flex; align-items: center; gap: 2px; white-space: nowrap; }
.ops :deep(.el-button) { padding: 0 4px; }

.legend {
  margin-top: 10px;
  display: flex;
  gap: 18px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  b { color: var(--el-text-color-regular); }
}

.form-hint { margin-top: 2px; font-size: 12px; line-height: 1.5; color: var(--el-text-color-secondary); }

.authz-target {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.at-label { font-size: 12px; color: var(--el-text-color-secondary); }
.at-arrow { color: var(--el-text-color-placeholder); }

.role-radio {
  display: flex; flex-direction: column; gap: 8px; width: 100%;
}
.role-radio-item {
  width: 100%;
  margin-right: 0;
}
.rr-title { margin-bottom: 2px; }
.rr-desc { font-size: 12px; line-height: 1.5; color: var(--el-text-color-secondary); }
</style>
