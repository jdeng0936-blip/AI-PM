'use client'

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Loader2,
  RotateCcw,
  Trash2,
} from 'lucide-react'
import {
  getMyDeletions,
  restoreMyDeletionBatch,
  type MyDeletionBatch,
} from '@/api/me-deletions'

type TableMeta = {
  label: string
  color: string
  bg: string
}

const TABLE_META: Record<string, TableMeta> = {
  daily_reports: { label: '日报', color: '#38bdf8', bg: 'rgba(56,189,248,0.14)' },
  projects: { label: '项目', color: '#22c55e', bg: 'rgba(34,197,94,0.14)' },
  sprint_tasks: { label: '任务', color: '#f59e0b', bg: 'rgba(245,158,11,0.14)' },
  risk_alerts: { label: '风险预警', color: '#ef4444', bg: 'rgba(239,68,68,0.14)' },
  knowledge_items: { label: '知识条目', color: '#a855f7', bg: 'rgba(168,85,247,0.14)' },
}

function tableMeta(tableName: string): TableMeta {
  return TABLE_META[tableName] || { label: tableName, color: '#94a3b8', bg: 'rgba(148,163,184,0.14)' }
}

function formatDateTime(value: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  const yyyy = date.getFullYear()
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const mi = String(date.getMinutes()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`
}

function expiryLabel(item: MyDeletionBatch): { label: string; color: string; icon: ReactNode } {
  if (item.restored_at) {
    return {
      label: `已于 ${formatDateTime(item.restored_at)} 恢复`,
      color: 'var(--color-text-muted)',
      icon: <CheckCircle2 size={13} />,
    }
  }
  const days = item.days_remaining ?? 0
  if (days <= 0) {
    return {
      label: '已过期',
      color: '#ef4444',
      icon: <AlertTriangle size={13} />,
    }
  }
  if (days <= 7) {
    return {
      label: `剩余 ${days} 天`,
      color: '#ef4444',
      icon: <AlertTriangle size={13} />,
    }
  }
  return {
    label: `剩余 ${days} 天`,
    color: '#22c55e',
    icon: <Clock3 size={13} />,
  }
}

export default function MyDeletionsPage() {
  const [items, setItems] = useState<MyDeletionBatch[]>([])
  const [loading, setLoading] = useState(false)
  const [restoringId, setRestoringId] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await getMyDeletions()
      setItems(res.items || [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '加载最近删除失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const activeCount = useMemo(
    () => items.filter((item) => !item.restored_at && (item.days_remaining ?? 0) > 0).length,
    [items],
  )

  async function handleRestore(item: MyDeletionBatch) {
    setRestoringId(item.id)
    try {
      const res = await restoreMyDeletionBatch(item.id)
      toast.success(`已恢复 ${res.restored_count} 条${tableMeta(res.table_name).label}`)
      await load()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '恢复失败')
    } finally {
      setRestoringId(null)
    }
  }

  return (
    <div className="page-container space-y-5">
      <div className="flex items-start justify-between gap-4 flex-wrap animate-in">
        <div>
          <div className="flex items-center gap-2">
            <Trash2 size={22} style={{ color: '#38bdf8' }} />
            <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
              我的最近删除
            </h1>
          </div>
          <p className="text-sm mt-2" style={{ color: 'var(--color-text-secondary)' }}>
            展示最近 30 天你自己执行的删除,过期后自动清理
          </p>
        </div>
        <div
          className="px-3 py-2 rounded-lg text-sm"
          style={{
            color: 'var(--color-text-primary)',
            border: '1px solid var(--color-border-subtle)',
            background: 'var(--color-bg-card)',
          }}
        >
          可恢复 <span style={{ color: '#22c55e', fontWeight: 700 }}>{activeCount}</span> 批
        </div>
      </div>

      {loading ? (
        <div
          className="flex items-center justify-center py-16"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          <Loader2 size={20} className="animate-spin mr-2" />
          加载中...
        </div>
      ) : items.length === 0 ? (
        <div
          className="rounded-lg py-16 text-center"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
            color: 'var(--color-text-secondary)',
          }}
        >
          最近 30 天没有删除记录
        </div>
      ) : (
        <div className="relative pl-5">
          <div
            className="absolute left-[9px] top-2 bottom-2 w-px"
            style={{ background: 'var(--color-border-subtle)' }}
          />
          <div className="space-y-3">
            {items.map((item) => {
              const meta = tableMeta(item.table_name)
              const expiry = expiryLabel(item)
              const expired = !item.restored_at && (item.days_remaining ?? 0) <= 0
              const disabled = Boolean(item.restored_at) || expired || restoringId === item.id
              return (
                <div key={item.id} className="relative animate-in">
                  <div
                    className="absolute -left-[19px] top-5 w-3 h-3 rounded-full"
                    style={{ background: meta.color, boxShadow: `0 0 0 4px ${meta.bg}` }}
                  />
                  <div
                    className="rounded-lg px-4 py-3 flex items-center gap-4"
                    style={{
                      background: 'var(--color-bg-card)',
                      border: '1px solid var(--color-border-subtle)',
                    }}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span
                          className="text-xs px-2 py-1 rounded font-medium"
                          style={{ background: meta.bg, color: meta.color }}
                        >
                          {meta.label}
                        </span>
                        <span className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
                          {item.record_count} 条
                        </span>
                        <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                          删除于 {formatDateTime(item.deleted_at)}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 mt-2 text-xs" style={{ color: expiry.color }}>
                        {expiry.icon}
                        <span>{expiry.label}</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleRestore(item)}
                      disabled={disabled}
                      className="shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-md text-xs font-medium disabled:opacity-45 disabled:cursor-not-allowed"
                      style={{
                        background: disabled ? 'var(--color-bg-secondary)' : '#22c55e',
                        color: disabled ? 'var(--color-text-secondary)' : '#fff',
                      }}
                    >
                      {restoringId === item.id ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <RotateCcw size={13} />
                      )}
                      恢复
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
