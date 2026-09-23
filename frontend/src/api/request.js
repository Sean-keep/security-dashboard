import axios from 'axios'
import { ElMessage } from 'element-plus'
import { getToken, setToken, clearToken } from './token'

// 确保 ElMessage 可用
const showMessage = (msg, type = 'error') => {
  if (typeof ElMessage !== 'undefined' && ElMessage[type]) {
    ElMessage[type](msg)
  } else {
    console.error('[ElMessage not available]', msg)
  }
}

// FastAPI HTTPException bodies use `detail`; the app envelope uses `msg`.
const extractMsg = (data, fallback = '请求失败') => {
  return data?.msg || data?.detail || fallback
}

const request = axios.create({
  baseURL: '/api',
  timeout: 30000,
  withCredentials: true
})

// 请求拦截器：仅在内存中有 token 时附加 Bearer（cookie 由 withCredentials 自动携带）
request.interceptors.request.use(config => {
  const token = getToken()
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

// 401 处理：清除登录态并跳到登录页（hash 路由）
// 注意：不能用 window.location.href = '/login' —— hash 模式下会整页重载并落到 #/ 根路由，
// 根路由无 auth 守卫会重定向回 #/dashboard，首个请求又 401，形成无限刷新死循环。
let redirecting = false
const clearAuthLocal = () => {
  clearToken()
  localStorage.removeItem('userInfo')
}
const redirectToLogin = () => {
  if (redirecting) return
  redirecting = true
  clearAuthLocal()
  if (window.location.hash === '#/login') {
    // 已在登录页仍收到 401（极端情况），强制整页刷新一次兜底，跳出可能的脏状态
    window.location.reload()
  } else {
    window.location.hash = '#/login'
  }
  // 留出时间让后续并发的 401 不再重复触发
  setTimeout(() => { redirecting = false }, 1000)
}

const isAuthUrl = (url = '') =>
  typeof url === 'string' && (url.includes('/auth/refresh') || url.includes('/auth/login'))

// ── 静默刷新（401 时只尝试一次，并发共享同一个 Promise） ──
let refreshPromise = null
const silentRefresh = () => {
  if (!refreshPromise) {
    refreshPromise = axios
      .post('/api/auth/refresh', {}, { withCredentials: true, timeout: 15000 })
      .then(resp => {
        const body = resp.data
        if (body && body.code === 200) {
          if (body.data && body.data.token) {
            setToken(body.data.token)
          }
          return body
        }
        // 业务失败（code !== 200）也视为刷新失败
        const err = new Error(body?.msg || body?.detail || '登录已过期')
        err.response = resp
        throw err
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

// 401 → 尝试一次静默刷新并重放原请求；失败则跳登录（redirecting 闩锁防抖）
const handleUnauthorized = async (originalConfig, originalError) => {
  const cfg = originalConfig || {}
  // 登录/刷新本身 401，或已经重放过一次：直接跳登录
  if (isAuthUrl(cfg.url) || cfg._retry) {
    clearAuthLocal()
    redirectToLogin()
    return Promise.reject(originalError || new Error('登录已过期'))
  }
  cfg._retry = true
  try {
    await silentRefresh()
    return request(cfg)
  } catch {
    clearAuthLocal()
    redirectToLogin()
    return Promise.reject(originalError || new Error('登录已过期'))
  }
}

// 响应拦截器：统一错误处理（成功仅 code === 200）
request.interceptors.response.use(
  response => {
    const res = response.data
    // 如果是 Blob 下载（如 CSV 导出），直接返回（不走信封解包）。
    // 服务端可在 Content-Disposition 里给出文件名；挂到 Blob.filename 供调用方优先使用。
    if (response.config?.responseType === 'blob') {
      try {
        const cd = response.headers?.['content-disposition'] || response.headers?.['Content-Disposition'] || ''
        const star = /filename\*\s*=\s*UTF-8''([^;]+)/i.exec(cd)
        const plain = /filename\s*=\s*"([^"]+)"|filename\s*=\s*([^;]+)/i.exec(cd)
        const raw = star?.[1] || plain?.[1] || plain?.[2]
        if (raw) {
          res.filename = decodeURIComponent(raw.trim())
        }
      } catch {
        /* header missing or malformed — fall back to client-side name */
      }
      return res
    }
    if (res && res.code === 200) {
      return res
    }
    const code = res?.code
    const msg = extractMsg(res, '请求失败')
    if (code === 401) {
      return handleUnauthorized(response.config, Object.assign(new Error(msg), { response }))
    }
    if (code === 403) {
      // 403：只提示，不强制登出
      showMessage(msg)
      return Promise.reject(new Error(msg))
    }
    if (code === 429) {
      showMessage(msg)
      return Promise.reject(new Error(msg))
    }
    showMessage(msg)
    return Promise.reject(new Error(msg))
  },
  error => {
    // 取消请求等无 response 场景
    if (!error.response) {
      showMessage(error.message || '网络错误')
      return Promise.reject(error)
    }
    const status = error.response.status
    const data = error.response.data
    const msg = extractMsg(data, '网络错误')
    if (status === 401) {
      return handleUnauthorized(error.config, error)
    }
    if (status === 403) {
      showMessage(msg)
      return Promise.reject(error)
    }
    if (status === 429) {
      showMessage(msg)
      return Promise.reject(error)
    }
    if (status >= 500) {
      showMessage(msg)
      return Promise.reject(error)
    }
    showMessage(msg)
    return Promise.reject(error)
  }
)

export default request
