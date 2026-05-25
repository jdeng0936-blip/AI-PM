// sentry.server.config.ts — Node.js runtime Sentry 初始化(SSR / API routes)
//
// 由 instrumentation.ts 在服务器启动时 register。
// DSN 缺失时 no-op。
import * as Sentry from '@sentry/nextjs'

const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.SENTRY_ENVIRONMENT || process.env.NODE_ENV || 'dev',
    tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
    sendDefaultPii: false,
  })
}
