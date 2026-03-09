import type { Metadata } from 'next'
import { Toaster } from 'sonner'
import { QueryProvider } from '@/providers/query-provider'
import { AuthGuard } from '@/components/auth-guard'
import { AppShell } from '@/components/app-shell'
import './globals.css'

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
    <html lang="zh-CN">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">
        <QueryProvider>
          <AuthGuard>
            <AppShell>
              {children}
            </AppShell>
          </AuthGuard>
        </QueryProvider>
        <Toaster position="top-center" richColors />
      </body>
    </html>
  )
}
