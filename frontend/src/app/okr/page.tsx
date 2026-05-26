/**
 * app/okr/page.tsx — OKR 战略对齐看板
 *
 * 功能:
 * - 顶部:周期选择 + 健康度三色分布 + 整体平均进度
 * - 主体:目标树状结构,每个 Objective 展开看 KR 列表
 * - 每个 KR 展示:进度条 + 当前值/目标值 + 信心指数 + AI 自动更新徽标
 * - 点击 KR 弹出变更历史(Drawer)
 * - admin/manager 可创建/编辑/删除
 */
'use client'

import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  Plus,
  Target,
  Trash2,
  Pencil,
  History,
  Sparkles,
  User as UserIcon,
  X,
} from 'lucide-react'
import {
  listCycles,
  fetchTree,
  createCycle,
  createObjective,
  deleteObjective,
  createKR,
  updateKR,
  deleteKR,
  listProgressLogs,
  type OKRCycle,
  type OKRTreeResponse,
  type TreeObjective,
  type KeyResult,
  type ProgressLog,
} from '@/api/okr'
import { useAuthStore } from '@/stores/use-auth-store'


function progressColor(p: number): string {
  if (p >= 70) return '#22c55e'    // 绿
  if (p >= 40) return '#f59e0b'    // 黄
  return '#ef4444'                  // 红
}

function progressLabel(p: number): string {
  if (p >= 70) return 'on track'
  if (p >= 40) return 'at risk'
  return 'behind'
}


export default function OKRPage() {
  const { userRole } = useAuthStore()
  const canWrite = userRole === 'admin' || userRole === 'manager'

  const [cycles, setCycles] = useState<OKRCycle[]>([])
  const [activeCycleId, setActiveCycleId] = useState<string>('')
  const [tree, setTree] = useState<OKRTreeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  // 新建表单
  const [showNewCycle, setShowNewCycle] = useState(false)
  const [showNewObj, setShowNewObj] = useState(false)
  const [newObjCycleId, setNewObjCycleId] = useState<string>('')
  const [showNewKR, setShowNewKR] = useState<string | null>(null)  // objective_id

  // 进度更新 / 变更历史
  const [editingKR, setEditingKR] = useState<KeyResult | null>(null)
  const [historyKR, setHistoryKR] = useState<KeyResult | null>(null)
  const [historyLogs, setHistoryLogs] = useState<ProgressLog[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  // ── 初始化 ──
  useEffect(() => {
    void loadCycles()
  }, [])

  useEffect(() => {
    if (activeCycleId) void reloadTree(activeCycleId)
    // reloadTree 是稳定的 fn,不进依赖避免触发额外 fetch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCycleId])

  async function loadCycles() {
    try {
      const list = await listCycles()
      setCycles(list)
      const active = list.find((c) => c.status === 'active') || list[0]
      if (active) setActiveCycleId(active.id)
      else {
        // 没有任何周期 → 拉一次 tree(后端会 404,这里降级)
        setTree(null)
      }
    } catch {
      toast.error('加载 OKR 周期失败')
    }
  }

  const reloadTree = useCallback(async (cycleId: string) => {
    setLoading(true)
    try {
      const data = await fetchTree(cycleId)
      setTree(data)
    } catch (err: any) {
      if (err?.response?.status === 404) {
        setTree(null)
      } else {
        toast.error('加载 OKR 树失败')
      }
    } finally {
      setLoading(false)
    }
  }, [])

  function toggleExpand(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  // ── 新建周期 ──
  async function handleCreateCycle(payload: {
    name: string
    cycle_type: string
    start_date: string
    end_date: string
  }) {
    try {
      const c = await createCycle(payload)
      toast.success(`周期「${c.name}」已创建`)
      setShowNewCycle(false)
      await loadCycles()
      setActiveCycleId(c.id)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '创建失败')
    }
  }

  // ── 新建目标 ──
  async function handleCreateObjective(payload: {
    title: string
    description: string
    weight: number
  }) {
    if (!newObjCycleId) return
    try {
      await createObjective({ cycle_id: newObjCycleId, ...payload })
      toast.success(`目标已创建`)
      setShowNewObj(false)
      await reloadTree(activeCycleId)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '创建失败')
    }
  }

  async function handleDeleteObjective(o: TreeObjective) {
    if (!confirm(`确认删除目标「${o.objective.title}」?其下所有 KR 也会被删除`)) return
    try {
      await deleteObjective(o.objective.id)
      toast.success('已删除')
      await reloadTree(activeCycleId)
    } catch {
      toast.error('删除失败')
    }
  }

  // ── 新建 KR ──
  async function handleCreateKR(
    objectiveId: string,
    payload: {
      title: string
      target_value: number
      unit: string
      description: string
    },
  ) {
    try {
      await createKR({ objective_id: objectiveId, ...payload })
      toast.success('KR 已创建')
      setShowNewKR(null)
      await reloadTree(activeCycleId)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '创建失败')
    }
  }

  // ── 更新 KR 进度 ──
  async function handleUpdateKR(
    krId: string,
    payload: { current_value?: number; confidence?: number; note?: string },
  ) {
    try {
      await updateKR(krId, payload)
      toast.success('已更新')
      setEditingKR(null)
      await reloadTree(activeCycleId)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '更新失败')
    }
  }

  async function handleDeleteKR(kr: KeyResult) {
    if (!confirm(`删除 KR「${kr.title}」?`)) return
    try {
      await deleteKR(kr.id)
      toast.success('已删除')
      await reloadTree(activeCycleId)
    } catch {
      toast.error('删除失败')
    }
  }

  // ── 变更历史 ──
  async function openHistory(kr: KeyResult) {
    setHistoryKR(kr)
    setHistoryLoading(true)
    try {
      setHistoryLogs(await listProgressLogs(kr.id))
    } catch {
      toast.error('加载历史失败')
    } finally {
      setHistoryLoading(false)
    }
  }

  const summary = tree?.summary
  const objectives = tree?.objectives || []

  return (
    <div className="page-container space-y-4">
      <Header
        cycles={cycles}
        activeCycleId={activeCycleId}
        onChangeCycle={setActiveCycleId}
        onNewCycle={() => setShowNewCycle(true)}
        onNewObjective={() => {
          setNewObjCycleId(activeCycleId)
          setShowNewObj(true)
        }}
        canWrite={canWrite}
      />

      {summary && tree && (
        <SummaryBar cycle={tree.cycle} summary={summary} />
      )}

      {/* 列表 */}
      <div className="space-y-3">
        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 size={28} className="animate-spin" style={{ color: '#6366f1' }} />
          </div>
        ) : !tree ? (
          <EmptyState onCreate={canWrite ? () => setShowNewCycle(true) : undefined} />
        ) : objectives.length === 0 ? (
          <div className="text-center py-10 opacity-60 text-sm">
            当前周期还没有目标,
            {canWrite ? '点击右上角「新建目标」开始 →' : '请联系管理员创建'}
          </div>
        ) : (
          objectives.map((o) => (
            <ObjectiveCard
              key={o.objective.id}
              data={o}
              expanded={!!expanded[o.objective.id]}
              onToggle={() => toggleExpand(o.objective.id)}
              onAddKR={() => setShowNewKR(o.objective.id)}
              onDelete={() => handleDeleteObjective(o)}
              onEditKR={setEditingKR}
              onDeleteKR={handleDeleteKR}
              onShowHistory={openHistory}
              canWrite={canWrite}
            />
          ))
        )}
      </div>

      {/* 弹窗 */}
      {showNewCycle && (
        <NewCycleModal
          onClose={() => setShowNewCycle(false)}
          onSubmit={handleCreateCycle}
        />
      )}
      {showNewObj && (
        <NewObjectiveModal
          onClose={() => setShowNewObj(false)}
          onSubmit={handleCreateObjective}
        />
      )}
      {showNewKR && (
        <NewKRModal
          onClose={() => setShowNewKR(null)}
          onSubmit={(p) => handleCreateKR(showNewKR, p)}
        />
      )}
      {editingKR && (
        <EditKRModal
          kr={editingKR}
          onClose={() => setEditingKR(null)}
          onSubmit={(p) => handleUpdateKR(editingKR.id, p)}
        />
      )}
      {historyKR && (
        <HistoryDrawer
          kr={historyKR}
          logs={historyLogs}
          loading={historyLoading}
          onClose={() => setHistoryKR(null)}
        />
      )}
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 子组件
// ────────────────────────────────────────────────────────────────


function Header({
  cycles, activeCycleId, onChangeCycle, onNewCycle, onNewObjective, canWrite,
}: {
  cycles: OKRCycle[]
  activeCycleId: string
  onChangeCycle: (id: string) => void
  onNewCycle: () => void
  onNewObjective: () => void
  canWrite: boolean
}) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-3 animate-in">
      <div>
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
          🎯 OKR 战略对齐
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
          目标 + 关键结果 + AI 自动从日报抽取进度
        </p>
      </div>
      <div className="flex items-center gap-2">
        {cycles.length > 0 && (
          <select
            value={activeCycleId}
            onChange={(e) => onChangeCycle(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm outline-none"
            style={{
              background: 'var(--color-bg-card)',
              border: '1px solid var(--color-border-subtle)',
              color: 'var(--color-text-primary)',
            }}
          >
            {cycles.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.status})
              </option>
            ))}
          </select>
        )}
        {canWrite && (
          <>
            <button
              onClick={onNewCycle}
              className="px-3 py-2 rounded-lg text-sm font-medium transition-all"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
                color: 'var(--color-text-primary)',
              }}
            >
              + 新周期
            </button>
            {activeCycleId && (
              <button
                onClick={onNewObjective}
                className="px-4 py-2 rounded-lg text-sm font-medium text-white flex items-center gap-1.5"
                style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
              >
                <Plus size={14} /> 新建目标
              </button>
            )}
          </>
        )}
      </div>
    </div>
  )
}


function SummaryBar({
  cycle, summary,
}: {
  cycle: OKRCycle
  summary: NonNullable<OKRTreeResponse['summary']>
}) {
  return (
    <div
      className="stat-card flex flex-wrap items-center gap-6 animate-in"
      style={{ padding: '14px 18px' }}
    >
      <Metric label="周期" value={cycle.name} sub={`${cycle.start_date} → ${cycle.end_date}`} />
      <Metric label="目标数" value={String(summary.objective_count)} />
      <Metric label="KR 数" value={String(summary.kr_count)} />
      <Metric
        label="平均进度"
        value={`${summary.avg_progress}%`}
        sub={progressLabel(summary.avg_progress)}
        color={progressColor(summary.avg_progress)}
      />
      {(summary.on_track !== undefined) && (
        <div className="flex gap-2 ml-auto text-xs">
          <Badge text={`🟢 on track ${summary.on_track || 0}`} color="#22c55e" />
          <Badge text={`🟡 at risk ${summary.at_risk || 0}`} color="#f59e0b" />
          <Badge text={`🔴 behind ${summary.behind || 0}`} color="#ef4444" />
        </div>
      )}
    </div>
  )
}


function Metric({
  label, value, sub, color,
}: {
  label: string; value: string; sub?: string; color?: string
}) {
  return (
    <div>
      <div className="text-[11px] opacity-60">{label}</div>
      <div
        className="text-lg font-bold"
        style={{ color: color || 'var(--color-text-primary)' }}
      >
        {value}
      </div>
      {sub && <div className="text-[11px] opacity-60">{sub}</div>}
    </div>
  )
}


function Badge({ text, color }: { text: string; color: string }) {
  return (
    <span
      className="px-2 py-1 rounded text-[11px]"
      style={{ background: `${color}22`, color }}
    >
      {text}
    </span>
  )
}


function ObjectiveCard({
  data, expanded, onToggle, onAddKR, onDelete, onEditKR, onDeleteKR, onShowHistory, canWrite,
}: {
  data: TreeObjective
  expanded: boolean
  onToggle: () => void
  onAddKR: () => void
  onDelete: () => void
  onEditKR: (kr: KeyResult) => void
  onDeleteKR: (kr: KeyResult) => void
  onShowHistory: (kr: KeyResult) => void
  canWrite: boolean
}) {
  const { objective, key_results: krs } = data
  const color = progressColor(objective.progress)
  return (
    <div
      className="stat-card animate-in"
      style={{ padding: '14px 18px' }}
    >
      <div className="flex items-start gap-3">
        <button
          onClick={onToggle}
          className="mt-1 shrink-0"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        </button>
        <Target size={18} className="mt-0.5 shrink-0" style={{ color }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="font-semibold text-sm"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {objective.title}
            </span>
            {objective.owner_name && (
              <span
                className="text-[11px] px-1.5 py-0.5 rounded flex items-center gap-1"
                style={{ background: 'rgba(99,102,241,0.12)', color: '#a5b4fc' }}
              >
                <UserIcon size={10} /> {objective.owner_name}
              </span>
            )}
            <span className="text-[11px] opacity-60">权重 {objective.weight}</span>
          </div>
          {objective.description && (
            <div className="text-xs mt-1 opacity-75">{objective.description}</div>
          )}
          <ProgressBar value={objective.progress} color={color} />
        </div>
        {canWrite && (
          <div className="flex gap-1 shrink-0">
            <IconBtn onClick={onAddKR} title="新建 KR"><Plus size={14} /></IconBtn>
            <IconBtn onClick={onDelete} title="删除目标"><Trash2 size={14} /></IconBtn>
          </div>
        )}
      </div>

      {expanded && (
        <div className="mt-3 pl-9 space-y-2">
          {krs.length === 0 ? (
            <div className="text-xs opacity-60 py-2">
              暂无 KR{canWrite ? ',点击 + 添加' : ''}
            </div>
          ) : (
            krs.map((kr) => (
              <KRRow
                key={kr.id}
                kr={kr}
                onEdit={() => onEditKR(kr)}
                onDelete={() => onDeleteKR(kr)}
                onHistory={() => onShowHistory(kr)}
                canWrite={canWrite}
              />
            ))
          )}
        </div>
      )}
    </div>
  )
}


function KRRow({
  kr, onEdit, onDelete, onHistory, canWrite,
}: {
  kr: KeyResult; onEdit: () => void; onDelete: () => void; onHistory: () => void; canWrite: boolean
}) {
  const color = progressColor(kr.progress)
  return (
    <div
      className="rounded-lg flex items-start gap-3 py-2.5 px-3"
      style={{
        background: 'var(--color-bg-secondary)',
        border: '1px solid var(--color-border-subtle)',
      }}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span
            className="font-medium"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {kr.title}
          </span>
          <span className="opacity-60">
            {kr.current_value}{kr.unit || ''} / {kr.target_value}{kr.unit || ''}
          </span>
          {kr.confidence > 0.7 && (
            <span
              className="text-[10px] px-1.5 rounded flex items-center gap-1"
              style={{ background: 'rgba(168,85,247,0.15)', color: '#c084fc' }}
              title="信心指数高"
            >
              <Sparkles size={9} /> {Math.round(kr.confidence * 100)}%
            </span>
          )}
        </div>
        <ProgressBar value={kr.progress} color={color} small />
      </div>
      <div className="flex gap-1 shrink-0">
        <IconBtn onClick={onHistory} title="变更历史"><History size={13} /></IconBtn>
        {canWrite && (
          <>
            <IconBtn onClick={onEdit} title="编辑"><Pencil size={13} /></IconBtn>
            <IconBtn onClick={onDelete} title="删除"><Trash2 size={13} /></IconBtn>
          </>
        )}
      </div>
    </div>
  )
}


function ProgressBar({ value, color, small }: { value: number; color: string; small?: boolean }) {
  return (
    <div className={small ? 'mt-1.5' : 'mt-2'}>
      <div
        className="rounded-full overflow-hidden"
        style={{
          height: small ? '5px' : '7px',
          background: 'rgba(255,255,255,0.06)',
        }}
      >
        <div
          className="h-full transition-all"
          style={{
            width: `${Math.min(value, 100)}%`,
            background: color,
          }}
        />
      </div>
      <div className="text-[10px] mt-0.5 opacity-70" style={{ color }}>
        {value}%
      </div>
    </div>
  )
}


function IconBtn({
  onClick, title, children,
}: { onClick: () => void; title: string; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className="p-1.5 rounded transition-colors hover:opacity-80"
      style={{
        background: 'var(--color-bg-card)',
        border: '1px solid var(--color-border-subtle)',
        color: 'var(--color-text-secondary)',
      }}
    >
      {children}
    </button>
  )
}


function EmptyState({ onCreate }: { onCreate?: () => void }) {
  return (
    <div className="text-center py-16 opacity-80">
      <Target size={42} className="mx-auto mb-3 opacity-40" />
      <div className="text-sm mb-4">还没有 OKR 周期</div>
      {onCreate && (
        <button
          onClick={onCreate}
          className="px-4 py-2 rounded-lg text-sm text-white"
          style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
        >
          创建第一个周期
        </button>
      )}
    </div>
  )
}


// ───────── 弹窗 ─────────


function ModalShell({
  title, onClose, children,
}: { title: string; onClose: () => void; children: React.ReactNode }) {
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
          <h3 className="font-semibold" style={{ color: 'var(--color-text-primary)' }}>{title}</h3>
          <button onClick={onClose} className="opacity-60 hover:opacity-100">
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}


function NewCycleModal({
  onClose, onSubmit,
}: {
  onClose: () => void
  onSubmit: (p: { name: string; cycle_type: string; start_date: string; end_date: string }) => void
}) {
  const [name, setName] = useState('')
  const today = new Date().toISOString().slice(0, 10)
  const [start, setStart] = useState(today)
  const [end, setEnd] = useState(today)
  const [ctype, setCtype] = useState('quarterly')
  return (
    <ModalShell title="新建 OKR 周期" onClose={onClose}>
      <Field label="名称(如 2026Q2)">
        <Input value={name} onChange={setName} placeholder="2026Q2" />
      </Field>
      <Field label="周期类型">
        <select
          value={ctype}
          onChange={(e) => setCtype(e.target.value)}
          className="form-input"
        >
          <option value="quarterly">季度</option>
          <option value="monthly">月度</option>
          <option value="yearly">年度</option>
        </select>
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="开始日期"><Input type="date" value={start} onChange={setStart} /></Field>
        <Field label="结束日期"><Input type="date" value={end} onChange={setEnd} /></Field>
      </div>
      <SubmitRow
        onCancel={onClose}
        onSubmit={() =>
          name && onSubmit({ name, cycle_type: ctype, start_date: start, end_date: end })
        }
      />
    </ModalShell>
  )
}


function NewObjectiveModal({
  onClose, onSubmit,
}: {
  onClose: () => void
  onSubmit: (p: { title: string; description: string; weight: number }) => void
}) {
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [weight, setWeight] = useState(1)
  return (
    <ModalShell title="新建目标" onClose={onClose}>
      <Field label="标题">
        <Input value={title} onChange={setTitle} placeholder="例如:206 样机具备行业参展能力" />
      </Field>
      <Field label="描述(可选)">
        <Textarea value={desc} onChange={setDesc} placeholder="更多上下文" />
      </Field>
      <Field label="权重">
        <Input
          type="number"
          value={String(weight)}
          onChange={(v) => setWeight(parseFloat(v) || 1)}
        />
      </Field>
      <SubmitRow
        onCancel={onClose}
        onSubmit={() => title && onSubmit({ title, description: desc, weight })}
      />
    </ModalShell>
  )
}


function NewKRModal({
  onClose, onSubmit,
}: {
  onClose: () => void
  onSubmit: (p: { title: string; target_value: number; unit: string; description: string }) => void
}) {
  const [title, setTitle] = useState('')
  const [desc, setDesc] = useState('')
  const [target, setTarget] = useState(100)
  const [unit, setUnit] = useState('%')
  return (
    <ModalShell title="新建关键结果(KR)" onClose={onClose}>
      <Field label="KR 标题">
        <Input value={title} onChange={setTitle} placeholder="例如:大模型推理延迟降至 500ms 内" />
      </Field>
      <Field label="描述(给 AI 抽取进度时的上下文)">
        <Textarea value={desc} onChange={setDesc} placeholder="可选,但建议填写" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="目标值"><Input type="number" value={String(target)} onChange={(v) => setTarget(parseFloat(v) || 0)} /></Field>
        <Field label="单位"><Input value={unit} onChange={setUnit} placeholder="% / ms / 个" /></Field>
      </div>
      <SubmitRow
        onCancel={onClose}
        onSubmit={() => title && onSubmit({ title, description: desc, target_value: target, unit })}
      />
    </ModalShell>
  )
}


function EditKRModal({
  kr, onClose, onSubmit,
}: {
  kr: KeyResult
  onClose: () => void
  onSubmit: (p: { current_value?: number; confidence?: number; note?: string }) => void
}) {
  const [val, setVal] = useState(String(kr.current_value))
  const [conf, setConf] = useState(String(kr.confidence))
  const [note, setNote] = useState('')
  return (
    <ModalShell title={`更新进度:${kr.title}`} onClose={onClose}>
      <Field label={`当前值(目标 ${kr.target_value}${kr.unit || ''})`}>
        <Input type="number" value={val} onChange={setVal} />
      </Field>
      <Field label="信心指数(0-1)">
        <Input type="number" value={conf} onChange={setConf} />
      </Field>
      <Field label="变更说明(可选)">
        <Textarea value={note} onChange={setNote} placeholder="本次进度更新的依据" />
      </Field>
      <SubmitRow
        onCancel={onClose}
        onSubmit={() =>
          onSubmit({
            current_value: parseFloat(val),
            confidence: parseFloat(conf),
            note: note || undefined,
          })
        }
      />
    </ModalShell>
  )
}


function HistoryDrawer({
  kr, logs, loading, onClose,
}: {
  kr: KeyResult; logs: ProgressLog[]; loading: boolean; onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end"
      style={{ background: 'rgba(0,0,0,0.5)' }}
      onClick={onClose}
    >
      <div
        className="w-full max-w-md h-full p-5 overflow-y-auto"
        style={{
          background: 'var(--color-bg-secondary)',
          borderLeft: '1px solid var(--color-border-subtle)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="text-xs opacity-60">变更历史</div>
            <h3 className="font-semibold text-sm" style={{ color: 'var(--color-text-primary)' }}>
              {kr.title}
            </h3>
          </div>
          <button onClick={onClose} className="opacity-60 hover:opacity-100">
            <X size={20} />
          </button>
        </div>

        {loading ? (
          <div className="text-center py-8 opacity-60">
            <Loader2 size={20} className="animate-spin inline" />
          </div>
        ) : logs.length === 0 ? (
          <div className="text-center py-8 opacity-60 text-sm">
            暂无变更记录
          </div>
        ) : (
          <div className="space-y-2">
            {logs.map((log) => (
              <div
                key={log.id}
                className="rounded-md p-3 text-xs"
                style={{
                  background: 'var(--color-bg-card)',
                  border: '1px solid var(--color-border-subtle)',
                }}
              >
                <div className="flex items-center justify-between mb-1">
                  <span
                    className="font-medium"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {log.previous_value} → <strong>{log.new_value}</strong>
                    {kr.unit && <span> {kr.unit}</span>}
                  </span>
                  <SourceBadge source={log.source} confidence={log.confidence} />
                </div>
                {log.note && <div className="opacity-75">{log.note}</div>}
                <div className="opacity-50 text-[10px] mt-1">
                  {log.created_at?.slice(0, 16).replace('T', ' ')}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}


function SourceBadge({
  source, confidence,
}: { source: ProgressLog['source']; confidence?: number | null }) {
  const map: Record<ProgressLog['source'], { label: string; color: string }> = {
    ai_extracted: { label: '🤖 AI 提取', color: '#c084fc' },
    manual: { label: '✋ 手工', color: '#a5b4fc' },
    sprint_close: { label: '🔁 Sprint 收尾', color: '#facc15' },
    system: { label: '⚙ 系统', color: '#94a3b8' },
  }
  const { label, color } = map[source] || { label: source, color: '#94a3b8' }
  return (
    <span
      className="text-[10px] px-1.5 py-0.5 rounded"
      style={{ background: `${color}22`, color }}
    >
      {label}
      {source === 'ai_extracted' && confidence != null && (
        <span> · {Math.round(confidence * 100)}%</span>
      )}
    </span>
  )
}


function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label
        className="text-[11px] block mb-1"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        {label}
      </label>
      {children}
    </div>
  )
}


function Input({
  value, onChange, placeholder, type = 'text',
}: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string
}) {
  return (
    <input
      type={type}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="form-input w-full px-3 py-2 rounded text-sm outline-none"
      style={{
        background: 'var(--color-bg-card)',
        border: '1px solid var(--color-border-subtle)',
        color: 'var(--color-text-primary)',
      }}
    />
  )
}


function Textarea({
  value, onChange, placeholder,
}: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <textarea
      value={value}
      placeholder={placeholder}
      rows={3}
      onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 rounded text-sm outline-none resize-none"
      style={{
        background: 'var(--color-bg-card)',
        border: '1px solid var(--color-border-subtle)',
        color: 'var(--color-text-primary)',
      }}
    />
  )
}


function SubmitRow({
  onCancel, onSubmit,
}: { onCancel: () => void; onSubmit: () => void }) {
  return (
    <div className="flex justify-end gap-2 pt-2">
      <button
        onClick={onCancel}
        className="px-3 py-1.5 rounded text-sm"
        style={{
          background: 'var(--color-bg-card)',
          color: 'var(--color-text-secondary)',
        }}
      >
        取消
      </button>
      <button
        onClick={onSubmit}
        className="px-4 py-1.5 rounded text-sm text-white"
        style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
      >
        提交
      </button>
    </div>
  )
}
