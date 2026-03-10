/**
 * app/login/page.tsx — 登录页 (1:1 port from Vue Login.vue)
 *
 * Rule: 'use client' — 使用浏览器 API (localStorage, form interaction)
 */
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'
import { login as loginApi } from '@/api/users'
import { toast } from 'sonner'
import { Shield, Users, User } from 'lucide-react'

const QUICK_USERS = [
  { username: 'admin',    label: '管理员',   role: 'admin',    dept: '管理层',     icon: Shield, color: '#ef4444' },
  { username: '张毅',     label: '张毅',     role: 'manager',  dept: '软件研发部', icon: Users,  color: '#3b82f6' },
  { username: '郭震',     label: '郭震',     role: 'employee', dept: '软件研发部', icon: User,   color: '#22c55e' },
  { username: '张维',     label: '张维',     role: 'employee', dept: '软件研发部', icon: User,   color: '#0ea5e9' },
  { username: '陈翔',     label: '陈翔',     role: 'employee', dept: '软件研发部', icon: User,   color: '#8b5cf6' },
  { username: '林跃文',   label: '林跃文',   role: 'employee', dept: '软件研发部', icon: User,   color: '#eab308' },
  { username: '郑韬慧',   label: '郑韬慧',   role: 'employee', dept: '软件研发部', icon: User,   color: '#a855f7' },
  { username: '宋伟承',   label: '宋伟承',   role: 'employee', dept: '生产部',     icon: User,   color: '#14b8a6' },
  { username: '陶群',     label: '陶群',     role: 'employee', dept: '采购部',     icon: User,   color: '#06b6d4' },
  { username: '陈家云',   label: '陈家云',   role: 'employee', dept: '仓储物流部', icon: User,   color: '#f97316' },
]

export default function LoginPage() {
  const router = useRouter()
  const { login } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({ username: '', password: '' })

  async function doLogin(username: string, password: string) {
    setLoading(true)
    try {
      const res: any = await loginApi(username, password)
      const { access_token, user } = res
      login(access_token, user.name, user.role)
      toast.success(`欢迎回来，${user.name}`)
      router.push('/dashboard')
    } catch (e: any) {
      const detail = e?.response?.data?.detail || '登录失败，请检查用户名和密码'
      toast.error(detail)
    } finally {
      setLoading(false)
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    if (!form.username) {
      toast.warning('请输入用户名')
      return
    }
    await doLogin(form.username, form.password)
  }

  async function quickLogin(username: string) {
    await doLogin(username, 'dev')
  }

  const roleTag = (role: string) => {
    const map: Record<string, string> = { admin: '管理员', manager: '经理', employee: '员工' }
    return map[role] || role
  }

  return (
    <div className="min-h-screen flex items-center justify-center gradient-hero">
      <div className="w-full max-w-md animate-in">
        {/* Logo Header */}
        <div className="text-center mb-8">
          <div
            className="inline-flex w-16 h-16 rounded-2xl items-center justify-center text-white text-2xl font-bold mb-4"
            style={{
              background: 'linear-gradient(135deg, #3b82f6, #a855f7)',
              boxShadow: '0 8px 32px rgba(59,130,246,0.3)',
            }}
          >
            AI
          </div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--color-text-primary)' }}>
            徽远成 AI-PM
          </h1>
          <p className="mt-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            智能项目管理系统 · 管理大盘
          </p>
        </div>

        {/* Login Form */}
        <div
          className="rounded-2xl p-8"
          style={{
            background: 'var(--color-bg-card)',
            border: '1px solid var(--color-border-subtle)',
          }}
        >
          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <input
                type="text"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                placeholder="用户名 / 手机号 / 企微ID"
                className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-colors"
                style={{
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-subtle)',
                  color: 'var(--color-text-primary)',
                }}
              />
            </div>
            <div>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="密码"
                className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-colors"
                style={{
                  background: 'var(--color-bg-secondary)',
                  border: '1px solid var(--color-border-subtle)',
                  color: 'var(--color-text-primary)',
                }}
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-xl text-white font-medium text-sm transition-opacity disabled:opacity-60"
              style={{
                background: 'linear-gradient(135deg, #3b82f6, #6366f1)',
              }}
            >
              {loading ? '登录中...' : '登 录'}
            </button>
          </form>

          {/* Quick Login Section */}
          <div className="mt-6 pt-5" style={{ borderTop: '1px solid var(--color-border-subtle)' }}>
            <div className="text-xs font-medium mb-3" style={{ color: 'var(--color-text-secondary)' }}>
              ⚡ 快捷登录（开发模式）
            </div>
            <div className="grid grid-cols-2 gap-2">
              {QUICK_USERS.map((u) => {
                const Icon = u.icon
                return (
                  <button
                    key={u.username}
                    onClick={() => quickLogin(u.username)}
                    disabled={loading}
                    className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-xs font-medium transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
                    style={{
                      background: `${u.color}12`,
                      border: `1px solid ${u.color}30`,
                      color: u.color,
                    }}
                  >
                    <Icon size={14} />
                    <div className="text-left flex-1 min-w-0">
                      <div className="truncate">{u.label}</div>
                      <div className="text-[10px] opacity-70 truncate">{roleTag(u.role)} · {u.dept}</div>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
