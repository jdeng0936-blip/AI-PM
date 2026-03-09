/**
 * components/auth-guard.tsx — 认证守卫 (替代 Vue Router beforeEach)
 *
 * Rule: 'use client' — 使用浏览器 API
 */
'use client'

import { useEffect, type ReactNode } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'

const PUBLIC_PATHS = ['/login']

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { isLoggedIn, hydrate } = useAuthStore()

  // 客户端首次加载 hydrate
  useEffect(() => {
    hydrate()
  }, [hydrate])

  useEffect(() => {
    if (!PUBLIC_PATHS.includes(pathname) && !isLoggedIn) {
      router.replace('/login')
    }
  }, [pathname, isLoggedIn, router])

  // 未登录时不渲染受保护内容
  if (!PUBLIC_PATHS.includes(pathname) && !isLoggedIn) {
    return null
  }

  return <>{children}</>
}
