'use client'

import { useEffect, useMemo, useState } from 'react'
import { CheckCircle, RefreshCw } from 'lucide-react'
import { toast } from 'sonner'
import {
  approveMilestone,
  listAdminMilestones,
  type MilestoneOut,
  type MilestoneStatus,
} from '@/api/milestones'

const TABS: Array<{ value: MilestoneStatus; label: string }> = [
  { value: 'pending', label: '待发起' },
  { value: 'in_review', label: '待审批' },
  { value: 'approved', label: '已入账' },
  { value: 'void', label: '已作废' },
]

const statusLabel: Record<MilestoneStatus, string> = {
  pending: '待发起',
  in_review: '待审批',
  approved: '已入账',
  void: '已作废',
}

type AdminMilestone = MilestoneOut & { project_name?: string | null }

export default function AdminMilestonesPage() {
  const [activeTab, setActiveTab] = useState<MilestoneStatus>('in_review')
  const [items, setItems] = useState<AdminMilestone[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [finalPoints, setFinalPoints] = useState(0)
  const [reason, setReason] = useState('')

  const selected = useMemo(
    () => items.find((item) => item.id === selectedId) || items[0] || null,
    [items, selectedId],
  )

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listAdminMilestones(activeTab)
      .then((data) => {
        if (cancelled) return
        setItems(data.items)
        setSelectedId(data.items[0]?.id || null)
      })
      .catch((err) => toast.error(err?.response?.data?.detail || '加载里程碑失败'))
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [activeTab])

  useEffect(() => {
    if (!selected) return
    setFinalPoints(selected.final_points ?? selected.initial_points)
    setReason(selected.adjustment_reason || '')
  }, [selected])

  async function handleApprove() {
    if (!selected || selected.status !== 'in_review') return
    if (finalPoints !== selected.initial_points && !reason.trim()) {
      toast.error('动态加减分必须填写原因')
      return
    }
    setSubmitting(true)
    try {
      const res = await approveMilestone(selected.id, {
        final_points: finalPoints,
        adjustment_reason: finalPoints !== selected.initial_points ? reason.trim() : null,
      })
      toast.success(`已终批入账 ${res.ledger_entries_created} 条流水`)
      const data = await listAdminMilestones(activeTab)
      setItems(data.items)
      setSelectedId(data.items[0]?.id || null)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '审批失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="min-h-screen p-6" style={{ background: 'var(--color-bg-primary)' }}>
      <div className="mx-auto max-w-6xl space-y-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>里程碑审批</h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>项目节点终批与贡献积分入账</p>
          </div>
          <button
            type="button"
            onClick={() => listAdminMilestones(activeTab).then((data) => setItems(data.items))}
            className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm"
            style={{ border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
          >
            <RefreshCw size={15} />
            刷新
          </button>
        </div>

        <div className="flex gap-2">
          {TABS.map((tab) => (
            <button
              key={tab.value}
              type="button"
              onClick={() => setActiveTab(tab.value)}
              className="rounded-lg px-3 py-2 text-sm"
              style={{
                background: activeTab === tab.value ? '#2563eb' : 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
                color: activeTab === tab.value ? '#fff' : 'var(--color-text-primary)',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
          <section className="overflow-hidden rounded-lg" style={{ border: '1px solid var(--color-border-subtle)' }}>
            <div className="grid grid-cols-[1.2fr_1fr_90px_90px_90px] gap-3 px-4 py-3 text-xs font-medium" style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)' }}>
              <span>节点</span>
              <span>项目</span>
              <span>状态</span>
              <span>初始积分</span>
              <span>最终积分</span>
            </div>
            {loading ? (
              <div className="px-4 py-8 text-sm" style={{ color: 'var(--color-text-secondary)' }}>加载中...</div>
            ) : items.length === 0 ? (
              <div className="px-4 py-8 text-sm" style={{ color: 'var(--color-text-secondary)' }}>暂无数据</div>
            ) : (
              items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                  className="grid w-full grid-cols-[1.2fr_1fr_90px_90px_90px] gap-3 border-t px-4 py-3 text-left text-sm"
                  style={{
                    borderColor: 'var(--color-border-subtle)',
                    background: selected?.id === item.id ? 'rgba(37,99,235,0.10)' : 'var(--color-bg-card)',
                    color: 'var(--color-text-primary)',
                  }}
                >
                  <span className="truncate">{item.title}</span>
                  <span className="truncate">{item.project_name || item.project_id}</span>
                  <span>{statusLabel[item.status]}</span>
                  <span>{item.initial_points}</span>
                  <span>{item.final_points ?? '—'}</span>
                </button>
              ))
            )}
          </section>

          <aside className="rounded-lg p-4" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
            {selected ? (
              <div className="space-y-4">
                <div>
                  <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>当前节点</div>
                  <div className="mt-1 text-base font-semibold" style={{ color: 'var(--color-text-primary)' }}>{selected.title}</div>
                  <div className="mt-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                    初始 {selected.initial_points} 分 · {statusLabel[selected.status]}
                  </div>
                </div>
                <label className="block text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                  最终积分
                  <input
                    type="number"
                    min={0}
                    value={finalPoints}
                    onChange={(event) => setFinalPoints(Number(event.target.value) || 0)}
                    disabled={selected.status !== 'in_review'}
                    className="mt-1 w-full rounded-lg px-3 py-2 text-sm outline-none"
                    style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                  />
                </label>
                <label className="block text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
                  调整原因
                  <textarea
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    disabled={selected.status !== 'in_review'}
                    rows={4}
                    className="mt-1 w-full resize-none rounded-lg px-3 py-2 text-sm outline-none"
                    style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                  />
                </label>
                <button
                  type="button"
                  onClick={handleApprove}
                  disabled={submitting || selected.status !== 'in_review'}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                  style={{ background: '#2563eb' }}
                >
                  <CheckCircle size={15} />
                  {submitting ? '提交中...' : '终批入账'}
                </button>
              </div>
            ) : (
              <div className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>请选择一条里程碑</div>
            )}
          </aside>
        </div>
      </div>
    </main>
  )
}
