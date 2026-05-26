// app/global-error.tsx — Next.js App Router 全局 React render error 兜底
//
// V2.5 Stage 1 大扫除 #2:配套 Sentry,捕获子树渲染异常并上报。
// 必须包含完整 <html>/<body> 因为 root layout 渲染失败时这里接管。
'use client'

import * as Sentry from '@sentry/nextjs'
import { useEffect } from 'react'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    Sentry.captureException(error)
  }, [error])

  return (
    <html lang="zh-CN">
      <body
        style={{
          background: '#0f172a',
          color: '#e2e8f0',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
        }}
      >
        <div style={{ maxWidth: 480, textAlign: 'center' }}>
          <h1 style={{ fontSize: 32, marginBottom: 12, color: '#f87171' }}>
            出错了
          </h1>
          <p style={{ color: '#94a3b8', marginBottom: 24, lineHeight: 1.6 }}>
            页面渲染时遇到错误,已自动上报。请刷新重试,或联系管理员。
          </p>
          {error.digest && (
            <p style={{ fontSize: 12, color: '#64748b', marginBottom: 16, fontFamily: 'monospace' }}>
              错误编号: {error.digest}
            </p>
          )}
          <button
            onClick={() => reset()}
            style={{
              background: '#3b82f6',
              color: '#fff',
              border: 'none',
              padding: '10px 24px',
              borderRadius: 8,
              fontSize: 14,
              cursor: 'pointer',
            }}
          >
            重试
          </button>
        </div>
      </body>
    </html>
  )
}
