/**
 * components/member-picker.tsx - 项目成员选择器(T-1105 立项指派成员场景)
 *
 * 可控组件:value: ProjectMemberInit[] + onChange 回调
 * 数据源:GET /api/v1/users/picker(manager + admin 可访问)
 */
'use client'

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Plus, Search, UserPlus, X } from 'lucide-react'
import { getUserPicker, type UserPickerItem } from '@/api/users'
import type { ProjectMemberInit } from '@/api/projects'

interface MemberPickerProps {
  value: ProjectMemberInit[]
  onChange: (next: ProjectMemberInit[]) => void
  children?: ReactNode
  maxMembers?: number
}

const TRACK_OPTIONS: Array<{ value: 'hardware' | 'software' | 'both'; label: string }> = [
  { value: 'both', label: '全项目' },
  { value: 'hardware', label: '硬件相关' },
  { value: 'software', label: '软件相关' },
]

const PROJECT_ROLE_OPTIONS = [
  '项目负责人',
  '软件',
  '硬件',
  '结构',
  '测试',
  '调试',
  '文档/验收',
  '采购支持',
  '生产支持',
  '仓储支持',
]

export default function MemberPicker({ value, onChange, children, maxMembers = 50 }: MemberPickerProps) {
  const [users, setUsers] = useState<UserPickerItem[]>([])
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [showPicker, setShowPicker] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getUserPicker()
      .then((data) => {
        if (!cancelled) setUsers(data)
      })
      .catch(() => {
        if (!cancelled) setUsers([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const selectedUserIds = useMemo(() => new Set(value.map((m) => m.user_id)), [value])

  const available = useMemo(() => {
    const query = search.trim().toLowerCase()
    return users
      .filter((u) => !selectedUserIds.has(u.id))
      .filter((u) => {
        if (!query) return true
        return (
          u.name.toLowerCase().includes(query) ||
          (u.department || '').toLowerCase().includes(query) ||
          u.role.toLowerCase().includes(query)
        )
      })
  }, [search, selectedUserIds, users])

  const selectedRows = useMemo(() => {
    const userMap = new Map(users.map((u) => [u.id, u]))
    return value.map((member) => ({ ...member, user: userMap.get(member.user_id) }))
  }, [users, value])

  function handleAdd(user: UserPickerItem) {
    if (value.length >= maxMembers || selectedUserIds.has(user.id)) return
    onChange([
      ...value,
      {
        user_id: user.id,
        track: 'both',
        role_in_project: '',
        name: user.name,
        department: user.department,
      },
    ])
  }

  function handleRemove(userId: string) {
    onChange(value.filter((m) => m.user_id !== userId))
  }

  function handleUpdate(userId: string, patch: Partial<ProjectMemberInit>) {
    onChange(value.map((m) => (m.user_id === userId ? { ...m, ...patch } : m)))
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <label className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
          项目成员({value.length}/{maxMembers})
        </label>
        <button
          type="button"
          onClick={() => setShowPicker((current) => !current)}
          disabled={value.length >= maxMembers}
          className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium disabled:opacity-50"
          style={{ background: 'rgba(59,130,246,0.16)', color: '#93c5fd' }}
          title={value.length >= maxMembers ? `已达上限 ${maxMembers} 人` : '添加成员'}
        >
          <UserPlus size={14} />
          {showPicker ? '收起' : '添加成员'}
        </button>
      </div>

      {selectedRows.length > 0 && (
        <div
          className="max-h-56 space-y-2 overflow-y-auto rounded-lg p-2"
          style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}
        >
          <div className="grid grid-cols-[minmax(96px,1fr)_92px_minmax(120px,1.2fr)_28px] items-center gap-2 px-1 text-[10px]" style={{ color: 'var(--color-text-muted)' }}>
            <span>成员</span>
            <span>参与范围</span>
            <span>项目职责</span>
            <span />
          </div>
          {selectedRows.map((row) => (
            <div
              key={row.user_id}
              className="grid grid-cols-[minmax(96px,1fr)_92px_minmax(120px,1.2fr)_28px] items-center gap-2 text-xs"
            >
              <div className="min-w-0">
                <div className="truncate font-medium" style={{ color: 'var(--color-text-primary)' }}>
                  {row.user?.name || row.name || '未知用户'}
                </div>
                <div className="truncate text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
                  {row.user?.department || row.department || '未填部门'}
                </div>
              </div>
              <select
                value={row.track}
                onChange={(e) =>
                  handleUpdate(row.user_id, { track: e.target.value as ProjectMemberInit['track'] })
                }
                className="h-8 rounded-lg px-2 text-xs outline-none"
                style={{
                  background: 'var(--color-bg-card)',
                  border: '1px solid var(--color-border-subtle)',
                  color: 'var(--color-text-primary)',
                }}
              >
                {TRACK_OPTIONS.map((track) => (
                  <option key={track.value} value={track.value}>
                    {track.label}
                  </option>
                ))}
              </select>
              <input
                list="project-role-options"
                type="text"
                value={row.role_in_project || ''}
                onChange={(e) => handleUpdate(row.user_id, { role_in_project: e.target.value })}
                placeholder="项目角色"
                maxLength={64}
                className="h-8 min-w-0 rounded-lg px-2 text-xs outline-none"
                style={{
                  background: 'var(--color-bg-card)',
                  border: '1px solid var(--color-border-subtle)',
                  color: 'var(--color-text-primary)',
                }}
              />
              <button
                type="button"
                onClick={() => handleRemove(row.user_id)}
                className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-red-500/15"
                title="移除"
              >
                <X size={14} color="#ef4444" />
              </button>
            </div>
          ))}
        </div>
      )}

      {children}

      <datalist id="project-role-options">
        {PROJECT_ROLE_OPTIONS.map((role) => (
          <option key={role} value={role} />
        ))}
      </datalist>

      {showPicker && (
        <div
          className="space-y-2 rounded-lg p-2"
          style={{ background: 'var(--color-bg-secondary)', border: '1px solid var(--color-border-subtle)' }}
        >
          <div className="relative">
            <Search
              size={14}
              className="absolute left-2 top-1/2 -translate-y-1/2"
              style={{ color: 'var(--color-text-secondary)' }}
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索姓名 / 部门 / 角色"
              className="h-8 w-full rounded-lg pl-8 pr-2 text-xs outline-none"
              style={{
                background: 'var(--color-bg-card)',
                border: '1px solid var(--color-border-subtle)',
                color: 'var(--color-text-primary)',
              }}
            />
          </div>
          <div className="max-h-52 overflow-y-auto">
            {loading && (
              <div className="py-3 text-center text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                加载中...
              </div>
            )}
            {!loading && available.length === 0 && (
              <div className="py-3 text-center text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                {users.length === 0 ? '无可选用户' : '无搜索结果'}
              </div>
            )}
            {!loading &&
              available.map((user) => (
                <button
                  key={user.id}
                  type="button"
                  onClick={() => handleAdd(user)}
                  disabled={value.length >= maxMembers}
                  className="grid w-full grid-cols-[20px_minmax(80px,1fr)_minmax(100px,1.2fr)] items-center gap-2 rounded-lg px-2 py-2 text-left text-xs hover:bg-white/5 disabled:opacity-50"
                >
                  <Plus size={13} color="#22c55e" />
                  <span className="truncate font-medium" style={{ color: 'var(--color-text-primary)' }}>
                    {user.name}
                  </span>
                  <span className="truncate text-[10px]" style={{ color: 'var(--color-text-secondary)' }}>
                    {user.department || '未填部门'} / {user.role}
                  </span>
                </button>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
