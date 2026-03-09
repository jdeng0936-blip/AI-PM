/**
 * app/reports/page.tsx — AI 日报流 (1:1 port from Vue ReportList.vue)
 */
'use client'

import { useState, useEffect, useCallback } from 'react'
import { getReports, getReportDetail } from '@/api/reports'
import { useAuthStore } from '@/stores/use-auth-store'
import { toast } from 'sonner'
import { RefreshCw, Download, Search, X } from 'lucide-react'

function DetailSection({ title, content, type }: { title: string; content?: string; type?: string }) {
  if (!content) return null
  const bgMap: Record<string, string> = { warning: 'rgba(234,179,8,0.08)', danger: 'rgba(239,68,68,0.08)', info: 'rgba(59,130,246,0.08)' }
  const borderMap: Record<string, string> = { warning: 'rgba(234,179,8,0.25)', danger: 'rgba(239,68,68,0.25)', info: 'rgba(59,130,246,0.25)' }
  return (
    <div className="mb-4 rounded-lg p-3" style={{ background: bgMap[type || ''] || 'var(--color-bg-secondary)', border: type ? `1px solid ${borderMap[type]}` : 'none' }}>
      <div className="text-sm font-semibold mb-1" style={{ color: 'var(--color-text-primary)' }}>{title}</div>
      <div className="text-xs whitespace-pre-wrap" style={{ color: 'var(--color-text-secondary)', lineHeight: '1.8' }}>{content}</div>
    </div>
  )
}

function FieldRow({ label, value, highlight, children }: { label: string; value?: string | null; highlight?: boolean; children?: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <span className="text-xs shrink-0" style={{ color: 'var(--color-text-secondary)', minWidth: 70 }}>{label}</span>
      <span className="text-xs flex-1" style={{ color: highlight && value ? '#ef4444' : 'var(--color-text-primary)', fontWeight: highlight && value ? 600 : 'normal' }}>
        {value || '-'}{children}
      </span>
    </div>
  )
}

export default function ReportsPage() {
  const { token } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [reports, setReports] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [filterDate, setFilterDate] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterName, setFilterName] = useState('')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [detail, setDetail] = useState<any>(null)

  const scoreColor = (score: number | null) => {
    if (score == null) return 'var(--color-text-secondary)'
    if (score >= 90) return '#22c55e'
    if (score >= 60) return '#eab308'
    return '#ef4444'
  }

  const fetchReports = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: 20 }
      if (filterDate) params.report_date = filterDate
      if (filterStatus) params.pass_check = filterStatus
      if (filterName) params.user_name = filterName
      const res: any = await getReports(params)
      setReports(Array.isArray(res) ? res : (res.items || []))
      setTotal(res.total || (Array.isArray(res) ? res.length : 0))
    } catch { setReports([]) }
    finally { setLoading(false) }
  }, [page, filterDate, filterStatus, filterName])

  useEffect(() => { fetchReports() }, [fetchReports])

  async function handleRowClick(row: any) {
    setDrawerOpen(true)
    setDetail(null)
    try { setDetail(await getReportDetail(row.id)) }
    catch { toast.error('加载日报详情失败'); setDrawerOpen(false) }
  }

  async function handleExport() {
    setExporting(true)
    try {
      let url = '/api/v1/export/daily-reports'
      if (filterDate) url += `?start_date=${filterDate}&end_date=${filterDate}`
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      if (!resp.ok) throw new Error()
      const blob = await resp.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `AI日报_${filterDate || new Date().toISOString().slice(0, 10)}.xlsx`
      a.click()
      toast.success('导出成功')
    } catch { toast.error('导出失败') }
    finally { setExporting(false) }
  }

  const pc = detail?.parsed_content || {}
  const hasFilters = filterDate || filterStatus || filterName

  return (
    <div className="page-container">
      {/* Header */}
      <div className="flex items-center justify-between mb-6 animate-in">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>AI 日报流</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>大模型质检结果一览</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleExport} disabled={exporting} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium" style={{ border: '1px solid var(--color-status-green)', color: 'var(--color-status-green)' }}>
            <Download size={14} />{exporting ? '导出中...' : '导出 Excel'}
          </button>
          <button onClick={fetchReports} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium" style={{ border: '1px solid var(--color-brand-blue)', color: 'var(--color-brand-blue)' }}>
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />刷新
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="stat-card mb-4 animate-in flex items-center gap-4 flex-wrap" style={{ animationDelay: '0.05s', padding: '12px 16px' }}>
        <input type="date" value={filterDate} onChange={(e) => { setFilterDate(e.target.value); setPage(1) }} className="px-3 py-1.5 rounded-lg text-xs" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)', width: 140 }} />
        <select value={filterStatus} onChange={(e) => { setFilterStatus(e.target.value); setPage(1) }} className="px-3 py-1.5 rounded-lg text-xs" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)', width: 100 }}>
          <option value="">全部</option>
          <option value="true">✅ 合格</option>
          <option value="false">❌ 退回</option>
        </select>
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-muted)' }} />
          <input value={filterName} onChange={(e) => setFilterName(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && fetchReports()} placeholder="搜索姓名" className="pl-8 pr-3 py-1.5 rounded-lg text-xs" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)', width: 130 }} />
        </div>
        {hasFilters && (
          <button onClick={() => { setFilterDate(''); setFilterStatus(''); setFilterName(''); setPage(1) }} className="ml-auto flex items-center gap-1 px-2 py-1 rounded text-[10px]" style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)' }}>
            已筛选 <X size={12} />
          </button>
        )}
      </div>

      {/* Table */}
      <div className="stat-card animate-in overflow-x-auto" style={{ animationDelay: '0.1s' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
              {['日期', '姓名', '部门', 'AI 评分', '今日进展', 'AI 评语', '状态'].map((h) => (
                <th key={h} className="text-left py-3 px-3 text-xs font-semibold" style={{ color: 'var(--color-text-secondary)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {reports.length === 0 ? (
              <tr><td colSpan={7} className="text-center py-12 text-sm" style={{ color: 'var(--color-text-secondary)' }}>暂无日报数据</td></tr>
            ) : reports.map((r: any) => (
              <tr key={r.id} className="cursor-pointer transition-colors hover:bg-white/[0.02]" onClick={() => handleRowClick(r)} style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                <td className="py-3 px-3 text-xs">{r.report_date}</td>
                <td className="py-3 px-3 text-xs">{r.member || r.user_name}</td>
                <td className="py-3 px-3 text-xs">{r.department}</td>
                <td className="py-3 px-3 text-center">
                  <span className="inline-block px-2 py-0.5 rounded-full text-xs font-bold" style={{ background: r.ai_score >= 90 ? 'rgba(34,197,94,0.15)' : r.ai_score >= 60 ? 'rgba(234,179,8,0.15)' : 'rgba(239,68,68,0.15)', color: scoreColor(r.ai_score) }}>
                    {r.ai_score ?? '-'}
                  </span>
                </td>
                <td className="py-3 px-3 text-xs max-w-[200px] truncate">{r.parsed_content?.tasks?.slice(0, 80) || r.raw_input_text?.slice(0, 80) || '-'}</td>
                <td className="py-3 px-3 text-xs max-w-[200px] truncate" style={{ color: 'var(--color-text-secondary)' }}>{r.ai_comment || '-'}</td>
                <td className="py-3 px-3">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-medium" style={{ background: r.pass_check === true ? 'rgba(34,197,94,0.15)' : r.pass_check === false ? 'rgba(239,68,68,0.15)' : 'rgba(100,116,139,0.15)', color: r.pass_check === true ? '#22c55e' : r.pass_check === false ? '#ef4444' : '#94a3b8' }}>
                    {r.pass_check === true ? '合格' : r.pass_check === false ? '退回' : '待审'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {/* Pagination */}
        <div className="flex justify-center gap-2 mt-6">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="px-3 py-1 rounded text-xs disabled:opacity-30" style={{ border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}>上一页</button>
          <span className="px-3 py-1 text-xs" style={{ color: 'var(--color-text-secondary)' }}>第 {page} 页 / 共 {Math.ceil(total / 20) || 1} 页</span>
          <button disabled={page >= Math.ceil(total / 20)} onClick={() => setPage(p => p + 1)} className="px-3 py-1 rounded text-xs disabled:opacity-30" style={{ border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}>下一页</button>
        </div>
      </div>

      {/* Detail Drawer */}
      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={() => setDrawerOpen(false)}>
          <div className="w-[520px] h-full overflow-y-auto p-6" style={{ background: 'var(--color-bg-card)' }} onClick={(e) => e.stopPropagation()}>
            {detail ? (
              <>
                <div className="flex items-center gap-4 mb-6">
                  <div className="text-center">
                    <div className="text-4xl font-bold" style={{ color: scoreColor(detail.ai_score) }}>{detail.ai_score ?? '-'}</div>
                    <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>AI 评分</div>
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-lg font-semibold" style={{ color: 'var(--color-text-primary)' }}>{detail.member}</span>
                      <span className="px-2 py-0.5 rounded-md text-xs font-medium" style={{ background: detail.pass_check ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)', color: detail.pass_check ? '#22c55e' : '#ef4444' }}>
                        {detail.pass_check ? '✅ 合格' : '❌ 退回'}
                      </span>
                    </div>
                    <div className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>{detail.department} · {detail.report_date}</div>
                  </div>
                  <button onClick={() => setDrawerOpen(false)} className="p-1"><X size={20} style={{ color: 'var(--color-text-secondary)' }} /></button>
                </div>
                <DetailSection title="💬 AI 评语" content={detail.ai_comment} />
                {!detail.pass_check && <DetailSection title="⚠️ 退回原因" content={detail.reject_reason} type="warning" />}
                <DetailSection title="📋 修改建议模板" content={detail.suggested_guidance} type="info" />
                <DetailSection title="🚨 管理预警" content={detail.management_alert} type="danger" />
                <div className="my-4" style={{ borderTop: '1px solid var(--color-border-subtle)' }} />
                <div className="text-sm font-semibold mb-3" style={{ color: 'var(--color-text-primary)' }}>🔍 AI 解析结果</div>
                <div className="text-xs font-semibold mb-2" style={{ color: '#3b82f6' }}>📋 计划</div>
                <div className="space-y-3 mb-3"><FieldRow label="今日任务" value={pc?.tasks} /><FieldRow label="验收标准" value={pc?.acceptance_criteria} /><FieldRow label="所需支持" value={pc?.support_needed} /></div>
                <div className="text-xs font-semibold mb-2" style={{ color: '#22c55e' }}>✅ 验收</div>
                <div className="space-y-3 mb-3"><FieldRow label="完成进度" value={pc?.progress != null ? `${pc.progress}%` : null} /><FieldRow label="验收人" value={pc?.reviewer} /><FieldRow label="Git 版本" value={pc?.git_version} /></div>
                <div className="text-xs font-semibold mb-2" style={{ color: '#eab308' }}>🔧 未完成工作复盘</div>
                <div className="space-y-3"><FieldRow label="核心卡点" value={pc?.blocker} highlight /><FieldRow label="解决方案" value={pc?.next_step} /><FieldRow label="预计解决" value={pc?.eta} /></div>
                <div className="my-4" style={{ borderTop: '1px solid var(--color-border-subtle)' }} />
                <div className="text-sm font-semibold mb-2" style={{ color: 'var(--color-text-primary)' }}>📝 原始汇报</div>
                <div className="text-xs rounded-lg p-3 whitespace-pre-wrap" style={{ background: 'var(--color-bg-secondary)', color: 'var(--color-text-secondary)', lineHeight: '1.8' }}>{detail.raw_input_text}</div>
              </>
            ) : (
              <div className="flex items-center justify-center h-full" style={{ color: 'var(--color-text-secondary)' }}>加载中...</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
