'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { changePassword } from '@/api/users'
import { toast } from 'sonner'

export default function ChangePasswordPage() {
  const router = useRouter()
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({ old_password: '', new_password: '', confirm_password: '' })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (form.new_password.length < 8) {
      toast.warning('新密码至少 8 位')
      return
    }
    if (form.new_password !== form.confirm_password) {
      toast.warning('两次输入的新密码不一致')
      return
    }
    setLoading(true)
    try {
      await changePassword(form.old_password, form.new_password)
      toast.success('密码已修改')
      router.push('/dashboard')
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || '修改密码失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--color-bg-primary)' }}>
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-semibold" style={{ color: 'var(--color-text-primary)' }}>修改密码</h1>
          <p className="mt-1 text-sm" style={{ color: 'var(--color-text-secondary)' }}>首次登录或密码重置后需要先设置新密码。</p>
        </div>
        <div className="space-y-1.5">
          <label className="block text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>旧密码 / 临时密码</label>
          <input
            type="password"
            value={form.old_password}
            onChange={(e) => setForm({ ...form, old_password: e.target.value })}
            placeholder="临时密码"
            className="w-full px-3 py-2 rounded-lg text-sm outline-none"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>新密码</label>
          <input
            type="password"
            value={form.new_password}
            onChange={(e) => setForm({ ...form, new_password: e.target.value })}
            placeholder="新密码"
            className="w-full px-3 py-2 rounded-lg text-sm outline-none"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
          />
        </div>
        <div className="space-y-1.5">
          <label className="block text-sm font-medium" style={{ color: 'var(--color-text-secondary)' }}>确认新密码</label>
          <input
            type="password"
            value={form.confirm_password}
            onChange={(e) => setForm({ ...form, confirm_password: e.target.value })}
            placeholder="再次输入新密码"
            className="w-full px-3 py-2 rounded-lg text-sm outline-none"
            style={{ background: 'var(--color-bg-card)', border: '1px solid var(--color-border-subtle)', color: 'var(--color-text-primary)' }}
          />
        </div>
        <button
          type="submit"
          disabled={loading}
          className="w-full px-4 py-2 rounded-lg text-sm text-white font-medium disabled:opacity-60"
          style={{ background: 'linear-gradient(135deg, #2563eb, #4f46e5)' }}
        >
          {loading ? '提交中...' : '确认修改'}
        </button>
      </form>
    </main>
  )
}
