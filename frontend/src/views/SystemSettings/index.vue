<template>
  <div class="page-container">

    <!-- ══ 用户管理 ══ -->
    <UserPanel v-if="activeNav === 'users'" />

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
import UserPanel from './components/UserPanel.vue'
import ConnectionPanel from './components/ConnectionPanel.vue'
import SecurityPanel from './components/SecurityPanel.vue'
import LogsPanel from './components/LogsPanel.vue'

const route = useRoute()

const { loadUsers, loadConfig, loadLogs } = useSystemSettings()

// ── 导航 ──
const validTabs = ['users', 'connection', 'security', 'logs']
const activeNav = computed(() => {
  const seg = route.path.split('/').pop()
  return validTabs.includes(seg) ? seg : 'users'
})

onMounted(() => { loadUsers(); loadConfig(); loadLogs() })
</script>

<style lang="scss" scoped>
.page-container { }
</style>
