/**
 * components/sidebar.tsx — 侧边栏导航组件
 *
 * 从 Vue App.vue 侧边栏 1:1 迁移。
 * Rule: 'use client' — 使用浏览器 API (usePathname, localStorage)
 */
'use client'

import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'
import {
  LayoutDashboard,
  Kanban,
  FileText,
  Users,
  BarChart3,
  Wand2,
  LogOut,
  FolderKanban,
  TrendingUp,
  MessageSquare,
  Download,
  PenLine,
} from 'lucide-react'

const NAV_ITEMS = [
  { href: '/dashboard', label: '监控台', icon: LayoutDashboard },
  { href: '/submit-report', label: '提交日报', icon: PenLine },
  { href: '/projects', label: '项目列表', icon: FolderKanban },
  { href: '/project/default', label: 'IPD 看板', icon: Kanban },
  { href: '/reports', label: 'AI 日报流', icon: FileText },
  { href: '/trends', label: '评分趋势', icon: TrendingUp },
]

const ADMIN_ITEMS = [
  { href: '/chat', label: 'AI 对话', icon: MessageSquare },
  { href: '/users', label: '用户管理', icon: Users },
  { href: '/stats', label: '系统统计', icon: BarChart3 },
  { href: '/export', label: '数据导出', icon: Download },
  { href: '/simulate', label: '模拟提交', icon: Wand2 },
]

export function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const { userName, userRole, isAdmin, logout } = useAuthStore()

  const roleLabel: Record<string, string> = {
    admin: '管理员',
    manager: '经理',
    employee: '员工',
  }

  function handleLogout() {
    logout()
    router.push('/login')
  }

  const allItems = [...NAV_ITEMS, ...(isAdmin ? ADMIN_ITEMS : [])]

  return (
    <aside
      className="w-56 shrink-0 flex flex-col"
      style={{
        background: 'var(--color-bg-card)',
        borderRight: '1px solid var(--color-border-subtle)',
      }}
    >
      {/* Logo */}
      <div
        className="px-5 py-5 flex items-center gap-3"
        style={{ borderBottom: '1px solid var(--color-border-subtle)' }}
      >
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center text-white font-bold text-sm"
          style={{
            background: 'linear-gradient(135deg, #3b82f6, #a855f7)',
          }}
        >
          AI
        </div>
        <div>
          <div className="text-sm font-semibold" style={{ color: 'var(--color-text-primary)' }}>
            徽远成 AI-PM
          </div>
          <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            智能项目管理
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 pt-2 px-2 space-y-1">
        {allItems.map((item) => {
          const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
          const Icon = item.icon
          return (
            <button
              key={item.href}
              onClick={() => router.push(item.href)}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
              style={{
                color: isActive ? '#3b82f6' : '#94a3b8',
                background: isActive ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
              }}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          )
        })}
      </nav>

      {/* User area */}
      <div
        className="px-4 py-4 flex items-center gap-3"
        style={{ borderTop: '1px solid var(--color-border-subtle)' }}
      >
        <div
          className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold"
          style={{ background: 'linear-gradient(135deg, #22c55e, #16a34a)' }}
        >
          {(userName || '管').charAt(0)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-xs truncate" style={{ color: 'var(--color-text-primary)' }}>
            {userName || '管理员'}
          </div>
          <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            {roleLabel[userRole] || '员工'}
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="p-1.5 rounded-md hover:bg-white/5 transition-colors"
          style={{ color: 'var(--color-text-secondary)' }}
        >
          <LogOut size={16} />
        </button>
      </div>
    </aside>
  )
}
