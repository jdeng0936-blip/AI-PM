/**
 * components/notification-bell.tsx — 顶栏铃铛 + 未读红点 + 站内信抽屉
 *
 * 行为:
 *   - 60s 轮询 GET /notifications/unread-count
 *   - 点击铃铛展开侧边抽屉,显示最近站内信(channel=in_app)
 *   - 显示时自动调用 mark-read(打开即标记已读,与微信/钉钉行为一致)
 *   - 点击日报相关条目时关闭抽屉(后续可加跳转到 /submit-report)
 */
'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { Bell, X, CheckCheck } from 'lucide-react'
import { toast } from 'sonner'
import {
  getUnreadCount, getNotifications, markRead,
  type NotificationItem,
} from '@/api/notifications'
import { useAuthStore } from '@/stores/use-auth-store'

const POLL_INTERVAL_MS = 60_000

const TEMPLATE_LABEL: Record<string, string> = {
  reminder_soft:    '日报提醒',
  reminder_hard:    '日报催促',
  reminder_missed:  '缺勤通知',
  report_passed:    '日报已收录',
  report_rejected:  '日报需补充',
  risk_alert:       '风险预警',
  daily_briefing:   '战情简报',
  weekly_report:    '管理周报',
  sprint_review:    'Sprint 回顾',
  erp_resolved:     'ERP 解卡',
}

const TEMPLATE_COLOR: Record<string, string> = {
  reminder_soft:    '#3b82f6',
  reminder_hard:    '#f97316',
  reminder_missed:  '#ef4444',
  report_passed:    '#22c55e',
  report_rejected:  '#eab308',
  risk_alert:       '#ef4444',
}

function formatRelative(iso: string): string {
  const ts = new Date(iso).getTime()
  const diff = Date.now() - ts
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return `${Math.floor(diff / 86_400_000)} 天前`
}

export function NotificationBell() {
  const { isLoggedIn } = useAuthStore()
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState<NotificationItem[]>([])
  const [loading, setLoading] = useState(false)
  const timerRef = useRef<any>(null)

  const refreshCount = useCallback(async () => {
    if (!isLoggedIn) return
    try {
      const res = await getUnreadCount()
      setUnread(res?.unread ?? 0)
    } catch {
      // 静默失败 — 避免登录态切换瞬间报错
    }
  }, [isLoggedIn])

  useEffect(() => {
    if (!isLoggedIn) {
      setUnread(0)
      return
    }
    refreshCount()
    timerRef.current = setInterval(refreshCount, POLL_INTERVAL_MS)
    return () => clearInterval(timerRef.current)
  }, [isLoggedIn, refreshCount])

  async function openPanel() {
    setOpen(true)
    setLoading(true)
    try {
      const res = await getNotifications({
        page: 1,
        page_size: 20,
        channel: 'in_app',
        status: 'sent',
      })
      setItems(res.items || [])
      // 打开即视为已读
      if ((res.items || []).some((i) => !i.read_at)) {
        await markRead({ all: true })
        setUnread(0)
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '加载通知失败')
    } finally {
      setLoading(false)
    }
  }

  async function handleMarkAll() {
    try {
      await markRead({ all: true })
      setUnread(0)
      setItems((prev) => prev.map((i) => ({ ...i, read_at: i.read_at || new Date().toISOString() })))
      toast.success('已全部标为已读')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '操作失败')
    }
  }

  if (!isLoggedIn) return null

  return (
    <>
      <button
        type="button"
        onClick={openPanel}
        className="relative p-1.5 rounded-md hover:bg-white/5 transition-colors"
        style={{ color: 'var(--color-text-secondary)' }}
        title="通知"
        aria-label={`通知(${unread} 条未读)`}
      >
        <Bell size={16} />
        {unread > 0 && (
          <span
            className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full text-[10px] font-bold flex items-center justify-center text-white"
            style={{ background: '#ef4444' }}
          >
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex"
          onClick={() => setOpen(false)}
        >
          {/* 遮罩 */}
          <div className="flex-1 bg-black/40" />

          {/* 抽屉 */}
          <div
            className="w-96 max-w-[90vw] h-full flex flex-col"
            style={{ background: 'var(--color-bg-card)', borderLeft: '1px solid var(--color-border-subtle)' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="px-5 py-4 flex items-center justify-between"
              style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
            >
              <div>
                <div className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>通知中心</div>
                <div className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>最近 20 条站内信</div>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={handleMarkAll}
                  className="flex items-center gap-1 text-xs px-2 py-1 rounded-md hover:bg-white/5"
                  style={{ color: 'var(--color-text-secondary)' }}
                  title="全部标为已读"
                >
                  <CheckCheck size={14} /> 全部已读
                </button>
                <button
                  onClick={() => setOpen(false)}
                  className="p-1 rounded-md hover:bg-white/5"
                  style={{ color: 'var(--color-text-secondary)' }}
                  aria-label="关闭"
                >
                  <X size={16} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
              {loading && (
                <div className="text-center text-xs py-8" style={{ color: 'var(--color-text-muted)' }}>加载中...</div>
              )}
              {!loading && items.length === 0 && (
                <div className="text-center text-xs py-12" style={{ color: 'var(--color-text-muted)' }}>
                  暂无通知
                </div>
              )}
              {items.map((n) => {
                const tplLabel = TEMPLATE_LABEL[n.template] || n.template
                const tplColor = TEMPLATE_COLOR[n.template] || '#94a3b8'
                const wasUnread = !n.read_at
                return (
                  <div
                    key={n.id}
                    className="p-3 rounded-lg text-sm"
                    style={{
                      background: wasUnread ? 'rgba(59,130,246,0.06)' : 'var(--color-bg-secondary)',
                      border: `1px solid ${wasUnread ? 'rgba(59,130,246,0.25)' : 'var(--color-border-subtle)'}`,
                    }}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                        style={{ background: `${tplColor}20`, color: tplColor }}
                      >
                        {tplLabel}
                      </span>
                      <span className="text-[11px]" style={{ color: 'var(--color-text-muted)' }}>
                        {formatRelative(n.created_at)}
                      </span>
                    </div>
                    {n.title && (
                      <div className="text-xs font-semibold mb-1" style={{ color: 'var(--color-text-primary)' }}>
                        {n.title}
                      </div>
                    )}
                    <div
                      className="text-xs whitespace-pre-wrap"
                      style={{ color: 'var(--color-text-secondary)', lineHeight: 1.55 }}
                    >
                      {n.body}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
