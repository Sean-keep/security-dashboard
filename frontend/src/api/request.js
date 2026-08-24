import axios from 'axios'
import { ElMessage } from 'element-plus'

// 确保 ElMessage 可用
const showMessage = (msg, type = 'error') => {
  if (typeof ElMessage !== 'undefined' && ElMessage[type]) {
    ElMessage[type](msg)
  } else {
    console.error('[ElMessage not available]', msg)
  }
}

const request = axios.create({
  baseURL: '/api',
  timeout: 30000
})

// 请求拦截器：注入 token
request.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers['Authorization'] = `Bearer ${token}`
  }
  return config
})

// 401/403 处理：清除登录态并跳到登录页（hash 路由）
// 注意：不能用 window.location.href = '/login' —— hash 模式下会整页重载并落到 #/ 根路由，
// 根路由无 auth 守卫会重定向回 #/dashboard，首个请求又 401，形成无限刷新死循环。
let redirecting = false
const redirectToLogin = () => {
  if (redirecting) return
  redirecting = true
  localStorage.clear()
  if (window.location.hash === '#/login') {
    // 已在登录页仍收到 401（极端情况），强制整页刷新一次兜底，跳出可能的脏状态
    window.location.reload()
  } else {
    window.location.hash = '#/login'
  }
  // 留出时间让后续并发的 401 不再重复触发
  setTimeout(() => { redirecting = false }, 1000)
}

// 响应拦截器：统一错误处理
request.interceptors.response.use(
  response => {
    const res = response.data
    // 如果是 Blob 下载（如 CSV 导出），直接返回
    if (response.config?.responseType === 'blob') {
      return res
    }
    // 后端统一返回 code: 0 表示成功，200 保留给登录等少数接口
    if (res.code !== 0 && res.code !== 200) {
      if (res.code === 401 || res.code === 403) {
        showMessage(res.msg || '登录已过期，请重新登录')
        redirectToLogin()
      } else {
        showMessage(res.msg || '请求失败')
      }
      return Promise.reject(new Error(res.msg || '请求失败'))
    }
    return res
  },
  error => {
    if (error.response?.status === 401) {
      showMessage('登录已过期')
      redirectToLogin()
    } else {
      showMessage(error.response?.data?.msg || '网络错误')
    }
    return Promise.reject(error)
  }
)

export default request
