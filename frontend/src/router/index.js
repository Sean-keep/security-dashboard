import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken } from '@/api/token'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/Login/index.vue') },
  {
    path: '/',
    component: () => import('@/components/Layout/MainLayout.vue'),
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/Dashboard/index.vue') },
      { path: 'addresses', name: 'AddressList', component: () => import('@/views/AddressList/index.vue') },
      { path: 'alerts', name: 'AlertList', component: () => import('@/views/AlertList/index.vue') },
      { path: 'rules', name: 'RuleList', component: () => import('@/views/RuleList/index.vue') },
      { path: 'scheduler', name: 'SchedulerCenter', component: () => import('@/views/SchedulerCenter/index.vue') },
      { path: 'raw-logs', name: 'RawLogQuery', component: () => import('@/views/RawLogQuery/index.vue') },
      { path: 'settings', redirect: '/settings/users' },
      { path: 'settings/users', name: 'SettingsUsers', component: () => import('@/views/SystemSettings/index.vue') },
      { path: 'settings/permissions', name: 'SettingsPermissions', component: () => import('@/views/SystemSettings/index.vue') },
      { path: 'settings/ui', name: 'SettingsUi', component: () => import('@/views/SystemSettings/index.vue') },
      { path: 'settings/connection', name: 'SettingsConnection', component: () => import('@/views/SystemSettings/index.vue') },
      { path: 'settings/security', name: 'SettingsSecurity', component: () => import('@/views/SystemSettings/index.vue') },
      { path: 'settings/logs', name: 'SettingsLogs', component: () => import('@/views/SystemSettings/index.vue') },
      { path: 'inspection', redirect: '/inspection/scripts' },
      { path: 'inspection/scripts', name: 'InspectionScripts', component: () => import('@/views/InspectionScripts/index.vue') },
      { path: 'inspection/report', name: 'InspectionReport', component: () => import('@/views/InspectionReport/index.vue') },
      { path: 'inspection/metrics', name: 'InspectionMetrics', component: () => import('@/views/InspectionMetrics/index.vue') },
      { path: 'remote', name: 'Remote', component: () => import('@/views/Remote/index.vue') },
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 旧路由兼容：?tab= 参数 → 新路径
const SETTINGS_TAB_MAP = {
  users: 'users',
  permissions: 'permissions',
  ui: 'ui',
  connection: 'connection',
  security: 'security',
  logs: 'logs',
}
const INSPECTION_TAB_MAP = { scripts: 'scripts', traffic: 'report', metrics: 'metrics' }

router.beforeEach((to, from, next) => {
  if (to.path === '/settings' && to.query.tab) {
    const target = SETTINGS_TAB_MAP[to.query.tab]
    if (target) return next(`/settings/${target}`)
  }
  if (to.path === '/inspection' && to.query.tab) {
    const target = INSPECTION_TAB_MAP[to.query.tab]
    if (target) return next(`/inspection/${target}`)
  }
  // auth 守卫：/login 始终放行；其余路由 best-effort 检查（HttpOnly cookie 无法同步读取，
  // 真正的鉴权由 401 拦截器 + 静默刷新兜底）。无内存 token 且无缓存 userInfo 时视为未登录。
  if (to.path !== '/login') {
    const hasToken = !!getToken()
    let hasUserInfo = false
    try {
      const cached = JSON.parse(localStorage.getItem('userInfo') || '{}')
      hasUserInfo = !!(cached && (cached.id || cached.username || (cached.user && cached.user.id)))
    } catch {
      /* treat as no cached user */
    }
    if (!hasToken && !hasUserInfo) {
      return next('/login')
    }
  }
  next()
})

export default router
