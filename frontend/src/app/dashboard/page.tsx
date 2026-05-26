/**
 * app/dashboard/page.tsx — 监控台 (1:1 port from Vue Dashboard.vue)
 *
 * Sections:
 *   1. 统计卡片 (活跃项目 / AI 日报 / 未汇报+卡点)
 *   2. AI 日报明细表
 *   3. 未汇报名单
 *   4. 项目健康矩阵
 *   5. 风险阻碍池
 *   6. 新建项目弹窗
 */
'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'
import { getMorningBriefing, getRiskAlerts, getTempTicketSummary } from '@/api/dashboard'
import { getProjectsOverview, createProject } from '@/api/projects'
import { batchSoftDeleteReports, batchRestoreReports } from '@/api/reports'
import {
  MAIN_TRACK_OPTIONS,
  TEMP_TRACK_OPTIONS,
  TRACK_LABELS,
  trackLabel,
} from '@/lib/project-track'
import { useListFilters, type FilterSpec } from '@/lib/hooks/use-list-filters'
import { useMultiSelect } from '@/lib/hooks/use-multi-select'
import FilterBar from '@/components/filter-bar'
import ListActionBar from '@/components/list-action-bar'
import { toast } from 'sonner'
import {
  LayoutDashboard,
  Cpu,
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  RefreshCw,
  Plus,
  Ticket,
  Trophy,
  Trash2,
} from 'lucide-react'

export default function DashboardPage() {
  const router = useRouter()
  const { isAdmin } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const today = new Date().toLocaleDateString('zh-CN', {
    month: 'long',
    day: 'numeric',
    weekday: 'long',
  })

  const [overview, setOverview] = useState<any>({})
  const [projects, setProjects] = useState<any[]>([])
  const [riskAlerts, setRiskAlerts] = useState<any[]>([])
  const [morningStats, setMorningStats] = useState<any>({})
  const [morningReports, setMorningReports] = useState<any[]>([])
  const [missingMembers, setMissingMembers] = useState<any[]>([])
  const [morningBriefingDate, setMorningBriefingDate] = useState('')
  // V2.3 临时工单看板数据
  const [tempSummary, setTempSummary] = useState<any>(null)

  // 新建项目弹窗
  const [showCreate, setShowCreate] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [projectForm, setProjectForm] = useState({
    name: '',
    code: '',
    description: '',
    track: 'dual',
    planned_launch_date: '',
    budget_total: 100000,
    is_temporary: false, // V2.3 临时工单项目
  })

  const healthColor = (status: string) =>
    ({ green: '#22c55e', yellow: '#eab308', red: '#ef4444', locked: '#4b5563' }[status] || '#4b5563')

  const scoreColor = (score: number | null) => {
    if (score == null) return 'var(--color-text-secondary)'
    if (score >= 90) return '#22c55e'
    if (score >= 60) return '#eab308'
    return '#ef4444'
  }

  const fetchAll = useCallback(async () => {
    setLoading(true)
    try {
      const [ov, br, ra, tt] = await Promise.allSettled([
        getProjectsOverview(),
        getMorningBriefing(),
        getRiskAlerts(),
        getTempTicketSummary({ top_n: 5 }),
      ])
      if (ov.status === 'fulfilled') {
        const data = ov.value as any
        setOverview(data)
        setProjects(data.projects || [])
      }
      if (br.status === 'fulfilled') {
        const data = br.value as any
        setMorningStats(data.stats || {})
        setMorningReports(data.reports || [])
        setMissingMembers(data.missing_members || [])
        setMorningBriefingDate(data.report_date || '')
      }
      if (ra.status === 'fulfilled') {
        setRiskAlerts((ra.value as unknown as any[]).filter((a: any) => a.status === 'unresolved'))
      }
      if (tt.status === 'fulfilled') {
        setTempSummary(tt.value as any)
      }
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  // V2.4 Stage 1:日报明细筛选(部门/合格/分数/进度)
  // department options 从当前数据 distinct(部门池动态变化)
  const reportFilterSpec: FilterSpec[] = useMemo(() => {
    const depts = Array.from(new Set(morningReports.map((r: any) => r.department).filter(Boolean))).sort() as string[]
    return [
      {
        key: 'department',
        type: 'multi-select',
        label: '部门',
        options: depts.map((d) => ({ value: d, label: d })),
      },
      {
        key: 'pass_check',
        type: 'boolean',
        label: '质检',
        trueLabel: '合格',
        falseLabel: '退回',
      },
      { key: 'ai_score', type: 'range', label: 'AI 分', min: 0, max: 100, step: 5 },
      { key: 'progress', type: 'range', label: '进度', min: 0, max: 100, step: 5, unit: '%' },
    ]
  }, [morningReports])

  const {
    filteredItems: filteredReports,
    filters: reportFilters,
    setFilter: setReportFilter,
    clearFilter: clearReportFilter,
    clearAll: clearReportAll,
    activeCount: reportActiveCount,
  } = useListFilters(morningReports, reportFilterSpec, { urlPrefix: 'rep_' })

  // V2.4 Stage 2:dashboard 日报明细多选 + 批量软删(走 filteredReports,filter 变即清空)
  const {
    selectedIds: reportSelectedIds,
    selectedCount: reportSelectedCount,
    isSelected: isReportSelected,
    isAllSelected: isAllReportsSelected,
    isIndeterminate: isReportIndeterminate,
    toggle: toggleReport,
    selectAll: selectAllReports,
    clearAll: clearReportSelection,
  } = useMultiSelect(filteredReports)
  const [reportDeleting, setReportDeleting] = useState(false)

  async function handleReportBatchDelete() {
    if (reportSelectedCount === 0) return
    if (!confirm(`确定软删除选中的 ${reportSelectedCount} 条日报?\n(历史 AI 评分 / 关联保留,不影响聚合数据)`)) return
    setReportDeleting(true)
    try {
      const ids = Array.from(reportSelectedIds)
      const res: any = await batchSoftDeleteReports(ids)
      const deletedIds: string[] = res?.deleted_ids ?? ids
      clearReportSelection()
      await fetchAll()
      // V2.4 Stage 3 C3:toast 内 5 秒撤销
      toast.success(`已删除 ${deletedIds.length} 条日报`, {
        duration: 5000,
        action: {
          label: '撤销',
          onClick: async () => {
            try {
              const r: any = await batchRestoreReports(deletedIds)
              await fetchAll()
              toast.success(`已撤销恢复 ${r?.restored_count ?? deletedIds.length} 条`)
            } catch (e: any) {
              toast.error(e?.response?.data?.detail || '撤销失败')
            }
          },
        },
      })
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '批量删除失败')
    } finally {
      setReportDeleting(false)
    }
  }

  async function handleCreateProject() {
    if (!projectForm.name) {
      toast.error('项目名称必填')
      return
    }
    setSubmitting(true)
    try {
      // V2.3:临时工单项目只传精简字段,避免后端强校验 budget/launch_date
      const payload: any = projectForm.is_temporary
        ? {
            name: projectForm.name,
            code: projectForm.code || undefined,
            description: projectForm.description || undefined,
            planned_launch_date: projectForm.planned_launch_date || undefined,
            is_temporary: true,
            track: projectForm.track,
          }
        : projectForm
      const created = (await createProject(payload)) as any
      toast.success(
        projectForm.is_temporary
          ? `🎫 临时工单项目 ${created?.code || projectForm.name} 创建成功`
          : `项目 ${created?.code || projectForm.code || projectForm.name} 立项成功`,
      )
      setShowCreate(false)
      setProjectForm({
        name: '',
        code: '',
        description: '',
        track: 'dual',
        planned_launch_date: '',
        budget_total: 100000,
        is_temporary: false,
      })
      fetchAll()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '立项失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page-container">
      {/* 页面标题 */}
      <div className="flex items-center justify-between mb-6 animate-in">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
            监控台
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            项目健康度实时总览 · {today}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchAll}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
            style={{
              border: '1px solid var(--color-brand-blue)',
              color: 'var(--color-brand-blue)',
            }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            刷新数据
          </button>
          {isAdmin && (
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white"
              style={{ background: 'var(--color-status-green)' }}
            >
              <Plus size={14} />
              新建项目
            </button>
          )}
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
        {/* 活跃项目 */}
        <div className="stat-card animate-in" style={{ animationDelay: '0.1s' }}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'rgba(59,130,246,0.15)' }}>
              <LayoutDashboard size={20} color="#3b82f6" />
            </div>
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>活跃项目</span>
          </div>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
            {overview.total ?? '-'}
          </div>
          <div className="flex gap-3 mt-2 text-xs">
            <span style={{ color: '#22c55e' }}>🟢 {overview.green_count ?? 0}</span>
            <span style={{ color: '#eab308' }}>🟡 {overview.yellow_count ?? 0}</span>
            <span style={{ color: '#ef4444' }}>🔴 {overview.red_count ?? 0}</span>
          </div>
        </div>

        {/* AI 日报 */}
        <div className="stat-card animate-in" style={{ animationDelay: '0.2s' }}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'rgba(168,85,247,0.15)' }}>
              <Cpu size={20} color="#a855f7" />
            </div>
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>今日 AI 日报</span>
          </div>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
            {morningStats.total_reports ?? '-'}
          </div>
          <div className="flex gap-3 mt-2 text-xs">
            <span style={{ color: '#22c55e' }}>✅ {morningStats.pass_count ?? 0}</span>
            <span style={{ color: '#ef4444' }}>❌ {morningStats.fail_count ?? 0}</span>
            <span style={{ color: 'var(--color-text-secondary)' }}>均分 {morningStats.avg_score ?? '-'}</span>
          </div>
        </div>

        {/* 未汇报 / 卡点 */}
        <div className="stat-card animate-in" style={{ animationDelay: '0.3s' }}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'rgba(239,68,68,0.15)' }}>
              <AlertTriangle size={20} color="#ef4444" />
            </div>
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>未汇报 / 卡点</span>
          </div>
          <div
            className="text-2xl font-bold"
            style={{ color: (missingMembers.length + riskAlerts.length) > 0 ? '#ef4444' : 'var(--color-text-primary)' }}
          >
            {missingMembers.length} / {riskAlerts.length}
          </div>
          <div className="text-xs mt-2" style={{ color: 'var(--color-text-secondary)' }}>
            需管理层关注介入
          </div>
        </div>
      </div>

      {/* AI 日报明细 */}
      {/* relative z-50 — 打破 animate-in 创建的层叠上下文,让 FilterBar 下拉能盖住下方日报卡片 */}
      {morningReports.length > 0 && (
        <div className="mb-8 animate-in relative z-50" style={{ animationDelay: '0.35s' }}>
          <div className="section-title flex items-center gap-2">
            📋 AI 日报明细（{morningBriefingDate}）
            <span className="text-[11px] font-normal" style={{ color: 'var(--color-text-secondary)' }}>
              共 {morningReports.length} 条 · 显示 {filteredReports.length} 条
            </span>
            {filteredReports.length > 0 && (
              <button
                onClick={() => (isAllReportsSelected ? clearReportSelection() : selectAllReports())}
                className="ml-auto text-[11px] px-2 py-0.5 rounded"
                style={{ color: '#a855f7', border: '1px solid rgba(168,85,247,0.3)' }}
                title="全选 / 取消全选 当前显示的日报"
              >
                {isAllReportsSelected ? '取消全选' : '全选'}
              </button>
            )}
          </div>
          <FilterBar
            spec={reportFilterSpec}
            filters={reportFilters}
            setFilter={setReportFilter}
            clearFilter={clearReportFilter}
            clearAll={clearReportAll}
            activeCount={reportActiveCount}
          />
          <ListActionBar
            selectedCount={reportSelectedCount}
            onClear={clearReportSelection}
          >
            <button
              onClick={handleReportBatchDelete}
              disabled={reportDeleting}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-60"
              style={{ background: '#ef4444', color: '#fff' }}
            >
              <Trash2 size={13} />
              {reportDeleting ? '删除中...' : '批量软删'}
            </button>
          </ListActionBar>
          <div className="grid grid-cols-1 gap-3">
            {filteredReports.length === 0 && (
              <div className="stat-card text-center py-8 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                无符合筛选条件的日报
              </div>
            )}
            {filteredReports.map((r: any) => (
              <div
                key={r.id || r.member}
                className="stat-card flex items-start gap-3"
                style={{
                  padding: '14px 18px',
                  borderColor: r.id && isReportSelected(r.id) ? '#a855f7' : undefined,
                  borderWidth: r.id && isReportSelected(r.id) ? 1 : undefined,
                  borderStyle: r.id && isReportSelected(r.id) ? 'solid' : undefined,
                }}
              >
                {r.id && (
                  <input
                    type="checkbox"
                    checked={isReportSelected(r.id)}
                    onChange={() => toggleReport(r.id)}
                    className="mt-1 cursor-pointer shrink-0"
                    title="选中该条日报"
                  />
                )}
                <div className="text-center shrink-0" style={{ minWidth: 48 }}>
                  <div className="text-2xl font-bold" style={{ color: scoreColor(r.ai_score) }}>
                    {r.ai_score ?? '-'}
                  </div>
                  <span
                    className="inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] font-medium"
                    style={{
                      background: r.pass_check ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
                      color: r.pass_check ? '#22c55e' : '#ef4444',
                    }}
                  >
                    {r.pass_check ? '合格' : '退回'}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold text-sm" style={{ color: 'var(--color-text-primary)' }}>{r.member}</span>
                    <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{r.department}</span>
                  </div>
                  <div className="text-xs mb-1" style={{ color: 'var(--color-text-primary)', lineHeight: 1.6 }}>
                    {r.tasks?.slice(0, 100) || '-'}
                  </div>
                  <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{r.ai_comment}</div>
                  {r.blocker && (
                    <div className="text-xs mt-1" style={{ color: '#ef4444' }}>⛔ 卡点：{r.blocker}</div>
                  )}
                </div>
                <div className="shrink-0 text-right" style={{ minWidth: 50 }}>
                  <div
                    className="w-11 h-11 rounded-full border-[3px] flex items-center justify-center text-xs font-bold"
                    style={{
                      borderColor: (r.progress || 0) >= 80 ? '#22c55e' : (r.progress || 0) >= 50 ? '#eab308' : '#ef4444',
                      color: 'var(--color-text-primary)',
                    }}
                  >
                    {r.progress || 0}%
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 未汇报名单 */}
      {missingMembers.length > 0 && (
        <div className="mb-8 animate-in" style={{ animationDelay: '0.4s' }}>
          <div className="section-title">
            🔕 未汇报名单
            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium" style={{ background: 'rgba(234,179,8,0.15)', color: '#eab308' }}>
              {missingMembers.length}
            </span>
          </div>
          <div className="stat-card">
            <div className="flex flex-wrap gap-3">
              {missingMembers.map((m: any) => (
                <div key={m.name} className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: 'var(--color-bg-secondary)' }}>
                  <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-xs" style={{ background: 'linear-gradient(135deg, #94a3b8, #64748b)' }}>
                    {m.name.charAt(0)}
                  </div>
                  <div>
                    <div className="text-xs font-semibold" style={{ color: 'var(--color-text-primary)' }}>{m.name}</div>
                    <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{m.department}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* V2.3 临时工单看板(两张卡片:TOP5 + 占比) */}
      {tempSummary && (
        <div className="mb-8 animate-in" style={{ animationDelay: '0.42s' }}>
          <div className="section-title flex items-center gap-2">
            <Ticket size={16} color="#a855f7" />
            临时工单看板
            <span className="text-[10px] font-normal" style={{ color: 'var(--color-text-secondary)' }}>
              （{tempSummary.window?.start} → {tempSummary.window?.end} · 口径:每条日报 ≈ {tempSummary.hours_per_report}h）
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {/* 左卡:本月工时 TOP N */}
            <div className="stat-card">
              <div className="flex items-center gap-2 mb-3">
                <Trophy size={16} color="#a855f7" />
                <span className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
                  本月临时工单工时 TOP {tempSummary.top_members?.length || 0}
                </span>
              </div>
              {tempSummary.top_members?.length ? (
                <div className="space-y-2">
                  {tempSummary.top_members.map((m: any, i: number) => {
                    const maxHours = tempSummary.top_members[0]?.hours_estimated || 1
                    const pct = Math.round((m.hours_estimated / maxHours) * 100)
                    return (
                      <div key={m.user_id} className="flex items-center gap-3">
                        <div
                          className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0"
                          style={{
                            background:
                              i === 0
                                ? '#fbbf24'
                                : i === 1
                                  ? '#94a3b8'
                                  : i === 2
                                    ? '#d97706'
                                    : 'var(--color-bg-secondary)',
                            color: i < 3 ? '#fff' : 'var(--color-text-secondary)',
                          }}
                        >
                          {i + 1}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between text-xs mb-1">
                            <span style={{ color: 'var(--color-text-primary)' }}>
                              {m.user_name}
                              <span className="ml-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                                · {m.department || '—'}
                              </span>
                            </span>
                            <span style={{ color: '#a855f7', fontWeight: 600 }}>
                              {m.hours_estimated}h
                              <span className="ml-1 text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
                                ({m.report_count} 条)
                              </span>
                            </span>
                          </div>
                          <div
                            className="h-1.5 rounded-full"
                            style={{ background: 'var(--color-bg-secondary)' }}
                          >
                            <div
                              className="h-full rounded-full transition-all"
                              style={{
                                width: `${pct}%`,
                                background: 'linear-gradient(90deg, #a855f7, #6366f1)',
                              }}
                            />
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <div className="text-xs py-6 text-center" style={{ color: 'var(--color-text-secondary)' }}>
                  本月暂无临时工单数据
                </div>
              )}
            </div>

            {/* 右卡:临时 vs 主干 工时占比环形图 */}
            <div className="stat-card">
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
                  临时工单 vs 主干项目 · 工时占比
                </span>
              </div>
              {tempSummary.ratio?.total_hours > 0 ? (
                <div className="flex items-center gap-6">
                  {/* conic-gradient 环形图 */}
                  <div
                    className="w-32 h-32 rounded-full relative shrink-0"
                    style={{
                      background: `conic-gradient(#a855f7 0% ${tempSummary.ratio.temp_pct}%, #3b82f6 ${tempSummary.ratio.temp_pct}% 100%)`,
                    }}
                  >
                    <div
                      className="absolute inset-3 rounded-full flex flex-col items-center justify-center"
                      style={{ background: 'var(--color-bg-card)' }}
                    >
                      <div className="text-lg font-bold" style={{ color: '#a855f7' }}>
                        {tempSummary.ratio.temp_pct}%
                      </div>
                      <div className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
                        临时占比
                      </div>
                    </div>
                  </div>
                  {/* 图例 */}
                  <div className="flex-1 space-y-3 text-xs">
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2" style={{ color: 'var(--color-text-primary)' }}>
                        <span className="w-3 h-3 rounded-sm" style={{ background: '#a855f7' }} />
                        🎫 临时工单
                      </span>
                      <span style={{ color: '#a855f7', fontWeight: 600 }}>
                        {tempSummary.ratio.temp_hours}h
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="flex items-center gap-2" style={{ color: 'var(--color-text-primary)' }}>
                        <span className="w-3 h-3 rounded-sm" style={{ background: '#3b82f6' }} />
                        📁 主干项目
                      </span>
                      <span style={{ color: '#3b82f6', fontWeight: 600 }}>
                        {tempSummary.ratio.main_hours}h
                      </span>
                    </div>
                    <div className="pt-2 mt-2 text-[11px]" style={{ borderTop: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}>
                      合计 <span style={{ color: 'var(--color-text-primary)', fontWeight: 600 }}>{tempSummary.ratio.total_hours}h</span>
                      {tempSummary.ratio.temp_pct > 30 && (
                        <span className="block mt-1" style={{ color: '#eab308' }}>
                          ⚠️ 临时工单占比偏高,建议关注主干推进
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-xs py-6 text-center" style={{ color: 'var(--color-text-secondary)' }}>
                  本月暂无项目维度的工时数据
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 项目健康矩阵 */}
      <div className="mb-8 animate-in" style={{ animationDelay: '0.45s' }}>
        <div className="section-title">项目健康矩阵</div>
        <div className="grid grid-cols-1 gap-4">
          {projects.map((p: any) => (
            <div
              key={p.project_id}
              className="stat-card cursor-pointer flex items-center gap-5"
              onClick={() => router.push(`/project/${p.project_id}`)}
            >
              <div className="w-3 h-3 rounded-full shrink-0" style={{ background: healthColor(p.health_status) }} />
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-sm" style={{ color: 'var(--color-text-primary)' }}>
                  {p.code} · {p.name}
                </div>
                <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                  第{p.current_stage}阶段「{p.stage_name}」 · {trackLabel(p.track)}
                </div>
              </div>
              <div className="text-right shrink-0">
                <div className="text-lg font-bold" style={{ color: healthColor(p.health_status) }}>{p.health_score}</div>
                <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>距交付 {p.days_to_deadline}天</div>
              </div>
              <ArrowRight size={16} color="#4b5563" />
            </div>
          ))}
        </div>
      </div>

      {/* 风险阻碍池 */}
      <div className="animate-in" style={{ animationDelay: '0.5s' }}>
        <div className="section-title">
          风险阻碍池
          {riskAlerts.length > 0 && (
            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium" style={{ background: 'rgba(239,68,68,0.15)', color: '#ef4444' }}>
              {riskAlerts.length}
            </span>
          )}
        </div>
        {riskAlerts.length === 0 ? (
          <div className="text-center py-12" style={{ color: 'var(--color-text-secondary)' }}>
            <CheckCircle size={48} className="mx-auto mb-3 opacity-50" />
            <p>暂无未解除的风险卡点 🎉</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {riskAlerts.map((alert: any) => (
              <div key={alert.id} className="stat-card flex items-start gap-4">
                <AlertTriangle size={20} color="#ef4444" className="mt-0.5 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm" style={{ color: 'var(--color-text-primary)' }}>{alert.title}</div>
                  <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                    {alert.department} · {alert.reporter} · {alert.created_at}
                  </div>
                  <div className="text-xs mt-2" style={{ color: 'var(--color-text-secondary)' }}>{alert.description}</div>
                </div>
                <button
                  onClick={() => {
                    toast.success('已标记为已解决')
                    setRiskAlerts((prev) => prev.filter((a) => a.id !== alert.id))
                  }}
                  className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium"
                  style={{ border: '1px solid var(--color-status-green)', color: 'var(--color-status-green)' }}
                >
                  标记解决
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 新建项目弹窗 */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setShowCreate(false)}>
          <div
            className="w-full max-w-md rounded-2xl p-6"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold mb-5" style={{ color: 'var(--color-text-primary)' }}>新建项目</h2>
            <div className="space-y-4">
              {/* V2.3 临时工单项目复选框 */}
              <label
                className="flex items-start gap-2.5 p-3 rounded-lg cursor-pointer transition-colors"
                style={{
                  background: projectForm.is_temporary ? 'rgba(168,85,247,0.12)' : 'var(--color-bg-secondary)',
                  border: `1px solid ${projectForm.is_temporary ? '#a855f7' : 'var(--color-border-subtle)'}`,
                }}
              >
                <input
                  type="checkbox"
                  checked={projectForm.is_temporary}
                  onChange={(e) => {
                    const next = e.target.checked
                    // 联动:勾上时把 track 默认重置为 support;取消时回 dual
                    setProjectForm({
                      ...projectForm,
                      is_temporary: next,
                      track: next ? 'support' : 'dual',
                    })
                  }}
                  className="mt-0.5"
                />
                <div className="flex-1">
                  <div className="text-sm font-medium flex items-center gap-1.5" style={{ color: 'var(--color-text-primary)' }}>
                    <Ticket size={14} />
                    临时工单项目(轻量模式)
                  </div>
                  <div className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                    用于承载日常 bug、改价、临时维护类零散工单。<br />
                    跳过 IPD 5 阶段初始化,不进项目健康矩阵,自动生成 Backlog 占位。
                  </div>
                </div>
              </label>

              {[
                { label: '项目名称', key: 'name', placeholder: projectForm.is_temporary ? '例如:日常支撑与临时工单' : '例如:206样机研发及落地', type: 'text' },
                { label: '项目编号', key: 'code', placeholder: projectForm.is_temporary ? '留空则自动生成 (如 P2026-T01)' : '留空则自动生成 (如 P2026-002)', type: 'text' },
              ].map((f) => (
                <div key={f.key}>
                  <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>{f.label}</label>
                  <input
                    type={f.type}
                    value={(projectForm as any)[f.key]}
                    onChange={(e) => setProjectForm({ ...projectForm, [f.key]: e.target.value })}
                    placeholder={f.placeholder}
                    className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                    style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                  />
                </div>
              ))}
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>项目描述 / 任务简述</label>
                <textarea
                  value={projectForm.description}
                  onChange={(e) => setProjectForm({ ...projectForm, description: e.target.value })}
                  rows={2}
                  placeholder={projectForm.is_temporary ? '简要描述该临时工单的任务内容...' : '输入项目背景或描述...'}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>轨道</label>
                <select
                  value={projectForm.track}
                  onChange={(e) => setProjectForm({ ...projectForm, track: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                >
                  {(projectForm.is_temporary ? TEMP_TRACK_OPTIONS : MAIN_TRACK_OPTIONS).map((t) => (
                    <option key={t} value={t}>
                      {TRACK_LABELS[t]}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>计划交付时间</label>
                <input
                  type="date"
                  value={projectForm.planned_launch_date}
                  onChange={(e) => setProjectForm({ ...projectForm, planned_launch_date: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
              {/* 临时项目只隐藏预算 */}
              {!projectForm.is_temporary && (
                <>
                  <div>
                    <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>预算总额(元)</label>
                    <input
                      type="number"
                      value={projectForm.budget_total}
                      onChange={(e) => setProjectForm({ ...projectForm, budget_total: Number(e.target.value) || 0 })}
                      className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                      style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                    />
                  </div>
                </>
              )}
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded-lg text-sm"
                style={{ color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}
              >
                取消
              </button>
              <button
                onClick={handleCreateProject}
                disabled={submitting}
                className="px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-60"
                style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
              >
                {submitting ? '提交中...' : '立项'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
