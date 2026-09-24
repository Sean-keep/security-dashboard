<template>
  <div class="page-container">

    <!-- ══ 用户管理 ══ -->
    <UserPanel v-if="activeNav === 'users'" />

    <!-- ══ 权限管理（三权分立） ══ -->
    <PermissionPanel v-if="activeNav === 'permissions'" />

    <!-- ══ 界面管理 ══ -->
    <UiPanel v-if="activeNav === 'ui'" />

    <!-- ══ 连接设置（预览列表模式） ══ -->
    <ConnectionPanel v-if="activeNav === 'connection'" />

    <!-- ══ 安全设置 ══ -->
    <SecurityPanel v-if="activeNav === 'security'" />

    <!-- ══ 登录日志 ══ -->
    <LogsPanel v-if="activeNav === 'logs'" />

  </div><!-- /page-container -->
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useSystemSettings } from './composables/useSystemSettings'
import { useUserStore } from '@/store/user'
import UserPanel from './components/UserPanel.vue'
import PermissionPanel from './components/PermissionPanel.vue'
import UiPanel from './components/UiPanel.vue'
import ConnectionPanel from './components/ConnectionPanel.vue'
import SecurityPanel from './components/SecurityPanel.vue'
import LogsPanel from './components/LogsPanel.vue'

const route = useRoute()
const userStore = useUserStore()

const { loadUsers, loadConfig, loadLogs } = useSystemSettings()

// ── 导航 ──
const validTabs = ['users', 'permissions', 'ui', 'connection', 'security', 'logs']
const activeNav = computed(() => {
  const seg = route.path.split('/').pop()
  return validTabs.includes(seg) ? seg : 'users'
})

onMounted(() => {
  // 审计日志是审计管理员独占的 —— 其他人打了也是 403，不如一开始就不打
  if (userStore.hasPerm('manage_accounts', 'manage_authz')) loadUsers()
  if (userStore.hasPerm('manage_system') || activeNav.value === 'ui') loadConfig()
  if (userStore.hasPerm('audit')) loadLogs()
})
</script>

<style lang="scss" scoped>
.page-container { }
</style>
