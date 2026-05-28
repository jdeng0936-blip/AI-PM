'use client'

import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import { Building2, Pencil, Plus, Trash2 } from 'lucide-react'
import { useAuthStore } from '@/stores/use-auth-store'
import {
  createDepartment,
  deleteDepartment,
  listDepartments,
  updateDepartment,
  type DepartmentIn,
  type DepartmentOut,
} from '@/api/admin'

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

type DeptFormState = {
  name: string
  manager_id: string
}

const emptyForm: DeptFormState = { name: '', manager_id: '' }

function getErrorMessage(error: any, fallback = '操作失败') {
  const detail = error?.response?.data?.detail
  if (Array.isArray(detail)) return detail[0]?.msg || fallback
  return detail || fallback
}

function formatDate(value: string | null) {
  if (!value) return '-'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '-' : d.toLocaleString('zh-CN')
}

function mapDepartmentError(error: any, router: ReturnType<typeof useRouter>, fallback: string) {
  const status = error?.response?.status
  const detail = error?.response?.data?.detail
  if (status === 403) {
    toast.error('权限不足')
    router.replace('/')
    return
  }
  if (detail === 'name_conflict' || detail === '部门名称已存在') {
    toast.error('部门名称已存在')
    return
  }
  if (detail === 'manager_not_found' || detail === 'manager_id 对应的用户不存在或已删除') {
    toast.error('指定的 user.id 不存在或非 manager 角色')
    return
  }
  if (detail === 'department_not_found' || detail === 'not_found' || detail === '部门不存在') {
    toast.error('部门不存在')
    return
  }
  console.error(error)
  toast.error(getErrorMessage(error, fallback))
}

export default function DepartmentsAdminPage() {
  const router = useRouter()
  const { userRole } = useAuthStore()
  const canManage = userRole === 'admin' || userRole === 'manager'

  const [rows, setRows] = useState<DepartmentOut[]>([])
  const [loading, setLoading] = useState(false)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState<DeptFormState>(emptyForm)

  useEffect(() => {
    if (userRole && !canManage) {
      toast.error('需 admin 或 manager 权限')
      router.replace('/')
    }
  }, [userRole, canManage, router])

  const loadRows = useCallback(async () => {
    setLoading(true)
    try {
      const res = await listDepartments()
      setRows(Array.isArray(res) ? res : [])
    } catch (error: any) {
      mapDepartmentError(error, router, '加载部门列表失败')
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => {
    if (canManage) {
      loadRows()
    }
  }, [canManage, loadRows])

  function openCreate() {
    setEditingId(null)
    setForm(emptyForm)
    setDialogOpen(true)
  }

  function openEdit(row: DepartmentOut) {
    setEditingId(row.id)
    setForm({ name: row.name, manager_id: row.manager_id ?? '' })
    setDialogOpen(true)
  }

  function closeDialog() {
    setDialogOpen(false)
    setEditingId(null)
    setForm(emptyForm)
  }

  async function handleSubmit() {
    const trimmedName = form.name.trim()
    if (!trimmedName) {
      toast.error('部门名称必填')
      return
    }
    if (trimmedName.length > 64) {
      toast.error('部门名称不能超过 64 字符')
      return
    }
    const trimmedManager = form.manager_id.trim()
    if (trimmedManager && !UUID_REGEX.test(trimmedManager)) {
      toast.error('负责人 ID 必须是合法 UUID')
      return
    }
    const payload: DepartmentIn = {
      name: trimmedName,
      manager_id: trimmedManager || null,
    }
    setSubmitting(true)
    try {
      if (editingId) {
        await updateDepartment(editingId, payload)
        toast.success('部门更新成功')
      } else {
        await createDepartment(payload)
        toast.success('部门创建成功')
      }
      closeDialog()
      await loadRows()
    } catch (error: any) {
      mapDepartmentError(error, router, '操作失败,请重试')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleDelete(row: DepartmentOut) {
    if (!window.confirm(`确认删除部门「${row.name}」?`)) return
    try {
      await deleteDepartment(row.id)
      toast.success('部门已删除')
      await loadRows()
    } catch (error: any) {
      mapDepartmentError(error, router, '操作失败,请重试')
    }
  }

  if (!userRole) {
    return (
      <main className="p-8 max-w-7xl mx-auto">
        <div className="rounded-lg border p-8 text-center text-sm" style={{ borderColor: '#334155', background: '#0f172a', color: '#94a3b8' }}>
          正在校验权限...
        </div>
      </main>
    )
  }

  if (!canManage) return null

  return (
    <main className="p-8 max-w-7xl mx-auto">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
        <div>
          <div className="flex items-center gap-3">
            <Building2 size={24} style={{ color: '#3b82f6' }} />
            <h1 className="text-2xl font-semibold" style={{ color: '#e2e8f0' }}>部门管理</h1>
          </div>
          <p className="text-sm mt-2" style={{ color: '#94a3b8' }}>
            管理独立部门主数据,并维护可选负责人 user.id
          </p>
        </div>
        <button
          type="button"
          onClick={openCreate}
          className="flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium"
          style={{ background: '#3b82f6', color: '#fff' }}
        >
          <Plus size={16} /> 新建部门
        </button>
      </header>

      <section
        className="rounded-lg border overflow-hidden"
        style={{ borderColor: '#334155', background: '#0f172a' }}
      >
        {loading ? (
          <div className="text-sm p-6 text-slate-400">加载中...</div>
        ) : rows.length === 0 ? (
          <div className="text-sm p-6 text-slate-400">暂无部门</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead>
                <tr style={{ color: '#94a3b8', background: '#1e293b' }}>
                  <th className="text-left px-4 py-3">部门名</th>
                  <th className="text-left px-4 py-3">负责人 ID</th>
                  <th className="text-left px-4 py-3">创建时间</th>
                  <th className="text-left px-4 py-3">更新时间</th>
                  <th className="text-right px-4 py-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-t" style={{ borderColor: '#334155' }}>
                    <td className="px-4 py-3" style={{ color: '#e2e8f0' }}>{row.name}</td>
                    <td className="px-4 py-3 font-mono text-xs" style={{ color: '#94a3b8' }}>
                      {row.manager_id ?? '-'}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap" style={{ color: '#94a3b8' }}>{formatDate(row.created_at)}</td>
                    <td className="px-4 py-3 whitespace-nowrap" style={{ color: '#94a3b8' }}>{formatDate(row.updated_at)}</td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => openEdit(row)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded mr-2 text-xs"
                        style={{ background: '#1e293b', color: '#3b82f6' }}
                      >
                        <Pencil size={12} /> 编辑
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDelete(row)}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs"
                        style={{ background: '#1e293b', color: '#ef4444' }}
                      >
                        <Trash2 size={12} /> 删除
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center px-4" style={{ background: 'rgba(0,0,0,0.7)' }} onClick={closeDialog}>
          <div className="w-full max-w-md rounded-lg p-6" style={{ background: '#0f172a', border: '1px solid #334155' }} onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-4" style={{ color: '#e2e8f0' }}>
              {editingId ? '编辑部门' : '新建部门'}
            </h2>
            <label className="block mb-3 text-sm">
              <span style={{ color: '#94a3b8' }}>部门名称 *</span>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                maxLength={64}
                className="w-full mt-1 px-3 py-2 rounded text-sm outline-none"
                style={{ background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155' }}
              />
            </label>
            <label className="block mb-4 text-sm">
              <span style={{ color: '#94a3b8' }}>负责人 user.id(可选,UUID)</span>
              <input
                type="text"
                value={form.manager_id}
                onChange={(e) => setForm({ ...form, manager_id: e.target.value })}
                placeholder="留空表示无负责人"
                className="w-full mt-1 px-3 py-2 rounded font-mono text-xs outline-none"
                style={{ background: '#1e293b', color: '#e2e8f0', border: '1px solid #334155' }}
              />
            </label>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={closeDialog}
                className="px-4 py-2 rounded text-sm"
                style={{ background: '#1e293b', color: '#94a3b8' }}
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting}
                className="px-4 py-2 rounded text-sm disabled:cursor-not-allowed"
                style={{ background: '#3b82f6', color: '#fff', opacity: submitting ? 0.6 : 1 }}
              >
                {submitting ? '保存中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}
