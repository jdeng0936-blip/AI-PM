/**
 * app/users/page.tsx — 用户管理 (1:1 port from Vue UserManagement.vue)
 */
'use client'

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import {
  getUsers, createUser, updateUser, deleteUser, resetPassword,
  updateUserStatus, batchDisableUsers, batchEnableUsers, type UserStatus,
} from '@/api/users'
import { useAuthStore } from '@/stores/use-auth-store'
import { useListFilters, type FilterSpec } from '@/lib/hooks/use-list-filters'
import { useMultiSelect } from '@/lib/hooks/use-multi-select'
import FilterBar from '@/components/filter-bar'
import ListActionBar from '@/components/list-action-bar'
import { toast } from 'sonner'
import { Plus, Search, Ban, CheckSquare } from 'lucide-react'

// V2.4 Stage 1 TECH DEBT:后端 users 列表暂无 role/department/is_active query params,
// Stage 1 临时把 pageSize 从 20 调到 100 一次拉全(公司当前人数 ~15 远不到 100),
// 前端纯本地筛选。Stage 2 还原成 20 并补后端 query params。
const USERS_PAGE_SIZE = 100

const DEPARTMENTS = ['管理层', '软件研发部', '硬件测试部', '采购部', '仓储物流部']
const ROLES = [
  { value: 'employee', label: '普通员工' },
  { value: 'manager', label: '部门经理' },
  { value: 'admin', label: '管理员' },
]

const roleLabel = (r: string) => ({ admin: '管理员', manager: '经理', employee: '员工' }[r] || r)
const roleColor = (r: string) => ({ admin: '#ef4444', manager: '#eab308', employee: '#3b82f6' }[r] || '#94a3b8')

const STATUS_OPTIONS: { value: UserStatus; label: string; color: string }[] = [
  { value: 'active',     label: '在岗', color: '#22c55e' },
  { value: 'on_leave',   label: '请假', color: '#eab308' },
  { value: 'on_travel',  label: '出差', color: '#3b82f6' },
  { value: 'sick_leave', label: '病假', color: '#f97316' },
]
const statusMeta = (s: string) => STATUS_OPTIONS.find((o) => o.value === s) || STATUS_OPTIONS[0]

export default function UsersPage() {
  const { isAdmin } = useAuthStore()
  const [users, setUsers] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [isEditing, setIsEditing] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [form, setForm] = useState({ name: '', wechat_userid: '', phone: '', email: '', department: '', role: 'employee', password: 'aipm2026' })
  const searchTimer = useRef<any>(null)

  // 出勤状态对话框
  const [statusDialogOpen, setStatusDialogOpen] = useState(false)
  const [statusRow, setStatusRow] = useState<any>(null)
  const [statusForm, setStatusForm] = useState<{ status: UserStatus; status_until: string }>({
    status: 'active', status_until: '',
  })
  const [statusSubmitting, setStatusSubmitting] = useState(false)

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await getUsers({ page: currentPage, page_size: USERS_PAGE_SIZE, search })
      setUsers(res.items || [])
      setTotal(res.total || 0)
    } catch (e: any) { toast.error(e?.response?.data?.detail || '获取用户列表失败') }
    finally { setLoading(false) }
  }, [currentPage, search])

  // V2.4 Stage 1:用户列表筛选(role/department/status/is_active)
  // department 选项动态从数据 distinct;搜索框继续走后端 search param 不进 spec
  const userFilterSpec: FilterSpec[] = useMemo(() => {
    const depts = Array.from(new Set(users.map((u: any) => u.department).filter(Boolean))).sort() as string[]
    return [
      {
        key: 'role',
        type: 'multi-select',
        label: '角色',
        options: ROLES.map((r) => ({ value: r.value, label: r.label })),
      },
      {
        key: 'department',
        type: 'multi-select',
        label: '部门',
        options: depts.map((d) => ({ value: d, label: d })),
      },
      {
        key: 'status',
        type: 'multi-select',
        label: '出勤',
        options: STATUS_OPTIONS.map((s) => ({ value: s.value, label: s.label })),
      },
      {
        key: 'is_active',
        type: 'boolean',
        label: '账号',
        trueLabel: '启用',
        falseLabel: '停用',
      },
    ]
  }, [users])

  const {
    filteredItems: filteredUsers,
    filters: userFilters,
    setFilter: setUserFilter,
    clearFilter: clearUserFilter,
    clearAll: clearUserAll,
    activeCount: userActiveCount,
  } = useListFilters(users, userFilterSpec, { urlPrefix: 'usr_' })

  // V2.4 Stage 2:用户多选 + 批量启/禁用(不暴露真删除)
  const {
    selectedIds: userSelectedIds,
    selectedCount: userSelectedCount,
    selectedItems: selectedUsers,
    isSelected: isUserSelected,
    isAllSelected: isAllUsersSelected,
    isIndeterminate: isUserIndeterminate,
    toggle: toggleUser,
    selectAll: selectAllUsers,
    clearAll: clearUserSelection,
  } = useMultiSelect(filteredUsers)
  const [bulkUserActing, setBulkUserActing] = useState(false)

  // 选中里全部为"启用"或全部为"停用",决定按钮显示
  const allActive = userSelectedCount > 0 && selectedUsers.every((u) => u.is_active)
  const allInactive = userSelectedCount > 0 && selectedUsers.every((u) => !u.is_active)

  async function handleBatchDisable() {
    if (!confirm(`确定批量停用选中的 ${userSelectedCount} 个用户?\n(is_active=false,历史日报与关联不动)`)) return
    setBulkUserActing(true)
    try {
      const ids = Array.from(userSelectedIds)
      const res: any = await batchDisableUsers(ids)
      toast.success(`已停用 ${res?.disabled_count ?? ids.length} 个用户`)
      clearUserSelection()
      await fetchUsers()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '批量停用失败')
    } finally {
      setBulkUserActing(false)
    }
  }

  async function handleBatchEnable() {
    if (!confirm(`确定批量启用选中的 ${userSelectedCount} 个用户?`)) return
    setBulkUserActing(true)
    try {
      const ids = Array.from(userSelectedIds)
      const res: any = await batchEnableUsers(ids)
      toast.success(`已启用 ${res?.enabled_count ?? ids.length} 个用户`)
      clearUserSelection()
      await fetchUsers()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '批量启用失败')
    } finally {
      setBulkUserActing(false)
    }
  }

  useEffect(() => { fetchUsers() }, [fetchUsers])

  function handleSearch(val: string) {
    setSearch(val)
    clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => { setCurrentPage(1) }, 300)
  }

  function openCreate() {
    setIsEditing(false); setEditingId('')
    setForm({ name: '', wechat_userid: '', phone: '', email: '', department: '', role: 'employee', password: 'aipm2026' })
    setDialogOpen(true)
  }

  function openEdit(row: any) {
    setIsEditing(true); setEditingId(row.id)
    setForm({ name: row.name, wechat_userid: row.wechat_userid, phone: row.phone || '', email: row.email || '', department: row.department, role: row.role, password: '' })
    setDialogOpen(true)
  }

  async function handleSubmit() {
    if (!form.name || !form.wechat_userid) { toast.warning('请填写姓名和企微ID'); return }
    if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) { toast.warning('请输入有效的邮箱地址'); return }
    setSubmitting(true)
    try {
      if (isEditing) {
        await updateUser(editingId, { name: form.name, phone: form.phone || undefined, email: form.email || undefined, department: form.department, role: form.role })
        toast.success('用户信息已更新')
      } else {
        await createUser({ name: form.name, wechat_userid: form.wechat_userid, phone: form.phone || undefined, email: form.email || undefined, department: form.department, role: form.role, password: form.password || 'aipm2026' })
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

  function openStatus(row: any) {
    setStatusRow(row)
    setStatusForm({
      status: (row.status as UserStatus) || 'active',
      status_until: row.status_until || '',
    })
    setStatusDialogOpen(true)
  }

  async function handleStatusSubmit() {
    if (!statusRow) return
    if (statusForm.status !== 'active' && !statusForm.status_until) {
      toast.warning('请选择截止日期')
      return
    }
    setStatusSubmitting(true)
    try {
      await updateUserStatus(
        statusRow.id,
        statusForm.status,
        statusForm.status === 'active' ? null : statusForm.status_until,
      )
      toast.success(`${statusRow.name} 的出勤状态已更新`)
      setStatusDialogOpen(false)
      fetchUsers()
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '状态更新失败')
    } finally {
      setStatusSubmitting(false)
    }
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

      {/* V2.4 Stage 1 — 多维筛选 */}
      {/* relative z-50 — 防止下方 table 创建的层叠上下文困住 FilterBar 的下拉 */}
      <div className="relative z-50">
        <FilterBar
          spec={userFilterSpec}
          filters={userFilters}
          setFilter={setUserFilter}
          clearFilter={clearUserFilter}
          clearAll={clearUserAll}
          activeCount={userActiveCount}
        />
      </div>

      {/* V2.4 Stage 2:批量启 / 停用栏(只允许 admin/manager) */}
      <ListActionBar
        selectedCount={userSelectedCount}
        onClear={clearUserSelection}
        hint={allActive ? '全部为启用 — 可批量停用' : allInactive ? '全部为停用 — 可批量启用' : '混合状态 — 请按单一状态选中'}
      >
        {allActive && (
          <button
            onClick={handleBatchDisable}
            disabled={bulkUserActing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-60"
            style={{ background: '#ef4444', color: '#fff' }}
          >
            <Ban size={13} />
            {bulkUserActing ? '处理中...' : '批量停用'}
          </button>
        )}
        {allInactive && isAdmin && (
          <button
            onClick={handleBatchEnable}
            disabled={bulkUserActing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-60"
            style={{ background: '#22c55e', color: '#fff' }}
          >
            <CheckSquare size={13} />
            {bulkUserActing ? '处理中...' : '批量启用'}
          </button>
        )}
      </ListActionBar>

      {/* Table */}
      <div className="rounded-xl overflow-hidden" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'var(--color-bg-secondary)' }}>
              <th className="py-3 px-3 w-8">
                <input
                  type="checkbox"
                  checked={isAllUsersSelected}
                  ref={(el) => { if (el) el.indeterminate = isUserIndeterminate }}
                  onChange={() => (isAllUsersSelected ? clearUserSelection() : selectAllUsers())}
                  className="cursor-pointer"
                  title="全选当前页"
                />
              </th>
              {['姓名', '部门', '手机号', '邮箱', '企微ID', '角色', '出勤', '状态', '操作'].map((h) => (
                <th key={h} className="text-left py-3 px-4 text-xs font-semibold" style={{ color: 'var(--color-text-primary)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredUsers.length === 0 && (
              <tr>
                <td colSpan={10} className="text-center py-8 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  {users.length === 0 ? '暂无用户数据' : '无符合筛选条件的用户'}
                </td>
              </tr>
            )}
            {filteredUsers.map((u: any) => (
              <tr
                key={u.id}
                style={{
                  borderBottom: '1px solid var(--color-border-subtle)',
                  background: isUserSelected(u.id) ? 'rgba(168,85,247,0.06)' : undefined,
                }}
              >
                <td className="py-3 px-3">
                  <input
                    type="checkbox"
                    checked={isUserSelected(u.id)}
                    onChange={() => toggleUser(u.id)}
                    className="cursor-pointer"
                  />
                </td>
                <td className="py-3 px-4 text-sm">{u.name}</td>
                <td className="py-3 px-4 text-sm">{u.department}</td>
                <td className="py-3 px-4 text-sm">{u.phone || '-'}</td>
                <td className="py-3 px-4 text-sm">{u.email || '-'}</td>
                <td className="py-3 px-4 text-sm">{u.wechat_userid}</td>
                <td className="py-3 px-4">
                  <span className="px-2 py-0.5 rounded-md text-xs font-medium" style={{ background: `${roleColor(u.role)}20`, color: roleColor(u.role) }}>{roleLabel(u.role)}</span>
                </td>
                <td className="py-3 px-4">
                  {(() => {
                    const meta = statusMeta(u.status || 'active')
                    return (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium" style={{ background: `${meta.color}20`, color: meta.color }}>
                        {meta.label}
                        {u.status && u.status !== 'active' && u.status_until && (
                          <span style={{ opacity: 0.75 }}>· 至 {String(u.status_until).slice(5)}</span>
                        )}
                      </span>
                    )
                  })()}
                </td>
                <td className="py-3 px-4">
                  <span className="px-2 py-0.5 rounded-md text-xs" style={{ background: u.is_active ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)', color: u.is_active ? '#22c55e' : '#ef4444' }}>{u.is_active ? '启用' : '停用'}</span>
                </td>
                <td className="py-3 px-4 flex gap-3">
                  <button onClick={() => openEdit(u)} className="text-xs" style={{ color: 'var(--color-brand-blue)' }}>编辑</button>
                  <button onClick={() => openStatus(u)} className="text-xs" style={{ color: '#a855f7' }}>出勤</button>
                  <button onClick={() => handleReset(u)} className="text-xs" style={{ color: '#eab308' }}>重置密码</button>
                  <button onClick={() => handleToggle(u)} className="text-xs" style={{ color: u.is_active ? '#ef4444' : '#22c55e' }}>{u.is_active ? '停用' : '启用'}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination — V2.4 Stage 1 期间 pageSize=100,< 100 人时分页按钮不会显示 */}
      <div className="flex justify-end mt-4 gap-2 items-center text-xs" style={{ color: 'var(--color-text-secondary)' }}>
        <span>共 {total} 条 · 筛选后 {filteredUsers.length} 条</span>
        {total > USERS_PAGE_SIZE && (
          <>
            <button disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)} className="px-2 py-1 rounded disabled:opacity-30" style={{ border: '1px solid var(--color-border-subtle)' }}>上一页</button>
            <span>{currentPage}</span>
            <button disabled={currentPage >= Math.ceil(total / USERS_PAGE_SIZE)} onClick={() => setCurrentPage(p => p + 1)} className="px-2 py-1 rounded disabled:opacity-30" style={{ border: '1px solid var(--color-border-subtle)' }}>下一页</button>
          </>
        )}
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
                { label: '邮箱', key: 'email', placeholder: '用于接收邮件通知 (可选)' },
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

      {/* 出勤状态对话框 */}
      {statusDialogOpen && statusRow && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setStatusDialogOpen(false)}>
          <div className="w-full max-w-md rounded-2xl p-6" style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)' }} onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-1" style={{ color: 'var(--color-text-primary)' }}>设置出勤状态</h2>
            <p className="text-xs mb-5" style={{ color: 'var(--color-text-secondary)' }}>{statusRow.name} · {statusRow.department}</p>

            <div className="space-y-4">
              <div>
                <label className="block text-xs mb-2 font-medium" style={{ color: 'var(--color-text-secondary)' }}>状态</label>
                <div className="grid grid-cols-2 gap-2">
                  {STATUS_OPTIONS.map((opt) => {
                    const selected = statusForm.status === opt.value
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        onClick={() => setStatusForm({ ...statusForm, status: opt.value })}
                        className="px-3 py-2 rounded-lg text-sm transition-colors"
                        style={{
                          background: selected ? `${opt.color}25` : 'var(--color-bg-secondary)',
                          border: `1px solid ${selected ? opt.color : 'var(--color-border-subtle)'}`,
                          color: selected ? opt.color : 'var(--color-text-primary)',
                          fontWeight: selected ? 600 : 400,
                        }}
                      >
                        {opt.label}
                      </button>
                    )
                  })}
                </div>
              </div>

              {statusForm.status !== 'active' && (
                <div>
                  <label className="block text-xs mb-1.5 font-medium" style={{ color: 'var(--color-text-secondary)' }}>截止日期(到期自动恢复在岗)</label>
                  <input
                    type="date"
                    value={statusForm.status_until}
                    min={new Date().toISOString().slice(0, 10)}
                    onChange={(e) => setStatusForm({ ...statusForm, status_until: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                    style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
                  />
                  <p className="text-xs mt-1.5" style={{ color: 'var(--color-text-muted)' }}>
                    该员工在此期间不会被催报。次日 00:05 检查并自动恢复。
                  </p>
                </div>
              )}
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setStatusDialogOpen(false)} className="px-4 py-2 rounded-lg text-sm" style={{ color: 'var(--color-text-secondary)', border: '1px solid var(--color-border-subtle)' }}>取消</button>
              <button onClick={handleStatusSubmit} disabled={statusSubmitting} className="px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-60" style={{ background: 'linear-gradient(135deg, #a855f7, #6366f1)' }}>
                {statusSubmitting ? '提交中...' : '保存'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
