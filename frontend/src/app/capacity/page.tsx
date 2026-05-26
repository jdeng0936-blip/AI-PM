/**
 * app/capacity/page.tsx — 资源负载水位看板
 *
 * 布局:
 * - 顶部:项目+Sprint 选择 + 全员水位分布徽标 + 刷新快照
 * - 中:个人水位条列表(过载/高位/健康/闲置)
 * - 右上:部门级聚合柱状图
 * - 右下:AI 调配建议
 */
'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  ArrowRight, Loader2, RefreshCw, Sparkles, TrendingUp, Users, Zap,
  AlertOctagon, ThermometerSun, Activity,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend, Cell,
} from 'recharts'
import { getProjectsOverview } from '@/api/projects'
import { listSprints, type SprintSummary } from '@/api/sprint-tracking'
import {
  getSprintCapacity, snapshotSprintCapacity, getRebalance,
  getDepartmentSummary,
  type SprintCapacityResponse, type MemberCapacity, type RebalanceResponse,
  type DeptSummaryResponse, type CapacityLevel,
} from '@/api/capacity'
import { useAuthStore } from '@/stores/use-auth-store'


const LEVEL_META: Record<CapacityLevel, { label: string; color: string; bg: string }> = {
  overload: { label: '过载', color: '#ef4444', bg: 'rgba(239,68,68,0.15)' },
  high:     { label: '高位', color: '#f59e0b', bg: 'rgba(245,158,11,0.15)' },
  healthy:  { label: '健康', color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
  idle:     { label: '闲置', color: '#3b82f6', bg: 'rgba(59,130,246,0.15)' },
}


export default function CapacityPage() {
  const { userRole } = useAuthStore()
  const canWrite = userRole === 'admin' || userRole === 'manager'

  const [projects, setProjects] = useState<any[]>([])
  const [projectId, setProjectId] = useState('')
  const [sprints, setSprints] = useState<SprintSummary[]>([])
  const [sprintId, setSprintId] = useState('')

  const [capacity, setCapacity] = useState<SprintCapacityResponse | null>(null)
  const [deptSummary, setDeptSummary] = useState<DeptSummaryResponse | null>(null)
  const [rebalance, setRebalance] = useState<RebalanceResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [rebalanceLoading, setRebalanceLoading] = useState(false)

  useEffect(() => {
    getProjectsOverview()
      .then((res: any) => {
        const list = res?.projects || res || []
        setProjects(list)
        if (list.length > 0) setProjectId(list[0].id || list[0].code)
      })
      .catch(() => toast.error('加载项目失败'))
  }, [])

  useEffect(() => {
    if (!projectId) return
    setSprints([])
    setSprintId('')
    listSprints(projectId)
      .then((list) => {
        setSprints(list)
        const active = list.find((s) => s.status === 'active') || list[list.length - 1]
        if (active) setSprintId(active.sprint_id)
      })
      .catch(() => toast.error('加载 Sprint 失败'))
  }, [projectId])

  const reload = useCallback(async () => {
    if (!sprintId) return
    setLoading(true)
    try {
      const [cap, dept] = await Promise.all([
        getSprintCapacity(sprintId),
        getDepartmentSummary(sprintId).catch(() => null),
      ])
      setCapacity(cap)
      setDeptSummary(dept)
    } catch {
      toast.error('加载水位失败')
    } finally {
      setLoading(false)
    }
  }, [sprintId])

  useEffect(() => { void reload() }, [reload])

  async function handleSnapshot() {
    if (!sprintId) return
    setRefreshing(true)
    try {
      const r = await snapshotSprintCapacity(sprintId)
      toast.success(`已刷新 ${r.snapshot_count} 条快照`)
      await reload()
    } catch {
      toast.error('刷新失败')
    } finally {
      setRefreshing(false)
    }
  }

  async function handleRebalance() {
    if (!sprintId) return
    setRebalanceLoading(true)
    try {
      const r = await getRebalance(sprintId)
      setRebalance(r)
      if (r.moves.length === 0) {
        toast.success('无需调配:无过载或无可移动任务')
      }
    } catch {
      toast.error('生成调配建议失败')
    } finally {
      setRebalanceLoading(false)
    }
  }

  const sortedMembers = useMemo(() => {
    if (!capacity) return []
    return [...capacity.members].sort((a, b) => b.utilization - a.utilization)
  }, [capacity])

  return (
    <div className="page-container space-y-4">
      {/* 顶部 */}
      <div className="flex items-center justify-between flex-wrap gap-3 animate-in">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
            🌡️ 资源水位预判
          </h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            故事点池 + 实时占用 + AI 调配建议
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <select
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm outline-none"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
          >
            {projects.map((p: any) => (
              <option key={p.id || p.code} value={p.id || p.code}>
                {p.code ? `${p.code} · ${p.name}` : p.name}
              </option>
            ))}
          </select>
          {sprints.length > 0 && (
            <select
              value={sprintId}
              onChange={(e) => setSprintId(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
                color: 'var(--color-text-primary)',
              }}
            >
              {sprints.map((s) => (
                <option key={s.sprint_id} value={s.sprint_id}>
                  Sprint #{s.sprint_number} ({s.status})
                </option>
              ))}
            </select>
          )}
          {canWrite && sprintId && (
            <button
              onClick={handleSnapshot}
              disabled={refreshing}
              className="px-3 py-2 rounded-lg text-xs flex items-center gap-1.5 disabled:opacity-50"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
                color: 'var(--color-text-primary)',
              }}
            >
              {refreshing ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              刷新快照
            </button>
          )}
          {sprintId && (
            <button
              onClick={handleRebalance}
              disabled={rebalanceLoading}
              className="px-4 py-2 rounded-lg text-xs text-white flex items-center gap-1.5 disabled:opacity-50"
              style={{ background: 'linear-gradient(135deg, #a855f7, #ec4899)' }}
            >
              {rebalanceLoading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
              AI 调配建议
            </button>
          )}
        </div>
      </div>

      {!sprintId ? (
        <EmptyState />
      ) : loading ? (
        <div className="flex justify-center py-20">
          <Loader2 size={28} className="animate-spin" style={{ color: '#6366f1' }} />
        </div>
      ) : (
        <>
          {capacity?.summary && <DistributionBar summary={capacity.summary} total={capacity.count} />}

          <div className="grid gap-4" style={{ gridTemplateColumns: '1.4fr 1fr', minHeight: '60vh' }}>
            {/* 左:个人水位条 */}
            <div className="space-y-2">
              <h3 className="text-sm font-semibold flex items-center gap-1.5" style={{ color: 'var(--color-text-primary)' }}>
                <Users size={14} /> 个人水位 ({sortedMembers.length})
              </h3>
              <div className="space-y-2">
                {sortedMembers.map((m) => (
                  <MemberRow key={m.user_id} member={m} />
                ))}
                {sortedMembers.length === 0 && (
                  <div className="stat-card text-center py-10 text-sm opacity-60">
                    当前 Sprint 没有任务分配,无法计算水位
                  </div>
                )}
              </div>
            </div>

            {/* 右:部门聚合 + 调配建议 */}
            <div className="space-y-4">
              {deptSummary && <DepartmentPanel data={deptSummary} />}
              {rebalance && <RebalancePanel data={rebalance} />}
            </div>
          </div>
        </>
      )}
    </div>
  )
}


// ────────────────────────────────────────────────────────────────


function EmptyState() {
  return (
    <div className="stat-card text-center py-16" style={{ color: 'var(--color-text-secondary)' }}>
      <ThermometerSun size={42} className="mx-auto mb-3 opacity-40" />
      <div className="text-sm">请选择项目和 Sprint 开始查看资源水位</div>
    </div>
  )
}


function DistributionBar({ summary, total }: {
  summary: { overload: number; high: number; healthy: number; idle: number }
  total: number
}) {
  const items: Array<{ k: CapacityLevel; n: number }> = [
    { k: 'overload', n: summary.overload },
    { k: 'high', n: summary.high },
    { k: 'healthy', n: summary.healthy },
    { k: 'idle', n: summary.idle },
  ]
  return (
    <div className="stat-card flex items-center flex-wrap gap-6 animate-in" style={{ padding: '12px 18px' }}>
      <div className="flex items-center gap-2">
        <ThermometerSun size={18} className="opacity-70" />
        <span className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
          团队水位分布
        </span>
        <span className="text-xs opacity-60">共 {total} 人</span>
      </div>
      <div className="flex-1 min-w-[200px]">
        <div className="flex rounded overflow-hidden" style={{ height: 14 }}>
          {items.map((it) => {
            if (it.n === 0) return null
            const w = (it.n / Math.max(total, 1)) * 100
            return (
              <div
                key={it.k}
                title={`${LEVEL_META[it.k].label}: ${it.n}`}
                style={{
                  width: `${w}%`,
                  background: LEVEL_META[it.k].color,
                  minWidth: '12px',
                }}
              />
            )
          })}
        </div>
      </div>
      <div className="flex gap-2 text-xs">
        {items.map((it) => (
          <span
            key={it.k}
            className="px-2 py-0.5 rounded flex items-center gap-1"
            style={{ background: LEVEL_META[it.k].bg, color: LEVEL_META[it.k].color }}
          >
            ●{LEVEL_META[it.k].label} {it.n}
          </span>
        ))}
      </div>
    </div>
  )
}


function MemberRow({ member }: { member: MemberCapacity }) {
  const meta = LEVEL_META[member.level]
  const utilPct = Math.round(member.utilization * 100)
  // 进度条最多 150%(>100% 显示溢出)
  const barWidth = Math.min(member.utilization * 100, 150)
  return (
    <div
      className="rounded-lg p-3"
      style={{
        background: 'var(--color-bg-card)',
        border: `1px solid ${member.level === 'overload' ? '#ef4444aa' : 'var(--color-border-subtle)'}`,
      }}
    >
      <div className="flex items-center gap-3 mb-2 flex-wrap">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
              {member.user_name}
            </span>
            <span className="text-[11px] opacity-60">{member.department}</span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded flex items-center gap-1"
              style={{ background: meta.bg, color: meta.color }}
            >
              {member.level === 'overload' ? <AlertOctagon size={9} /> : <Activity size={9} />}
              {meta.label}
            </span>
            {member.user_status !== 'active' && (
              <span className="text-[10px] px-1.5 py-0.5 rounded" style={{
                background: 'rgba(148,163,184,0.2)', color: '#94a3b8',
              }}>
                {member.user_status}
              </span>
            )}
            {member.velocity_factor !== 1 && (
              <span className="text-[10px] opacity-60" title="历史速率调整系数">
                ×{member.velocity_factor}
              </span>
            )}
          </div>
        </div>
        <div className="text-xs flex items-center gap-2 shrink-0">
          <span className="opacity-70">
            {member.allocated_points} / {member.effective_capacity}pt
          </span>
          <span style={{ color: meta.color }} className="font-semibold">
            {utilPct}%
          </span>
        </div>
      </div>
      <div
        className="rounded-full overflow-hidden relative"
        style={{ height: 7, background: 'rgba(255,255,255,0.06)' }}
      >
        {/* 100% 标记线 */}
        <div
          className="absolute top-0 bottom-0"
          style={{
            left: `${100 / 1.5}%`,
            width: 1,
            background: 'rgba(255,255,255,0.3)',
            zIndex: 1,
          }}
        />
        <div
          className="h-full transition-all"
          style={{ width: `${(barWidth / 1.5)}%`, background: meta.color }}
        />
      </div>
      {/* 任务摘要 */}
      <div className="mt-2 flex items-center gap-3 text-[11px] opacity-70 flex-wrap">
        <span>📋 {member.active_task_count} 任务</span>
        {member.blocked_task_count > 0 && (
          <span style={{ color: '#ef4444' }}>⚠️ {member.blocked_task_count} 阻塞</span>
        )}
        {member.critical_path_task_count > 0 && (
          <span style={{ color: '#fca5a5' }} className="flex items-center gap-0.5">
            <Zap size={9} /> {member.critical_path_task_count} 关键
          </span>
        )}
        {member.completed_points > 0 && (
          <span style={{ color: '#86efac' }}>✓ {member.completed_points}pt 已完成</span>
        )}
      </div>
    </div>
  )
}


function DepartmentPanel({ data }: { data: DeptSummaryResponse }) {
  if (data.count === 0) return null
  const chart = data.departments.map((d) => ({
    name: d.department,
    占用: d.total_allocated,
    容量: d.total_capacity,
  }))
  return (
    <div className="stat-card" style={{ padding: '14px 18px' }}>
      <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5" style={{ color: 'var(--color-text-primary)' }}>
        <TrendingUp size={14} /> 部门级水位
      </h3>
      <ResponsiveContainer width="100%" height={Math.max(120, data.count * 36)}>
        <BarChart data={chart} layout="vertical" margin={{ top: 5, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis type="number" tick={{ fontSize: 10, fill: '#94a3b8' }} />
          <YAxis dataKey="name" type="category" tick={{ fontSize: 10, fill: '#94a3b8' }} width={80} />
          <Tooltip
            contentStyle={{
              background: '#1e1e2e', border: '1px solid #3a3a55',
              borderRadius: 6, fontSize: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Bar dataKey="容量" fill="#6366f1" radius={[0, 2, 2, 0]} />
          <Bar dataKey="占用" radius={[0, 2, 2, 0]}>
            {data.departments.map((d, i) => (
              <Cell key={i} fill={LEVEL_META[d.level].color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="text-[11px] mt-2 space-y-1">
        {data.departments.map((d) => (
          <div key={d.department} className="flex items-center justify-between">
            <span style={{ color: LEVEL_META[d.level].color }}>● {d.department}</span>
            <span className="opacity-70">
              {d.total_allocated}/{d.total_capacity}pt · {Math.round(d.utilization * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}


function RebalancePanel({ data }: { data: RebalanceResponse }) {
  return (
    <div className="stat-card" style={{ padding: '14px 18px' }}>
      <h3 className="text-sm font-semibold mb-2 flex items-center gap-1.5" style={{ color: 'var(--color-text-primary)' }}>
        <Sparkles size={14} className="text-purple-400" /> AI 调配建议
      </h3>
      {data.moves.length === 0 ? (
        <div className="text-xs opacity-60 py-4 text-center">
          {data.overloaded.length === 0
            ? '当前无过载人员,无需调配'
            : '过载人员的任务均在关键路径上或已开始,无可移动任务'}
        </div>
      ) : (
        <>
          <div className="text-[11px] mb-2 opacity-70">
            过载 {data.overloaded.length} 人 · 闲置 {data.idle.length} 人 · 建议调配 {data.moves.length} 项任务
          </div>
          <div className="space-y-1.5">
            {data.moves.slice(0, 8).map((m, i) => (
              <div
                key={i}
                className="rounded p-2 text-xs"
                style={{
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-subtle)',
                }}
              >
                <div className="font-medium mb-1 truncate" style={{ color: 'var(--color-text-primary)' }}>
                  {m.title}
                </div>
                <div className="flex items-center gap-1 opacity-80">
                  <span style={{ color: '#ef4444' }}>{m.from_user}</span>
                  <ArrowRight size={10} />
                  <span style={{ color: '#22c55e' }}>{m.to_user}</span>
                  <span className="opacity-60 ml-auto">{m.points}pt</span>
                  {m.department_match && (
                    <span className="text-[9px] px-1 rounded" style={{
                      background: 'rgba(99,102,241,0.15)', color: '#a5b4fc',
                    }}>
                      同部门
                    </span>
                  )}
                </div>
              </div>
            ))}
            {data.moves.length > 8 && (
              <div className="text-[10px] opacity-50 text-center pt-1">
                还有 {data.moves.length - 8} 项建议未显示
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
