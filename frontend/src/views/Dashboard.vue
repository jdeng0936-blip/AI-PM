<template>
  <div class="page-container">
    <!-- 页面标题 -->
    <div class="flex items-center justify-between mb-6 animate-in">
      <div>
        <h1 class="text-xl font-bold" style="color: var(--text-primary)">监控台</h1>
        <p class="text-sm mt-1" style="color: var(--text-secondary)">项目健康度实时总览 · {{ today }}</p>
      </div>
      <el-button type="primary" plain size="small" @click="fetchAll" :loading="loading">
        <el-icon class="mr-1"><Refresh /></el-icon>刷新数据
      </el-button>
      <el-button v-if="isAdmin" type="success" size="small" @click="projectCreateVisible = true">
        <el-icon class="mr-1"><Plus /></el-icon>新建项目
      </el-button>
    </div>

    <!-- 统计卡片 -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
      <div class="stat-card animate-in" style="animation-delay: 0.1s">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-10 h-10 rounded-lg flex items-center justify-center" style="background: rgba(59,130,246,0.15)">
            <el-icon :size="20" color="#3b82f6"><DataBoard /></el-icon>
          </div>
          <span class="label">活跃项目</span>
        </div>
        <div class="number">{{ overview.total ?? '-' }}</div>
        <div class="flex gap-3 mt-2 text-xs">
          <span style="color: #22c55e">🟢 {{ overview.green_count ?? 0 }}</span>
          <span style="color: #eab308">🟡 {{ overview.yellow_count ?? 0 }}</span>
          <span style="color: #ef4444">🔴 {{ overview.red_count ?? 0 }}</span>
        </div>
      </div>

      <div class="stat-card animate-in" style="animation-delay: 0.2s">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-10 h-10 rounded-lg flex items-center justify-center" style="background: rgba(168,85,247,0.15)">
            <el-icon :size="20" color="#a855f7"><Cpu /></el-icon>
          </div>
          <span class="label">今日 AI 日报</span>
        </div>
        <div class="number">{{ morningStats.total_reports ?? '-' }}</div>
        <div class="flex gap-3 mt-2 text-xs">
          <span style="color: #22c55e">✅ {{ morningStats.pass_count ?? 0 }}</span>
          <span style="color: #ef4444">❌ {{ morningStats.fail_count ?? 0 }}</span>
          <span style="color: var(--text-secondary)">均分 {{ morningStats.avg_score ?? '-' }}</span>
        </div>
      </div>

      <div class="stat-card animate-in" style="animation-delay: 0.3s">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-10 h-10 rounded-lg flex items-center justify-center" style="background: rgba(239,68,68,0.15)">
            <el-icon :size="20" color="#ef4444"><WarningFilled /></el-icon>
          </div>
          <span class="label">未汇报 / 卡点</span>
        </div>
        <div class="number" :style="{ color: (missingMembers.length + riskAlerts.length) > 0 ? '#ef4444' : undefined }">
          {{ missingMembers.length }} / {{ riskAlerts.length }}
        </div>
        <div class="text-xs mt-2" style="color: var(--text-secondary)">
          需管理层关注介入
        </div>
      </div>
    </div>

    <!-- ═══ 晨报明细（AI 日报一览）═══ -->
    <div v-if="morningReports.length" class="mb-8 animate-in" style="animation-delay: 0.35s">
      <div class="section-title">📋 AI 日报明细（{{ morningBriefingDate }}）</div>
      <div class="grid grid-cols-1 gap-3">
        <div v-for="r in morningReports" :key="r.member"
             class="stat-card flex items-start gap-4"
             style="padding: 14px 18px">
          <!-- 评分 -->
          <div class="text-center flex-shrink-0" style="min-width: 48px">
            <div class="text-2xl font-bold" :style="{ color: scoreColor(r.ai_score) }">{{ r.ai_score ?? '-' }}</div>
            <el-tag :type="r.pass_check ? 'success' : 'danger'" size="small" round
                    style="margin-top: 4px; font-size: 10px">
              {{ r.pass_check ? '合格' : '退回' }}
            </el-tag>
          </div>
          <!-- 内容 -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span class="font-semibold text-sm" style="color: var(--text-primary)">{{ r.member }}</span>
              <span class="text-xs" style="color: var(--text-secondary)">{{ r.department }}</span>
            </div>
            <div class="text-xs mb-1" style="color: var(--text-primary); line-height: 1.6">
              {{ r.tasks?.slice(0, 100) || '-' }}
            </div>
            <div class="text-xs" style="color: var(--text-secondary)">
              {{ r.ai_comment }}
            </div>
            <div v-if="r.blocker" class="text-xs mt-1" style="color: #ef4444">
              ⛔ 卡点：{{ r.blocker }}
            </div>
          </div>
          <!-- 进度 -->
          <div class="flex-shrink-0 text-right" style="min-width: 60px">
            <el-progress type="circle" :percentage="r.progress || 0" :width="44" :stroke-width="4"
                         :color="r.progress >= 80 ? '#22c55e' : r.progress >= 50 ? '#eab308' : '#ef4444'" />
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 未汇报名单 ═══ -->
    <div v-if="missingMembers.length" class="mb-8 animate-in" style="animation-delay: 0.4s">
      <div class="section-title">
        🔕 未汇报名单
        <el-tag type="warning" size="small" round>{{ missingMembers.length }}</el-tag>
      </div>
      <div class="stat-card">
        <div class="flex flex-wrap gap-3">
          <div v-for="m in missingMembers" :key="m.name"
               class="flex items-center gap-2 px-3 py-2 rounded-lg"
               style="background: var(--bg-secondary)">
            <el-avatar :size="28" style="background: linear-gradient(135deg, #94a3b8, #64748b); font-size: 12px">
              {{ m.name.charAt(0) }}
            </el-avatar>
            <div>
              <div class="text-xs font-semibold" style="color: var(--text-primary)">{{ m.name }}</div>
              <div class="text-xs" style="color: var(--text-secondary)">{{ m.department }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 项目列表 -->
    <div class="mb-8 animate-in" style="animation-delay: 0.45s">
      <div class="section-title">项目健康矩阵</div>
      <div class="grid grid-cols-1 gap-4">
        <div v-for="p in projects" :key="p.project_id"
             class="stat-card cursor-pointer flex items-center gap-5"
             @click="$router.push(`/project/${p.project_id}`)">
          <!-- 健康指示灯 -->
          <div class="w-3 h-3 rounded-full flex-shrink-0"
               :style="{ background: healthColor(p.health_status) }" />
          <!-- 项目信息 -->
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-sm" style="color: var(--text-primary)">
              {{ p.code }} · {{ p.name }}
            </div>
            <div class="text-xs mt-1" style="color: var(--text-secondary)">
              第{{ p.current_stage }}阶段「{{ p.stage_name }}」 · {{ p.track === 'dual' ? '软硬双轨' : p.track }}
            </div>
          </div>
          <!-- 健康分数 -->
          <div class="text-right flex-shrink-0">
            <div class="text-lg font-bold" :style="{ color: healthColor(p.health_status) }">
              {{ p.health_score }}
            </div>
            <div class="text-xs" style="color: var(--text-secondary)">
              距交付 {{ p.days_to_deadline }}天
            </div>
          </div>
          <el-icon color="#4b5563"><ArrowRight /></el-icon>
        </div>
      </div>
    </div>

    <!-- 风险阻碍池 -->
    <div class="animate-in" style="animation-delay: 0.5s">
      <div class="section-title">
        风险阻碍池
        <el-tag v-if="riskAlerts.length" type="danger" size="small" round>{{ riskAlerts.length }}</el-tag>
      </div>
      <div v-if="riskAlerts.length === 0" class="text-center py-12" style="color: var(--text-secondary)">
        <el-icon :size="48"><CircleCheckFilled /></el-icon>
        <p class="mt-3">暂无未解除的风险卡点 🎉</p>
      </div>
      <div v-else class="grid grid-cols-1 gap-4">
        <div v-for="alert in riskAlerts" :key="alert.id" class="risk-card flex items-start gap-4">
          <el-icon :size="20" color="#ef4444" class="mt-0.5"><WarningFilled /></el-icon>
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-sm" style="color: var(--text-primary)">{{ alert.title }}</div>
            <div class="text-xs mt-1" style="color: var(--text-secondary)">
              {{ alert.department }} · {{ alert.reporter }} · {{ alert.created_at }}
            </div>
            <div class="text-xs mt-2" style="color: var(--text-secondary)">{{ alert.description }}</div>
          </div>
          <el-button type="success" size="small" plain @click="resolveAlert(alert.id)">
            标记解决
          </el-button>
        </div>
      </div>
    </div>

    <!-- ═══ 新建项目弹窗 ═══ -->
    <el-dialog v-model="projectCreateVisible" title="新建项目" width="480px" :close-on-click-modal="false">
      <el-form label-width="80px" label-position="left">
        <el-form-item label="项目名称" required>
          <el-input v-model="projectForm.name" placeholder="例如：206样机研发及落地" />
        </el-form-item>
        <el-form-item label="项目编号" required>
          <el-input v-model="projectForm.code" placeholder="P2026-002" />
        </el-form-item>
        <el-form-item label="轨道">
          <el-select v-model="projectForm.track" style="width:100%">
            <el-option label="软硬双轨" value="dual" />
            <el-option label="纯软件" value="software" />
            <el-option label="纯硬件" value="hardware" />
          </el-select>
        </el-form-item>
        <el-form-item label="计划交付">
          <el-date-picker v-model="projectForm.planned_launch_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="预算（元）">
          <el-input-number v-model="projectForm.budget_total" :min="0" :step="10000" style="width:100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="projectCreateVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateProject" :loading="projectSubmitting"
                   style="background: linear-gradient(135deg, #3b82f6, #6366f1); border: none">立项</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { getMorningBriefing, getRiskAlerts } from '../api/dashboard'
import { getProjectsOverview, createProject } from '../api/projects'
import { Refresh, DataBoard, Cpu, WarningFilled, ArrowRight, CircleCheckFilled, Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const isAdmin = computed(() => authStore.isAdmin)

const loading = ref(false)
const today = new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })

const overview = ref<any>({})
const projects = ref<any[]>([])
const riskAlerts = ref<any[]>([])

// ── 晨报数据 ──
const morningStats = ref<any>({})
const morningReports = ref<any[]>([])
const missingMembers = ref<any[]>([])
const morningBriefingDate = ref('')

function healthColor(status: string) {
  return { green: '#22c55e', yellow: '#eab308', red: '#ef4444', locked: '#4b5563' }[status] || '#4b5563'
}

function scoreColor(score: number | null) {
  if (score == null) return 'var(--text-secondary)'
  if (score >= 90) return '#22c55e'
  if (score >= 60) return '#eab308'
  return '#ef4444'
}

async function fetchAll() {
  loading.value = true
  try {
    const [ov, br, ra] = await Promise.allSettled([
      getProjectsOverview(),
      getMorningBriefing(),
      getRiskAlerts(),
    ])
    if (ov.status === 'fulfilled') {
      const data = ov.value as any
      overview.value = data
      projects.value = data.projects || []
    }
    if (br.status === 'fulfilled') {
      const data = br.value as any
      morningStats.value = data.stats || {}
      morningReports.value = data.reports || []
      missingMembers.value = data.missing_members || []
      morningBriefingDate.value = data.report_date || ''
    }
    if (ra.status === 'fulfilled') {
      riskAlerts.value = (ra.value as any[]).filter((a: any) => a.status === 'unresolved')
    }
  } finally {
    loading.value = false
  }
}

async function resolveAlert(id: string) {
  ElMessage.success('已标记为已解决')
  riskAlerts.value = riskAlerts.value.filter(a => a.id !== id)
}

// ── 新建项目 ──
const projectCreateVisible = ref(false)
const projectSubmitting = ref(false)
const projectForm = reactive({
  name: '',
  code: '',
  track: 'dual',
  planned_launch_date: '',
  budget_total: 100000,
})

async function handleCreateProject() {
  projectSubmitting.value = true
  try {
    await createProject(projectForm)
    ElMessage.success(`项目 ${projectForm.code} 立项成功`)
    projectCreateVisible.value = false
    fetchAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '立项失败')
  } finally {
    projectSubmitting.value = false
  }
}

onMounted(fetchAll)
</script>
