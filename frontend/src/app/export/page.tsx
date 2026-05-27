/**
 * app/export/page.tsx — 数据导出页
 */
'use client'

import type { ReactNode } from 'react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { CalendarDays, FileSpreadsheet, FileText, Layers3, Loader2 } from 'lucide-react'

import { getProjectsOverview } from '@/api/projects'

type ExportKey = 'legacy-xlsx' | 'legacy-csv' | 'reports-xlsx' | 'scores-pdf' | 'project-xlsx'

type ProjectOption = {
  id: string
  code: string
  name: string
}

type DepartmentCompareResponse = {
  departments?: Array<{ department?: string }>
}

const inputStyle = {
  background: 'var(--color-bg-secondary)',
  border: '1px solid var(--color-border-subtle)',
  color: 'var(--color-text-primary)',
}

export default function ExportPage() {
  const today = new Date().toISOString().slice(0, 10)
  const weekAgo = new Date(Date.now() - 6 * 86400000).toISOString().slice(0, 10)
  const currentMonth = today.slice(0, 7)

  const [startDate, setStartDate] = useState(weekAgo)
  const [endDate, setEndDate] = useState(today)
  const [month, setMonth] = useState(currentMonth)
  const [department, setDepartment] = useState('')
  const [departments, setDepartments] = useState<string[]>([])
  const [projects, setProjects] = useState<ProjectOption[]>([])
  const [projectId, setProjectId] = useState('')
  const [loading, setLoading] = useState<ExportKey | null>(null)

  useEffect(() => {
    let mounted = true

    async function loadOptions() {
      try {
        const token = localStorage.getItem('aipm_token')
        const [projectResult, departmentResult] = await Promise.allSettled([
          getProjectsOverview(false, null, true),
          fetch('/api/analytics/department-compare?period=week&weeks=8', {
            headers: token ? { Authorization: `Bearer ${token}` } : undefined,
          }),
        ])

        if (!mounted) return

        if (projectResult.status === 'fulfilled') {
          const raw = projectResult.value as { projects?: Array<Record<string, unknown>> }
          const options = (raw.projects || [])
            .map((project) => ({
              id: String(project.project_id || project.id || ''),
              code: String(project.code || ''),
              name: String(project.name || ''),
            }))
            .filter((project) => project.id)
          setProjects(options)
          setProjectId((current) => current || options[0]?.id || '')
        }

        if (departmentResult.status === 'fulfilled' && departmentResult.value.ok) {
          const data = (await departmentResult.value.json()) as DepartmentCompareResponse
          const nextDepartments = Array.from(
            new Set((data.departments || []).map((item) => item.department).filter(Boolean) as string[]),
          ).sort()
          setDepartments(nextDepartments)
        }
      } catch {
        if (mounted) toast.error('加载导出选项失败')
      }
    }

    loadOptions()
    return () => {
      mounted = false
    }
  }, [])

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === projectId),
    [projectId, projects],
  )

  async function downloadFile(url: string, filename: string, loadingKey: ExportKey, successMessage: string) {
    setLoading(loadingKey)
    try {
      const token = localStorage.getItem('aipm_token')
      const resp = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })

      if (!resp.ok) {
        throw new Error(await readErrorMessage(resp))
      }

      const blob = await resp.blob()
      const objectUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = objectUrl
      anchor.download = filename
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(objectUrl)
      toast.success(successMessage)
    } catch (error) {
      toast.error(error instanceof Error && error.message ? error.message : '导出失败')
    } finally {
      setLoading(null)
    }
  }

  async function exportLegacy(format: 'xlsx' | 'csv') {
    const endpoint = format === 'xlsx' ? 'daily-reports' : 'daily-reports-csv'
    const params = new URLSearchParams({ start_date: startDate, end_date: endDate })
    await downloadFile(
      `/api/v1/export/${endpoint}?${params.toString()}`,
      `AI日报_${startDate}_${endDate}.${format}`,
      format === 'xlsx' ? 'legacy-xlsx' : 'legacy-csv',
      `${format.toUpperCase()} 导出成功`,
    )
  }

  async function exportReportsWorkbook() {
    const params = new URLSearchParams({
      format: 'xlsx',
      start_date: startDate,
      end_date: endDate,
    })
    if (department) params.set('department', department)
    await downloadFile(
      `/api/v1/export/reports?${params.toString()}`,
      `AI日报汇总_${startDate}_${endDate}.xlsx`,
      'reports-xlsx',
      '日报多维汇总导出成功',
    )
  }

  async function exportScoresPdf() {
    const params = new URLSearchParams({ format: 'pdf', month })
    if (department) params.set('department', department)
    await downloadFile(
      `/api/v1/export/scores?${params.toString()}`,
      `评分报告_${month}.pdf`,
      'scores-pdf',
      '月度评分报告导出成功',
    )
  }

  async function exportProjectSummary() {
    if (!projectId) {
      toast.warning('请选择项目')
      return
    }

    const params = new URLSearchParams({ format: 'xlsx', project_id: projectId })
    const code = selectedProject?.code || projectId.slice(0, 8)
    await downloadFile(
      `/api/v1/export/project-summary?${params.toString()}`,
      `项目摘要_${code}_${today}.xlsx`,
      'project-xlsx',
      '项目摘要导出成功',
    )
  }

  return (
    <div className="page-container">
      <div className="mb-6 animate-in">
        <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
          数据导出
        </h1>
        <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>
          Excel 与 PDF 汇报文件
        </p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <ExportCard
          title="日报 Excel / CSV"
          subtitle="兼容原有日报明细导出"
          icon={<FileSpreadsheet size={18} />}
          accent="#22c55e"
          delay="0.05s"
        >
          <DateRangeControls
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <ExportButton
              icon={<FileSpreadsheet size={16} />}
              label="导出 Excel"
              loading={loading === 'legacy-xlsx'}
              disabled={!!loading}
              onClick={() => exportLegacy('xlsx')}
              color="#22c55e"
            />
            <ExportButton
              icon={<FileText size={16} />}
              label="导出 CSV"
              loading={loading === 'legacy-csv'}
              disabled={!!loading}
              onClick={() => exportLegacy('csv')}
              color="#3b82f6"
            />
          </div>
        </ExportCard>

        <ExportCard
          title="日报多维汇总"
          subtitle="汇总、每日明细、部门小结"
          icon={<Layers3 size={18} />}
          accent="#0ea5e9"
          delay="0.1s"
        >
          <DateRangeControls
            startDate={startDate}
            endDate={endDate}
            onStartDateChange={setStartDate}
            onEndDateChange={setEndDate}
          />
          <DepartmentSelect value={department} options={departments} onChange={setDepartment} />
          <ExportButton
            icon={<FileSpreadsheet size={16} />}
            label="下载 XLSX"
            loading={loading === 'reports-xlsx'}
            disabled={!!loading}
            onClick={exportReportsWorkbook}
            color="#0ea5e9"
          />
        </ExportCard>

        <ExportCard
          title="月度评分报告"
          subtitle="评分对比、员工排行、风险预警"
          icon={<CalendarDays size={18} />}
          accent="#a855f7"
          delay="0.15s"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="月份">
              <input
                type="month"
                value={month}
                onChange={(event) => setMonth(event.target.value)}
                className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
                style={inputStyle}
              />
            </Field>
            <DepartmentSelect value={department} options={departments} onChange={setDepartment} />
          </div>
          <ExportButton
            icon={<FileText size={16} />}
            label="下载 PDF"
            loading={loading === 'scores-pdf'}
            disabled={!!loading}
            onClick={exportScoresPdf}
            color="#a855f7"
          />
        </ExportCard>

        <ExportCard
          title="项目摘要"
          subtitle="概况、Sprint、日报、风险卡点"
          icon={<FileSpreadsheet size={18} />}
          accent="#f59e0b"
          delay="0.2s"
        >
          <Field label="项目">
            <select
              value={projectId}
              onChange={(event) => setProjectId(event.target.value)}
              className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
              style={inputStyle}
            >
              <option value="">选择项目</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.code ? `${project.code} · ${project.name}` : project.name}
                </option>
              ))}
            </select>
          </Field>
          <ExportButton
            icon={<FileSpreadsheet size={16} />}
            label="下载 XLSX"
            loading={loading === 'project-xlsx'}
            disabled={!!loading || !projectId}
            onClick={exportProjectSummary}
            color="#f59e0b"
          />
        </ExportCard>
      </div>
    </div>
  )
}

function ExportCard({
  title,
  subtitle,
  icon,
  accent,
  delay,
  children,
}: {
  title: string
  subtitle: string
  icon: ReactNode
  accent: string
  delay: string
  children: ReactNode
}) {
  return (
    <section className="stat-card animate-in" style={{ animationDelay: delay }}>
      <div className="flex items-start gap-3 mb-5">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: `${accent}1f`, color: accent }}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            {title}
          </h2>
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
            {subtitle}
          </p>
        </div>
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  )
}

function DateRangeControls({
  startDate,
  endDate,
  onStartDateChange,
  onEndDateChange,
}: {
  startDate: string
  endDate: string
  onStartDateChange: (value: string) => void
  onEndDateChange: (value: string) => void
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      <Field label="起始日期">
        <input
          type="date"
          value={startDate}
          onChange={(event) => onStartDateChange(event.target.value)}
          className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
          style={inputStyle}
        />
      </Field>
      <Field label="结束日期">
        <input
          type="date"
          value={endDate}
          onChange={(event) => onEndDateChange(event.target.value)}
          className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
          style={inputStyle}
        />
      </Field>
    </div>
  )
}

function DepartmentSelect({
  value,
  options,
  onChange,
}: {
  value: string
  options: string[]
  onChange: (value: string) => void
}) {
  return (
    <Field label="部门">
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full px-3 py-2.5 rounded-lg text-sm outline-none"
        style={inputStyle}
      >
        <option value="">全部门</option>
        {options.map((department) => (
          <option key={department} value={department}>
            {department}
          </option>
        ))}
      </select>
    </Field>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>
        {label}
      </span>
      {children}
    </label>
  )
}

function ExportButton({
  icon,
  label,
  loading,
  disabled,
  onClick,
  color,
}: {
  icon: ReactNode
  label: string
  loading: boolean
  disabled: boolean
  onClick: () => void
  color: string
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg text-sm font-medium text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed"
      style={{ background: color }}
    >
      {loading ? <Loader2 size={16} className="animate-spin" /> : icon}
      {label}
    </button>
  )
}

async function readErrorMessage(resp: Response) {
  const fallback = '导出失败，请重试'
  const text = await resp.text()
  if (!text) return fallback

  try {
    const data = JSON.parse(text) as { detail?: unknown }
    if (typeof data.detail === 'string') return data.detail
    if (data.detail) return JSON.stringify(data.detail)
  } catch {
    return text
  }

  return fallback
}
