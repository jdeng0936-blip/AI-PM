/**
 * components/sidebar.tsx — 侧边栏导航组件
 *
 * 从 Vue App.vue 侧边栏 1:1 迁移。
 * Rule: 'use client' — 使用浏览器 API (usePathname, localStorage)
 */
'use client'

import { usePathname, useRouter } from 'next/navigation'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useAuthStore } from '@/stores/use-auth-store'
import { NotificationBell } from '@/components/notification-bell'
import {
  LayoutDashboard,
  Kanban,
  FileText,
  Users,
  BarChart3,
  LogOut,
  FolderKanban,
  TrendingUp,
  MessageSquare,
  Download,
  PenLine,
  Target,
  RotateCw,
  Flame,
  ThermometerSun,
  ChevronDown,
  ChevronRight,
  Trash2,
  History,
  type LucideIcon,
} from 'lucide-react'

type NavItem = { href: string; label: string; icon: LucideIcon }

const CORE_ITEMS: NavItem[] = [
  { href: '/dashboard', label: '监控台', icon: LayoutDashboard },
  { href: '/submit-report', label: '提交日报', icon: PenLine },
  { href: '/reports', label: 'AI 日报流', icon: FileText },
  { href: '/projects', label: '项目列表', icon: FolderKanban },
  { href: '/trends', label: '评分趋势', icon: TrendingUp },
  { href: '/me/deletions', label: '最近删除', icon: History },
]

const ADVANCED_ITEMS: NavItem[] = [
  { href: '/project/default', label: 'IPD 看板', icon: Kanban },
  { href: '/sprints', label: 'Sprint 燃尽', icon: Flame },
  { href: '/capacity', label: '资源水位', icon: ThermometerSun },
  { href: '/okr', label: 'OKR 战略', icon: Target },
  { href: '/retro', label: 'AI 复盘库', icon: RotateCw },
]

const ADMIN_ITEMS: NavItem[] = [
  { href: '/chat', label: 'AI 对话', icon: MessageSquare },
  { href: '/users', label: '用户管理', icon: Users },
  { href: '/stats', label: '系统统计', icon: BarChart3 },
  { href: '/export', label: '数据导出', icon: Download },
  { href: '/admin/recycle-bin', label: '回收站', icon: Trash2 },  // V2.4 Stage 3 C4
]

const ADVANCED_STORAGE_KEY = 'sidebar.advancedExpanded'

function isPathActive(pathname: string, href: string) {
  return pathname === href || pathname.startsWith(href + '/')
}

export function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const { userName, userRole, isAdmin, logout } = useAuthStore()

  const onAdvancedPage = ADVANCED_ITEMS.some((item) => isPathActive(pathname, item.href))

  const [advancedExpanded, setAdvancedExpanded] = useState(false)

  useEffect(() => {
    if (onAdvancedPage) {
      setAdvancedExpanded(true)
      return
    }
    const stored = typeof window !== 'undefined' ? localStorage.getItem(ADVANCED_STORAGE_KEY) : null
    if (stored === 'true') setAdvancedExpanded(true)
  }, [onAdvancedPage])

  function toggleAdvanced() {
    const next = !advancedExpanded
    setAdvancedExpanded(next)
    if (typeof window !== 'undefined') {
      localStorage.setItem(ADVANCED_STORAGE_KEY, String(next))
    }
  }

  const roleLabel: Record<string, string> = {
    admin: '管理员',
    manager: '经理',
    employee: '员工',
  }

  function handleLogout() {
    logout()
    router.push('/login')
  }

  function renderNavLink(item: NavItem) {
    const isActive = isPathActive(pathname, item.href)
    const Icon = item.icon
    return (
      <Link
        key={item.href}
        href={item.href}
        className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
        style={{
          color: isActive ? '#3b82f6' : '#94a3b8',
          background: isActive ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
        }}
      >
        <Icon size={18} />
        <span>{item.label}</span>
      </Link>
    )
  }

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
      <nav className="flex-1 pt-2 px-2 space-y-1 overflow-y-auto">
        {CORE_ITEMS.map(renderNavLink)}

        {/* 高级功能折叠组 */}
        <button
          type="button"
          onClick={toggleAdvanced}
          className="w-full flex items-center gap-2 px-3 py-2 mt-3 rounded-lg text-xs uppercase tracking-wider transition-colors hover:bg-white/5"
          style={{ color: 'var(--color-text-secondary)' }}
          aria-expanded={advancedExpanded}
        >
          {advancedExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <span>高级功能</span>
        </button>
        {advancedExpanded && ADVANCED_ITEMS.map(renderNavLink)}

        {/* 管理分组(仅 admin 可见) */}
        {isAdmin && (
          <>
            <div
              className="px-3 pt-3 pb-1 text-xs uppercase tracking-wider"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              管理
            </div>
            {ADMIN_ITEMS.map(renderNavLink)}
          </>
        )}
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
        <NotificationBell />
        <button
          onClick={handleLogout}
          className="p-1.5 rounded-md hover:bg-white/5 transition-colors"
          style={{ color: 'var(--color-text-secondary)' }}
          title="退出登录"
        >
          <LogOut size={16} />
        </button>
      </div>
    </aside>
  )
}
