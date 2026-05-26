/**
 * app/sprints/page.tsx — Sprint 看板 + 燃尽图 + 关键路径
 *
 * 布局:
 * - 顶部:项目选择 + Sprint 选择 + 健康度
 * - 左:任务清单(分状态列)
 * - 右上:燃尽图(Recharts)
 * - 右下:关键路径任务 + 项目速率历史
 */
'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend, BarChart, Bar,
} from 'recharts'
import {
  Activity, AlertTriangle, CheckCircle2, Clock, Flame, Loader2,
  PauseCircle, Plus, Sparkles, Target, Trash2, Zap, X,
} from 'lucide-react'
import { getProjectsOverview } from '@/api/projects'
import {
  listSprints, listTasks, createTask, updateTask, deleteTask,
  batchDeleteTasks, batchRestoreTasks,
  getBurndown, getCriticalPath, getVelocityHistory, triggerSnapshot,
  type SprintSummary, type SprintTaskItem, type BurndownData,
  type CriticalPathResult, type VelocityHistory, type TaskStatus, type TaskPriority,
} from '@/api/sprint-tracking'
import { useAuthStore } from '@/stores/use-auth-store'
import { useMultiSelect } from '@/lib/hooks/use-multi-select'
import ListActionBar from '@/components/list-action-bar'


const STATUS_META: Record<TaskStatus, { label: string; color: string; icon: any }> = {
  todo: { label: '待开始', color: '#94a3b8', icon: Clock },
  in_progress: { label: '进行中', color: '#3b82f6', icon: Activity },
  blocked: { label: '阻塞', color: '#ef4444', icon: AlertTriangle },
  done: { label: '完成', color: '#22c55e', icon: CheckCircle2 },
  cancelled: { label: '取消', color: '#6b7280', icon: PauseCircle },
}

const PRIORITY_META: Record<TaskPriority, { label: string; color: string }> = {
  p0: { label: 'P0', color: '#ef4444' },
  p1: { label: 'P1', color: '#f59e0b' },
  p2: { label: 'P2', color: '#3b82f6' },
  p3: { label: 'P3', color: '#94a3b8' },
}


export default function SprintsPage() {
  const { userRole } = useAuthStore()
  const canWrite = userRole === 'admin' || userRole === 'manager'

  const [projects, setProjects] = useState<any[]>([])
  const [projectId, setProjectId] = useState<string>('')
  const [sprints, setSprints] = useState<SprintSummary[]>([])
  const [sprintId, setSprintId] = useState<string>('')
  const [tasks, setTasks] = useState<SprintTaskItem[]>([])
  const [burndown, setBurndown] = useState<BurndownData | null>(null)
  const [criticalPath, setCriticalPath] = useState<CriticalPathResult | null>(null)
  const [velocity, setVelocity] = useState<VelocityHistory | null>(null)
  const [loading, setLoading] = useState(false)
  const [showNewTask, setShowNewTask] = useState(false)

  // ── 初始加载项目 ──
  useEffect(() => {
    getProjectsOverview()
      .then((res: any) => {
        const list = res?.projects || res || []
        setProjects(list)
        if (list.length > 0 && !projectId) setProjectId(list[0].id || list[0].code)
      })
      .catch(() => toast.error('加载项目列表失败'))
    // 故意不把 projectId 列入依赖:本 effect 是"加载项目列表 + 默认选中第一个"
    // 一次性副作用,projectId 变化时不该重 fetch 整个 projects 列表
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ── 项目切换 → 加载 Sprint + 速率 ──
  useEffect(() => {
    if (!projectId) return
    setSprints([])
    setSprintId('')
    listSprints(projectId)
      .then((list) => {
        setSprints(list)
        // 默认选 active 或最新
        const active = list.find((s) => s.status === 'active') || list[list.length - 1]
        if (active) setSprintId(active.sprint_id)
      })
      .catch(() => toast.error('加载 Sprint 失败'))
    getVelocityHistory(projectId, 6).then(setVelocity).catch(() => setVelocity(null))
  }, [projectId])

  // ── Sprint 切换 → 加载任务 + 燃尽 + 关键路径 ──
  const reloadSprintDetail = useCallback(async () => {
    if (!sprintId) return
    setLoading(true)
    try {
      const [t, b, cp] = await Promise.all([
        listTasks(sprintId),
        getBurndown(sprintId).catch(() => null),
        getCriticalPath(sprintId).catch(() => null),
      ])
      setTasks(t)
      setBurndown(b)
      setCriticalPath(cp)
    } catch {
      toast.error('加载 Sprint 详情失败')
    } finally {
      setLoading(false)
    }
  }, [sprintId])

  useEffect(() => { void reloadSprintDetail() }, [reloadSprintDetail])

  // ── 任务状态变更 ──
  async function handleStatusChange(task: SprintTaskItem, newStatus: TaskStatus) {
    try {
      await updateTask(task.id, { status: newStatus })
      await reloadSprintDetail()
    } catch {
      toast.error('更新状态失败')
    }
  }

  async function handleDeleteTask(task: SprintTaskItem) {
    if (!confirm(`删除任务「${task.title}」?`)) return
    try {
      await deleteTask(task.id)
      await reloadSprintDetail()
    } catch {
      toast.error('删除失败')
    }
  }

  async function handleCreateTask(payload: {
    title: string; description: string; story_points: number; priority: TaskPriority
  }) {
    try {
      await createTask(sprintId, payload)
      setShowNewTask(false)
      await reloadSprintDetail()
      toast.success('任务已创建')
    } catch {
      toast.error('创建失败')
    }
  }

  async function handleManualSnapshot() {
    try {
      await triggerSnapshot(sprintId)
      await reloadSprintDetail()
      toast.success('已生成燃尽快照')
    } catch {
      toast.error('快照失败')
    }
  }

  // V2.5 Stage 2:任务多选 + 批量软删 + toast 撤销
  // useMultiSelect 监听 tasks 引用 — sprintId 切换重 fetch 后会自动清空选中态
  const taskMs = useMultiSelect(tasks, { idKey: 'id' as any })
  const [bulkActing, setBulkActing] = useState(false)

  async function handleBatchDelete() {
    const ids = Array.from(taskMs.selectedIds) as string[]
    if (ids.length === 0) return
    if (!confirm(`确定删除选中的 ${ids.length} 个任务?\n(软删,可在回收站恢复;燃尽与关键路径会自动重算)`)) return
    setBulkActing(true)
    try {
      const res = await batchDeleteTasks(ids)
      const deletedIds = res.deleted_ids ?? ids
      taskMs.clearAll()
      await reloadSprintDetail()
      toast.success(`已删除 ${res.deleted_count ?? deletedIds.length} 个任务`, {
        duration: 5000,
        action: {
          label: '撤销',
          onClick: async () => {
            try {
              const r = await batchRestoreTasks(deletedIds)
              await reloadSprintDetail()
              toast.success(`已撤销恢复 ${r.restored_count ?? deletedIds.length} 个`)
            } catch (e: any) {
              toast.error(e?.response?.data?.detail || '撤销失败')
            }
          },
        },
      })
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '批量删除失败')
    } finally {
      setBulkActing(false)
    }
  }

  const currentSprint = sprints.find((s) => s.sprint_id === sprintId)

  const tasksByStatus = useMemo(() => {
    const groups: Record<TaskStatus, SprintTaskItem[]> = {
      todo: [], in_progress: [], blocked: [], done: [], cancelled: [],
    }
    for (const t of tasks) groups[t.status].push(t)
    return groups
  }, [tasks])

  return (
    <div className="page-container space-y-4">
      <TopBar
        projects={projects}
        projectId={projectId}
        onProjectChange={setProjectId}
        sprints={sprints}
        sprintId={sprintId}
        onSprintChange={setSprintId}
        currentSprint={currentSprint}
        canWrite={canWrite}
        onSnapshot={handleManualSnapshot}
      />

      {!sprintId ? (
        <EmptyState />
      ) : loading ? (
        <div className="flex justify-center py-20">
          <Loader2 size={28} className="animate-spin" style={{ color: '#6366f1' }} />
        </div>
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr', minHeight: '70vh' }}>
          {/* 左:任务看板 */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                📋 任务清单 ({tasks.length})
              </h3>
              {canWrite && (
                <button
                  onClick={() => setShowNewTask(true)}
                  className="px-3 py-1.5 rounded text-xs text-white flex items-center gap-1"
                  style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
                >
                  <Plus size={12} /> 新建任务
                </button>
              )}
            </div>
            {/* V2.5 Stage 2:多选 ActionBar(canWrite 时才显示 checkbox 与批量操作) */}
            {canWrite && (
              <div className="relative z-40">
                <ListActionBar
                  selectedCount={taskMs.selectedCount}
                  onClear={taskMs.clearAll}
                  hint="软删后可在回收站恢复;燃尽/关键路径自动重算"
                >
                  <button
                    onClick={handleBatchDelete}
                    disabled={bulkActing}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-60"
                    style={{ background: '#ef4444', color: '#fff' }}
                  >
                    <Trash2 size={13} />
                    {bulkActing ? '处理中...' : '批量删除'}
                  </button>
                </ListActionBar>
              </div>
            )}
            <TaskBoard
              tasksByStatus={tasksByStatus}
              onStatusChange={canWrite ? handleStatusChange : undefined}
              onDelete={canWrite ? handleDeleteTask : undefined}
              selectable={canWrite}
              isSelected={taskMs.isSelected}
              onToggleSelect={taskMs.toggle}
            />
          </div>

          {/* 右:燃尽 + 关键路径 + 速率 */}
          <div className="space-y-4">
            <BurndownPanel data={burndown} />
            <CriticalPathPanel result={criticalPath} />
            <VelocityPanel data={velocity} />
          </div>
        </div>
      )}

      {showNewTask && (
        <NewTaskDialog
          onClose={() => setShowNewTask(false)}
          onSubmit={handleCreateTask}
        />
      )}
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 顶部
// ────────────────────────────────────────────────────────────────


function TopBar({
  projects, projectId, onProjectChange,
  sprints, sprintId, onSprintChange, currentSprint,
  canWrite, onSnapshot,
}: any) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-3 animate-in">
      <div>
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
          🔥 Sprint 燃尽 & 关键路径
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
          短周期故事点 + 长周期里程碑联动
        </p>
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <select
          value={projectId}
          onChange={(e) => onProjectChange(e.target.value)}
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
            onChange={(e) => onSprintChange(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm outline-none"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
          >
            {sprints.map((s: SprintSummary) => (
              <option key={s.sprint_id} value={s.sprint_id}>
                Sprint #{s.sprint_number} ({s.status})
              </option>
            ))}
          </select>
        )}
        {currentSprint && (
          <span
            className="text-xs px-2 py-1 rounded"
            style={{
              background: 'rgba(99,102,241,0.15)',
              color: '#a5b4fc',
            }}
          >
            健康度 {currentSprint.health_score}
          </span>
        )}
        {canWrite && sprintId && (
          <button
            onClick={onSnapshot}
            className="px-3 py-2 rounded-lg text-xs"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
            title="重新计算燃尽快照"
          >
            🔄 刷新快照
          </button>
        )}
      </div>
    </div>
  )
}


function EmptyState() {
  return (
    <div className="stat-card text-center py-16" style={{ color: 'var(--color-text-secondary)' }}>
      <Target size={42} className="mx-auto mb-3 opacity-40" />
      <div className="text-sm">请选择项目和 Sprint 开始查看</div>
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 任务看板
// ────────────────────────────────────────────────────────────────


function TaskBoard({
  tasksByStatus, onStatusChange, onDelete,
  selectable, isSelected, onToggleSelect,
}: {
  tasksByStatus: Record<TaskStatus, SprintTaskItem[]>
  onStatusChange?: (t: SprintTaskItem, s: TaskStatus) => void
  onDelete?: (t: SprintTaskItem) => void
  selectable?: boolean
  isSelected?: (id: string) => boolean
  onToggleSelect?: (id: string) => void
}) {
  return (
    <div className="space-y-2">
      {(['in_progress', 'blocked', 'todo', 'done'] as TaskStatus[]).map((s) => {
        const list = tasksByStatus[s]
        if (list.length === 0) return null
        const meta = STATUS_META[s]
        const Icon = meta.icon
        return (
          <div
            key={s}
            className="rounded-lg p-2.5"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
            }}
          >
            <div
              className="text-xs font-semibold mb-2 flex items-center gap-1.5"
              style={{ color: meta.color }}
            >
              <Icon size={13} />
              {meta.label} · {list.length}
            </div>
            <div className="space-y-1.5">
              {list.map((t) => (
                <TaskCard
                  key={t.id}
                  task={t}
                  onStatusChange={onStatusChange}
                  onDelete={onDelete}
                  selectable={selectable}
                  selected={isSelected ? isSelected(t.id) : false}
                  onToggleSelect={onToggleSelect}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}


function TaskCard({
  task, onStatusChange, onDelete,
  selectable, selected, onToggleSelect,
}: {
  task: SprintTaskItem
  onStatusChange?: (t: SprintTaskItem, s: TaskStatus) => void
  onDelete?: (t: SprintTaskItem) => void
  selectable?: boolean
  selected?: boolean
  onToggleSelect?: (id: string) => void
}) {
  const pmeta = PRIORITY_META[task.priority]
  return (
    <div
      className="rounded p-2 text-xs"
      style={{
        background: selected ? 'rgba(168,85,247,0.10)' : 'var(--color-bg-secondary)',
        border: selected
          ? '1px solid #a855f7'
          : task.is_on_critical_path
            ? '1px solid #ef4444aa'
            : '1px solid var(--color-border-subtle)',
      }}
    >
      <div className="flex items-start gap-2">
        {/* V2.5 Stage 2:批量选择 checkbox(canWrite 时显示) */}
        {selectable && (
          <input
            type="checkbox"
            checked={!!selected}
            onChange={() => onToggleSelect?.(task.id)}
            className="mt-1 shrink-0 cursor-pointer"
            title="选中用于批量操作"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1 flex-wrap">
            <span
              className="text-[9px] px-1.5 py-0.5 rounded font-medium"
              style={{ background: `${pmeta.color}22`, color: pmeta.color }}
            >
              {pmeta.label}
            </span>
            {task.is_on_critical_path && (
              <span
                className="text-[9px] px-1.5 py-0.5 rounded flex items-center gap-0.5"
                style={{ background: 'rgba(239,68,68,0.15)', color: '#fca5a5' }}
                title="关键路径"
              >
                <Zap size={9} /> 关键
              </span>
            )}
            <span className="text-[10px] opacity-60">{task.story_points}pt</span>
          </div>
          <div
            className="font-medium leading-snug"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {task.title}
          </div>
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          {onStatusChange && (
            <select
              value={task.status}
              onChange={(e) => onStatusChange(task, e.target.value as TaskStatus)}
              className="text-[10px] rounded px-1 py-0.5 outline-none"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
                color: 'var(--color-text-primary)',
              }}
            >
              {(Object.keys(STATUS_META) as TaskStatus[]).map((s) => (
                <option key={s} value={s}>{STATUS_META[s].label}</option>
              ))}
            </select>
          )}
          {onDelete && (
            <button
              onClick={() => onDelete(task)}
              className="text-[10px] opacity-40 hover:opacity-100 hover:text-red-400"
            >
              <X size={11} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 燃尽图
// ────────────────────────────────────────────────────────────────


function BurndownPanel({ data }: { data: BurndownData | null }) {
  if (!data) {
    return (
      <div className="stat-card text-center py-8 text-sm opacity-60">
        <Flame size={24} className="mx-auto mb-2 opacity-40" /> 暂无燃尽数据
      </div>
    )
  }

  // 合并 ideal + actual,按日期对齐
  const allDates = Array.from(new Set([
    ...data.ideal_line.map((p) => p.date),
    ...data.actual_line.map((p) => p.date),
  ])).sort()
  const idealMap = Object.fromEntries(data.ideal_line.map((p) => [p.date, p.points]))
  const actualMap = Object.fromEntries(data.actual_line.map((p) => [p.date, p.points]))
  const chart = allDates.map((d) => ({
    date: d.slice(5),  // MM-DD
    ideal: idealMap[d] ?? null,
    actual: actualMap[d] ?? null,
  }))

  const est = data.today_estimate
  const onTrack = est.on_track !== false

  return (
    <div className="stat-card" style={{ padding: '14px 18px' }}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold flex items-center gap-1.5" style={{ color: 'var(--color-text-primary)' }}>
          <Flame size={14} /> 燃尽图(剩余故事点)
        </h3>
        <span className="text-xs opacity-70">总 {data.total_points} pt · {data.task_count} 任务</span>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={chart} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
          <Tooltip
            contentStyle={{
              background: '#1e1e2e', border: '1px solid #3a3a55',
              borderRadius: 6, fontSize: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Line
            type="monotone" dataKey="ideal" name="理想"
            stroke="#94a3b8" strokeDasharray="4 4" strokeWidth={1.5}
            dot={false}
          />
          <Line
            type="monotone" dataKey="actual" name="实际"
            stroke={onTrack ? '#22c55e' : '#ef4444'}
            strokeWidth={2}
            dot={{ r: 3 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
      {est.projected_end_date && (
        <div
          className="text-[11px] mt-1 px-2 py-1 rounded"
          style={{
            background: onTrack ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
            color: onTrack ? '#86efac' : '#fca5a5',
          }}
        >
          {onTrack ? '✅' : '⚠️'} 预计 {est.projected_end_date} 完成
          {' '}(计划 {est.planned_end_date},{est.days_delta && est.days_delta > 0 ? `延迟 ${est.days_delta} 天` : est.days_delta && est.days_delta < 0 ? `提前 ${-est.days_delta} 天` : '准时'})
          {' · '}速率 {est.burn_rate_per_day} pt/天
        </div>
      )}
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 关键路径
// ────────────────────────────────────────────────────────────────


function CriticalPathPanel({ result }: { result: CriticalPathResult | null }) {
  if (!result) return null
  const pathIds = new Set(result.critical_path)
  const onPath = result.tasks.filter((t) => pathIds.has(t.id))
  if (onPath.length === 0) {
    return (
      <div
        className="stat-card text-center py-6 text-xs opacity-60"
      >
        无关键路径(任务间无依赖关系)
      </div>
    )
  }
  return (
    <div className="stat-card" style={{ padding: '14px 18px' }}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold flex items-center gap-1.5" style={{ color: 'var(--color-text-primary)' }}>
          <Zap size={14} className="text-red-400" /> 关键路径
        </h3>
        <span className="text-xs opacity-70">
          {onPath.length} 任务 · {result.critical_length}pt
        </span>
      </div>
      <div className="space-y-1.5">
        {onPath.map((t, i) => {
          const meta = STATUS_META[t.status]
          return (
            <div
              key={t.id}
              className="flex items-center gap-2 text-xs rounded p-1.5"
              style={{
                background: t.blocked ? 'rgba(239,68,68,0.1)' : 'var(--color-bg-secondary)',
                border: '1px solid var(--color-border-subtle)',
              }}
            >
              <span className="text-[10px] opacity-50 shrink-0">#{i + 1}</span>
              <span style={{ color: meta.color }} className="shrink-0">●</span>
              <span className="flex-1 truncate" style={{ color: 'var(--color-text-primary)' }}>
                {t.title}
              </span>
              <span className="text-[10px] opacity-70 shrink-0">{t.weight}pt</span>
              {t.blocked && <span className="text-[10px] text-red-400">阻塞</span>}
            </div>
          )
        })}
      </div>
      {result.has_cycle && (
        <div className="text-[11px] mt-2 text-amber-400">
          ⚠️ 检测到任务依赖环,部分任务已被跳过
        </div>
      )}
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 速率历史
// ────────────────────────────────────────────────────────────────


function VelocityPanel({ data }: { data: VelocityHistory | null }) {
  if (!data || data.count === 0) return null
  const chart = data.history.map((h) => ({
    name: `S${h.sprint_number}`,
    planned: h.planned,
    completed: h.completed,
  }))
  return (
    <div className="stat-card" style={{ padding: '14px 18px' }}>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold flex items-center gap-1.5" style={{ color: 'var(--color-text-primary)' }}>
          <Sparkles size={14} /> 历史速率
        </h3>
        <span className="text-xs opacity-70">
          均速 {data.avg_velocity} pt/Sprint · {data.count} 次
        </span>
      </div>
      <ResponsiveContainer width="100%" height={140}>
        <BarChart data={chart} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
          <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#94a3b8' }} />
          <YAxis tick={{ fontSize: 10, fill: '#94a3b8' }} />
          <Tooltip
            contentStyle={{
              background: '#1e1e2e', border: '1px solid #3a3a55',
              borderRadius: 6, fontSize: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Bar dataKey="planned" name="计划" fill="#6366f1" radius={[2, 2, 0, 0]} />
          <Bar dataKey="completed" name="完成" fill="#22c55e" radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 新建任务
// ────────────────────────────────────────────────────────────────


function NewTaskDialog({
  onClose, onSubmit,
}: {
  onClose: () => void
  onSubmit: (p: {
    title: string; description: string; story_points: number; priority: TaskPriority
  }) => void
}) {
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [pts, setPts] = useState(1)
  const [prio, setPrio] = useState<TaskPriority>('p2')
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl p-5 space-y-3"
        style={{
          background: 'var(--color-bg-secondary)',
          border: '1px solid var(--color-border-subtle)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            新建任务
          </h3>
          <button onClick={onClose} className="opacity-60 hover:opacity-100">
            <X size={18} />
          </button>
        </div>
        <div>
          <label className="text-[11px] block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
            标题
          </label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如:完成 LoRa 模块选型评审"
            className="w-full px-3 py-2 rounded text-sm outline-none"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
          />
        </div>
        <div>
          <label className="text-[11px] block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
            描述(可选)
          </label>
          <textarea
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            rows={3}
            className="w-full px-3 py-2 rounded text-sm outline-none resize-none"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-[11px] block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              故事点
            </label>
            <input
              type="number"
              value={pts}
              onChange={(e) => setPts(parseInt(e.target.value) || 1)}
              className="w-full px-3 py-2 rounded text-sm outline-none"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
                color: 'var(--color-text-primary)',
              }}
            />
          </div>
          <div>
            <label className="text-[11px] block mb-1" style={{ color: 'var(--color-text-secondary)' }}>
              优先级
            </label>
            <select
              value={prio}
              onChange={(e) => setPrio(e.target.value as TaskPriority)}
              className="w-full px-3 py-2 rounded text-sm outline-none"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
                color: 'var(--color-text-primary)',
              }}
            >
              {(Object.keys(PRIORITY_META) as TaskPriority[]).map((p) => (
                <option key={p} value={p}>{PRIORITY_META[p].label}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-sm"
            style={{ background: 'var(--color-bg-card)', color: 'var(--color-text-secondary)' }}
          >
            取消
          </button>
          <button
            onClick={() => title && onSubmit({ title, description: desc, story_points: pts, priority: prio })}
            className="px-4 py-1.5 rounded text-sm text-white"
            style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
          >
            创建
          </button>
        </div>
      </div>
    </div>
  )
}
