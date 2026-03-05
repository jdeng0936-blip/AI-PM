<template>
  <div class="page-container">
    <div class="flex items-center justify-between mb-6 animate-in">
      <div>
        <h1 class="text-xl font-bold" style="color: var(--text-primary)">🧪 模拟日报提交</h1>
        <p class="text-sm mt-1" style="color: var(--text-secondary)">按 Excel 日报表格式逐项填写，AI 自动质检评分</p>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- 左：结构化表单 -->
      <div class="animate-in" style="animation-delay: 0.1s">
        <!-- 基础信息 -->
        <div class="stat-card mb-4">
          <div class="section-title mb-4">👤 基础信息</div>
          <el-form label-width="80px" label-position="left">
            <el-form-item label="姓名" required>
              <el-select v-model="selectedUser" placeholder="选择用户" style="width: 100%" filterable>
                <el-option v-for="u in users" :key="u.wechat_userid"
                           :label="`${u.name} (${u.department || ''})`"
                           :value="u.wechat_userid" />
              </el-select>
            </el-form-item>
            <el-form-item label="日期">
              <el-date-picker v-model="reportDate" type="date" value-format="YYYY-MM-DD"
                              placeholder="默认今天" style="width: 100%" clearable />
            </el-form-item>
          </el-form>
        </div>

        <!-- 计划区 -->
        <div class="stat-card mb-4">
          <div class="flex items-center gap-2 mb-4">
            <div class="w-1 h-5 rounded" style="background: #3b82f6"></div>
            <span class="section-title" style="margin: 0">📋 计划</span>
          </div>
          <el-form label-width="80px" label-position="top">
            <el-form-item label="今日任务" required>
              <el-input v-model="form.tasks" type="textarea" :rows="3"
                        placeholder="1. 完成XX模块开发&#10;2. 修复XX Bug&#10;3. 参加Sprint评审会议" />
            </el-form-item>
            <el-form-item label="验收标准">
              <el-input v-model="form.acceptance_criteria" type="textarea" :rows="2"
                        placeholder="API测试全部通过，覆盖率85%以上" />
            </el-form-item>
            <el-form-item label="所需支持">
              <el-input v-model="form.support_needed"
                        placeholder="无 / 需要DBA协助优化查询" />
            </el-form-item>
          </el-form>
        </div>

        <!-- 验收区 -->
        <div class="stat-card mb-4">
          <div class="flex items-center gap-2 mb-4">
            <div class="w-1 h-5 rounded" style="background: #22c55e"></div>
            <span class="section-title" style="margin: 0">✅ 验收</span>
          </div>
          <el-form label-width="80px" label-position="top">
            <el-form-item label="完成进度" required>
              <div class="flex items-center gap-3" style="width: 100%">
                <el-slider v-model="form.progress" :min="0" :max="100" :step="5"
                           style="flex: 1" :marks="{ 0: '0%', 50: '50%', 100: '100%' }" />
                <el-tag :type="form.progress >= 80 ? 'success' : form.progress >= 50 ? 'warning' : 'danger'"
                        size="small" style="min-width: 45px; text-align: center">{{ form.progress }}%</el-tag>
              </div>
            </el-form-item>
            <el-form-item label="成果演示">
              <el-input v-model="form.deliverable"
                        placeholder="已部署到测试环境 / ID表发生产、电源箱柜发天勤市检" />
            </el-form-item>
            <el-form-item label="验收人">
              <el-input v-model="form.reviewer" placeholder="新雷" />
            </el-form-item>
            <el-form-item label="Git 版本号">
              <el-input v-model="form.git_version" placeholder="a3f8d2c / v1.2.0">
                <template #prefix><span style="color: var(--text-secondary); font-family: monospace">🔗</span></template>
              </el-input>
            </el-form-item>
          </el-form>
        </div>

        <!-- 未完成工作复盘 -->
        <div class="stat-card mb-4">
          <div class="flex items-center gap-2 mb-4">
            <div class="w-1 h-5 rounded" style="background: #eab308"></div>
            <span class="section-title" style="margin: 0">🔧 未完成工作复盘</span>
          </div>
          <el-form label-width="80px" label-position="top">
            <el-form-item label="核心卡点">
              <el-input v-model="form.blocker" type="textarea" :rows="2"
                        placeholder="无 / 生产环境连接数已达上限，需要DBA扩容" />
            </el-form-item>
            <el-form-item label="解决方案">
              <el-input v-model="form.solution" type="textarea" :rows="2"
                        placeholder="临时方案：增加连接池上限；根本方案：优化慢查询" />
            </el-form-item>
            <el-form-item label="预计解决时间">
              <el-date-picker v-model="form.eta" type="date" value-format="YYYY-MM-DD"
                              placeholder="选择日期" style="width: 100%" clearable />
            </el-form-item>
          </el-form>
        </div>

        <!-- 提交按钮 -->
        <el-button type="primary" @click="handleSubmit" :loading="submitting" size="large"
                   :disabled="!selectedUser || !form.tasks"
                   style="background: linear-gradient(135deg, #3b82f6, #6366f1); border: none; width: 100%; height: 48px; font-size: 15px; border-radius: 12px">
          <el-icon class="mr-1"><Promotion /></el-icon>提交模拟日报
        </el-button>
      </div>

      <!-- 右：AI 结果区 -->
      <div class="animate-in" style="animation-delay: 0.2s">
        <div class="stat-card" style="position: sticky; top: 24px">
          <div class="section-title mb-4">🤖 AI 分析结果</div>

          <!-- 空状态 -->
          <div v-if="!result" class="flex flex-col items-center justify-center py-16" style="color: var(--text-secondary)">
            <div class="text-4xl mb-3">🔬</div>
            <div class="text-sm">填写左侧表单后提交，AI 分析结果将在此展示</div>
          </div>

          <!-- 结果展示 -->
          <div v-else>
            <!-- 评分 + 状态 -->
            <div class="flex items-center justify-between mb-5 p-4 rounded-xl"
                 :style="{ background: result.pass_check ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)' }">
              <div>
                <div class="text-3xl font-bold" :style="{ color: scoreColor(result.ai_score) }">
                  {{ result.ai_score }}
                </div>
                <div class="text-xs mt-1" style="color: var(--text-secondary)">AI 评分</div>
              </div>
              <el-tag :type="result.pass_check ? 'success' : 'danger'" size="large" effect="dark">
                {{ result.pass_check ? '✅ 合格' : '❌ 退回' }}
              </el-tag>
            </div>

            <!-- 用户信息 -->
            <div class="flex items-center gap-3 mb-4">
              <el-avatar :size="36" style="background: linear-gradient(135deg, #3b82f6, #6366f1)">
                {{ result.user_name?.charAt(0) }}
              </el-avatar>
              <div>
                <div class="text-sm font-semibold" style="color: var(--text-primary)">{{ result.user_name }}</div>
                <div class="text-xs" style="color: var(--text-secondary)">{{ result.department }}</div>
              </div>
            </div>

            <!-- AI 评语 -->
            <div class="rounded-lg p-3 mb-4" style="background: var(--bg-secondary)">
              <div class="text-xs font-semibold mb-1" style="color: var(--text-primary)">💡 AI 评语</div>
              <div class="text-xs" style="color: var(--text-secondary); line-height: 1.8">{{ result.ai_comment }}</div>
            </div>

            <!-- 管理预警 -->
            <div v-if="result.management_alert" class="rounded-lg p-3 mb-4"
                 style="background: rgba(239,68,68,0.06); border: 1px solid rgba(239,68,68,0.2)">
              <div class="text-xs font-semibold mb-1" style="color: #ef4444">🚨 管理预警</div>
              <div class="text-xs" style="color: var(--text-secondary)">{{ result.management_alert }}</div>
            </div>

            <!-- 退回原因 + 建议 -->
            <div v-if="!result.pass_check && result.reject_reason" class="rounded-lg p-3 mb-4"
                 style="background: rgba(234,179,8,0.06); border: 1px solid rgba(234,179,8,0.2)">
              <div class="text-xs font-semibold mb-1" style="color: #eab308">⚠️ 退回原因</div>
              <div class="text-xs mb-2" style="color: var(--text-secondary)">{{ result.reject_reason }}</div>
              <div v-if="result.suggested_guidance" class="text-xs" style="color: var(--text-secondary); white-space: pre-wrap">{{ result.suggested_guidance }}</div>
            </div>

            <!-- 解析字段预览 -->
            <div v-if="result.parsed_content" class="rounded-lg p-3 mb-4" style="background: var(--bg-secondary)">
              <div class="text-xs font-semibold mb-3" style="color: var(--text-primary)">📊 AI 解析确认</div>
              <div class="field-row" v-for="f in fieldPreview" :key="f.label">
                <span class="field-label">{{ f.label }}</span>
                <span class="field-value" :style="f.style || {}">{{ f.value }}</span>
              </div>
            </div>

            <!-- Token 用量 -->
            <div class="flex gap-4 text-xs" style="color: var(--text-secondary)">
              <span>Prompt: {{ result.tokens_used?.prompt }} tokens</span>
              <span>Completion: {{ result.tokens_used?.completion }} tokens</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { getUsers } from '../api/users'
import { Promotion } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import request from '../api/request'

const users = ref<any[]>([])
const selectedUser = ref('')
const reportDate = ref('')
const submitting = ref(false)
const result = ref<any>(null)

const form = reactive({
  tasks: '',
  acceptance_criteria: '',
  support_needed: '',
  progress: 50,
  deliverable: '',
  reviewer: '',
  git_version: '',
  blocker: '',
  solution: '',
  eta: '',
})

function scoreColor(score: number | null) {
  if (score == null) return 'var(--text-secondary)'
  if (score >= 90) return '#22c55e'
  if (score >= 60) return '#eab308'
  return '#ef4444'
}

// 将结构化表单拼接成 raw_text（后端 AI 解析所需格式）
function buildRawText(): string {
  const lines: string[] = []
  lines.push(`【今日任务】\n${form.tasks}`)
  if (form.acceptance_criteria) lines.push(`【验收标准】\n${form.acceptance_criteria}`)
  if (form.support_needed) lines.push(`【所需支持】${form.support_needed}`)
  lines.push(`【完成进度】${form.progress}%`)
  if (form.deliverable) lines.push(`【成果演示】${form.deliverable}`)
  if (form.reviewer) lines.push(`【验收人】${form.reviewer}`)
  if (form.git_version) lines.push(`【Git版本号】${form.git_version}`)
  lines.push(`【核心卡点】${form.blocker || '无'}`)
  if (form.solution) lines.push(`【解决方案】${form.solution}`)
  if (form.eta) lines.push(`【预计解决时间】${form.eta}`)
  return lines.join('\n\n')
}

const fieldPreview = computed(() => {
  const pc = result.value?.parsed_content || {}
  return [
    { label: '今日任务', value: pc.tasks || '—' },
    { label: '验收标准', value: pc.acceptance_criteria || '—' },
    { label: '所需支持', value: pc.support_needed || '—' },
    { label: '完成进度', value: pc.progress != null ? `${pc.progress}%` : '—', style: { color: scoreColor(pc.progress), fontWeight: 'bold' } },
    { label: '成果演示', value: pc.deliverable || '—' },
    { label: '验收人', value: pc.reviewer || '—' },
    { label: 'Git 版本', value: pc.git_version || '—', style: { fontFamily: 'monospace' } },
    { label: '核心卡点', value: pc.blocker || '无', style: pc.blocker ? { color: '#ef4444' } : {} },
    { label: '解决方案', value: pc.next_step || '—' },
    { label: '预计解决', value: pc.eta || '—' },
  ]
})

async function handleSubmit() {
  submitting.value = true
  result.value = null
  try {
    const payload: any = {
      wechat_userid: selectedUser.value,
      raw_text: buildRawText(),
    }
    if (reportDate.value) payload.report_date = reportDate.value
    const res = await request.post('/simulate/daily-report', payload) as any
    if (res.error) {
      ElMessage.error(res.error)
    } else {
      result.value = res
      ElMessage.success(`日报已提交，AI 评分: ${res.ai_score}`)
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  try {
    const res = await getUsers({ page_size: 100 }) as any
    users.value = (res.items || res || []).filter((u: any) => u.wechat_userid)
  } catch {
    users.value = []
  }
})
</script>

<style scoped>
.field-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
  line-height: 1.6;
}
.field-label {
  color: var(--text-secondary);
  white-space: nowrap;
  min-width: 60px;
}
.field-value {
  color: var(--text-primary);
  word-break: break-all;
}
</style>
