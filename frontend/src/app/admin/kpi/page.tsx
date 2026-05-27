/**
 * frontend/src/app/admin/kpi/page.tsx — KPI 目标管理 (Phase 9 / admin + manager)
 *
 * 业务流程:
 *  1. 进入页 → 校验 userRole ∈ {admin, manager},否则 toast + redirect /
 *  2. 加载列表 (loadTargets) → 表格展示
 *  3. 点「+ 新建目标」 → Modal 打开,空表单,提交走 upsert
 *  4. 点行「编辑」 → Modal 打开,四元组只读,target_value 可改,提交走 upsert (后端复用现有 id)
 *
 * 后端 RBAC: admin + manager;前端入口双层守卫,后端是真正的安全边界。
 */
'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Pencil, Plus } from 'lucide-react'
import { useAuthStore } from '@/stores/use-auth-store'
import {
  listKpiTargets,
  upsertKpiTarget,
  type KpiMetric,
  type KpiPeriod,
  type KpiScope,
  type KpiTargetOut,
} from '@/api/kpi'

const SCOPE_OPTIONS: { value: KpiScope; label: string }[] = [
  { value: 'global', label: '全公司' },
  { value: 'department', label: '部门' },
  { value: 'role', label: '岗位' },
]

const METRIC_OPTIONS: { value: KpiMetric; label: string }[] = [
  { value: 'submit_rate', label: '日报提交率(%)' },
  { value: 'avg_score', label: '日报均分' },
  { value: 'blocker_resolve_days', label: '阻塞解决天数' },
  { value: 'objective_completion', label: 'OKR 完成率(%)' },
]

const PERIOD_OPTIONS: { value: KpiPeriod; label: string }[] = [
  { value: 'weekly', label: '周' },
  { value: 'monthly', label: '月' },
  { value: 'quarterly', label: '季' },
]

type KpiFormState = {
  scope: KpiScope
  scope_value: string
  metric: KpiMetric
  period: KpiPeriod
  target_value: string
}

const emptyForm: KpiFormState = {
  scope: 'global',
  scope_value: '',
  metric: 'submit_rate',
  period: 'monthly',
  target_value: '',
}

function optionLabel<T extends string>(options: { value: T; label: string }[], value: T) {
  return options.find((o) => o.value === value)?.label ?? value
}

function formatUpdatedAt(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN')
}

function formatTargetValue(row: KpiTargetOut) {
  const value = Number(row.target_value)
  const text = Number.isInteger(value) ? String(value) : value.toFixed(2).replace(/\.?0+$/, '')
  if (row.metric === 'submit_rate' || row.metric === 'objective_completion') return `${text}%`
  return text
}

function getErrorMessage(error: any, fallback = '操作失败') {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) return detail[0]?.msg || fallback
  return detail || fallback
}

export default function KpiAdminPage() {
  const router = useRouter()
  const { userRole } = useAuthStore()
  const canManage = userRole === 'admin' || userRole === 'manager'

  const [rows, setRows] = useState<KpiTargetOut[]>([])
  const [loading, setLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<KpiFormState>(emptyForm)

  useEffect(() => {
    if (userRole && !canManage) {
      toast.error('需 admin 或 manager 权限')
      router.replace('/')
    }
  }, [userRole, canManage, router])

  const loadTargets = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listKpiTargets()
      setRows(Array.isArray(res) ? res : [])
    } catch (error: any) {
      toast.error(getErrorMessage(error, '加载 KPI 目标失败'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (canManage) {
      loadTargets()
    }
  }, [canManage, loadTargets])

  function openCreate() {
    setEditingId(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  function openEdit(row: KpiTargetOut) {
    setEditingId(row.id)
    setForm({
      scope: row.scope,
      scope_value: row.scope_value ?? '',
      metric: row.metric,
      period: row.period,
      target_value: String(row.target_value),
    })
    setDialogOpen(true)
  }

  async function handleSubmit() {
    const targetNum = parseFloat(form.target_value)
    if (!Number.isFinite(targetNum) || targetNum <= 0) {
      toast.error('target_value 必须 > 0')
      return
    }
    if (form.scope === 'global' && form.scope_value.trim() !== '') {
      toast.error('全公司 scope 必须留空 scope_value')
      return
    }
    if ((form.scope === 'department' || form.scope === 'role') && form.scope_value.trim() === '') {
      toast.error('部门/岗位 scope 必须填写 scope_value')
      return
    }

    setSubmitting(true)
    try {
      await upsertKpiTarget({
        scope: form.scope,
        scope_value: form.scope === 'global' ? null : form.scope_value.trim(),
        metric: form.metric,
        period: form.period,
        target_value: targetNum,
      })
      toast.success(editingId ? '已更新目标' : '已创建目标')
      setDialogOpen(false)
      await loadTargets()
    } catch (error: any) {
      toast.error(getErrorMessage(error, '提交失败'))
    } finally {
      setSubmitting(false)
    }
  }

  const isEditing = editingId !== null
  const immutableDisabled = isEditing

  if (!userRole) {
    return (
      <div className="p-6 max-w-6xl mx-auto">
        <div className="rounded-xl px-4 py-8 text-center text-sm" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-secondary)' }}>
          正在校验权限...
        </div>
      </div>
    )
  }

  if (!canManage) {
    return null
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>KPI 目标管理</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>管理全公司、部门和岗位的 KPI 目标值</p>
        </div>
        <button onClick={openCreate} className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg text-sm text-white font-medium" style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}>
          <Plus size={16} />
          新建目标
        </button>
      </div>

      <div className="rounded-xl overflow-hidden" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[900px] text-sm">
            <thead>
              <tr style={{ background: 'var(--color-bg-secondary)' }}>
                {['范围', '范围值', '指标', '周期', '目标值', '更新时间', '操作'].map((header) => (
                  <th key={header} className="text-left py-3 px-4 text-xs font-semibold" style={{ color: 'var(--color-text-primary)' }}>
                    {header}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && !loading && (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                    暂无 KPI 目标
                  </td>
                </tr>
              )}
              {loading && (
                <tr>
                  <td colSpan={7} className="text-center py-12 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                    加载中...
                  </td>
                </tr>
              )}
              {!loading && rows.map((row) => (
                <tr key={row.id} style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                  <td className="py-3 px-4" style={{ color: 'var(--color-text-primary)' }}>
                    {optionLabel(SCOPE_OPTIONS, row.scope)}
                  </td>
                  <td className="py-3 px-4" style={{ color: 'var(--color-text-secondary)' }}>
                    {row.scope_value ?? '—'}
                  </td>
                  <td className="py-3 px-4" style={{ color: 'var(--color-text-primary)' }}>
                    {optionLabel(METRIC_OPTIONS, row.metric)}
                  </td>
                  <td className="py-3 px-4" style={{ color: 'var(--color-text-secondary)' }}>
                    {optionLabel(PERIOD_OPTIONS, row.period)}
                  </td>
                  <td className="py-3 px-4 font-medium" style={{ color: 'var(--color-text-primary)' }}>
                    {formatTargetValue(row)}
                  </td>
                  <td className="py-3 px-4 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                    {formatUpdatedAt(row.updated_at)}
                  </td>
                  <td className="py-3 px-4">
                    <button onClick={() => openEdit(row)} className="inline-flex items-center gap-1.5 text-xs font-medium" style={{ color: 'var(--color-brand-blue)' }}>
                      <Pencil size={13} />
                      编辑
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex justify-end mt-4 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        共 {rows.length} 条 KPI 目标
      </div>

      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4" onClick={() => setDialogOpen(false)}>
          <div className="w-full max-w-md rounded-2xl p-6" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }} onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-2" style={{ color: 'var(--color-text-primary)' }}>{isEditing ? '编辑 KPI 目标' : '新建 KPI 目标'}</h2>
            {isEditing && (
              <p className="text-xs mb-5" style={{ color: 'var(--color-text-secondary)' }}>该目标已存在,只能修改目标值。</p>
            )}
            {!isEditing && <div className="mb-5" />}

            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>范围</label>
                <select value={form.scope} onChange={(e) => setForm({ ...form, scope: e.target.value as KpiScope, scope_value: e.target.value === 'global' ? '' : form.scope_value })} disabled={immutableDisabled} className="w-full px-3 py-2 rounded-lg text-sm outline-none disabled:opacity-50" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>
                  {SCOPE_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>范围值</label>
                <input value={form.scope_value} onChange={(e) => setForm({ ...form, scope_value: e.target.value })} placeholder={form.scope === 'global' ? '全公司无需填写' : '如 技术部 / 研发经理'} disabled={form.scope === 'global' || immutableDisabled} className="w-full px-3 py-2 rounded-lg text-sm outline-none disabled:opacity-50" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }} />
              </div>

              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>指标</label>
                <select value={form.metric} onChange={(e) => setForm({ ...form, metric: e.target.value as KpiMetric })} disabled={immutableDisabled} className="w-full px-3 py-2 rounded-lg text-sm outline-none disabled:opacity-50" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>
                  {METRIC_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>周期</label>
                <select value={form.period} onChange={(e) => setForm({ ...form, period: e.target.value as KpiPeriod })} disabled={immutableDisabled} className="w-full px-3 py-2 rounded-lg text-sm outline-none disabled:opacity-50" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>
                  {PERIOD_OPTIONS.map((opt) => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                </select>
              </div>

              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>目标值</label>
                <input type="number" min="0.01" step="0.01" value={form.target_value} onChange={(e) => setForm({ ...form, target_value: e.target.value })} placeholder="请输入大于 0 的数值" className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }} />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setDialogOpen(false)} className="px-4 py-2 rounded-lg text-sm" style={{ color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}>取消</button>
              <button onClick={handleSubmit} disabled={submitting} className="px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-60" style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}>
                {submitting ? '提交中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
