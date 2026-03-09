/**
 * app/stats/page.tsx — 系统统计 (port from Vue SystemStats.vue)
 */
'use client'

import { useState, useEffect } from 'react'
import { getTokenUsage, getWeeklyStats } from '@/api/dashboard'
import { RefreshCw, Zap, TrendingUp, FileText } from 'lucide-react'

export default function StatsPage() {
  const [loading, setLoading] = useState(false)
  const [tokenUsage, setTokenUsage] = useState<any>({})
  const [weeklyStats, setWeeklyStats] = useState<any>({})

  async function fetchAll() {
    setLoading(true)
    try {
      const [tu, ws] = await Promise.allSettled([getTokenUsage(), getWeeklyStats()])
      if (tu.status === 'fulfilled') setTokenUsage(tu.value as any)
      if (ws.status === 'fulfilled') setWeeklyStats(ws.value as any)
    } finally { setLoading(false) }
  }

  useEffect(() => { fetchAll() }, [])

  const formatNum = (n: number) => n?.toLocaleString() ?? '-'

  return (
    <div className="page-container">
      <div className="flex items-center justify-between mb-6 animate-in">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>系统统计</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>Token 用量与日报分析趋势</p>
        </div>
        <button onClick={fetchAll} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium" style={{ border: '1px solid var(--color-brand-blue)', color: 'var(--color-brand-blue)' }}>
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />刷新
        </button>
      </div>

      {/* Token 用量 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-8">
        <div className="stat-card animate-in" style={{ animationDelay: '0.1s' }}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'rgba(168,85,247,0.15)' }}>
              <Zap size={20} color="#a855f7" />
            </div>
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>今日 Token</span>
          </div>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-text-primary)' }}>{formatNum(tokenUsage.today_tokens)}</div>
          <div className="text-xs mt-2" style={{ color: 'var(--color-text-secondary)' }}>上限 {formatNum(tokenUsage.daily_limit)}</div>
          {tokenUsage.daily_limit > 0 && (
            <div className="mt-2 h-1.5 rounded-full overflow-hidden" style={{ background: 'var(--color-bg-secondary)' }}>
              <div className="h-full rounded-full transition-all" style={{ width: `${Math.min((tokenUsage.today_tokens / tokenUsage.daily_limit) * 100, 100)}%`, background: 'linear-gradient(90deg, #a855f7, #6366f1)' }} />
            </div>
          )}
        </div>

        <div className="stat-card animate-in" style={{ animationDelay: '0.2s' }}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'rgba(59,130,246,0.15)' }}>
              <TrendingUp size={20} color="#3b82f6" />
            </div>
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>本周调用</span>
          </div>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-text-primary)' }}>{formatNum(tokenUsage.week_calls)}</div>
          <div className="text-xs mt-2" style={{ color: 'var(--color-text-secondary)' }}>总消耗 {formatNum(tokenUsage.week_tokens)} tokens</div>
        </div>

        <div className="stat-card animate-in" style={{ animationDelay: '0.3s' }}>
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-lg flex items-center justify-center" style={{ background: 'rgba(34,197,94,0.15)' }}>
              <FileText size={20} color="#22c55e" />
            </div>
            <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>本周日报</span>
          </div>
          <div className="text-2xl font-bold" style={{ color: 'var(--color-text-primary)' }}>{weeklyStats.total_reports ?? '-'}</div>
          <div className="flex gap-3 mt-2 text-xs">
            <span style={{ color: '#22c55e' }}>✅ {weeklyStats.pass_count ?? 0}</span>
            <span style={{ color: '#ef4444' }}>❌ {weeklyStats.fail_count ?? 0}</span>
            <span style={{ color: 'var(--color-text-secondary)' }}>均分 {weeklyStats.avg_score ?? '-'}</span>
          </div>
        </div>
      </div>

      {/* 每日趋势简表 */}
      {weeklyStats.daily_breakdown && (
        <div className="stat-card animate-in" style={{ animationDelay: '0.4s' }}>
          <div className="section-title">📊 每日趋势</div>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                {['日期', '日报数', '合格', '退回', '均分', 'Token'].map((h) => (
                  <th key={h} className="text-left py-2 px-3 text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(weeklyStats.daily_breakdown as any[]).map((d: any) => (
                <tr key={d.date} style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                  <td className="py-2 px-3 text-xs">{d.date}</td>
                  <td className="py-2 px-3 text-xs">{d.count}</td>
                  <td className="py-2 px-3 text-xs" style={{ color: '#22c55e' }}>{d.pass}</td>
                  <td className="py-2 px-3 text-xs" style={{ color: '#ef4444' }}>{d.fail}</td>
                  <td className="py-2 px-3 text-xs">{d.avg_score}</td>
                  <td className="py-2 px-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{formatNum(d.tokens)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
