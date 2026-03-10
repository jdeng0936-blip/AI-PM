/**
 * components/app-shell.tsx — 应用外壳（侧边栏 + 主内容区）
 *
 * 替代 Vue App.vue 的布局逻辑：
 * - 已登录且非 /login → 显示侧边栏 + 内容
 * - /login 页面 → 全屏无侧边栏
 */
'use client'

import { usePathname } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'
import { Sidebar } from '@/components/sidebar'
import type { ReactNode } from 'react'

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const { isLoggedIn } = useAuthStore()

  const isLoginPage = pathname === '/login'

  // 登录页 → 全屏
  if (isLoginPage || !isLoggedIn) {
    return <>{children}</>
  }

  // 主布局 → 侧边栏 + 内容
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main
        className="flex-1 overflow-y-auto"
        style={{ background: 'var(--color-bg-primary)' }}
      >
        {children}
      </main>
    </div>
  )
}
