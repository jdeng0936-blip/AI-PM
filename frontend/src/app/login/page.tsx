/**
 * app/login/page.tsx — 登录页（重设计版）
 * 修复 CSS 变量失效 + 全面升级 UI 视觉
 */
'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'
import { login as loginApi } from '@/api/users'
import { toast } from 'sonner'
import { Shield, Users, User, Loader2, Sparkles, BarChart3, BrainCircuit } from 'lucide-react'

const QUICK_USERS = [
  { username: 'admin',    label: '总经理',   role: 'admin',    dept: '管理层',     icon: Shield, color: '#ef4444' },
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

const FEATURES = [
  { icon: BrainCircuit, label: 'AI 智能质检', desc: '自动解析日报，秒级反馈' },
  { icon: BarChart3,    label: '实时看板',    desc: '项目健康度一目了然' },
  { icon: Sparkles,     label: 'IPD 门径',    desc: '5阶段4关卡双轨管理' },
]

export default function LoginPage() {
  const router = useRouter()
  const { login } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [loadingUser, setLoadingUser] = useState<string | null>(null)
  const [form, setForm] = useState({ username: '', password: '' })

  async function doLogin(username: string, password: string) {
    setLoading(true)
    setLoadingUser(username)
    try {
      const res: any = await loginApi(username, password)
      const { access_token, user } = res
      login(access_token, user.name, user.role)
      toast.success(`欢迎回来，${user.name} 👋`)
      if (user.must_change_password) {
        router.push('/change-password')
      } else {
        router.push('/dashboard')
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail || '登录失败，请检查用户名和密码'
      toast.error(detail)
    } finally {
      setLoading(false)
      setLoadingUser(null)
    }
  }

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    if (!form.username) { toast.warning('请输入用户名'); return }
    await doLogin(form.username, form.password || 'dev')
  }

  const roleTag = (role: string) => {
    const map: Record<string, string> = { admin: '管理员', manager: '经理', employee: '员工' }
    return map[role] || role
  }

  return (
    <div style={{
      minHeight: '100vh',
      backgroundColor: '#0f1117',
      backgroundImage: `
        radial-gradient(ellipse at 20% 50%, rgba(59,130,246,0.12) 0%, transparent 55%),
        radial-gradient(ellipse at 80% 20%, rgba(168,85,247,0.08) 0%, transparent 50%),
        radial-gradient(ellipse at 50% 90%, rgba(99,102,241,0.06) 0%, transparent 40%)
      `,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '24px 16px',
      fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, sans-serif',
    }}>

      {/* 主容器 */}
      <div style={{ width: '100%', maxWidth: '440px', animation: 'loginFadeIn 0.5s cubic-bezier(0.16,1,0.3,1) both' }}>

        {/* Logo + 标题 */}
        <div style={{ textAlign: 'center', marginBottom: '32px' }}>
          {/* 图标 */}
          <div style={{
            display: 'inline-flex',
            width: '64px',
            height: '64px',
            borderRadius: '20px',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '22px',
            fontWeight: '800',
            color: '#fff',
            background: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 50%, #a855f7 100%)',
            boxShadow: '0 8px 32px rgba(99,102,241,0.35), 0 0 0 1px rgba(255,255,255,0.08)',
            marginBottom: '16px',
            letterSpacing: '-1px',
          }}>
            AI
          </div>

          <h1 style={{ margin: '0 0 6px', fontSize: '24px', fontWeight: '700', color: '#e2e8f0', letterSpacing: '-0.5px' }}>
            徽远成 AI-PM
          </h1>
          <p style={{ margin: 0, fontSize: '13px', color: '#64748b' }}>
            智能项目管理系统 · 让管理更高效
          </p>

          {/* 特性标签 */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', marginTop: '16px', flexWrap: 'wrap' }}>
            {FEATURES.map(f => (
              <div key={f.label} style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '4px 10px',
                borderRadius: '20px',
                fontSize: '11px',
                fontWeight: '500',
                color: '#94a3b8',
                background: 'rgba(255,255,255,0.04)',
                border: '1px solid rgba(255,255,255,0.07)',
              }}>
                <f.icon size={11} style={{ color: '#6366f1' }} />
                {f.label}
              </div>
            ))}
          </div>
        </div>

        {/* 登录卡片 */}
        <div style={{
          background: 'rgba(30,32,48,0.9)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: '20px',
          padding: '32px',
          backdropFilter: 'blur(20px)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.04)',
        }}>

          {/* 表单 */}
          <form onSubmit={handleLogin} style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '24px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '500', color: '#64748b', marginBottom: '6px' }}>
                用户名
              </label>
              <input
                type="text"
                value={form.username}
                onChange={(e) => setForm({ ...form, username: e.target.value })}
                placeholder="输入用户名"
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  borderRadius: '10px',
                  fontSize: '14px',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  color: '#e2e8f0',
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box',
                }}
                onFocus={e => (e.target.style.borderColor = 'rgba(99,102,241,0.6)')}
                onBlur={e => (e.target.style.borderColor = 'rgba(255,255,255,0.1)')}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: '500', color: '#64748b', marginBottom: '6px' }}>
                密码 <span style={{ color: '#3d4260' }}>（快捷登录可留空）</span>
              </label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                placeholder="输入密码"
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  borderRadius: '10px',
                  fontSize: '14px',
                  background: 'rgba(255,255,255,0.05)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  color: '#e2e8f0',
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box',
                }}
                onFocus={e => (e.target.style.borderColor = 'rgba(99,102,241,0.6)')}
                onBlur={e => (e.target.style.borderColor = 'rgba(255,255,255,0.1)')}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%',
                padding: '11px',
                borderRadius: '10px',
                fontSize: '14px',
                fontWeight: '600',
                color: '#fff',
                background: loading
                  ? 'linear-gradient(135deg, #4b5563, #374151)'
                  : 'linear-gradient(135deg, #3b82f6 0%, #6366f1 50%, #8b5cf6 100%)',
                border: 'none',
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'all 0.2s',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                boxShadow: loading ? 'none' : '0 4px 16px rgba(99,102,241,0.3)',
                marginTop: '4px',
              }}
            >
              {loading && loadingUser === form.username && (
                <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} />
              )}
              {loading ? '登录中...' : '登 录'}
            </button>
          </form>

          {/* 分割线 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.07)' }} />
            <span style={{ fontSize: '11px', color: '#3d4260', whiteSpace: 'nowrap' }}>⚡ 开发快捷登录</span>
            <div style={{ flex: 1, height: '1px', background: 'rgba(255,255,255,0.07)' }} />
          </div>

          {/* 快捷用户网格 */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
            {QUICK_USERS.map((u) => {
              const Icon = u.icon
              const isThisLoading = loading && loadingUser === u.username
              return (
                <button
                  key={u.username}
                  onClick={() => doLogin(u.username, 'dev')}
                  disabled={loading}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '8px 10px',
                    borderRadius: '10px',
                    fontSize: '12px',
                    fontWeight: '500',
                    background: `${u.color}10`,
                    border: `1px solid ${u.color}25`,
                    color: u.color,
                    cursor: loading ? 'not-allowed' : 'pointer',
                    transition: 'all 0.15s',
                    textAlign: 'left',
                    opacity: loading && !isThisLoading ? 0.5 : 1,
                  }}
                  onMouseEnter={e => {
                    if (!loading) {
                      (e.currentTarget as HTMLButtonElement).style.background = `${u.color}1a`
                      ;(e.currentTarget as HTMLButtonElement).style.borderColor = `${u.color}45`
                      ;(e.currentTarget as HTMLButtonElement).style.transform = 'translateY(-1px)'
                    }
                  }}
                  onMouseLeave={e => {
                    (e.currentTarget as HTMLButtonElement).style.background = `${u.color}10`
                    ;(e.currentTarget as HTMLButtonElement).style.borderColor = `${u.color}25`
                    ;(e.currentTarget as HTMLButtonElement).style.transform = 'translateY(0)'
                  }}
                >
                  {isThisLoading
                    ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />
                    : <Icon size={13} style={{ flexShrink: 0 }} />
                  }
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {u.label}
                    </div>
                    <div style={{ fontSize: '10px', opacity: 0.65, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {roleTag(u.role)} · {u.dept}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* 底部版权 */}
        <p style={{ textAlign: 'center', marginTop: '20px', fontSize: '11px', color: '#2d3148' }}>
          徽远成科技 · AI-PM v1.0 · 仅限内部使用
        </p>
      </div>

      <style>{`
        @keyframes loginFadeIn {
          from { opacity: 0; transform: translateY(16px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        input::placeholder { color: #3d4260; }
      `}</style>
    </div>
  )
}
