import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useUserStore = defineStore('user', () => {
  // Support both flat { role } and nested { user: { role } } formats
  const _raw = JSON.parse(localStorage.getItem('userInfo') || '{}')
  // If role is nested under 'user', extract it for compatibility
  const _normalized = _raw.user && _raw.user.role ? _raw.user : _raw

  const token = ref(localStorage.getItem('token') || '')
  const userInfo = ref(_normalized)

  const isLoggedIn = computed(() => !!token.value)
  // Support both flat and nested role
  const isAdmin = computed(() => {
    const u = userInfo.value || {}
    return u.role === 'admin' || (u.user && u.user.role === 'admin')
  })

  // If there's a token but no role, fetch fresh userInfo
  if (token.value && !isAdmin.value) {
    import('@/api/request').then(({ default: request }) => {
      request.get('/auth/me').then(res => {
        if (res.data) {
          const info = res.data.user ? res.data.user : res.data
          userInfo.value = info
          localStorage.setItem('userInfo', JSON.stringify(info))
        }
      }).catch(() => {})
    })
  }

  function setAuth(t, info) {
    token.value = t
    // Normalize: support both flat and nested user object
    const normalized = (info && info.user && info.user.role) ? info.user : info
    userInfo.value = normalized
    localStorage.setItem('token', t)
    localStorage.setItem('userInfo', JSON.stringify(normalized))
  }

  function clearAuth() {
    token.value = ''
    userInfo.value = {}
    localStorage.removeItem('token')
    localStorage.removeItem('userInfo')
  }

  return { token, userInfo, isLoggedIn, isAdmin, setAuth, clearAuth }
})
