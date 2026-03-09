/**
 * stores/use-auth-store.ts — 认证状态管理 (Zustand 替代 Pinia)
 *
 * Rule 01-Stack-Frontend: 使用 Zustand。
 * 从 Vue stores/auth.ts 1:1 迁移。
 */
'use client'

import { create } from 'zustand'

interface AuthState {
  token: string
  userName: string
  userRole: string
  isLoggedIn: boolean
  isAdmin: boolean
  login: (jwt: string, name: string, role?: string) => void
  logout: () => void
  hydrate: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  token: '',
  userName: '',
  userRole: '',
  isLoggedIn: false,
  isAdmin: false,

  login: (jwt: string, name: string, role: string = 'employee') => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('aipm_token', jwt)
      localStorage.setItem('aipm_user_name', name)
      localStorage.setItem('aipm_user_role', role)
    }
    set({
      token: jwt,
      userName: name,
      userRole: role,
      isLoggedIn: true,
      isAdmin: role === 'admin',
    })
  },

  logout: () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('aipm_token')
      localStorage.removeItem('aipm_user_name')
      localStorage.removeItem('aipm_user_role')
    }
    set({
      token: '',
      userName: '',
      userRole: '',
      isLoggedIn: false,
      isAdmin: false,
    })
  },

  /**
   * 客户端 hydrate — 从 localStorage 恢复登录状态
   * 必须在 useEffect 中调用（SSR 安全）
   */
  hydrate: () => {
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('aipm_token') || ''
      const userName = localStorage.getItem('aipm_user_name') || ''
      const userRole = localStorage.getItem('aipm_user_role') || ''
      set({
        token,
        userName,
        userRole,
        isLoggedIn: !!token,
        isAdmin: userRole === 'admin',
      })
    }
  },
}))
