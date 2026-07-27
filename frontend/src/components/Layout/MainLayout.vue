<template>
  <el-container class="main-layout">
    <!-- 左侧导航 -->
    <el-aside :width="isCollapse ? '64px' : '220px'" class="layout-aside">
      <div class="logo-area">
        <div class="logo-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="#409EFF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
        <transition name="fade">
          <span v-if="!isCollapse" class="logo-text">安全巡检平台</span>
        </transition>
      </div>

      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse"
        :collapse-transition="false"
        router
        class="sidebar-menu"
        background-color="#1a1a2e"
        text-color="#b0b0c3"
        active-text-color="#409EFF"
      >
        <!-- 一级固定菜单-->
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <template #title>仪表盘</template>
        </el-menu-item>
        <el-menu-item index="/addresses">
          <el-icon><Location /></el-icon>
          <template #title>地址列表</template>
        </el-menu-item>
        <el-menu-item index="/alerts">
          <el-icon><Bell /></el-icon>
          <template #title>告警管理</template>
        </el-menu-item>
        <el-menu-item index="/rules">
          <el-icon><Connection /></el-icon>
          <template #title>规则管理</template>
        </el-menu-item>

        <!-- 日常巡检（父级，点击后展开子项）-->
        <el-sub-menu v-if="!isCollapse" :default-active="activeMenu" :default-openeds="defaultOpeneds" :popper-class="'dark-popper'">
          <template #title>
            <el-icon><Monitor /></el-icon>
            <span>日常巡检</span>
          </template>
          <el-menu-item index="/inspection/scripts">
            <span class="sub-dot">·</span>
            <template #title>脚本执行</template>
          </el-menu-item>
          <el-menu-item index="/inspection/report">
            <span class="sub-dot">·</span>
            <template #title>巡检报告</template>
          </el-menu-item>
          <el-menu-item index="/inspection/metrics">
            <span class="sub-dot">·</span>
            <template #title>系统监控</template>
          </el-menu-item>
        </el-sub-menu>

        <!-- 折叠状态下的日常巡检 -->
        <el-menu-item v-if="isCollapse" index="/inspection/scripts">
          <el-icon><Monitor /></el-icon>
          <template #title>日常巡检</template>
        </el-menu-item>

        <!-- 系统设置（父级，点击后展开子项）-->
        <el-sub-menu v-if="!isCollapse" :default-active="activeMenu" :default-openeds="defaultOpeneds" :popper-class="'dark-popper'">
          <template #title>
            <el-icon><Tools /></el-icon>
            <span>系统设置</span>
          </template>
          <el-menu-item index="/settings/users">
            <span class="sub-dot">·</span>
            <template #title>用户管理</template>
          </el-menu-item>
          <el-menu-item index="/settings/connection">
            <span class="sub-dot">·</span>
            <template #title>连接设置</template>
          </el-menu-item>
          <el-menu-item index="/settings/security">
            <span class="sub-dot">·</span>
            <template #title>安全设置</template>
          </el-menu-item>
          <el-menu-item index="/settings/logs">
            <span class="sub-dot">·</span>
            <template #title>日志中心</template>
          </el-menu-item>
        </el-sub-menu>

        <!-- 折叠状态下的系统设置 -->
        <el-menu-item v-if="isCollapse" index="/settings/users">
          <el-icon><Tools /></el-icon>
          <template #title>系统设置</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- 右侧主内容 -->
    <el-container>
      <el-header class="layout-header">
        <div class="header-left">
          <el-button text @click="isCollapse = !isCollapse" class="collapse-btn">
            <el-icon size="20"><Fold v-if="!isCollapse" /><Expand v-else /></el-icon>
          </el-button>
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item v-if="currentParentTitle">{{ currentParentTitle }}</el-breadcrumb-item>
            <el-breadcrumb-item>{{ currentTitle }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="header-right">
          <el-dropdown @command="handleUserCommand">
            <span class="user-info">
              <el-avatar :size="32" style="background:#409EFF">
                {{ userStore.userInfo.nickname?.[0] || 'A' }}
              </el-avatar>
              <span class="username">{{ userStore.userInfo.nickname || userStore.userInfo.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="changePwd">修改密码</el-dropdown-item>
                <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="layout-main">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>

  <!-- 修改密码对话框 -->
  <el-dialog v-model="pwdDialogVisible" title="修改密码" width="400px" destroy-on-close>
    <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px">
      <el-form-item label="原密码" prop="old_password">
        <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入原密码" />
      </el-form-item>
      <el-form-item label="新密码" prop="new_password">
        <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="新密码（至少6位）" />
      </el-form-item>
      <el-form-item label="确认密码" prop="confirm_password">
        <el-input v-model="pwdForm.confirm_password" type="password" show-password placeholder="再输入一次" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="pwdDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="pwdLoading" @click="submitChangePwd">确认修改</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { auth } from '@/api'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const isCollapse = ref(false)

// 默认展开的一级菜单（不预展开，访问时才展开）
const defaultOpeneds = ref([])

// 当前激活的完整路由（含 query）
const activeMenu = computed(() => route.fullPath)

// 面包屑
const routeTitles = {
  '/dashboard': { parent: '', title: '仪表盘' },
  '/addresses': { parent: '', title: '地址列表' },
  '/alerts': { parent: '', title: '告警管理' },
  '/rules': { parent: '', title: '规则管理' },
  '/inspection/scripts': { parent: '日常巡检', title: '脚本执行' },
  '/inspection/report': { parent: '日常巡检', title: '巡检报告' },
  '/inspection/metrics': { parent: '日常巡检', title: '系统监控' },
  '/settings/users': { parent: '系统设置', title: '用户管理' },
  '/settings/connection': { parent: '系统设置', title: '连接设置' },
  '/settings/security': { parent: '系统设置', title: '安全设置' },
  '/settings/logs': { parent: '系统设置', title: '日志中心' },
}

const currentParentTitle = computed(() => routeTitles[route.path]?.parent || '')
const currentTitle = computed(() => routeTitles[route.path]?.title || '')

// 密码修改
const pwdDialogVisible = ref(false)
const pwdLoading = ref(false)
const pwdFormRef = ref()
const pwdForm = ref({ old_password: '', new_password: '', confirm_password: '' })

const validateConfirm = (rule, value, callback) => {
  if (value !== pwdForm.value.new_password) callback(new Error('两次密码不一致'))
  else callback()
}
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' }
  ],
  confirm_password: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    { validator: validateConfirm, trigger: 'blur' }
  ]
}

const handleUserCommand = async (cmd) => {
  if (cmd === 'logout') {
    localStorage.clear()
    router.push('/login')
  } else if (cmd === 'changePwd') {
    pwdDialogVisible.value = true
    pwdForm.value = { old_password: '', new_password: '', confirm_password: '' }
  }
}

const submitChangePwd = async () => {
  try {
    await pwdFormRef.value.validate()
    pwdLoading.value = true
    await auth.changePassword({ old_password: pwdForm.value.old_password, new_password: pwdForm.value.new_password })
    ElMessage.success('密码修改成功')
    pwdDialogVisible.value = false
  } catch (e) {} finally { pwdLoading.value = false }
}
</script>

<style lang="scss" scoped>
.main-layout { height: 100vh; overflow: hidden; }

.layout-aside {
  background: #1a1a2e;
  border-right: 1px solid #2a2a4e;
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
}

.logo-area {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 10px;
  border-bottom: 1px solid #2a2a4e;
  flex-shrink: 0;
}
.logo-icon { flex-shrink: 0; display: flex; align-items: center; }
.logo-text { font-size: 15px; font-weight: 600; color: #fff; white-space: nowrap; overflow: hidden; }

.sidebar-menu {
  border-right: none;
  flex: 1;
  background: #1a1a2e !important;
  :deep(.el-menu-item) {
    height: 46px;
    line-height: 46px;
    margin: 1px 8px;
    border-radius: 8px;
    &:hover { background: #252542 !important; }
    &.is-active { background: rgba(64,158,255,0.15) !important; color: #409EFF !important; }
  }
  :deep(.el-sub-menu) {
    .el-sub-menu__title {
      height: 46px;
      line-height: 46px;
      margin: 1px 8px;
      border-radius: 8px;
      padding: 0 20px 0 20px !important;
      &:hover { background: #252542 !important; }
    }
    &.is-active > .el-sub-menu__title {
      color: #409EFF !important;
    }
    .el-menu {
      background: transparent !important;
      .el-menu-item {
        height: 40px;
        line-height: 40px;
        margin: 1px 8px;
        padding-left: 36px !important;
        font-size: 13px;
      }
    }
  }
}

.sub-dot {
  width: 16px;
  display: inline-block;
  color: #555870;
  font-size: 18px;
  line-height: 46px;
  text-align: center;
}

.layout-header {
  background: #fff;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  height: 60px;
  flex-shrink: 0;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.collapse-btn { padding: 6px; }
.user-info {
  display: flex; align-items: center; gap: 8px; cursor: pointer;
  padding: 4px 8px; border-radius: 6px;
  &:hover { background: #f5f5f5; }
}
.username { font-size: 14px; color: #333; }

.layout-main {
  background: #f0f2f5;
  overflow-y: auto;
  padding: 20px;
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
.fade-slide-enter-active, .fade-slide-leave-active { transition: all 0.2s ease; }
.fade-slide-enter-from { opacity: 0; transform: translateX(10px); }
.fade-slide-leave-to { opacity: 0; transform: translateX(-10px); }
</style>

<style>
/* 深色弹出菜单（el-sub-menu 展开时） */
.dark-popper {
  background: #1a1a2e !important;
  border: 1px solid #2a2a4e !important;
}
.dark-popper .el-menu {
  background: transparent !important;
}
.dark-popper .el-menu-item {
  color: #b0b0c3 !important;
}
.dark-popper .el-menu-item:hover,
.dark-popper .el-menu-item.is-active {
  background: rgba(64,158,255,0.15) !important;
  color: #409EFF !important;
}
</style>
