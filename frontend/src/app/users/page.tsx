/**
 * app/users/page.tsx — 用户管理 (1:1 port from Vue UserManagement.vue)
 */
'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { getUsers, createUser, updateUser, deleteUser, resetPassword } from '@/api/users'
import { toast } from 'sonner'
import { Plus, Search } from 'lucide-react'

const DEPARTMENTS = ['管理层', '软件研发部', '硬件测试部', '采购部', '仓储物流部']
const ROLES = [
  { value: 'employee', label: '普通员工' },
  { value: 'manager', label: '部门经理' },
  { value: 'admin', label: '管理员' },
]

const roleLabel = (r: string) => ({ admin: '管理员', manager: '经理', employee: '员工' }[r] || r)
const roleColor = (r: string) => ({ admin: '#ef4444', manager: '#eab308', employee: '#3b82f6' }[r] || '#94a3b8')

export default function UsersPage() {
  const [users, setUsers] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({ name: '', wechat_userid: '', phone: '', department: '', role: 'employee', password: 'aipm2026' })
  const searchTimer = useRef<any>(null)

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await getUsers({ page: currentPage, page_size: 20, search })
      setUsers(res.items || [])
      setTotal(res.total || 0)
    } catch (e: any) { toast.error(e?.response?.data?.detail || '获取用户列表失败') }
    finally { setLoading(false) }
  }, [currentPage, search])

  useEffect(() => { fetchUsers() }, [fetchUsers])

  function handleSearch(val: string) {
    setSearch(val)
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => { setCurrentPage(1) }, 300)
  }

  function openCreate() {
    setIsEditing(false); setEditingId('')
    setForm({ name: '', wechat_userid: '', phone: '', department: '', role: 'employee', password: 'aipm2026' })
    setDialogOpen(true)
  }

  function openEdit(row: any) {
    setIsEditing(true); setEditingId(row.id)
    setForm({ name: row.name, wechat_userid: row.wechat_userid, phone: row.phone || '', department: row.department, role: row.role, password: '' })
    setDialogOpen(true)
  }

  async function handleSubmit() {
    if (!form.name || !form.wechat_userid) { toast.warning('请填写姓名和企微ID'); return }
    setSubmitting(true)
    try {
      if (isEditing) {
        await updateUser(editingId, { name: form.name, phone: form.phone || undefined, department: form.department, role: form.role })
        toast.success('用户信息已更新')
      } else {
        await createUser({ name: form.name, wechat_userid: form.wechat_userid, phone: form.phone || undefined, department: form.department, role: form.role, password: form.password || 'aipm2026' })
        toast.success('用户创建成功')
      }
      setDialogOpen(false); fetchUsers()
    } catch (e: any) { toast.error(e?.response?.data?.detail || '操作失败') }
    finally { setSubmitting(false) }
  }

  async function handleReset(row: any) {
    if (!confirm(`确定重置用户 "${row.name}" 的密码为 aipm2026？`)) return
    await resetPassword(row.id)
    toast.success(`${row.name} 的密码已重置为 aipm2026`)
  }

  async function handleToggle(row: any) {
    const action = row.is_active ? '停用' : '启用'
    if (!confirm(`确定${action}用户 "${row.name}"？`)) return
    if (row.is_active) await deleteUser(row.id)
    else await updateUser(row.id, { is_active: true })
    toast.success(`${row.name} 已${action}`)
    fetchUsers()
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold" style={{ color: 'var(--color-text-primary)' }}>用户管理</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>管理系统用户账号、角色和权限</p>
        </div>
        <button onClick={openCreate} className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm text-white font-medium" style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}>
          <Plus size={16} />新增用户
        </button>
      </div>

      <div className="mb-4 relative" style={{ maxWidth: 360 }}>
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: 'var(--color-text-muted)' }} />
        <input value={search} onChange={(e) => handleSearch(e.target.value)} placeholder="搜索姓名、部门、企微ID..." className="w-full pl-9 pr-4 py-2.5 rounded-lg text-sm outline-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }} />
      </div>

      {/* Table */}
      <div className="rounded-xl overflow-hidden" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--color-bg-secondary)' }}>
              {['姓名', '部门', '手机号', '企微ID', '角色', '状态', '操作'].map((h) => (
                <th key={h} className="text-left py-3 px-4 text-xs font-semibold" style={{ color: 'var(--color-text-primary)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map((u: any) => (
              <tr key={u.id} style={{ borderBottom: '1px solid var(--color-border-subtle)' }}>
                <td className="py-3 px-4 text-sm">{u.name}</td>
                <td className="py-3 px-4 text-sm">{u.department}</td>
                <td className="py-3 px-4 text-sm">{u.phone || '-'}</td>
                <td className="py-3 px-4 text-sm">{u.wechat_userid}</td>
                <td className="py-3 px-4">
                  <span className="px-2 py-0.5 rounded-md text-xs font-medium" style={{ background: `${roleColor(u.role)}20`, color: roleColor(u.role) }}>{roleLabel(u.role)}</span>
                </td>
                <td className="py-3 px-4">
                  <span className="px-2 py-0.5 rounded-md text-xs" style={{ background: u.is_active ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', color: u.is_active ? '#22c55e' : '#ef4444' }}>{u.is_active ? '启用' : '停用'}</span>
                </td>
                <td className="py-3 px-4 flex gap-3">
                  <button onClick={() => openEdit(u)} className="text-xs" style={{ color: 'var(--color-brand-blue)' }}>编辑</button>
                  <button onClick={() => handleReset(u)} className="text-xs" style={{ color: '#eab308' }}>重置密码</button>
                  <button onClick={() => handleToggle(u)} className="text-xs" style={{ color: u.is_active ? '#ef4444' : '#22c55e' }}>{u.is_active ? '停用' : '启用'}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex justify-end mt-4 gap-2 items-center text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        <span>共 {total} 条</span>
        <button disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)} className="px-2 py-1 rounded disabled:opacity-30" style={{ border: '1px solid var(--color-border-subtle)' }}>上一页</button>
        <span>{currentPage}</span>
        <button disabled={currentPage >= Math.ceil(total / 20)} onClick={() => setCurrentPage(p => p + 1)} className="px-2 py-1 rounded disabled:opacity-30" style={{ border: '1px solid var(--color-border-subtle)' }}>下一页</button>
      </div>

      {/* Dialog */}
      {dialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setDialogOpen(false)}>
          <div className="w-full max-w-md rounded-2xl p-6" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }} onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-5" style={{ color: 'var(--color-text-primary)' }}>{isEditing ? '编辑用户' : '新增用户'}</h2>
            <div className="space-y-4">
              {[
                { label: '姓名', key: 'name', placeholder: '请输入姓名' },
                { label: '企微ID', key: 'wechat_userid', placeholder: '如 wx_zhangsan', disabled: isEditing },
                { label: '手机号', key: 'phone', placeholder: '可选' },
              ].map((f) => (
                <div key={f.key}>
                  <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>{f.label}</label>
                  <input value={(form as any)[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} placeholder={f.placeholder} disabled={f.disabled} className="w-full px-3 py-2 rounded-lg text-sm outline-none disabled:opacity-50" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }} />
                </div>
              ))}
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>部门</label>
                <select value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>
                  <option value="">选择部门</option>
                  {DEPARTMENTS.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>角色</label>
                <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}>
                  {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </div>
              {!isEditing && (
                <div>
                  <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>初始密码</label>
                  <input value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="默认 aipm2026" className="w-full px-3 py-2 rounded-lg text-sm outline-none" style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }} />
                </div>
              )}
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setDialogOpen(false)} className="px-4 py-2 rounded-lg text-sm" style={{ color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}>取消</button>
              <button onClick={handleSubmit} disabled={submitting} className="px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-60" style={{ background: 'linear-gradient(135deg, #3b82f6, #6366f1)' }}>{submitting ? '提交中...' : isEditing ? '保存' : '创建'}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
