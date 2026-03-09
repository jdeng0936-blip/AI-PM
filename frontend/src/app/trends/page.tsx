/**
 * app/trends/page.tsx — 评分趋势看板
 *
 * 个人评分趋势 + 部门对比 + AI 周报生成
 */
'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAuthStore } from '@/stores/use-auth-store'
import { getMyScores, getDepartmentStats, getWeeklyReport } from '@/api/trends'
import { toast } from 'sonner'
import { TrendingUp, Building2, FileText, Loader2 } from 'lucide-react'

export default function TrendsPage() {
  const { isAdmin, userName } = useAuthStore()
  const [tab, setTab] = useState<'personal' | 'department' | 'weekly'>('personal')
  const [days, setDays] = useState(30)
  const [myData, setMyData] = useState<any>(null)
  const [deptData, setDeptData] = useState<any>(null)
  const [weeklyData, setWeeklyData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const fetchPersonal = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getMyScores(days)
      setMyData(data)
    } finally {
      setLoading(false)
    }
  }, [days])

  const fetchDept = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getDepartmentStats(days)
      setDeptData(data)
    } finally {
      setLoading(false)
    }
  }, [days])

  const fetchWeekly = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getWeeklyReport()
      setWeeklyData(data)
    } catch {
      toast.error('AI 周报生成失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (tab === 'personal') fetchPersonal()
    else if (tab === 'department' && isAdmin) fetchDept()
    else if (tab === 'weekly' && isAdmin) fetchWeekly()
  }, [tab, fetchPersonal, fetchDept, fetchWeekly, isAdmin])

  const tabs = [
    { key: 'personal', label: '个人趋势', icon: TrendingUp },
    ...(isAdmin ? [
      { key: 'department', label: '部门对比', icon: Building2 },
      { key: 'weekly', label: 'AI 周报', icon: FileText },
    ] : []),
  ]

  const scoreColor = (s: number) => s >= 80 ? '#22c55e' : s >= 60 ? '#eab308' : '#ef4444'

  return (
    <div className="page-container">
      <div className="mb-6 animate-in">
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>评分趋势</h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
          数据驱动的绩效分析
        </p>
      </div>

      {/* Tab 切换 */}
      <div className="flex gap-2 mb-6">
        {tabs.map((t) => {
          const Icon = t.icon
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key as any)}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              style={{
                background: tab === t.key ? 'rgba(59,130,246,0.15)' : 'transparent',
                color: tab === t.key ? '#3b82f6' : 'var(--color-text-secondary)',
                border: `1px solid ${tab === t.key ? '#3b82f6' : 'var(--color-border-subtle)'}`,
              }}
            >
              <Icon size={16} />
              {t.label}
            </button>
          )
        })}

        {/* 天数选择 */}
        {tab !== 'weekly' && (
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="ml-auto px-3 py-2 rounded-lg text-sm outline-none"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
          >
            <option value={7}>近 7 天</option>
            <option value={14}>近 14 天</option>
            <option value={30}>近 30 天</option>
            <option value={60}>近 60 天</option>
          </select>
        )}
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20" style={{ color: 'var(--color-text-secondary)' }}>
          <Loader2 size={24} className="animate-spin mr-2" />
          加载中...
        </div>
      )}

      {/* 个人趋势 */}
      {tab === 'personal' && myData && !loading && (
        <div className="animate-in">
          {/* 摘要卡片 */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
            {[
              { label: '提交数', value: myData.summary.total_reports },
              { label: '平均分', value: myData.summary.avg_score, color: scoreColor(myData.summary.avg_score) },
              { label: '最高', value: myData.summary.max_score, color: '#22c55e' },
              { label: '最低', value: myData.summary.min_score, color: '#ef4444' },
              { label: '通过率', value: `${myData.summary.pass_rate}%` },
            ].map((s, i) => (
              <div key={i} className="stat-card text-center">
                <div className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>{s.label}</div>
                <div className="text-2xl font-bold" style={{ color: s.color || 'var(--color-text-primary)' }}>{s.value}</div>
              </div>
            ))}
          </div>

          {/* 逐日评分柱图（简化版，纯 CSS） */}
          <div className="stat-card">
            <div className="text-sm font-semibold mb-4" style={{ color: 'var(--color-text-primary)' }}>
              {userName} 近 {days} 天评分
            </div>
            <div className="flex items-end gap-1" style={{ height: 160 }}>
              {(myData.daily || []).map((d: any, i: number) => (
                <div key={i} className="flex-1 flex flex-col items-center gap-1">
                  <div
                    className="w-full rounded-t-sm transition-all"
                    style={{
                      height: `${(d.score || 0) * 1.4}px`,
                      background: d.pass_check ? 'rgba(34,197,94,0.6)' : 'rgba(239,68,68,0.6)',
                      minHeight: 4,
                    }}
                    title={`${d.date}: ${d.score}分`}
                  />
                </div>
              ))}
            </div>
            <div className="flex justify-between mt-2 text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
              <span>{myData.daily?.[0]?.date}</span>
              <span>{myData.daily?.[myData.daily.length - 1]?.date}</span>
            </div>
          </div>
        </div>
      )}

      {/* 部门对比 */}
      {tab === 'department' && deptData && !loading && (
        <div className="animate-in">
          <div className="grid grid-cols-1 gap-4">
            {(deptData.departments || []).map((d: any, i: number) => (
              <div key={i} className="stat-card flex items-center gap-5">
                <div className="text-center shrink-0" style={{ minWidth: 60 }}>
                  <div className="text-2xl font-bold" style={{ color: scoreColor(d.avg_score) }}>{d.avg_score}</div>
                  <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>均分</div>
                </div>
                <div className="flex-1">
                  <div className="font-semibold text-sm" style={{ color: 'var(--color-text-primary)' }}>{d.department}</div>
                  <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                    {d.total_members}人 · {d.report_count}份日报 · 通过率 {d.pass_rate}%
                  </div>
                  {/* 进度条 */}
                  <div className="mt-2 h-2 rounded-full overflow-hidden" style={{ background: 'var(--color-bg-secondary)' }}>
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${Math.min(d.avg_score, 100)}%`, background: scoreColor(d.avg_score) }}
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* AI 周报 */}
      {tab === 'weekly' && weeklyData && !loading && (
        <div className="animate-in">
          <div className="stat-card">
            <div className="flex items-center justify-between mb-4">
              <div className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                📋 {weeklyData.week} 管理层周报
              </div>
              <span className="text-xs px-2 py-0.5 rounded-full" style={{ background: 'rgba(59,130,246,0.15)', color: '#3b82f6' }}>
                {weeklyData.total_reports} 份日报
              </span>
            </div>
            <div
              className="text-sm leading-relaxed whitespace-pre-wrap"
              style={{ color: 'var(--color-text-primary)' }}
            >
              {weeklyData.report}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
