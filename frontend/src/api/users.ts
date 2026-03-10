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
export const getUsers = (params: { page?: number; page_size?: number; search?: string } = {}) =>
  request.get('/users', { params })

export const createUser = (data: {
  name: string
  wechat_userid: string
  phone?: string
  department?: string
  role?: string
  password?: string
}) => request.post('/users', data)

export const updateUser = (userId: string, data: {
  name?: string
  phone?: string
  department?: string
  role?: string
  is_active?: boolean
}) => request.put(`/users/${userId}`, data)

export const deleteUser = (userId: string) =>
  request.delete(`/users/${userId}`)

export const resetPassword = (userId: string) =>
  request.post(`/users/${userId}/reset-password`)
