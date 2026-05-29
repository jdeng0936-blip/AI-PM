/**
 * components/followup-timeline.tsx — 项目跟进时间轴(T-1106)
 *
 * 数据源:GET /api/v1/projects/{id}/followups + POST /api/v1/projects/{id}/followups
 */
'use client'

import { useCallback, useEffect, useState } from 'react'
import { createFollowup, listFollowups, type ProjectFollowUp } from '@/api/projects'
import { toast } from 'sonner'
import { MessageCircle, RefreshCw, Send } from 'lucide-react'

interface FollowupTimelineProps {
  projectId: string
  onAdded?: () => void
}

function formatRelative(iso: string): string {
  const now = new Date()
  const then = new Date(iso)
  const diff = (now.getTime() - then.getTime()) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)} 天前`
  return then.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

function initialOf(name: string | null): string {
  return (name || '系').charAt(0)
}

export default function FollowupTimeline({ projectId, onAdded }: FollowupTimelineProps) {
  const [items, setItems] = useState<ProjectFollowUp[]>([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [content, setContent] = useState('')

  const fetchAll = useCallback(async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const data = await listFollowups(projectId, 50)
      setItems((data as unknown as ProjectFollowUp[]) || [])
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '加载跟进记录失败')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  async function handleSubmit() {
    const trimmed = content.trim()
    if (!trimmed) {
      toast.error('请输入跟进内容')
      return
    }
    if (trimmed.length > 1024) {
      toast.error('内容超过 1024 字符上限')
      return
    }

    setSubmitting(true)
    try {
      await createFollowup(projectId, trimmed)
      setContent('')
      toast.success('跟进已记录')
      await fetchAll()
      onAdded?.()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '追加失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="stat-card">
        <div className="section-title flex items-center gap-2">
          <MessageCircle size={14} />
          追加跟进
        </div>
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={3}
          maxLength={1024}
          placeholder="记录最新进展、协作动态、阶段性发现..."
          className="w-full px-3 py-2 rounded-lg text-sm outline-none resize-none mt-2"
          style={{
            background: 'var(--color-bg-secondary)',
            border: '1px solid var(--color-border-subtle)',
            color: 'var(--color-text-primary)',
          }}
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
            {content.length}/1024
          </span>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={submitting || !content.trim()}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white disabled:opacity-50"
            style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
          >
            <Send size={12} />
            {submitting ? '提交中...' : '追加'}
          </button>
        </div>
      </div>

      <div className="stat-card">
        <div className="flex items-center justify-between mb-3">
          <div className="section-title">跟进时间轴({items.length})</div>
          <button
            type="button"
            onClick={fetchAll}
            disabled={loading}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
            刷新
          </button>
        </div>

        {loading && items.length === 0 && (
          <div className="text-center text-xs py-8" style={{ color: 'var(--color-text-secondary)' }}>
            加载中...
          </div>
        )}

        {!loading && items.length === 0 && (
          <div className="text-center py-8" style={{ color: 'var(--color-text-secondary)' }}>
            <MessageCircle size={32} className="mx-auto opacity-30 mb-2" />
            <p className="text-xs">暂无跟进记录</p>
          </div>
        )}

        {items.length > 0 && (
          <div className="space-y-3">
            {items.map((item) => (
              <div
                key={item.id}
                className="flex gap-3 rounded-lg p-3"
                style={{ background: 'var(--color-bg-secondary)' }}
              >
                <div
                  className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold text-white shrink-0"
                  style={{ background: 'linear-gradient(135deg, #14b8a6, #3b82f6)' }}
                >
                  {initialOf(item.created_by_name)}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs font-medium" style={{ color: 'var(--color-text-primary)' }}>
                      {item.created_by_name || '系统'}
                    </span>
                    <span className="text-[10px] shrink-0" style={{ color: 'var(--color-text-secondary)' }}>
                      {formatRelative(item.created_at)}
                    </span>
                  </div>
                  <p
                    className="text-sm mt-1 whitespace-pre-wrap break-words leading-6"
                    style={{ color: 'var(--color-text-primary)' }}
                  >
                    {item.content}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
