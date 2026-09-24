import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { setToken, getToken, clearToken } from '@/api/token'
import request from '@/api/request'
import { ROLE_PERMISSIONS, roleLabel, roleTag } from '@/config/roles'

function normalizeUser(info) {
  // Support both flat { role } and nested { user: { role } } formats
  if (info && info.user && info.user.role) return info.user
  return info || {}
}

// 旧角色名 → 新角色名。后端迁移会改库，但 localStorage 里可能还缓存着旧值。
const LEGACY_ROLE = { admin: 'sys_admin' }

export const useUserStore = defineStore('user', () => {
  const _raw = JSON.parse(localStorage.getItem('userInfo') || '{}')
  const _normalized = normalizeUser(_raw)

  // token 仅存内存（src/api/token.js），绝不写 localStorage
  const token = ref(getToken())
  const userInfo = ref(_normalized)

  const isLoggedIn = computed(
    () => !!token.value || !!(userInfo.value && (userInfo.value.id || userInfo.value.username))
  )

  const role = computed(() => {
    const u = userInfo.value || {}
    const r = u.role || (u.user && u.user.role) || 'viewer'
    return ROLE_PERMISSIONS[r] ? r : (LEGACY_ROLE[r] || 'viewer')
  })

  // 以后端返回的 permissions 为准；没拿到时才退回角色表推导。
  // 显隐只是省得点出 403 —— 越权一律由后端挡。
  const perms = computed(() => {
    const u = userInfo.value || {}
    if (Array.isArray(u.permissions) && u.permissions.length) return u.permissions
    return ROLE_PERMISSIONS[role.value] || []
  })

  const hasPerm = (...names) => {
    const held = perms.value
    return names.some(n => held.includes(n))
  }

  const isAdmin = computed(() => hasPerm('manage_accounts', 'manage_authz', 'audit', 'manage_system'))
  const roleName = computed(() => roleLabel(role.value))
  const roleTagType = computed(() => roleTag(role.value))

  // token 可选（cookie-first）；refresh 仅作占位兼容，不落盘
  function setAuth(t, _refresh, info) {
    if (t) {
      setToken(t)
    } else {
      clearToken()
    }
    token.value = getToken()
    const normalized = normalizeUser(info)
    userInfo.value = normalized
    localStorage.setItem('userInfo', JSON.stringify(normalized))
  }

  function clearAuth() {
    clearToken()
    token.value = ''
    userInfo.value = {}
    localStorage.removeItem('userInfo')
  }

  async function logout() {
    // 服务端清 cookie，fire-and-forget
    try {
      request.post('/auth/logout').catch(() => {})
    } catch {
      /* ignore */
    }
    clearAuth()
  }

  // 启动时用 cookie 会话恢复用户信息
  async function fetchMe() {
    const res = await request.get('/auth/me')
    const info = res?.data
    const normalized = normalizeUser(info)
    userInfo.value = normalized
    localStorage.setItem('userInfo', JSON.stringify(normalized))
    return normalized
  }

  return {
    token, userInfo, isLoggedIn, role, perms, hasPerm,
    isAdmin, roleName, roleTagType, setAuth, clearAuth, logout, fetchMe,
  }
})
