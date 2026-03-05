<template>
  <div class="page-container">
    <div class="flex items-center justify-between mb-6 animate-in">
      <div>
        <h1 class="text-xl font-bold" style="color: var(--text-primary)">AI 日报流</h1>
        <p class="text-sm mt-1" style="color: var(--text-secondary)">大模型质检结果一览</p>
      </div>
      <div class="flex gap-2">
        <el-button type="success" plain size="small" @click="handleExport" :loading="exporting">
          <el-icon class="mr-1"><Download /></el-icon>导出 Excel
        </el-button>
        <el-button type="primary" plain size="small" @click="fetchReports" :loading="loading">
          <el-icon class="mr-1"><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="stat-card mb-4 animate-in flex items-center gap-4 flex-wrap" style="animation-delay: 0.05s; padding: 12px 16px">
      <el-date-picker v-model="filterDate" type="date" placeholder="日期" size="small"
                      value-format="YYYY-MM-DD" clearable style="width: 140px"
                      @change="fetchReports" />
      <el-select v-model="filterStatus" placeholder="状态" size="small" clearable
                 style="width: 100px" @change="fetchReports">
        <el-option label="全部" value="" />
        <el-option label="✅ 合格" value="true" />
        <el-option label="❌ 退回" value="false" />
      </el-select>
      <el-input v-model="filterName" placeholder="搜索姓名" size="small" clearable
                style="width: 130px" @clear="fetchReports" @keyup.enter="fetchReports">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <el-tag v-if="filterDate || filterStatus || filterName" type="info" size="small"
              closable @close="clearFilters" style="margin-left: auto">
        已筛选
      </el-tag>
    </div>

    <!-- 日报表格 -->
    <div class="stat-card animate-in" style="animation-delay: 0.1s">
      <el-table :data="reports" style="width: 100%"
                :header-cell-style="{ background: 'var(--bg-card)', color: 'var(--text-secondary)', fontWeight: 600, fontSize: '12px', borderColor: 'var(--border-subtle)' }"
                :cell-style="{ background: 'transparent', color: 'var(--text-primary)', borderColor: 'var(--border-subtle)' }"
                empty-text="暂无日报数据（请通过企微发送日报后查看）"
                stripe
                @row-click="handleRowClick"
                :row-style="{ cursor: 'pointer' }">
        <el-table-column label="日期" prop="report_date" width="110" />
        <el-table-column label="姓名" width="80">
          <template #default="{ row }">{{ row.member || row.user_name }}</template>
        </el-table-column>
        <el-table-column label="部门" prop="department" width="100" />

        <!-- AI 评分 -->
        <el-table-column label="AI 评分" width="90" align="center">
          <template #default="{ row }">
            <div class="score-badge"
                 :class="row.ai_score >= 90 ? 'high' : row.ai_score >= 60 ? 'medium' : 'low'">
              {{ row.ai_score ?? '-' }}
            </div>
          </template>
        </el-table-column>

        <!-- 进展摘要 -->
        <el-table-column label="今日进展" min-width="200">
          <template #default="{ row }">
            <div class="text-xs" style="line-height: 1.6">
              {{ row.parsed_content?.tasks?.slice(0, 80) || row.raw_input_text?.slice(0, 80) || '-' }}
            </div>
          </template>
        </el-table-column>

        <!-- AI 评语 -->
        <el-table-column label="AI 评语" min-width="200">
          <template #default="{ row }">
            <div class="text-xs" style="color: var(--text-secondary); line-height: 1.6">
              {{ row.ai_comment || '-' }}
            </div>
          </template>
        </el-table-column>

        <!-- 状态 -->
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.pass_check === true ? 'success' : row.pass_check === false ? 'danger' : 'info'"
                    size="small" round>
              {{ row.pass_check === true ? '合格' : row.pass_check === false ? '退回' : '待审' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="flex justify-center mt-6">
        <el-pagination
          v-model:current-page="page"
          :page-size="20"
          :total="total"
          layout="prev, pager, next"
          @current-change="fetchReports"
          background
        />
      </div>
    </div>

    <!-- ═══ 日报详情抽屉 ═══ -->
    <el-drawer v-model="drawerVisible" title="" size="520px" :with-header="false" destroy-on-close>
      <div v-if="detail" class="p-2">
        <!-- 顶部：评分 + 状态 -->
        <div class="flex items-center gap-4 mb-6">
          <div class="text-center">
            <div class="text-4xl font-bold" :style="{ color: scoreColor(detail.ai_score) }">
              {{ detail.ai_score ?? '-' }}
            </div>
            <div class="text-xs mt-1" style="color: var(--text-secondary)">AI 评分</div>
          </div>
          <div class="flex-1">
            <div class="flex items-center gap-2">
              <span class="text-lg font-semibold" style="color: var(--text-primary)">{{ detail.member }}</span>
              <el-tag :type="detail.pass_check ? 'success' : 'danger'" size="small" effect="dark"
                      style="border-radius: 6px">
                {{ detail.pass_check ? '✅ 合格' : '❌ 退回' }}
              </el-tag>
            </div>
            <div class="text-xs mt-1" style="color: var(--text-secondary)">
              {{ detail.department }} · {{ detail.report_date }}
            </div>
          </div>
        </div>

        <!-- AI 评语 -->
        <DetailSection title="💬 AI 评语" :content="detail.ai_comment" />

        <!-- 退回原因 -->
        <DetailSection v-if="!detail.pass_check && detail.reject_reason"
                       title="⚠️ 退回原因" :content="detail.reject_reason" type="warning" />

        <!-- 修改建议 -->
        <DetailSection v-if="detail.suggested_guidance"
                       title="📋 修改建议模板" :content="detail.suggested_guidance" type="info" />

        <!-- 管理预警 -->
        <DetailSection v-if="detail.management_alert"
                       title="🚨 管理预警" :content="detail.management_alert" type="danger" />

        <!-- 分隔线 -->
        <el-divider style="margin: 16px 0; border-color: var(--border-subtle)" />

        <!-- AI 解析字段 — 对齐 Excel 表 -->
        <div class="text-sm font-semibold mb-3" style="color: var(--text-primary)">🔍 AI 解析结果</div>

        <!-- 计划 -->
        <div class="text-xs font-semibold mb-2" style="color: #3b82f6">📋 计划</div>
        <div class="space-y-3 mb-3">
          <FieldRow label="今日任务" :value="pc?.tasks" />
          <FieldRow label="验收标准" :value="pc?.acceptance_criteria" />
          <FieldRow label="所需支持" :value="pc?.support_needed" />
        </div>

        <!-- 验收 -->
        <div class="text-xs font-semibold mb-2" style="color: #22c55e">✅ 验收</div>
        <div class="space-y-3 mb-3">
          <FieldRow label="完成进度" :value="pc?.progress != null ? `${pc.progress}%` : null">
            <el-progress v-if="pc?.progress != null" :percentage="pc.progress"
                         :stroke-width="6" :color="progressColor"
                         style="width: 120px; display: inline-flex; margin-left: 8px" />
          </FieldRow>
          <FieldRow label="成果演示" :value="pc?.deliverable" />
          <FieldRow label="验收人" :value="pc?.reviewer" />
          <FieldRow label="Git 版本" :value="pc?.git_version" />
        </div>

        <!-- 未完成工作复盘 -->
        <div class="text-xs font-semibold mb-2" style="color: #eab308">🔧 未完成工作复盘</div>
        <div class="space-y-3">
          <FieldRow label="核心卡点" :value="pc?.blocker" highlight />
          <FieldRow label="解决方案" :value="pc?.next_step" />
          <FieldRow label="预计解决" :value="pc?.eta" />
        </div>

        <!-- 分隔线 -->
        <el-divider style="margin: 16px 0; border-color: var(--border-subtle)" />

        <!-- 原始文本 -->
        <div class="text-sm font-semibold mb-2" style="color: var(--text-primary)">📝 原始汇报</div>
        <div class="text-xs rounded-lg p-3" style="background: var(--bg-secondary); color: var(--text-secondary); line-height: 1.8; white-space: pre-wrap">{{ detail.raw_input_text }}</div>
      </div>
      <div v-else class="flex items-center justify-center h-full">
        <el-icon class="is-loading" :size="24" />&nbsp;加载中...
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { getReports, getReportDetail } from '../api/reports'
import { Refresh, Download, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()
const loading = ref(false)
const exporting = ref(false)
const reports = ref<any[]>([])
const total = ref(0)
const page = ref(1)

// ── 筛选 ──
const filterDate = ref('')
const filterStatus = ref('')
const filterName = ref('')

function clearFilters() {
  filterDate.value = ''
  filterStatus.value = ''
  filterName.value = ''
  fetchReports()
}

// ── 导出 Excel ──
async function handleExport() {
  exporting.value = true
  try {
    let exportUrl = '/api/v1/export/daily-reports'
    if (filterDate.value) exportUrl += `?start_date=${filterDate.value}&end_date=${filterDate.value}`
    const resp = await fetch(exportUrl, {
      headers: { Authorization: `Bearer ${authStore.token}` },
    })
    if (!resp.ok) throw new Error('导出失败')
    const blob = await resp.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `AI日报_${filterDate.value || new Date().toISOString().slice(0, 10)}.xlsx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}

// ── 详情抽屉 ──
const drawerVisible = ref(false)
const detail = ref<any>(null)

const pc = computed(() => detail.value?.parsed_content || {})

function scoreColor(score: number | null) {
  if (score == null) return 'var(--text-secondary)'
  if (score >= 90) return '#22c55e'
  if (score >= 60) return '#eab308'
  return '#ef4444'
}

const progressColor = [
  { color: '#ef4444', percentage: 30 },
  { color: '#eab308', percentage: 70 },
  { color: '#22c55e', percentage: 100 },
]

async function handleRowClick(row: any) {
  drawerVisible.value = true
  detail.value = null
  try {
    detail.value = await getReportDetail(row.id)
  } catch {
    ElMessage.error('加载日报详情失败')
    drawerVisible.value = false
  }
}

async function fetchReports() {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: 20 }
    if (filterDate.value) params.report_date = filterDate.value
    if (filterStatus.value) params.pass_check = filterStatus.value
    if (filterName.value) params.user_name = filterName.value
    const res: any = await getReports(params)
    reports.value = Array.isArray(res) ? res : (res.items || [])
    total.value = res.total || reports.value.length
  } catch {
    reports.value = []
  } finally {
    loading.value = false
  }
}

onMounted(fetchReports)

// ── 子组件 ──
const DetailSection = (props: { title: string; content?: string; type?: string }) => {
  if (!props.content) return null
  const bgMap: Record<string, string> = {
    warning: 'rgba(234,179,8,0.08)',
    danger: 'rgba(239,68,68,0.08)',
    info: 'rgba(59,130,246,0.08)',
  }
  const borderMap: Record<string, string> = {
    warning: 'rgba(234,179,8,0.25)',
    danger: 'rgba(239,68,68,0.25)',
    info: 'rgba(59,130,246,0.25)',
  }
  return h('div', { class: 'mb-4 rounded-lg p-3', style: {
    background: bgMap[props.type || ''] || 'var(--bg-secondary)',
    border: props.type ? `1px solid ${borderMap[props.type]}` : 'none',
  }}, [
    h('div', { class: 'text-sm font-semibold mb-1', style: { color: 'var(--text-primary)' } }, props.title),
    h('div', { class: 'text-xs', style: { color: 'var(--text-secondary)', lineHeight: '1.8', whiteSpace: 'pre-wrap' } }, props.content),
  ])
}

const FieldRow = (props: { label: string; value?: string | null; highlight?: boolean }, { slots }: any) => {
  return h('div', { class: 'flex items-start gap-2' }, [
    h('span', { class: 'text-xs flex-shrink-0', style: { color: 'var(--text-secondary)', minWidth: '70px' } }, props.label),
    h('span', {
      class: 'text-xs flex-1',
      style: {
        color: props.highlight && props.value ? '#ef4444' : 'var(--text-primary)',
        fontWeight: props.highlight && props.value ? '600' : 'normal',
      },
    }, [props.value || '-', slots?.default?.()]),
  ])
}
</script>
