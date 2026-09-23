<template>
  <div class="login-container">
    <el-card class="login-card" shadow="always">
      <div class="login-header">
        <h2 class="login-title">安全巡检平台</h2>
        <p class="login-subtitle">Security Dashboard</p>
      </div>

      <el-form
        ref="loginFormRef"
        :model="loginForm"
        :rules="loginRules"
        size="large"
        @keyup.enter="handleLogin"
      >
        <el-form-item prop="username">
          <el-input
            v-model="loginForm.username"
            placeholder="用户名"
            :prefix-icon="User"
            clearable
          />
        </el-form-item>

        <el-form-item prop="password">
          <el-input
            v-model="loginForm.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            show-password
            clearable
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            class="login-btn"
            :loading="loading"
            @click="handleLogin"
          >
            登 录
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-tip">首次登录后请修改默认密码</div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { User, Lock } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import request from '@/api/request'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const loginFormRef = ref()
const loading = ref(false)

const loginForm = reactive({
  username: '',
  password: ''
})

const loginRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const handleLogin = async () => {
  if (!loginFormRef.value) return
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const res = await request.post('/auth/login', {
        username: loginForm.username,
        password: loginForm.password
      })
      // 统一响应体 {code:200, data:{token, refresh_token, user}}；cookie 已由后端写入
      const { token, refresh_token: refreshToken, user } = res.data || {}
      if (user) {
        userStore.setAuth(token || '', refreshToken, user)
        router.push('/dashboard')
      } else {
        throw new Error('登录失败：未获取到用户信息')
      }
    } catch (err) {
      console.error('[login error]', err)
      // 拦截器已对 HTTP 业务错误弹窗（含 429 的 detail）；这里只兜底非 HTTP 错误
      if (!err.response) {
        const msg = err.message || '登录失败'
        import('element-plus').then(({ ElMessage }) => ElMessage.error(msg))
      }
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0a0a1a 0%, #1a1a3a 100%);
}

.login-card {
  width: 380px;
  padding: 20px 30px;
  border-radius: 12px;
}

.login-header {
  text-align: center;
  margin-bottom: 28px;
}

.login-title {
  font-size: 22px;
  color: var(--el-text-color-primary);
  margin: 0 0 6px;
  font-weight: 600;
}

.login-subtitle {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin: 0;
  letter-spacing: 1px;
}

.login-btn {
  width: 100%;
  letter-spacing: 4px;
}

.login-tip {
  text-align: center;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 10px;
}
</style>
