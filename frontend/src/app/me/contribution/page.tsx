'use client'

import { useEffect, useState } from 'react'
import { ChevronDown, Trophy } from 'lucide-react'
import { toast } from 'sonner'
import {
  getMyContribution,
  getMyLedger,
  type ContributionPeriod,
  type LedgerEntryOut,
  type UserContributionResponse,
} from '@/api/milestones'

const PERIODS: Array<{ value: ContributionPeriod; label: string }> = [
  { value: 'all', label: '累计' },
  { value: 'year', label: '全年' },
  { value: 'quarter', label: '本季' },
  { value: 'month', label: '本月' },
]

const directionColor = {
  income: '#16a34a',
  refund: '#dc2626',
  adjustment: '#6b7280',
}

function formatTime(value: string) {
  try {
    return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return value
  }
}

export default function MyContributionPage() {
  const [period, setPeriod] = useState<ContributionPeriod>('all')
  const [data, setData] = useState<UserContributionResponse | null>(null)
  const [ledger, setLedger] = useState<LedgerEntryOut[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([getMyContribution(period), getMyLedger(20)])
      .then(([summary, history]) => {
        if (cancelled) return
        setData(summary)
        setLedger(history.items)
        setCursor(history.next_cursor || null)
      })
      .catch((err) => toast.error(err?.response?.data?.detail || '加载贡献积分失败'))
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [period])

  async function loadMore() {
    if (!cursor) return
    try {
      const history = await getMyLedger(20, cursor)
      setLedger((items) => [...items, ...history.items])
      setCursor(history.next_cursor || null)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || '加载更多失败')
    }
  }

  const summary = data?.summary

  return (
    <main className="min-h-screen p-6" style={{ background: 'var(--color-bg-primary)' }}>
      <div className="mx-auto max-w-5xl space-y-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>我的贡献积分</h1>
            <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>里程碑终批后的个人积分账户</p>
          </div>
          <div className="flex gap-2">
            {PERIODS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => setPeriod(item.value)}
                className="rounded-lg px-3 py-2 text-sm"
                style={{
                  background: period === item.value ? '#2563eb' : 'var(--color-bg-card)',
                  border: '1px solid var(--color-border-subtle)',
                  color: period === item.value ? '#fff' : 'var(--color-text-primary)',
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <section className="rounded-lg p-5" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                <Trophy size={16} />
                当前周期总积分
              </div>
              <div className="mt-3 text-4xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                {loading && !summary ? '...' : summary?.total_points ?? 0}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <span className="rounded-lg px-3 py-2" style={{ background: 'rgba(22,163,74,0.12)', color: '#16a34a' }}>入账 {summary?.income_points ?? 0}</span>
              <span className="rounded-lg px-3 py-2" style={{ background: 'rgba(220,38,38,0.12)', color: '#dc2626' }}>冲销 {summary?.refund_points ?? 0}</span>
              <span className="rounded-lg px-3 py-2" style={{ background: 'rgba(107,114,128,0.12)', color: '#6b7280' }}>调整 {summary?.adjustment_points ?? 0}</span>
              <span className="rounded-lg px-3 py-2" style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-primary)' }}>节点 {summary?.milestone_count ?? 0}</span>
            </div>
          </div>
        </section>

        <section className="rounded-lg" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
          <div className="border-b px-4 py-3 text-sm font-medium" style={{ borderColor: 'var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>积分流水</div>
          {ledger.length === 0 ? (
            <div className="px-4 py-8 text-sm" style={{ color: 'var(--color-text-secondary)' }}>暂无流水</div>
          ) : (
            <div className="divide-y" style={{ borderColor: 'var(--color-border-subtle)' }}>
              {ledger.map((entry) => (
                <div key={entry.id} className="grid grid-cols-[120px_1fr_90px] gap-3 px-4 py-3 text-sm">
                  <div style={{ color: 'var(--color-text-secondary)' }}>{formatTime(entry.occurred_at)}</div>
                  <div>
                    <div className="font-medium" style={{ color: 'var(--color-text-primary)' }}>
                      {entry.project_name || '未关联项目'} · {entry.milestone_title || '未关联节点'}
                    </div>
                    <div className="mt-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{entry.reason}</div>
                  </div>
                  <div className="text-right font-semibold" style={{ color: directionColor[entry.direction] }}>
                    {entry.amount > 0 ? '+' : ''}{entry.amount}
                  </div>
                </div>
              ))}
            </div>
          )}
          {cursor && (
            <div className="border-t p-3 text-center" style={{ borderColor: 'var(--color-border-subtle)' }}>
              <button
                type="button"
                onClick={loadMore}
                className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm"
                style={{ border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
              >
                <ChevronDown size={15} />
                加载更多
              </button>
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
