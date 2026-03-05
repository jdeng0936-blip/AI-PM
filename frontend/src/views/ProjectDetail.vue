<template>
  <div class="page-container">
    <!-- 项目头部 -->
    <div class="flex items-center justify-between mb-6 animate-in" v-if="project">
      <div>
        <div class="flex items-center gap-3">
          <h1 class="text-xl font-bold" style="color: var(--text-primary)">{{ project.name }}</h1>
          <el-tag size="small" :type="project.health_status === 'green' ? 'success' : project.health_status === 'red' ? 'danger' : 'warning'">
            {{ project.health_status?.toUpperCase() }}
          </el-tag>
        </div>
        <p class="text-sm mt-1" style="color: var(--text-secondary)">
          {{ project.code }} · {{ project.track === 'dual' ? '软硬双轨' : project.track }} · 第{{ project.current_stage }}阶段
        </p>
      </div>
      <div class="text-right">
        <div class="text-2xl font-bold" :style="{ color: healthColor(project.health_status) }">
          {{ project.health_score }}
        </div>
        <div class="text-xs" style="color: var(--text-secondary)">健康度</div>
      </div>
    </div>

    <!-- 甘特图区域 -->
    <div class="stat-card mb-6 animate-in" style="animation-delay: 0.1s">
      <div class="section-title">IPD 生命周期甘特图</div>
      <div class="mt-4">
        <div class="gantt-row text-xs font-semibold" style="color: var(--text-secondary); border-bottom: 2px solid var(--border-subtle)">
          <div>阶段</div>
          <div class="flex justify-between px-2">
            <span>{{ timelineStart }}</span>
            <span>{{ timelineMid }}</span>
            <span>{{ timelineEnd }}</span>
          </div>
        </div>
        <div v-for="stage in ganttData" :key="stage.stage_number" class="gantt-row">
          <div class="text-xs" style="color: var(--text-primary)">
            <div class="font-semibold">{{ stage.stage_name }}</div>
            <div class="mt-0.5" style="color: var(--text-secondary)">{{ stage.planned_start }} → {{ stage.planned_end }}</div>
          </div>
          <div class="relative w-full h-8 rounded" style="background: rgba(255,255,255,0.03)">
            <div class="gantt-bar absolute top-0.5" :class="stage.health_status" :style="ganttBarStyle(stage)">
              <span class="absolute inset-0 flex items-center justify-center text-xs text-white font-semibold">
                {{ stage.progress_pct }}%
                <span v-if="stage.gate_passed" class="ml-1">✓</span>
                <span v-if="stage.health_status === 'locked'" class="ml-1">🔒</span>
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ IPD 关卡评审 ═══ -->
    <div class="stat-card mb-6 animate-in" style="animation-delay: 0.15s">
      <div class="section-title">🚪 IPD 关卡评审</div>
      <div class="mt-4">
        <!-- 4 关卡步骤条 -->
        <div class="flex items-stretch gap-3">
          <div v-for="g in gateSteps" :key="g.number"
               class="flex-1 rounded-xl p-4 transition-all relative"
               :style="gateCardStyle(g)">
            <!-- 关卡编号 -->
            <div class="flex items-center gap-2 mb-2">
              <div class="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold"
                   :style="{
                     background: g.status === 'passed' ? '#22c55e' : g.status === 'current' ? '#3b82f6' : 'var(--bg-secondary)',
                     color: g.status === 'locked' ? 'var(--text-secondary)' : 'white',
                   }">
                {{ g.status === 'passed' ? '✓' : g.number }}
              </div>
              <div class="text-xs font-semibold" style="color: var(--text-primary)">{{ g.name }}</div>
            </div>
            <!-- 已通过：评审信息 -->
            <div v-if="g.review" class="text-xs" style="color: var(--text-secondary); line-height: 1.6">
              <div>{{ g.review.reviewer }} · {{ formatDate(g.review.reviewed_at) }}</div>
              <el-tag :type="decisionType(g.review.decision)" size="small" effect="dark" style="border-radius: 6px; margin-top: 4px">
                {{ decisionLabel(g.review.decision) }}
              </el-tag>
            </div>
            <!-- 当前可评审 -->
            <div v-else-if="g.status === 'current' && isAdmin">
              <el-button type="primary" size="small" @click="openReviewDialog(g)"
                         style="margin-top: 4px; background: linear-gradient(135deg, #3b82f6, #6366f1); border: none">
                提交评审
              </el-button>
            </div>
            <!-- 未开放 -->
            <div v-else-if="g.status === 'locked'" class="text-xs" style="color: var(--text-secondary)">
              🔒 未开放
            </div>
            <!-- 连接线 -->
            <div v-if="g.number < 4" class="absolute right-0 top-1/2 w-3 h-0.5"
                 :style="{ background: g.status === 'passed' ? '#22c55e' : 'var(--border-subtle)', transform: 'translateX(100%)' }" />
          </div>
        </div>
      </div>
    </div>

    <!-- Sprint 进度 -->
    <div class="stat-card mb-6 animate-in" style="animation-delay: 0.2s">
      <div class="flex items-center justify-between">
        <div class="section-title">当前 Sprint</div>
        <el-button v-if="isAdmin" type="primary" size="small" plain @click="openCreateSprintDialog">
          <el-icon class="mr-1"><Plus /></el-icon>新建 Sprint
        </el-button>
      </div>
      <div v-if="sprints.length === 0" class="text-center py-8" style="color: var(--text-secondary)">
        暂无 Sprint 数据，点击上方按钮创建第一个 Sprint
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-5 mt-4">
        <div v-for="s in sprints" :key="s.sprint_id" class="rounded-xl p-5"
             :style="sprintCardStyle(s.status)">
          <div class="flex items-center justify-between mb-3">
            <div class="font-semibold text-sm" style="color: var(--text-primary)">Sprint #{{ s.sprint_number }}</div>
            <el-tag size="small" :type="sprintStatusType(s.status)">{{ sprintStatusLabel(s.status) }}</el-tag>
          </div>
          <div class="text-xs mb-3" style="color: var(--text-secondary)">{{ s.goal }}</div>
          <div class="flex items-center gap-3">
            <el-progress
              :percentage="s.planned_sp ? Math.round((s.completed_sp / s.planned_sp) * 100) : 0"
              :stroke-width="8"
              :color="s.velocity_pct >= 80 ? '#22c55e' : s.velocity_pct >= 50 ? '#eab308' : '#3b82f6'"
              style="flex: 1"
            />
            <span class="text-xs font-semibold whitespace-nowrap" style="color: var(--text-primary)">
              {{ s.completed_sp }} / {{ s.planned_sp }} SP
            </span>
          </div>
          <div class="flex justify-between mt-3 text-xs" style="color: var(--text-secondary)">
            <span>{{ s.start_date }} → {{ s.end_date }}</span>
            <span>健康度 {{ s.health_score }}</span>
          </div>
          <!-- 操作按钮 -->
          <div class="mt-3 flex gap-2" v-if="isAdmin">
            <el-button v-if="s.status === 'planning'" type="primary" size="small"
                       @click="handleStartSprint(s)" style="background: linear-gradient(135deg,#3b82f6,#6366f1); border:none">
              🚀 启动
            </el-button>
            <el-button v-if="s.status === 'active'" type="success" size="small"
                       @click="openCompleteDialog(s)">
              ✅ 完成
            </el-button>
          </div>
          <!-- 回顾三问 -->
          <div v-if="s.status === 'completed' && s.retrospective" class="mt-3 pt-3" style="border-top: 1px solid var(--border-subtle)">
            <div class="text-xs font-semibold mb-2" style="color: var(--text-primary)">📝 Sprint 回顾</div>
            <div v-if="s.retrospective.went_well?.length" class="text-xs mb-1">
              <span style="color: #22c55e">😊 做得好：</span>
              <span style="color: var(--text-secondary)">{{ s.retrospective.went_well.join('、') }}</span>
            </div>
            <div v-if="s.retrospective.improve?.length" class="text-xs mb-1">
              <span style="color: #eab308">🔧 待改进：</span>
              <span style="color: var(--text-secondary)">{{ s.retrospective.improve.join('、') }}</span>
            </div>
            <div v-if="s.retrospective.action_items?.length" class="text-xs">
              <span style="color: #3b82f6">📋 行动项：</span>
              <span v-for="(a, i) in s.retrospective.action_items" :key="i" style="color: var(--text-secondary)">
                {{ a.item }}({{ a.owner }}) {{ i < s.retrospective.action_items.length - 1 ? '、' : '' }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 项目团队 ═══ -->
    <div class="stat-card mb-6 animate-in" style="animation-delay: 0.25s">
      <div class="section-title">👥 项目团队</div>
      <div v-if="members.length === 0" class="text-center py-6" style="color: var(--text-secondary)">
        暂无成员数据
      </div>
      <div v-else class="flex flex-wrap gap-3 mt-4">
        <div v-for="m in members" :key="m.id"
             class="flex items-center gap-3 px-4 py-3 rounded-xl"
             style="background: var(--bg-secondary); min-width: 180px">
          <el-avatar :size="32" style="font-size: 13px"
                     :style="{ background: trackColor(m.track) }">
            {{ m.name.charAt(0) }}
          </el-avatar>
          <div>
            <div class="text-xs font-semibold" style="color: var(--text-primary)">
              {{ m.name }}
              <span v-if="m.role_in_project" class="font-normal" style="color: var(--text-secondary)">
                · {{ m.role_in_project }}
              </span>
            </div>
            <div class="text-xs" style="color: var(--text-secondary)">
              {{ m.department }} ·
              <el-tag size="small" :type="m.track === 'hardware' ? 'warning' : m.track === 'software' ? '' : 'info'"
                      effect="plain" style="border-radius: 4px; font-size: 10px">
                {{ trackLabel(m.track) }}
              </el-tag>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 项目概况 -->
    <div class="stat-card animate-in" style="animation-delay: 0.3s" v-if="project">
      <div class="section-title">项目概况</div>
      <el-descriptions :column="3" border size="small" class="mt-4">
        <el-descriptions-item label="项目编号">{{ project.code }}</el-descriptions-item>
        <el-descriptions-item label="轨道">{{ project.track === 'dual' ? '软硬双轨' : project.track }}</el-descriptions-item>
        <el-descriptions-item label="状态">{{ project.status }}</el-descriptions-item>
        <el-descriptions-item label="计划交付">{{ project.planned_launch_date }}</el-descriptions-item>
        <el-descriptions-item label="预算总额">¥{{ Number(project.budget_total).toLocaleString() }}</el-descriptions-item>
        <el-descriptions-item label="已支出">{{ project.budget_spent ? `¥${Number(project.budget_spent).toLocaleString()}` : '暂无' }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <!-- ═══ 评审弹窗 ═══ -->
    <el-dialog v-model="reviewDialogVisible" title="提交关卡评审" width="480px" :close-on-click-modal="false">
      <div v-if="reviewingGate" class="mb-4 text-sm" style="color: var(--text-secondary)">
        正在评审：<strong style="color: var(--text-primary)">Gate {{ reviewingGate.number }} · {{ reviewingGate.name }}</strong>
      </div>
      <el-form label-width="80px" label-position="left">
        <el-form-item label="评审决策" required>
          <el-radio-group v-model="reviewForm.decision">
            <el-radio value="pass">✅ 通过</el-radio>
            <el-radio value="conditional_pass">⚠️ 有条件通过</el-radio>
            <el-radio value="fail">❌ 不通过</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="评审备注">
          <el-input v-model="reviewForm.notes" type="textarea" :rows="3" placeholder="评审意见..." />
        </el-form-item>
        <el-form-item label="整改项" v-if="reviewForm.decision === 'conditional_pass'">
          <el-input v-model="reviewForm.remediation" type="textarea" :rows="2" placeholder="需整改的具体项..." />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="reviewDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmitReview" :loading="submitting"
                   style="background: linear-gradient(135deg, #3b82f6, #6366f1); border: none">
          提交评审
        </el-button>
      </template>
    </el-dialog>

    <!-- ═══ 创建 Sprint 弹窗 ═══ -->
    <el-dialog v-model="sprintCreateVisible" title="新建 Sprint" width="450px" :close-on-click-modal="false">
      <el-form label-width="80px" label-position="left">
        <el-form-item label="编号" required>
          <el-input-number v-model="sprintForm.sprint_number" :min="1" :max="99" />
        </el-form-item>
        <el-form-item label="目标">
          <el-input v-model="sprintForm.goal" type="textarea" :rows="2" placeholder="Sprint 目标描述" />
        </el-form-item>
        <el-form-item label="开始日期" required>
          <el-date-picker v-model="sprintForm.start_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="结束日期" required>
          <el-date-picker v-model="sprintForm.end_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="故事点">
          <el-input-number v-model="sprintForm.planned_story_points" :min="0" :max="999" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sprintCreateVisible = false">取消</el-button>
        <el-button type="primary" @click="handleCreateSprint" :loading="sprintSubmitting"
                   style="background: linear-gradient(135deg, #3b82f6, #6366f1); border: none">创建</el-button>
      </template>
    </el-dialog>

    <!-- ═══ 完成 Sprint 弹窗 ═══ -->
    <el-dialog v-model="sprintCompleteVisible" title="完成 Sprint" width="500px" :close-on-click-modal="false">
      <div v-if="completingSprint" class="mb-4 text-sm" style="color: var(--text-secondary)">
        Sprint #{{ completingSprint.sprint_number }} · 计划 {{ completingSprint.planned_sp }} SP
      </div>
      <el-form label-width="90px" label-position="left">
        <el-form-item label="完成故事点" required>
          <el-input-number v-model="completeForm.completed_story_points" :min="0" :max="999" />
        </el-form-item>
        <el-form-item label="😊 做得好">
          <el-input v-model="completeForm.went_well" placeholder="逗号分隔多项" />
        </el-form-item>
        <el-form-item label="🔧 待改进">
          <el-input v-model="completeForm.improve" placeholder="逗号分隔多项" />
        </el-form-item>
        <el-form-item label="📋 行动项">
          <el-input v-model="completeForm.action_item" placeholder="具体改进事项" />
          <el-input v-model="completeForm.action_owner" placeholder="负责人" style="margin-top:4px" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sprintCompleteVisible = false">取消</el-button>
        <el-button type="success" @click="handleCompleteSprint" :loading="sprintSubmitting">✅ 完成 Sprint</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { getProject, getProjectGantt, getProjectMembers, getGateReviews, submitGateReview } from '../api/projects'
import { getProjectSprints, createSprint, startSprint, completeSprint } from '../api/sprints'
import { useAuthStore } from '../stores/auth'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const route = useRoute()
const authStore = useAuthStore()
const projectId = computed(() => route.params.id as string)
const isAdmin = computed(() => authStore.isAdmin)

const project = ref<any>(null)
const ganttData = ref<any[]>([])
const sprints = ref<any[]>([])
const gateReviews = ref<any[]>([])
const members = ref<any[]>([])

// ── 甘特图时间轴 ──
const timelineStart = computed(() => ganttData.value[0]?.planned_start || '')
const timelineEnd = computed(() => ganttData.value[ganttData.value.length - 1]?.planned_end || '')
const timelineMid = computed(() => ganttData.value.length >= 3 ? ganttData.value[2]?.planned_start || '' : '')

function healthColor(status: string) {
  return { green: '#22c55e', yellow: '#eab308', red: '#ef4444', locked: '#4b5563' }[status] || '#4b5563'
}

function ganttBarStyle(stage: any) {
  if (!ganttData.value.length) return {}
  const allStart = new Date(ganttData.value[0].planned_start).getTime()
  const allEnd = new Date(ganttData.value[ganttData.value.length - 1].planned_end).getTime()
  const totalDays = allEnd - allStart
  if (totalDays <= 0) return {}
  const stageStart = new Date(stage.planned_start).getTime()
  const stageEnd = new Date(stage.planned_end).getTime()
  const left = ((stageStart - allStart) / totalDays) * 100
  const width = ((stageEnd - stageStart) / totalDays) * 100
  return { left: `${left}%`, width: `${Math.max(width, 3)}%` }
}

// ── 关卡步骤 ──
const GATE_NAMES = ['立项评审', '设计评审', '发布就绪 TR6', '量产放行']
const gateSteps = computed(() => {
  const currentStage = project.value?.current_stage || 1
  return [1, 2, 3, 4].map(n => {
    const review = gateReviews.value.find(r => r.gate_number === n)
    let status = 'locked'
    if (review) status = 'passed'
    else if (n === currentStage) status = 'current'
    else if (n < currentStage) status = 'passed'
    return { number: n, name: GATE_NAMES[n - 1], status, review }
  })
})

function gateCardStyle(g: any) {
  if (g.status === 'passed') return { background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.2)' }
  if (g.status === 'current') return { background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.2)' }
  return { background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', opacity: '0.6' }
}

function decisionType(d: string) {
  return { pass: 'success', conditional_pass: 'warning', fail: 'danger' }[d] || ''
}
function decisionLabel(d: string) {
  return { pass: '✅ 通过', conditional_pass: '⚠️ 有条件通过', fail: '❌ 不通过' }[d] || d
}
function formatDate(s: string) {
  return s ? s.slice(0, 10) : ''
}

// ── 评审弹窗 ──
const reviewDialogVisible = ref(false)
const reviewingGate = ref<any>(null)
const submitting = ref(false)
const reviewForm = reactive({ decision: 'pass', notes: '', remediation: '' })

function openReviewDialog(gate: any) {
  reviewingGate.value = gate
  Object.assign(reviewForm, { decision: 'pass', notes: '', remediation: '' })
  reviewDialogVisible.value = true
}

async function handleSubmitReview() {
  submitting.value = true
  try {
    await submitGateReview({
      project_id: projectId.value,
      gate_number: reviewingGate.value.number,
      decision: reviewForm.decision,
      decision_notes: reviewForm.notes || undefined,
      remediation_items: reviewForm.remediation || undefined,
    })
    ElMessage.success(`Gate ${reviewingGate.value.number} 评审已提交`)
    reviewDialogVisible.value = false
    fetchData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '评审提交失败')
  } finally {
    submitting.value = false
  }
}

// ── Sprint ──
function sprintStatusType(s: string) { return { planning: 'info', active: 'primary', completed: 'success' }[s] || 'info' }
function sprintStatusLabel(s: string) { return { planning: '规划中', active: '进行中', completed: '已完成' }[s] || s }
function sprintCardStyle(status: string) {
  if (status === 'active') return { background: 'rgba(59,130,246,0.06)', border: '1px solid rgba(59,130,246,0.2)' }
  if (status === 'completed') return { background: 'rgba(34,197,94,0.06)', border: '1px solid rgba(34,197,94,0.15)' }
  return { background: 'rgba(148,163,184,0.06)', border: '1px solid rgba(148,163,184,0.15)' }
}

// Sprint 创建
const sprintCreateVisible = ref(false)
const sprintSubmitting = ref(false)
const sprintForm = reactive({
  sprint_number: 1,
  goal: '',
  start_date: '',
  end_date: '',
  planned_story_points: 20,
})

function openCreateSprintDialog() {
  const nextNum = sprints.value.length > 0
    ? Math.max(...sprints.value.map((s: any) => s.sprint_number)) + 1
    : 1
  Object.assign(sprintForm, { sprint_number: nextNum, goal: '', start_date: '', end_date: '', planned_story_points: 20 })
  sprintCreateVisible.value = true
}

async function handleCreateSprint() {
  sprintSubmitting.value = true
  try {
    await createSprint({
      project_id: projectId.value,
      sprint_number: sprintForm.sprint_number,
      goal: sprintForm.goal,
      start_date: sprintForm.start_date,
      end_date: sprintForm.end_date,
      planned_story_points: sprintForm.planned_story_points,
    })
    ElMessage.success(`Sprint #${sprintForm.sprint_number} 已创建`)
    sprintCreateVisible.value = false
    fetchData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '创建失败')
  } finally {
    sprintSubmitting.value = false
  }
}

async function handleStartSprint(s: any) {
  try {
    await startSprint(s.sprint_id)
    ElMessage.success(`Sprint #${s.sprint_number} 已启动`)
    fetchData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '启动失败')
  }
}

// Sprint 完成
const sprintCompleteVisible = ref(false)
const completingSprint = ref<any>(null)
const completeForm = reactive({
  completed_story_points: 0,
  went_well: '',
  improve: '',
  action_item: '',
  action_owner: '',
})

function openCompleteDialog(s: any) {
  completingSprint.value = s
  Object.assign(completeForm, { completed_story_points: s.planned_sp || 0, went_well: '', improve: '', action_item: '', action_owner: '' })
  sprintCompleteVisible.value = true
}

async function handleCompleteSprint() {
  sprintSubmitting.value = true
  try {
    const retro: any = {
      went_well: completeForm.went_well ? completeForm.went_well.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean) : [],
      improve: completeForm.improve ? completeForm.improve.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean) : [],
      action_items: completeForm.action_item ? [{ item: completeForm.action_item, owner: completeForm.action_owner || '待定' }] : [],
    }
    await completeSprint(completingSprint.value.sprint_id, {
      completed_story_points: completeForm.completed_story_points,
      retrospective: retro,
    })
    ElMessage.success(`Sprint #${completingSprint.value.sprint_number} 已完成`)
    sprintCompleteVisible.value = false
    fetchData()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '完成失败')
  } finally {
    sprintSubmitting.value = false
  }
}

// ── 团队 ──
function trackLabel(t: string) { return { hardware: '硬件轨', software: '软件轨', both: '双轨' }[t] || t }
function trackColor(t: string) {
  return { hardware: 'linear-gradient(135deg, #f59e0b, #d97706)', software: 'linear-gradient(135deg, #3b82f6, #6366f1)', both: 'linear-gradient(135deg, #8b5cf6, #a855f7)' }[t] || '#6b7280'
}

// ── 数据加载 ──
async function fetchData() {
  const id = projectId.value
  const [pRes, gRes, sRes, grRes, mRes] = await Promise.allSettled([
    getProject(id),
    getProjectGantt(id),
    getProjectSprints(id),
    getGateReviews(id),
    getProjectMembers(id),
  ])
  if (pRes.status === 'fulfilled') {
    const data = pRes.value as any
    project.value = data.project || data
  }
  if (gRes.status === 'fulfilled') ganttData.value = gRes.value as unknown as any[]
  if (sRes.status === 'fulfilled') sprints.value = sRes.value as unknown as any[]
  if (grRes.status === 'fulfilled') gateReviews.value = grRes.value as unknown as any[]
  if (mRes.status === 'fulfilled') members.value = mRes.value as unknown as any[]
}

onMounted(fetchData)
</script>

