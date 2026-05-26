/**
 * app/project/[id]/page.tsx — IPD 项目看板 (port from Vue ProjectDetail.vue)
 */
'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import { getProject, getProjectMembers, getGateReviews, addProjectMember, updateStage } from '@/api/projects'
import { getUsers } from '@/api/users'
import { getProjectSprints } from '@/api/sprints'
import { trackLabel } from '@/lib/project-track'
import { toast } from 'sonner'
import { RefreshCw, Users, CheckCircle, Shield, Plus, Play, Check, Lock, Target, Calendar, Pencil } from 'lucide-react'

const STAGE_STATUS_MAP: Record<string, { icon: any; color: string; label: string }> = {
  green:  { icon: CheckCircle, color: '#22c55e', label: '进行中' },
  yellow: { icon: Target,      color: '#eab308', label: '有风险' },
  red:    { icon: Target,      color: '#ef4444', label: '严重滞后' },
  locked: { icon: Lock,        color: '#4b5563', label: '锁定' },
}

const MS_STATUS_ICON: Record<string, string> = {
  done: '✅', in_progress: '🟡', pending: '⬜', blocked: '🔴',
}

const GATE_NAMES = ['立项评审 (G0)', '需求评审 (G1)', '设计评审 (G2)', '试产评审 (G3)', '量产评审 (G4)', '结项 (G5)']

export default function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [loading, setLoading] = useState(false)
  const [project, setProject] = useState<any>(null)
  const [members, setMembers] = useState<any[]>([])
  const [stages, setStages] = useState<any[]>([])
  const [sprints, setSprints] = useState<any[]>([])
  const [gates, setGates] = useState<any[]>([])
  const [activeTab, setActiveTab] = useState<'overview' | 'sprints' | 'gates' | 'members'>('overview')
  const [allUsers, setAllUsers] = useState<any[]>([])
  const [showAddMember, setShowAddMember] = useState(false)
  const [addingMember, setAddingMember] = useState(false)
  const [addMemberForm, setAddMemberForm] = useState({ user_id: '', role: '' })
  const [editingStage, setEditingStage] = useState<any>(null)
  const [editMilestones, setEditMilestones] = useState<any[]>([])
  const [savingMs, setSavingMs] = useState(false)

  const fetchAll = useCallback(async () => {
    if (!id || id === 'default') return
    setLoading(true)
    try {
      const [p, m, s, g] = await Promise.allSettled([
        getProject(id), getProjectMembers(id), getProjectSprints(id), getGateReviews(id),
      ])
      if (p.status === 'fulfilled') {
        const resp = p.value as any
        setProject(resp?.project ?? resp)
        if (resp?.stages) setStages(resp.stages)
      }
      if (m.status === 'fulfilled') setMembers((m.value as any) || [])
      if (s.status === 'fulfilled') setSprints(Array.isArray(s.value) ? s.value as any[] : [])
      if (g.status === 'fulfilled') setGates(Array.isArray(g.value) ? g.value as any[] : [])
    } finally { setLoading(false) }
  }, [id])

  useEffect(() => { fetchAll() }, [fetchAll])

  // 打开弹窗时加载用户列表
  useEffect(() => {
    if (showAddMember && allUsers.length === 0) {
      getUsers({ page_size: 100 }).then((res: any) => {
        setAllUsers(res?.items || res || [])
      }).catch(() => {})
    }
  }, [showAddMember, allUsers.length])

  async function handleAddMember() {
    if (!addMemberForm.user_id) return
    setAddingMember(true)
    try {
      await addProjectMember(id, {
        project_id: id,
        user_id: addMemberForm.user_id,
        track: 'software',
        role_in_project: addMemberForm.role || '成员',
      })
      toast.success('成员添加成功')
      setShowAddMember(false)
      setAddMemberForm({ user_id: '', role: '' })
      fetchAll()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      const msg = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((d: any) => d.msg).join('; ') : '添加失败'
      toast.error(msg)
    } finally {
      setAddingMember(false)
    }
  }

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
            {project ? `${project.code} · ${trackLabel(project.track)} · 第${project.current_stage}阶段` : ''}
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
        <div className="space-y-5 animate-in">
          {/* Row 1: 项目信息 + 团队 */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="stat-card">
              <div className="section-title">🏗️ 项目信息</div>
              <div className="space-y-3 text-sm">
                {[['项目名称', project.name], ['项目编号', project.code], ['轨道', trackLabel(project.track)], ['当前阶段', `第${project.current_stage}阶段`], ['计划交付', project.planned_launch_date || '-'], ['健康分', project.health_score]].map(([l, v]: any) => (
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

          {/* Row 2: 阶段时间线 */}
          {stages.length > 0 && (
            <div className="stat-card">
              <div className="section-title">📋 项目阶段进度</div>
              <div className="space-y-3 mt-3">
                {stages.map((st: any) => {
                  const status = STAGE_STATUS_MAP[st.health_status] || STAGE_STATUS_MAP.locked
                  const StatusIcon = status.icon
                  const isCurrent = st.stage_number === project.current_stage
                  return (
                    <div key={st.id} className="rounded-lg px-4 py-3" style={{
                      background: isCurrent ? 'rgba(99,102,241,0.08)' : 'var(--color-bg-secondary)',
                      border: isCurrent ? '1px solid rgba(99,102,241,0.3)' : '1px solid transparent',
                    }}>
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <StatusIcon size={14} style={{ color: status.color }} />
                          <span className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
                            {st.stage_number}. {st.stage_name}
                          </span>
                          {isCurrent && (
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-medium" style={{ background: 'rgba(99,102,241,0.15)', color: '#6366f1' }}>当前</span>
                          )}
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                            {st.planned_start} → {st.planned_end}
                          </span>
                          <span className="text-xs font-medium" style={{ color: status.color }}>
                            {st.health_status === 'locked' ? '🔒' : `${st.progress_pct}%`}
                          </span>
                        </div>
                      </div>
                      {/* 进度条 */}
                      <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.06)' }}>
                        <div className="h-full rounded-full transition-all" style={{
                          width: `${st.health_status === 'locked' ? 0 : st.progress_pct}%`,
                          background: `linear-gradient(90deg, ${status.color}, ${status.color}88)`,
                        }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Row 3: 当前阶段里程碑 */}
          {(() => {
            const currentStage = stages.find((st: any) => st.stage_number === project.current_stage)
            const milestones = currentStage?.milestones || []
            if (milestones.length === 0) return null
            const doneCount = milestones.filter((m: any) => m.status === 'done').length
            return (
              <div className="stat-card">
                <div className="flex items-center justify-between">
                  <div className="section-title">🎯 当前阶段里程碑 — {currentStage?.stage_name}</div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                      {doneCount}/{milestones.length} 已完成
                    </span>
                    <button onClick={() => { setEditingStage(currentStage); setEditMilestones(JSON.parse(JSON.stringify(milestones))) }} className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium" style={{ border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}>
                      <Pencil size={11} />编辑
                    </button>
                  </div>
                </div>
                <div className="space-y-2 mt-3">
                  {milestones.map((ms: any, i: number) => (
                    <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg" style={{ background: 'var(--color-bg-secondary)' }}>
                      <div className="flex items-center gap-2">
                        <span className="text-sm">{MS_STATUS_ICON[ms.status] || '⬜'}</span>
                        <span className="text-sm" style={{
                          color: ms.status === 'done' ? 'var(--color-text-secondary)' : 'var(--color-text-primary)',
                          textDecoration: ms.status === 'done' ? 'line-through' : 'none',
                        }}>{ms.name}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Calendar size={11} style={{ color: 'var(--color-text-muted)' }} />
                        <span className="text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
                          {ms.planned_date || '-'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })()}
        </div>
      )}

      {/* 里程碑编辑弹窗 */}
      {editingStage && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}>
          <div className="w-full max-w-lg mx-4 rounded-2xl p-6 max-h-[80vh] overflow-y-auto" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
            <h3 className="text-lg font-bold mb-4" style={{ color: 'var(--color-text-primary)' }}>编辑里程碑 — {editingStage.stage_name}</h3>
            <div className="space-y-3">
              {editMilestones.map((ms: any, i: number) => (
                <div key={i} className="rounded-lg p-3" style={{ background: 'var(--color-bg-secondary)' }}>
                  <div className="grid grid-cols-[1fr_130px_100px] gap-2 items-center">
                    <input value={ms.name} onChange={e => { const arr = [...editMilestones]; arr[i] = { ...arr[i], name: e.target.value }; setEditMilestones(arr) }} className="px-2 py-1.5 rounded text-sm" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }} />
                    <input type="date" value={ms.planned_date || ''} onChange={e => { const arr = [...editMilestones]; arr[i] = { ...arr[i], planned_date: e.target.value }; setEditMilestones(arr) }} className="px-2 py-1.5 rounded text-xs" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }} />
                    <select value={ms.status} onChange={e => { const arr = [...editMilestones]; arr[i] = { ...arr[i], status: e.target.value }; setEditMilestones(arr) }} className="px-2 py-1.5 rounded text-xs" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>
                      <option value="pending">待开始</option>
                      <option value="in_progress">进行中</option>
                      <option value="done">已完成</option>
                      <option value="blocked">受阻</option>
                    </select>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-3 mt-5">
              <button onClick={() => setEditingStage(null)} className="px-4 py-2 rounded-lg text-xs font-medium" style={{ border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}>取消</button>
              <button disabled={savingMs} onClick={async () => {
                setSavingMs(true)
                try {
                  await updateStage(editingStage.id, { milestones: editMilestones })
                  toast.success('里程碑已更新')
                  setEditingStage(null)
                  fetchAll()
                } catch (e: any) {
                  const d = e?.response?.data?.detail
                  toast.error(typeof d === 'string' ? d : '保存失败')
                } finally { setSavingMs(false) }
              }} className="px-4 py-2 rounded-lg text-xs font-medium text-white disabled:opacity-50" style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}>
                {savingMs ? '保存中...' : '保存'}
              </button>
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
          <div className="flex items-center justify-between mb-4">
            <div className="text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>
              共 {members.length} 名成员
            </div>
            <button
              onClick={() => setShowAddMember(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white"
              style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
            >
              <Plus size={14} />添加成员
            </button>
          </div>

          <div className="stat-card">
            {members.length === 0 ? (
              <div className="text-center py-12" style={{ color: 'var(--color-text-secondary)' }}>
                <Users size={40} className="mx-auto mb-3 opacity-30" />
                <p className="text-sm">暂无成员，点击上方按钮添加</p>
              </div>
            ) : (
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
                      <td className="py-3 px-3 text-xs">{m.role_in_project || m.project_role || m.role || '-'}</td>
                      <td className="py-3 px-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{m.joined_at || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* 添加成员弹窗 */}
      {showAddMember && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }}>
          <div className="w-full max-w-md mx-4 rounded-2xl p-6" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
            <h3 className="text-lg font-bold mb-4" style={{ color: 'var(--color-text-primary)' }}>添加项目成员</h3>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>选择用户</label>
                <select
                  value={addMemberForm.user_id}
                  onChange={e => setAddMemberForm({ ...addMemberForm, user_id: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                >
                  <option value="">-- 请选择 --</option>
                  {allUsers.filter(u => !members.some((m: any) => m.user_id === u.id)).map((u: any) => (
                    <option key={u.id} value={u.id}>{u.name} ({u.department || '未分配'})</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>项目角色</label>
                <input
                  value={addMemberForm.role}
                  onChange={e => setAddMemberForm({ ...addMemberForm, role: e.target.value })}
                  placeholder="如：负责人、开发、测试、产品"
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setShowAddMember(false)} className="px-4 py-2 rounded-lg text-xs font-medium" style={{ border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}>取消</button>
              <button
                disabled={!addMemberForm.user_id || addingMember}
                onClick={handleAddMember}
                className="px-4 py-2 rounded-lg text-xs font-medium text-white disabled:opacity-50"
                style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
              >
                {addingMember ? '添加中...' : '确认添加'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
