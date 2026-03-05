<template>
  <div class="min-h-screen flex items-center justify-center" style="background: var(--gradient-hero)">
    <div class="w-full max-w-md animate-in">
      <!-- Logo Header -->
      <div class="text-center mb-8">
        <div class="inline-flex w-16 h-16 rounded-2xl items-center justify-center text-white text-2xl font-bold mb-4"
             style="background: linear-gradient(135deg, #3b82f6, #a855f7); box-shadow: 0 8px 32px rgba(59,130,246,0.3)">
          AI
        </div>
        <h1 class="text-2xl font-bold" style="color: var(--text-primary)">徽远成 AI-PM</h1>
        <p class="mt-2 text-sm" style="color: var(--text-secondary)">智能项目管理系统 · 管理大盘</p>
      </div>

      <!-- Login Form -->
      <div class="rounded-2xl p-8" style="background: var(--bg-card); border: 1px solid var(--border-subtle)">
        <el-form :model="form" @submit.prevent="handleLogin" size="large">
          <el-form-item>
            <el-input v-model="form.username" placeholder="用户名 / 手机号 / 企微ID" prefix-icon="User" />
          </el-form-item>
          <el-form-item>
            <el-input v-model="form.password" type="password" placeholder="密码" prefix-icon="Lock" show-password />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" native-type="submit" :loading="loading" class="w-full"
                       style="height: 44px; font-size: 15px; border-radius: 10px; background: linear-gradient(135deg, #3b82f6, #6366f1)">
              登 录
            </el-button>
          </el-form-item>
        </el-form>
        <div class="text-center text-xs mt-2" style="color: var(--text-secondary)">
          默认密码：aipm2026
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { login as loginApi } from '../api/users'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)

const form = reactive({ username: '', password: '' })

async function handleLogin() {
  if (!form.username) {
    ElMessage.warning('请输入用户名')
    return
  }
  loading.value = true
  try {
    const res: any = await loginApi(form.username, form.password)
    const { access_token, user } = res
    authStore.login(access_token, user.name, user.role)
    ElMessage.success(`欢迎回来，${user.name}`)
    router.push('/dashboard')
  } catch (e: any) {
    const detail = e?.response?.data?.detail || '登录失败，请检查用户名和密码'
    ElMessage.error(detail)
  } finally {
    loading.value = false
  }
}
</script>

