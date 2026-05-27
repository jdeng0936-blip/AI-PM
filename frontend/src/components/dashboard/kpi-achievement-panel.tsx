/**
 * components/dashboard/kpi-achievement-panel.tsx — Phase 9 KPI 达成率面板
 *
 * 渲染位置: /dashboard 内, canManageAlerts 守卫块下方。
 * 数据源: GET /api/v1/admin/kpi/achievement?period=<weekly|monthly|quarterly>
 * 业务规则: 达成绿 / 未达成红 / 暂无数据灰。
 */
'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Target } from 'lucide-react'
import { CompareBarChart } from '@/components/charts'
import {
  getKpiAchievement,
  type AchievementStatus,
  type KpiAchievementResponse,
  type KpiAchievementRow,
  type KpiMetric,
  type KpiPeriod,
  type KpiScope,
} from '@/api/kpi'

const PERIOD_OPTIONS: { value: KpiPeriod; label: string }[] = [
  { value: 'weekly', label: '周' },
  { value: 'monthly', label: '月' },
  { value: 'quarterly', label: '季' },
]

const SCOPE_LABELS: Record<KpiScope, string> = {
  global: '全公司',
  department: '部门',
  role: '岗位',
}

const METRIC_LABELS: Record<KpiMetric, string> = {
  submit_rate: '日报提交率',
  avg_score: '日报均分',
  blocker_resolve_days: '阻塞解决天数',
  objective_completion: 'OKR 完成率',
}

const STATUS_STYLE: Record<AchievementStatus, { label: string; color: string; bg: string }> = {
  on_track: { label: '已达成', color: '#16a34a', bg: 'rgba(34,197,94,0.15)' },
  below_target: { label: '未达成', color: '#dc2626', bg: 'rgba(239,68,68,0.15)' },
  no_data: { label: '暂无数据', color: '#64748b', bg: 'rgba(100,116,139,0.15)' },
}

function rowLabel(row: KpiAchievementRow): string {
  const scopeLabel = SCOPE_LABELS[row.scope]
  const scopePart = row.scope_value ? `${scopeLabel}·${row.scope_value}` : scopeLabel
  return `${scopePart}/${METRIC_LABELS[row.metric]}`
}

function formatNumber(value: number | null, suffix = ''): string {
  if (value === null || value === undefined) return '—'
  const text = Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, '')
  return `${text}${suffix}`
}

function metricSuffix(metric: KpiMetric): string {
  return metric === 'submit_rate' || metric === 'objective_completion' ? '%' : ''
}

function getErrorMessage(error: any) {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) return detail[0]?.msg || '加载达成率失败'
  return detail || '加载达成率失败'
}

export function KpiAchievementPanel() {
  const [period, setPeriod] = useState<KpiPeriod>('monthly')
  const [data, setData] = useState<KpiAchievementResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const loadData = useCallback(async (p: KpiPeriod) => {
    setLoading(true)
    try {
      const res = await getKpiAchievement(p)
      setData(res)
    } catch (error: any) {
      toast.error(getErrorMessage(error))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadData(period)
  }, [period, loadData])

  const chartData = useMemo(() => {
    if (!data) return []
    return data.rows.map((row) => ({
      label: rowLabel(row),
      target: row.target_value,
      actual: row.actual_value,
    }))
  }, [data])

  return (
    <div className="mb-8 animate-in" style={{ animationDelay: '0.36s' }}>
      <div className="section-title flex items-center gap-2">
        <Target size={16} color="#22c55e" />
        KPI 达成率
        {data?.snapshot_at && (
          <span className="text-[10px] font-normal" style={{ color: 'var(--color-text-secondary)' }}>
            快照 · {new Date(data.snapshot_at).toLocaleString('zh-CN')}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>周期</span>
          <select
            value={period}
            onChange={(e) => setPeriod(e.target.value as KpiPeriod)}
            className="px-2 py-1 rounded-lg text-xs outline-none"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
          >
            {PERIOD_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
          </select>
        </div>
      </div>

      <div className="stat-card mb-4">
        <CompareBarChart
          data={chartData}
          bars={[
            { dataKey: 'target', name: '目标', color: '#3b82f6' },
            { dataKey: 'actual', name: '实际', color: '#22c55e' },
          ]}
          xKey="label"
          yDomain={[0, 100]}
          emptyLabel={loading ? '加载中...' : '暂无 KPI 目标'}
        />
      </div>

      <div className="rounded-xl overflow-hidden" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr style={{ background: 'var(--color-bg-secondary)' }}>
                {['范围', '指标', '目标值', '实际值', '缺口', '达成率', '状态'].map((header) => (
                  <th key={header} className="text-left py-2.5 px-4 text-xs font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(!data || data.rows.length === 0) && (
                <tr>
                  <td colSpan={7} className="text-center py-10 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                    {loading ? '加载中...' : '暂无 KPI 数据'}
                  </td>
                </tr>
              )}
              {data?.rows.map((row, idx) => {
                const style = STATUS_STYLE[row.status]
                const suffix = metricSuffix(row.metric)
                return (
                  <tr key={`${row.scope}-${row.scope_value ?? '_'}-${row.metric}-${idx}`} style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-primary)' }}>
                      {SCOPE_LABELS[row.scope]}{row.scope_value ? ` · ${row.scope_value}` : ''}
                    </td>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-secondary)' }}>{METRIC_LABELS[row.metric]}</td>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-primary)' }}>{formatNumber(row.target_value, suffix)}</td>
                    <td className="py-2.5 px-4" style={{ color: row.actual_value === null ? 'var(--color-text-secondary)' : 'var(--color-text-primary)' }}>
                      {row.actual_value === null ? '暂无数据' : formatNumber(row.actual_value, suffix)}
                    </td>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-secondary)' }}>{formatNumber(row.gap, suffix)}</td>
                    <td className="py-2.5 px-4" style={{ color: 'var(--color-text-secondary)' }}>
                      {row.achievement_rate === null ? '—' : `${row.achievement_rate.toFixed(1)}%`}
                    </td>
                    <td className="py-2.5 px-4">
                      <span className="inline-block px-2 py-0.5 rounded text-[11px] font-medium" style={{ color: style.color, background: style.bg }}>
                        {style.label}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
