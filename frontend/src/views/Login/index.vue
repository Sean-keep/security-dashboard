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

const router = useRouter()
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
      const token = res.data?.token
      const user = res.data?.user
      if (token) {
        localStorage.setItem('token', token)
        if (user) localStorage.setItem('userInfo', JSON.stringify(user))
        router.push('/dashboard')
      } else {
        throw new Error('登录失败：未获取到 token')
      }
    } catch (err) {
      console.error('[login error]', err)
      const msg = err.response?.data?.msg || err.message || '登录失败'
      // Element Plus 已全局注册，ElMessage 可直接使用
      import('element-plus').then(({ ElMessage }) => ElMessage.error(msg))
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
  color: #303133;
  margin: 0 0 6px;
  font-weight: 600;
}

.login-subtitle {
  font-size: 13px;
  color: #909399;
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
  color: #c0c4cc;
  margin-top: 10px;
}
</style>
