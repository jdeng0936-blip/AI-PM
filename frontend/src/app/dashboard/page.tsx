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

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'
import { getMorningBriefing, getRiskAlerts } from '@/api/dashboard'
import { getProjectsOverview, createProject } from '@/api/projects'
import { toast } from 'sonner'
import {
  LayoutDashboard,
  Cpu,
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  RefreshCw,
  Plus,
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

  // 新建项目弹窗
  const [showCreate, setShowCreate] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [projectForm, setProjectForm] = useState({
    name: '',
    code: '',
    track: 'dual',
    planned_launch_date: '',
    budget_total: 100000,
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
      const [ov, br, ra] = await Promise.allSettled([
        getProjectsOverview(),
        getMorningBriefing(),
        getRiskAlerts(),
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
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  async function handleCreateProject() {
    setSubmitting(true)
    try {
      await createProject(projectForm)
      toast.success(`项目 ${projectForm.code} 立项成功`)
      setShowCreate(false)
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
      {morningReports.length > 0 && (
        <div className="mb-8 animate-in" style={{ animationDelay: '0.35s' }}>
          <div className="section-title">📋 AI 日报明细（{morningBriefingDate}）</div>
          <div className="grid grid-cols-1 gap-3">
            {morningReports.map((r: any) => (
              <div key={r.member} className="stat-card flex items-start gap-4" style={{ padding: '14px 18px' }}>
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
                  第{p.current_stage}阶段「{p.stage_name}」 · {p.track === 'dual' ? '软硬双轨' : p.track}
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
              {[
                { label: '项目名称', key: 'name', placeholder: '例如：206样机研发及落地', type: 'text' },
                { label: '项目编号', key: 'code', placeholder: 'P2026-002', type: 'text' },
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
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>轨道</label>
                <select
                  value={projectForm.track}
                  onChange={(e) => setProjectForm({ ...projectForm, track: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                >
                  <option value="dual">软硬双轨</option>
                  <option value="software">纯软件</option>
                  <option value="hardware">纯硬件</option>
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>计划交付</label>
                <input
                  type="date"
                  value={projectForm.planned_launch_date}
                  onChange={(e) => setProjectForm({ ...projectForm, planned_launch_date: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
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
