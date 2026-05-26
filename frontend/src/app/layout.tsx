import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import { Toaster } from 'sonner'
import { QueryProvider } from '@/providers/query-provider'
import { AuthGuard } from '@/components/auth-guard'
import { AppShell } from '@/components/app-shell'
import './globals.css'

// V2.5 Stage 1 大扫除 #3:用 next/font 替代手动 <link>
// 自动优化、消除 layout shift、并解决 ESLint @next/next/no-page-custom-font warning
const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  display: 'swap',
  variable: '--font-inter',
})

export const metadata: Metadata = {
  title: '徽远成 AI-PM — 智能项目管理系统',
  description: 'AI 驱动的 IPD 双轨项目管理系统，支持日报解析、健康度监控、风险预警',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html
      lang="zh-CN"
      suppressHydrationWarning
      className={inter.variable}
      style={{ backgroundColor: '#0f1117' }}
    >
      <body suppressHydrationWarning style={{ backgroundColor: '#0f1117', margin: 0, padding: 0 }}>
        <div style={{ backgroundColor: '#0f1117', minHeight: '100vh' }}>
          <QueryProvider>
            <AuthGuard>
              <AppShell>
                {children}
              </AppShell>
            </AuthGuard>
          </QueryProvider>
          <Toaster position="top-center" richColors />
        </div>
      </body>
    </html>
  )
}
