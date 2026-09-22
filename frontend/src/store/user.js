import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { setToken, getToken, clearToken } from '@/api/token'
import request from '@/api/request'

function normalizeUser(info) {
  // Support both flat { role } and nested { user: { role } } formats
  if (info && info.user && info.user.role) return info.user
  return info || {}
}

export const useUserStore = defineStore('user', () => {
  const _raw = JSON.parse(localStorage.getItem('userInfo') || '{}')
  const _normalized = normalizeUser(_raw)

  // token 仅存内存（src/api/token.js），绝不写 localStorage
  const token = ref(getToken())
  const userInfo = ref(_normalized)

  const isLoggedIn = computed(
    () => !!token.value || !!(userInfo.value && (userInfo.value.id || userInfo.value.username))
  )
  // Support both flat and nested role
  const isAdmin = computed(() => {
    const u = userInfo.value || {}
    return u.role === 'admin' || (u.user && u.user.role === 'admin')
  })

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

  return { token, userInfo, isLoggedIn, isAdmin, setAuth, clearAuth, logout, fetchMe }
})
