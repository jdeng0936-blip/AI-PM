/**
 * components/auth-guard.tsx — 认证守卫 (替代 Vue Router beforeEach)
 *
 * Rule: 'use client' — 使用浏览器 API
 */
'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuthStore } from '@/stores/use-auth-store'

const PUBLIC_PATHS = ['/login']

export function AuthGuard({ children }: { children: ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { isLoggedIn, hydrate } = useAuthStore()
  const [hydrated, setHydrated] = useState(false)

  // 客户端首次加载 hydrate
  useEffect(() => {
    hydrate()
    setHydrated(true)
  }, [hydrate])

  // 只有 hydrate 完毕后才判断是否需要重定向
  useEffect(() => {
    if (hydrated && !PUBLIC_PATHS.includes(pathname) && !isLoggedIn) {
      router.replace('/login')
    }
  }, [pathname, isLoggedIn, router, hydrated])

  // hydrate 前什么都不渲染，避免闪烁和竞态
  if (!hydrated) {
    return null
  }

  // 未登录时不渲染受保护内容
  if (!PUBLIC_PATHS.includes(pathname) && !isLoggedIn) {
    return null
  }

  return <>{children}</>
}

