/**
 * API 模块 — 用户 & 认证 (1:1 port from Vue api/users.ts)
 */
import request from '@/api/request'

// ── 认证 API ────────────────────────────────────────────
export const login = (username: string, password: string) =>
  request.post('/auth/login', { username, password })

export const getMe = () =>
  request.get('/auth/me')

export const changePassword = (old_password: string, new_password: string) =>
  request.post('/auth/change-password', { old_password, new_password })

// ── 用户管理 API ────────────────────────────────────────
export const getUsers = (params: {
  page?: number
  page_size?: number
  search?: string
  role?: string         // V2.4 Stage 3 C2:csv 多选 'admin,manager'
  department?: string   // V2.4 Stage 3 C2:csv 多选
  is_active?: string    // V2.4 Stage 3 C2:'true'/'false'/'' (空 = 不限)
} = {}) =>
  request.get('/users', { params })

export const createUser = (data: {
  name: string
  wechat_userid: string
  phone?: string
  email?: string
  department?: string
  role?: string
  password?: string
}) => request.post('/users', data)

export const updateUser = (userId: string, data: {
  name?: string
  phone?: string
  email?: string
  department?: string
  role?: string
  is_active?: boolean
}) => request.put(`/users/${userId}`, data)

export const deleteUser = (userId: string) =>
  request.delete(`/users/${userId}`)

export const resetPassword = (userId: string) =>
  request.post(`/users/${userId}/reset-password`)

// 请假/出差状态
export type UserStatus = 'active' | 'on_leave' | 'on_travel' | 'sick_leave'

export const updateUserStatus = (
  userId: string,
  status: UserStatus,
  statusUntil?: string | null,
) => {
  const params: Record<string, string> = { status }
  if (statusUntil) params.status_until = statusUntil
  return request.patch(`/users/${userId}/status`, null, { params })
}

// V2.4 Stage 2:批量启 / 禁用用户(不允许真删,避免破坏 daily_report FK)
export const batchDisableUsers = (ids: string[]) =>
  request.post('/users/batch-disable', { ids })

export const batchEnableUsers = (ids: string[]) =>
  request.post('/users/batch-enable', { ids })

// T-1105 立项指派成员用户选择器(轻量 + manager 可访问)
export interface UserPickerItem {
  id: string
  name: string
  department: string
  role: string
  is_active: boolean
}

export const getUserPicker = (params: { search?: string; include_inactive?: boolean } = {}) =>
  request.get<unknown, UserPickerItem[]>('/users/picker', { params })
