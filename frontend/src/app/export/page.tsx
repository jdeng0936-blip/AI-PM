/**
 * app/export/page.tsx — 数据导出页
 *
 * 按日期范围导出日报为 Excel / CSV
 */
'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react'

export default function ExportPage() {
  const today = new Date().toISOString().split('T')[0]
  const weekAgo = new Date(Date.now() - 6 * 86400000).toISOString().split('T')[0]

  const [startDate, setStartDate] = useState(weekAgo)
  const [endDate, setEndDate] = useState(today)
  const [loading, setLoading] = useState<string | null>(null)

  async function handleExport(format: 'xlsx' | 'csv') {
    setLoading(format)
    try {
      const token = localStorage.getItem('aipm_token')
      const endpoint = format === 'xlsx' ? 'daily-reports' : 'daily-reports-csv'
      const url = `/api/v1/export/${endpoint}?start_date=${startDate}&end_date=${endDate}`

      const resp = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      })

      if (!resp.ok) throw new Error('导出失败')

      const blob = await resp.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `AI日报_${startDate}_${endDate}.${format}`
      a.click()
      URL.revokeObjectURL(a.href)
      toast.success(`${format.toUpperCase()} 导出成功`)
    } catch {
      toast.error('导出失败，请重试')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="page-container">
      <div className="mb-6 animate-in">
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
          数据导出
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
          按日期范围导出日报数据
        </p>
      </div>

      <div className="stat-card max-w-lg animate-in" style={{ animationDelay: '0.1s' }}>
        {/* 日期选择 */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div>
            <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>
              起始日期
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
              style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
            />
          </div>
          <div>
            <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>
              结束日期
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
              style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
            />
          </div>
        </div>

        {/* 导出按钮 */}
        <div className="flex gap-3">
          <button
            onClick={() => handleExport('xlsx')}
            disabled={!!loading}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium text-white transition-all disabled:opacity-50"
            style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
          >
            {loading === 'xlsx' ? <Loader2 size={16} className="animate-spin" /> : <FileSpreadsheet size={16} />}
            导出 Excel
          </button>
          <button
            onClick={() => handleExport('csv')}
            disabled={!!loading}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium text-white transition-all disabled:opacity-50"
            style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}
          >
            {loading === 'csv' ? <Loader2 size={16} className="animate-spin" /> : <FileText size={16} />}
            导出 CSV
          </button>
        </div>
      </div>
    </div>
  )
}
