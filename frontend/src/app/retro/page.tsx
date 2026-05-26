/**
 * app/retro/page.tsx — AI 复盘库
 *
 * 功能:
 * - 左侧:复盘列表(可按 scope 筛选 + 搜索)
 * - 右侧:选中条目的 Markdown 详情
 * - admin/manager 可点「+ 生成复盘」打开生成对话框
 */
'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  BookOpen,
  Loader2,
  Search,
  Sparkles,
  Trash2,
  X,
  FileBarChart,
  Target,
  Calendar,
  AlertTriangle,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { listCycles, type OKRCycle } from '@/api/okr'
import {
  listRetros,
  getRetro,
  deleteRetro,
  generateRetro,
  batchDeleteKnowledgeItems,
  batchRestoreKnowledgeItems,
  type RetroItem,
  type RetroItemDetail,
  type RetroScope,
} from '@/api/retro'
import { useAuthStore } from '@/stores/use-auth-store'
import { useMultiSelect } from '@/lib/hooks/use-multi-select'
import ListActionBar from '@/components/list-action-bar'


const SCOPE_META: Record<
  RetroScope,
  { label: string; icon: React.ReactNode; color: string }
> = {
  okr_cycle: { label: 'OKR 周期', icon: <Target size={12} />, color: '#a855f7' },
  project: { label: '项目', icon: <FileBarChart size={12} />, color: '#3b82f6' },
  monthly: { label: '月度', icon: <Calendar size={12} />, color: '#22c55e' },
  incident: { label: '事故', icon: <AlertTriangle size={12} />, color: '#ef4444' },
}


export default function RetroPage() {
  const { userRole } = useAuthStore()
  const canWrite = userRole === 'admin' || userRole === 'manager'
  const canBatchManage = userRole === 'admin'  // V2.5 Stage 3:批量软删仅 admin

  const [items, setItems] = useState<RetroItem[]>([])
  const [loading, setLoading] = useState(false)
  const [scopeFilter, setScopeFilter] = useState<RetroScope | ''>('')
  const [keyword, setKeyword] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<RetroItemDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const [showGenerate, setShowGenerate] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)

  // ── 列表加载 ──
  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listRetros({
        scope: scopeFilter || undefined,
        page: 1,
        page_size: 50,
      })
      setItems(res.items)
      // 默认选中第一条 — 故意不把 selectedId 列入依赖:
      // selectedId 变化时不该触发重新 reload,否则会陷入 fetch 循环
      if (!selectedId && res.items.length > 0) {
        setSelectedId(res.items[0].id)
      }
    } catch {
      toast.error('加载复盘列表失败')
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scopeFilter])

  useEffect(() => {
    void reload()
  }, [reload])

  // ── 详情加载 ──
  useEffect(() => {
    if (!selectedId) {
      setDetail(null)
      return
    }
    setDetailLoading(true)
    getRetro(selectedId)
      .then(setDetail)
      .catch(() => toast.error('加载详情失败'))
      .finally(() => setDetailLoading(false))
  }, [selectedId])

  const filteredItems = useMemo(() => {
    if (!keyword.trim()) return items
    const kw = keyword.trim().toLowerCase()
    return items.filter(
      (it) =>
        it.title.toLowerCase().includes(kw) ||
        (it.tags || '').toLowerCase().includes(kw),
    )
  }, [items, keyword])

  // V2.5 Stage 3:多选 hook 跟随 filteredItems(filter 变即清空,与 dashboard 范式一致)
  const ms = useMultiSelect(filteredItems, { idKey: 'id' as any })

  async function handleDelete(id: string) {
    if (!confirm('确认软删这条复盘?\n(历史 view_count / source_id 锚定保留,可在回收站恢复)')) return
    try {
      await deleteRetro(id)
      toast.success('已软删,可在回收站恢复')
      if (selectedId === id) setSelectedId(null)
      await reload()
    } catch {
      toast.error('删除失败')
    }
  }

  async function handleBatchDelete() {
    if (ms.selectedCount === 0) return
    if (!confirm(
      `确定软删选中的 ${ms.selectedCount} 条复盘?\n(历史 view_count / source_id 关联保留,可在回收站恢复;chat AI 引用 / 检索下次刷新会排除)`
    )) return
    setBulkDeleting(true)
    try {
      const ids = Array.from(ms.selectedIds) as string[]
      const res = await batchDeleteKnowledgeItems(ids)
      const deletedIds: string[] = res?.deleted_ids ?? ids
      // 当前选中的详情若在被删列表里,清空
      if (selectedId && deletedIds.includes(selectedId)) setSelectedId(null)
      ms.clearAll()
      await reload()
      toast.success(`已软删 ${deletedIds.length} 条复盘`, {
        duration: 5000,
        action: {
          label: '撤销',
          onClick: async () => {
            try {
              const r = await batchRestoreKnowledgeItems(deletedIds)
              await reload()
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
      setBulkDeleting(false)
    }
  }

  return (
    <div className="page-container space-y-4">
      <Header
        canWrite={canWrite}
        onGenerate={() => setShowGenerate(true)}
      />

      <FilterBar
        scope={scopeFilter}
        onScopeChange={setScopeFilter}
        keyword={keyword}
        onKeywordChange={setKeyword}
        total={items.length}
      />

      {/* V2.5 Stage 3:批量软删操作栏(admin) */}
      {canBatchManage && (
        <ListActionBar
          selectedCount={ms.selectedCount}
          onClear={ms.clearAll}
          hint="软删后历史关联保留,可在回收站恢复"
        >
          <button
            onClick={handleBatchDelete}
            disabled={bulkDeleting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50"
            style={{ background: '#ef4444', color: '#fff' }}
          >
            <Trash2 size={14} />
            {bulkDeleting ? '处理中…' : `批量删除 (${ms.selectedCount})`}
          </button>
        </ListActionBar>
      )}

      <div
        className="grid gap-4"
        style={{ gridTemplateColumns: 'minmax(280px, 360px) 1fr', minHeight: '60vh' }}
      >
        <LeftList
          items={filteredItems}
          loading={loading}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onDelete={handleDelete}
          canWrite={canWrite}
          canBatchManage={canBatchManage}
          isSelected={ms.isSelected}
          toggleSelect={ms.toggle}
        />
        <RightDetail
          item={detail}
          loading={detailLoading}
          empty={!selectedId && !loading}
        />
      </div>

      {showGenerate && (
        <GenerateDialog
          onClose={() => setShowGenerate(false)}
          onCreated={async (id) => {
            setShowGenerate(false)
            await reload()
            setSelectedId(id)
            toast.success('复盘已生成并沉淀到知识库')
          }}
        />
      )}
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 子组件
// ────────────────────────────────────────────────────────────────


function Header({
  canWrite, onGenerate,
}: { canWrite: boolean; onGenerate: () => void }) {
  return (
    <div className="flex items-center justify-between flex-wrap gap-3 animate-in">
      <div>
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
          🔁 AI 复盘库
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
          周期 / 项目 / 月度 / 事故 复盘自动沉淀,服务下次决策
        </p>
      </div>
      {canWrite && (
        <button
          onClick={onGenerate}
          className="px-4 py-2 rounded-lg text-sm font-medium text-white flex items-center gap-1.5"
          style={{ background: 'linear-gradient(135deg, #a855f7, #ec4899)' }}
        >
          <Sparkles size={14} /> 生成复盘
        </button>
      )}
    </div>
  )
}


function FilterBar({
  scope, onScopeChange, keyword, onKeywordChange, total,
}: {
  scope: RetroScope | ''
  onScopeChange: (v: RetroScope | '') => void
  keyword: string
  onKeywordChange: (v: string) => void
  total: number
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Chip
        active={scope === ''}
        onClick={() => onScopeChange('')}
        label="全部"
      />
      {(Object.keys(SCOPE_META) as RetroScope[]).map((s) => (
        <Chip
          key={s}
          active={scope === s}
          onClick={() => onScopeChange(s)}
          label={SCOPE_META[s].label}
          icon={SCOPE_META[s].icon}
          color={SCOPE_META[s].color}
        />
      ))}
      <div className="flex-1" />
      <div className="relative">
        <Search size={14} className="absolute left-2 top-2.5 opacity-50" />
        <input
          value={keyword}
          onChange={(e) => onKeywordChange(e.target.value)}
          placeholder="标题/标签搜索"
          className="pl-7 pr-3 py-1.5 rounded text-xs outline-none"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            color: 'var(--color-text-primary)',
            width: 180,
          }}
        />
      </div>
      <span className="text-xs opacity-60">共 {total}</span>
    </div>
  )
}


function Chip({
  active, onClick, label, icon, color,
}: {
  active: boolean
  onClick: () => void
  label: string
  icon?: React.ReactNode
  color?: string
}) {
  return (
    <button
      onClick={onClick}
      className="px-2.5 py-1 rounded-full text-xs flex items-center gap-1 transition-all"
      style={{
        background: active ? (color || '#6366f1') : 'var(--color-bg-card)',
        color: active ? 'white' : 'var(--color-text-primary)',
        border: '1px solid var(--color-border-subtle)',
      }}
    >
      {icon}
      {label}
    </button>
  )
}


function LeftList({
  items, loading, selectedId, onSelect, onDelete, canWrite,
  canBatchManage, isSelected, toggleSelect,
}: {
  items: RetroItem[]
  loading: boolean
  selectedId: string | null
  onSelect: (id: string) => void
  onDelete: (id: string) => void
  canWrite: boolean
  canBatchManage: boolean
  isSelected: (id: string) => boolean
  toggleSelect: (id: string) => void
}) {
  if (loading) {
    return (
      <div className="stat-card flex justify-center items-center py-12">
        <Loader2 size={20} className="animate-spin" style={{ color: '#6366f1' }} />
      </div>
    )
  }
  if (items.length === 0) {
    return (
      <div
        className="stat-card flex flex-col justify-center items-center py-16 text-center"
        style={{ color: 'var(--color-text-secondary)' }}
      >
        <BookOpen size={40} className="opacity-40 mb-3" />
        <div className="text-sm">还没有复盘记录</div>
        {canWrite && (
          <div className="text-xs mt-1 opacity-75">点右上角「生成复盘」开始</div>
        )}
      </div>
    )
  }
  return (
    <div className="space-y-2 overflow-y-auto" style={{ maxHeight: '70vh' }}>
      {items.map((it) => (
        <RetroCard
          key={it.id}
          item={it}
          active={selectedId === it.id}
          onClick={() => onSelect(it.id)}
          onDelete={canWrite ? () => onDelete(it.id) : undefined}
          checkbox={canBatchManage ? {
            checked: isSelected(it.id),
            onToggle: () => toggleSelect(it.id),
          } : undefined}
        />
      ))}
    </div>
  )
}


function RetroCard({
  item, active, onClick, onDelete, checkbox,
}: {
  item: RetroItem
  active: boolean
  onClick: () => void
  onDelete?: () => void
  checkbox?: { checked: boolean; onToggle: () => void }
}) {
  const meta = item.scope ? SCOPE_META[item.scope] : null
  const selected = checkbox?.checked === true
  return (
    <div
      onClick={onClick}
      className="rounded-lg p-3 cursor-pointer transition-all animate-in"
      style={{
        background: selected
          ? 'rgba(168,85,247,0.06)'
          : active
            ? 'linear-gradient(135deg, rgba(168,85,247,0.15), rgba(99,102,241,0.12))'
            : 'var(--color-bg-card)',
        border: `1px solid ${selected ? '#a855f7' : active ? '#a855f7aa' : 'var(--color-border-subtle)'}`,
      }}
    >
      <div className="flex items-start justify-between gap-2">
        {checkbox && (
          <input
            type="checkbox"
            checked={checkbox.checked}
            onClick={(e) => e.stopPropagation()}
            onChange={checkbox.onToggle}
            className="mt-1 cursor-pointer shrink-0"
            title="选中以批量操作"
          />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            {meta && (
              <span
                className="text-[10px] px-1.5 py-0.5 rounded flex items-center gap-1 shrink-0"
                style={{ background: `${meta.color}22`, color: meta.color }}
              >
                {meta.icon} {meta.label}
              </span>
            )}
            <span className="text-[10px] opacity-50 shrink-0">
              {item.created_at?.slice(0, 10) || ''}
            </span>
          </div>
          <div
            className="text-sm font-medium leading-snug truncate"
            style={{ color: 'var(--color-text-primary)' }}
          >
            {item.title}
          </div>
          {item.source_type === 'ai_retrospective' && (
            <div
              className="text-[10px] mt-1 flex items-center gap-1"
              style={{ color: '#c084fc' }}
            >
              <Sparkles size={9} /> AI 自动生成
            </div>
          )}
        </div>
        {onDelete && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            className="opacity-40 hover:opacity-100 hover:text-red-400 shrink-0 mt-0.5"
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </div>
  )
}


function RightDetail({
  item, loading, empty,
}: { item: RetroItemDetail | null; loading: boolean; empty: boolean }) {
  if (loading) {
    return (
      <div className="stat-card flex justify-center items-center" style={{ minHeight: 400 }}>
        <Loader2 size={24} className="animate-spin" style={{ color: '#6366f1' }} />
      </div>
    )
  }
  if (empty || !item) {
    return (
      <div
        className="stat-card flex flex-col justify-center items-center"
        style={{ color: 'var(--color-text-secondary)', minHeight: 400 }}
      >
        <BookOpen size={48} className="opacity-30 mb-3" />
        <div className="text-sm">从左侧选择一条复盘查看详情</div>
      </div>
    )
  }
  return (
    <div className="stat-card overflow-y-auto" style={{ padding: '20px', maxHeight: '76vh' }}>
      <div className="mb-3 pb-3" style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
        <h2 className="text-lg font-bold" style={{ color: 'var(--color-text-primary)' }}>
          {item.title}
        </h2>
        <div className="flex items-center gap-3 mt-1.5 text-[11px]" style={{ color: 'var(--color-text-secondary)' }}>
          {item.tags && <span>🏷 {item.tags}</span>}
          <span>📅 {item.created_at?.slice(0, 16).replace('T', ' ')}</span>
          {item.source_type === 'ai_retrospective' && (
            <span style={{ color: '#c084fc' }}>✨ AI 生成</span>
          )}
        </div>
      </div>
      <div className="prose prose-sm prose-invert max-w-none">
        <ReactMarkdown>{item.content}</ReactMarkdown>
      </div>
    </div>
  )
}


// ────────────────────────────────────────────────────────────────
// 生成对话框
// ────────────────────────────────────────────────────────────────


function GenerateDialog({
  onClose, onCreated,
}: { onClose: () => void; onCreated: (id: string) => void }) {
  const [scope, setScope] = useState<RetroScope>('okr_cycle')
  const [cycles, setCycles] = useState<OKRCycle[]>([])
  const [cycleId, setCycleId] = useState('')
  const [projectId, setProjectId] = useState('')
  const [incidentId, setIncidentId] = useState('')
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth() + 1)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (scope === 'okr_cycle') {
      listCycles().then(setCycles).catch(() => {})
    }
  }, [scope])

  async function submit() {
    setBusy(true)
    try {
      const res = await generateRetro({
        scope,
        target_id: scope === 'okr_cycle' ? cycleId : undefined,
        project_id: scope === 'project' ? projectId : undefined,
        incident_id: scope === 'incident' ? incidentId : undefined,
        year: scope === 'monthly' ? year : undefined,
        month: scope === 'monthly' ? month : undefined,
        persist: true,
      })
      if (res.knowledge_item_id) {
        onCreated(res.knowledge_item_id)
      } else {
        toast.success('生成成功(未沉淀)')
        onClose()
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '生成失败')
    } finally {
      setBusy(false)
    }
  }

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
            ✨ 生成 AI 复盘
          </h3>
          <button onClick={onClose} className="opacity-60 hover:opacity-100">
            <X size={18} />
          </button>
        </div>

        <div>
          <label className="text-[11px] block mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            复盘类型
          </label>
          <div className="grid grid-cols-2 gap-2">
            {(Object.keys(SCOPE_META) as RetroScope[]).map((s) => {
              const meta = SCOPE_META[s]
              const active = scope === s
              return (
                <button
                  key={s}
                  onClick={() => setScope(s)}
                  className="px-3 py-2 rounded text-xs flex items-center gap-1.5"
                  style={{
                    background: active ? `${meta.color}22` : 'var(--color-bg-card)',
                    color: active ? meta.color : 'var(--color-text-primary)',
                    border: `1px solid ${active ? meta.color : 'var(--color-border-subtle)'}`,
                  }}
                >
                  {meta.icon} {meta.label}
                </button>
              )
            })}
          </div>
        </div>

        {scope === 'okr_cycle' && (
          <Field label="OKR 周期">
            <select
              value={cycleId}
              onChange={(e) => setCycleId(e.target.value)}
              className="form-input"
            >
              <option value="">— 请选择 —</option>
              {cycles.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name} ({c.status})
                </option>
              ))}
            </select>
          </Field>
        )}

        {scope === 'project' && (
          <Field label="项目 ID(UUID)">
            <input
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              placeholder="项目 UUID,可从项目列表复制"
              className="form-input"
            />
          </Field>
        )}

        {scope === 'monthly' && (
          <div className="grid grid-cols-2 gap-3">
            <Field label="年份">
              <input
                type="number"
                value={year}
                onChange={(e) => setYear(parseInt(e.target.value) || today.getFullYear())}
                className="form-input"
              />
            </Field>
            <Field label="月份">
              <input
                type="number"
                value={month}
                onChange={(e) => setMonth(parseInt(e.target.value) || today.getMonth() + 1)}
                min={1}
                max={12}
                className="form-input"
              />
            </Field>
          </div>
        )}

        {scope === 'incident' && (
          <Field label="风险/事故 ID(UUID)">
            <input
              value={incidentId}
              onChange={(e) => setIncidentId(e.target.value)}
              placeholder="risk_alerts.id,从监控台事件流复制"
              className="form-input"
            />
          </Field>
        )}

        <div
          className="text-[11px] rounded p-2"
          style={{ background: 'rgba(168,85,247,0.08)', color: '#c084fc' }}
        >
          ⏱ 生成可能需要 30-120 秒,完成后将自动加入复盘库
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            disabled={busy}
            className="px-3 py-1.5 rounded text-sm"
            style={{
              background: 'var(--color-bg-card)',
              color: 'var(--color-text-secondary)',
            }}
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={busy}
            className="px-4 py-1.5 rounded text-sm text-white flex items-center gap-1.5 disabled:opacity-50"
            style={{ background: 'linear-gradient(135deg, #a855f7, #ec4899)' }}
          >
            {busy ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
            {busy ? '生成中...' : '开始生成'}
          </button>
        </div>
      </div>
    </div>
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
