import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'

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
        localStorage.clear()
        router.push('/login')
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
      localStorage.clear()
      router.push('/login')
    } else {
      showMessage(error.response?.data?.msg || '网络错误')
    }
    return Promise.reject(error)
  }
)

export default request
