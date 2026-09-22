import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken } from '@/api/token'
import Login from '@/views/Login/index.vue'
import MainLayout from '@/components/Layout/MainLayout.vue'
import Dashboard from '@/views/Dashboard/index.vue'
import AddressList from '@/views/AddressList/index.vue'
import AlertList from '@/views/AlertList/index.vue'
import RuleList from '@/views/RuleList/index.vue'
import SystemSettings from '@/views/SystemSettings/index.vue'
import InspectionScripts from '@/views/InspectionScripts/index.vue'
import InspectionReport from '@/views/InspectionReport/index.vue'
import InspectionMetrics from '@/views/InspectionMetrics/index.vue'
import Remote from '@/views/Remote/index.vue'
import RawLogQuery from '@/views/RawLogQuery/index.vue'

const routes = [
  { path: '/login', name: 'Login', component: Login },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: Dashboard },
      { path: 'addresses', name: 'AddressList', component: AddressList },
      { path: 'alerts', name: 'AlertList', component: AlertList },
      { path: 'rules', name: 'RuleList', component: RuleList },
      { path: 'raw-logs', name: 'RawLogQuery', component: RawLogQuery },
      { path: 'settings', redirect: '/settings/users' },
      { path: 'settings/users', name: 'SettingsUsers', component: SystemSettings },
      { path: 'settings/connection', name: 'SettingsConnection', component: SystemSettings },
      { path: 'settings/security', name: 'SettingsSecurity', component: SystemSettings },
      { path: 'settings/logs', name: 'SettingsLogs', component: SystemSettings },
      { path: 'inspection', redirect: '/inspection/scripts' },
      { path: 'inspection/scripts', name: 'InspectionScripts', component: InspectionScripts },
      { path: 'inspection/report', name: 'InspectionReport', component: InspectionReport },
      { path: 'inspection/metrics', name: 'InspectionMetrics', component: InspectionMetrics },
      { path: 'remote', name: 'Remote', component: Remote },
    ]
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

// 旧路由兼容：?tab= 参数 → 新路径
const SETTINGS_TAB_MAP = { users: 'users', connection: 'connection', security: 'security', logs: 'logs' }
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
