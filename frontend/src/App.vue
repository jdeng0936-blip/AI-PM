<template>
  <el-config-provider :locale="zhCn" namespace="el" :size="'default'">
    <!-- 有侧边栏的布局（已登录） -->
    <div v-if="isLoggedIn && !isLoginPage" class="flex h-screen overflow-hidden">
      <!-- 侧边栏 -->
      <aside class="w-56 flex-shrink-0 flex flex-col" style="background: var(--bg-card); border-right: 1px solid var(--border-subtle)">
        <!-- Logo -->
        <div class="px-5 py-5 flex items-center gap-3" style="border-bottom: 1px solid var(--border-subtle)">
          <div class="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-sm"
               style="background: linear-gradient(135deg, #3b82f6, #a855f7)">AI</div>
          <div>
            <div class="text-sm font-semibold" style="color: var(--text-primary)">徽远成 AI-PM</div>
            <div class="text-xs" style="color: var(--text-secondary)">智能项目管理</div>
          </div>
        </div>

        <!-- 导航菜单 -->
        <el-menu
          :default-active="$route.path"
          :router="true"
          background-color="transparent"
          text-color="#94a3b8"
          active-text-color="#3b82f6"
          class="flex-1 border-0 pt-2"
        >
          <el-menu-item index="/dashboard">
            <el-icon><Monitor /></el-icon>
            <template #title>
              <span class="flex items-center justify-between flex-1">
                监控台
                <el-badge v-if="alertCount > 0" :value="alertCount" :max="9" class="badge-small" />
              </span>
            </template>
          </el-menu-item>
          <el-menu-item :index="`/project/${defaultProjectId}`">
            <el-icon><DataBoard /></el-icon>
            <span>IPD 看板</span>
          </el-menu-item>
          <el-menu-item index="/reports">
            <el-icon><Document /></el-icon>
            <template #title>
              <span class="flex items-center justify-between flex-1">
                AI 日报流
                <el-badge v-if="failCount > 0" :value="failCount" :max="9" type="danger" class="badge-small" />
              </span>
            </template>
          </el-menu-item>
          <el-menu-item v-if="isAdmin" index="/users">
            <el-icon><UserFilled /></el-icon>
            <span>用户管理</span>
          </el-menu-item>
          <el-menu-item v-if="isAdmin" index="/stats">
            <el-icon><TrendCharts /></el-icon>
            <span>系统统计</span>
          </el-menu-item>
          <el-menu-item v-if="isAdmin" index="/simulate">
            <el-icon><MagicStick /></el-icon>
            <span>模拟提交</span>
          </el-menu-item>
        </el-menu>

        <!-- 底部用户区 -->
        <div class="px-4 py-4 flex items-center gap-3" style="border-top: 1px solid var(--border-subtle)">
          <el-avatar :size="32" style="background: linear-gradient(135deg, #22c55e, #16a34a)">
            {{ userName.charAt(0) }}
          </el-avatar>
          <div class="flex-1 min-w-0">
            <div class="text-xs truncate" style="color: var(--text-primary)">{{ userName }}</div>
            <div class="text-xs" style="color: var(--text-secondary)">{{ roleName }}</div>
          </div>
          <el-button text size="small" @click="handleLogout">
            <el-icon><SwitchButton /></el-icon>
          </el-button>
        </div>
      </aside>

      <!-- 主内容区 -->
      <main class="flex-1 overflow-y-auto" style="background: var(--bg-primary)">
        <router-view />
      </main>
    </div>

    <!-- 登录页（无侧边栏） -->
    <router-view v-else />
  </el-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { useNotifications } from './composables/useNotifications'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { Monitor, DataBoard, Document, SwitchButton, UserFilled, TrendCharts, MagicStick } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { alertCount, failCount } = useNotifications()

const isLoggedIn = computed(() => authStore.isLoggedIn)
const userName = computed(() => authStore.userName || '管理员')
const isLoginPage = computed(() => route.path === '/login')
const isAdmin = computed(() => authStore.isAdmin)
const roleName = computed(() => {
  const m: Record<string, string> = { admin: '管理员', manager: '经理', employee: '员工' }
  return m[authStore.userRole] || '员工'
})

// 默认项目 ID（从 Step 2 测试结果获取）
const defaultProjectId = '6d71f8fa-7c55-421f-b45a-d5589f9df65a'

function handleLogout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style>
.badge-small .el-badge__content {
  font-size: 10px !important;
  height: 16px !important;
  line-height: 16px !important;
  padding: 0 4px !important;
}
</style>
