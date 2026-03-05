<template>
  <div class="page-container">
    <div class="flex items-center justify-between mb-6 animate-in">
      <div>
        <h1 class="text-xl font-bold" style="color: var(--text-primary)">系统统计</h1>
        <p class="text-sm mt-1" style="color: var(--text-secondary)">AI 用量 · 团队汇报率 · 数据趋势</p>
      </div>
      <el-button type="primary" plain size="small" @click="fetchAll" :loading="loading">
        <el-icon class="mr-1"><Refresh /></el-icon>刷新
      </el-button>
    </div>

    <!-- ═══ Token 用量 + 团队人数 ═══ -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-5 mb-8">
      <!-- Token 仪表盘 -->
      <div class="stat-card animate-in" style="animation-delay: 0.1s">
        <div class="flex items-center gap-3 mb-4">
          <div class="w-10 h-10 rounded-lg flex items-center justify-center" style="background: rgba(168,85,247,0.15)">
            <el-icon :size="20" color="#a855f7"><Cpu /></el-icon>
          </div>
          <span class="label">今日 Token 用量</span>
        </div>
        <div class="flex items-center gap-6">
          <el-progress type="dashboard" :percentage="tokenUsage.usage_pct || 0" :width="100"
                       :color="tokenUsage.usage_pct >= 80 ? '#ef4444' : tokenUsage.usage_pct >= 50 ? '#eab308' : '#22c55e'"
                       :stroke-width="8">
            <template #default>
              <div class="text-center">
                <div class="text-lg font-bold" style="color: var(--text-primary)">{{ tokenUsage.usage_pct || 0 }}%</div>
              </div>
            </template>
          </el-progress>
          <div class="flex-1">
            <div class="flex items-center justify-between text-xs mb-2">
              <span style="color: var(--text-secondary)">已用</span>
              <span class="font-semibold" style="color: var(--text-primary)">{{ formatTokens(tokenUsage.used_tokens) }}</span>
            </div>
            <div class="flex items-center justify-between text-xs mb-2">
              <span style="color: var(--text-secondary)">限额</span>
              <span class="font-semibold" style="color: var(--text-primary)">{{ formatTokens(tokenUsage.limit_tokens) }}</span>
            </div>
            <div class="flex items-center justify-between text-xs">
              <span style="color: var(--text-secondary)">状态</span>
              <el-tag :type="tokenUsage.is_throttled ? 'danger' : 'success'" size="small" effect="dark"
                      style="border-radius: 6px">
                {{ tokenUsage.is_throttled ? '🚫 已熔断' : '✅ 正常' }}
              </el-tag>
            </div>
          </div>
        </div>
      </div>

      <!-- 团队汇报率 -->
      <div class="stat-card animate-in" style="animation-delay: 0.2s">
        <div class="flex items-center gap-3 mb-4">
          <div class="w-10 h-10 rounded-lg flex items-center justify-center" style="background: rgba(59,130,246,0.15)">
            <el-icon :size="20" color="#3b82f6"><UserFilled /></el-icon>
          </div>
          <span class="label">团队概况</span>
        </div>
        <div class="space-y-4">
          <div>
            <div class="flex justify-between text-xs mb-1">
              <span style="color: var(--text-secondary)">系统用户</span>
              <span class="font-bold text-lg" style="color: var(--text-primary)">{{ weeklyStats.total_users || 0 }} 人</span>
            </div>
          </div>
          <div>
            <div class="flex justify-between text-xs mb-1">
              <span style="color: var(--text-secondary)">今日已汇报</span>
              <span class="font-semibold" style="color: var(--text-primary)">
                {{ todayReportCount }} / {{ weeklyStats.total_users || 0 }}
              </span>
            </div>
            <el-progress :percentage="todayReportRate" :stroke-width="8"
                         :color="todayReportRate >= 80 ? '#22c55e' : todayReportRate >= 50 ? '#eab308' : '#ef4444'" />
          </div>
          <div>
            <div class="flex justify-between text-xs mb-1">
              <span style="color: var(--text-secondary)">今日均分</span>
              <span class="font-semibold" :style="{ color: scoreColor(todayAvgScore) }">{{ todayAvgScore || '-' }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 近 7 天趋势 ═══ -->
    <div class="stat-card animate-in mb-8" style="animation-delay: 0.3s">
      <div class="section-title mb-4">📈 近 7 天日报趋势</div>
      <div class="grid grid-cols-7 gap-3">
        <div v-for="day in weeklyDays" :key="day.date"
             class="text-center rounded-xl p-3 transition-all"
             :style="{
               background: day.count > 0 ? 'var(--bg-secondary)' : 'transparent',
               border: isToday(day.date) ? '2px solid #3b82f6' : '1px solid var(--border-subtle)',
             }">
          <!-- 日期 -->
          <div class="text-xs mb-2" style="color: var(--text-secondary)">
            {{ formatDay(day.date) }}
          </div>
          <!-- 提交数圆圈 -->
          <div class="mx-auto w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold mb-2"
               :style="{
                 background: day.count > 0 ? 'linear-gradient(135deg, #3b82f6, #6366f1)' : 'var(--bg-secondary)',
                 color: day.count > 0 ? 'white' : 'var(--text-secondary)',
               }">
            {{ day.count }}
          </div>
          <!-- 均分 -->
          <div class="text-xs font-semibold" :style="{ color: scoreColor(day.avg_score) }">
            {{ day.avg_score || '-' }}
          </div>
          <div class="text-xs" style="color: var(--text-secondary)">均分</div>
          <!-- 通过率 -->
          <div class="text-xs mt-1">
            <span :style="{ color: day.pass_rate >= 80 ? '#22c55e' : day.pass_rate >= 50 ? '#eab308' : '#ef4444' }">
              {{ day.count > 0 ? `${day.pass_rate}%` : '-' }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 7 天汇总统计 ═══ -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-5 animate-in" style="animation-delay: 0.4s">
      <div class="stat-card text-center">
        <div class="label mb-2">7 天总提交</div>
        <div class="text-2xl font-bold" style="color: var(--text-primary)">{{ weeklyTotal }}</div>
      </div>
      <div class="stat-card text-center">
        <div class="label mb-2">7 天均分</div>
        <div class="text-2xl font-bold" :style="{ color: scoreColor(weeklyAvg) }">{{ weeklyAvg || '-' }}</div>
      </div>
      <div class="stat-card text-center">
        <div class="label mb-2">7 天通过率</div>
        <div class="text-2xl font-bold" :style="{ color: weeklyPassRate >= 80 ? '#22c55e' : '#eab308' }">
          {{ weeklyPassRate }}%
        </div>
      </div>
      <div class="stat-card text-center">
        <div class="label mb-2">日均提交</div>
        <div class="text-2xl font-bold" style="color: var(--text-primary)">{{ dailyAvgCount }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getTokenUsage, getWeeklyStats } from '../api/dashboard'
import { Refresh, Cpu, UserFilled } from '@element-plus/icons-vue'

const loading = ref(false)
const tokenUsage = ref<any>({})
const weeklyStats = ref<any>({})
const weeklyDays = ref<any[]>([])

const todayStr = new Date().toISOString().slice(0, 10)

const todayReportCount = computed(() => {
  const d = weeklyDays.value.find(d => d.date === todayStr)
  return d?.count || 0
})
const todayReportRate = computed(() => {
  const total = weeklyStats.value.total_users || 1
  return Math.round(todayReportCount.value / total * 100)
})
const todayAvgScore = computed(() => {
  const d = weeklyDays.value.find(d => d.date === todayStr)
  return d?.avg_score || 0
})

const weeklyTotal = computed(() => weeklyDays.value.reduce((s, d) => s + d.count, 0))
const weeklyAvg = computed(() => {
  const scored = weeklyDays.value.filter(d => d.count > 0)
  if (!scored.length) return 0
  return Math.round(scored.reduce((s, d) => s + d.avg_score, 0) / scored.length)
})
const weeklyPassRate = computed(() => {
  const total = weeklyTotal.value
  if (!total) return 0
  const passed = weeklyDays.value.reduce((s, d) => s + d.pass_count, 0)
  return Math.round(passed / total * 100)
})
const dailyAvgCount = computed(() => {
  const active = weeklyDays.value.filter(d => d.count > 0).length
  if (!active) return 0
  return Math.round(weeklyTotal.value / active * 10) / 10
})

function scoreColor(score: number | null) {
  if (!score) return 'var(--text-secondary)'
  if (score >= 90) return '#22c55e'
  if (score >= 60) return '#eab308'
  return '#ef4444'
}

function formatTokens(n: number) {
  if (!n) return '0'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatDay(dateStr: string) {
  const d = new Date(dateStr + 'T00:00:00')
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function isToday(dateStr: string) {
  return dateStr === todayStr
}

async function fetchAll() {
  loading.value = true
  try {
    const [tu, ws] = await Promise.allSettled([getTokenUsage(), getWeeklyStats()])
    if (tu.status === 'fulfilled') tokenUsage.value = tu.value as any
    if (ws.status === 'fulfilled') {
      const data = ws.value as any
      weeklyStats.value = data
      weeklyDays.value = data.days || []
    }
  } finally {
    loading.value = false
  }
}

onMounted(fetchAll)
</script>
