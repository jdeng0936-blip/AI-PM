/**
 * app/project/[id]/page.tsx — IPD 项目看板 (port from Vue ProjectDetail.vue)
 */
'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { getProject, getProjectMembers, getGateReviews, submitGateReview, addProjectMember } from '@/api/projects'
import { getProjectSprints, createSprint, startSprint, completeSprint } from '@/api/sprints'
import { toast } from 'sonner'
import { RefreshCw, Users, CheckCircle, Shield, Plus, Play, Check } from 'lucide-react'

const GATE_NAMES = ['立项评审 (G0)', '需求评审 (G1)', '设计评审 (G2)', '试产评审 (G3)', '量产评审 (G4)', '结项 (G5)']

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [loading, setLoading] = useState(false)
  const [project, setProject] = useState<any>(null)
  const [members, setMembers] = useState<any[]>([])
  const [sprints, setSprints] = useState<any[]>([])
  const [gates, setGates] = useState<any[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'sprints' | 'gates' | 'members'>('overview')

  const fetchAll = useCallback(async () => {
    if (!id || id === 'default') return
    setLoading(true)
    try {
      const [p, m, s, g] = await Promise.allSettled([
        getProject(id), getProjectMembers(id), getProjectSprints(id), getGateReviews(id),
      ])
      if (p.status === 'fulfilled') setProject(p.value as any)
      if (m.status === 'fulfilled') setMembers((m.value as any) || [])
      if (s.status === 'fulfilled') setSprints(Array.isArray(s.value) ? s.value as any[] : [])
      if (g.status === 'fulfilled') setGates(Array.isArray(g.value) ? g.value as any[] : [])
    } finally { setLoading(false) }
  }, [id])

  useEffect(() => { fetchAll() }, [fetchAll])

  const healthColor = (s: string) => ({ green: '#22c55e', yellow: '#eab308', red: '#ef4444' }[s] || '#4b5563')
  const tabs = [
    { key: 'overview', label: '概览' },
    { key: 'sprints', label: 'Sprint' },
    { key: 'gates', label: '门禁' },
    { key: 'members', label: '成员' },
  ]

  if (id === 'default') {
    return (
      <div className="page-container">
        <div className="text-center py-20" style={{ color: 'var(--color-text-secondary)' }}>
          <Shield size={48} className="mx-auto mb-3 opacity-30" />
          <p>请先从监控台选择一个项目进入 IPD 看板</p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-container">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 animate-in">
        <div>
          <div className="flex items-center gap-3">
            {project && <div className="w-3 h-3 rounded-full" style={{ background: healthColor(project.health_status) }} />}
            <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>{project?.name || '加载中...'}</h1>
          </div>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            {project ? `${project.code} · ${project.track === 'dual' ? '软硬双轨' : project.track} · 第${project.current_stage}阶段` : ''}
          </p>
        </div>
        <button onClick={fetchAll} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium" style={{ border: '1px solid var(--color-brand-blue)', color: 'var(--color-brand-blue)' }}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />刷新
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 p-1 rounded-lg" style={{ background: 'var(--color-bg-secondary)' }}>
        {tabs.map((t) => (
          <button key={t.key} onClick={() => setActiveTab(t.key as any)} className="px-4 py-2 rounded-md text-xs font-medium transition-colors" style={{ background: activeTab === t.key ? 'var(--color-bg-card)' : 'transparent', color: activeTab === t.key ? 'var(--color-text-primary)' : 'var(--color-text-secondary)' }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === 'overview' && project && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 animate-in">
          <div className="stat-card">
            <div className="section-title">🏗️ 项目信息</div>
            <div className="space-y-3 text-sm">
              {[['项目名称', project.name], ['项目编号', project.code], ['轨道', project.track === 'dual' ? '软硬双轨' : project.track], ['当前阶段', `第${project.current_stage}阶段`], ['计划交付', project.planned_launch_date || '-'], ['健康分', project.health_score]].map(([l, v]: any) => (
                <div key={l} className="flex justify-between">
                  <span style={{ color: 'var(--color-text-secondary)' }}>{l}</span>
                  <span style={{ color: 'var(--color-text-primary)' }}>{v}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="stat-card">
            <div className="section-title">👥 团队概况</div>
            <div className="text-2xl font-bold mb-3" style={{ color: 'var(--color-text-primary)' }}>{members.length} 人</div>
            <div className="flex flex-wrap gap-2">
              {members.slice(0, 8).map((m: any) => (
                <div key={m.user_id || m.name} className="flex items-center gap-2 px-2 py-1 rounded-md" style={{ background: 'var(--color-bg-secondary)' }}>
                  <div className="w-6 h-6 rounded-full flex items-center justify-center text-white text-[10px]" style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}>{m.name?.charAt(0)}</div>
                  <span className="text-xs" style={{ color: 'var(--color-text-primary)' }}>{m.name}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Sprints */}
      {activeTab === 'sprints' && (
        <div className="animate-in">
          {sprints.length === 0 ? (
            <div className="text-center py-16" style={{ color: 'var(--color-text-secondary)' }}>
              <Play size={48} className="mx-auto mb-3 opacity-30" />
              <p>暂无 Sprint</p>
            </div>
          ) : (
            <div className="space-y-4">
              {sprints.map((s: any) => (
                <div key={s.id} className="stat-card flex items-center gap-4">
                  <div className="flex-1">
                    <div className="font-semibold text-sm" style={{ color: 'var(--color-text-primary)' }}>{s.goal || `Sprint ${s.sprint_number}`}</div>
                    <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>{s.start_date} → {s.end_date} · {s.status}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-lg font-bold" style={{ color: 'var(--color-text-primary)' }}>{s.story_points_done ?? 0}/{s.story_points_total ?? 0}</div>
                    <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>故事点</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Gates */}
      {activeTab === 'gates' && (
        <div className="animate-in">
          <div className="space-y-3">
            {GATE_NAMES.map((name, i) => {
              const gate = gates.find((g: any) => g.gate_number === i)
              return (
                <div key={i} className="stat-card flex items-center gap-4">
                  <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: gate?.result === 'pass' ? 'rgba(34,197,94,0.15)' : 'var(--color-bg-secondary)', color: gate?.result === 'pass' ? '#22c55e' : 'var(--color-text-muted)' }}>
                    {gate?.result === 'pass' ? <Check size={16} /> : `G${i}`}
                  </div>
                  <div className="flex-1">
                    <div className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>{name}</div>
                    {gate && <div className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>{gate.review_date} · {gate.reviewer}</div>}
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium" style={{ background: gate?.result === 'pass' ? 'rgba(34,197,94,0.15)' : 'var(--color-bg-secondary)', color: gate?.result === 'pass' ? '#22c55e' : 'var(--color-text-muted)' }}>
                    {gate?.result === 'pass' ? '已通过' : '待审'}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Members */}
      {activeTab === 'members' && (
        <div className="animate-in">
          <div className="stat-card">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                  {['姓名', '部门', '角色', '加入时间'].map((h) => (
                    <th key={h} className="text-left py-3 px-3 text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {members.map((m: any) => (
                  <tr key={m.user_id || m.name} style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    <td className="py-3 px-3 flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[10px]" style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}>{m.name?.charAt(0)}</div>
                      {m.name}
                    </td>
                    <td className="py-3 px-3 text-xs">{m.department}</td>
                    <td className="py-3 px-3 text-xs">{m.project_role || m.role}</td>
                    <td className="py-3 px-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{m.joined_at || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
