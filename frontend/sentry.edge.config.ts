// sentry.edge.config.ts — Edge runtime Sentry 初始化(middleware / edge routes)
//
// DSN 缺失时 no-op。Edge runtime 不支持完整 Node API,Sentry 也降级运行。
import * as Sentry from '@sentry/nextjs'

const dsn = process.env.SENTRY_DSN || process.env.NEXT_PUBLIC_SENTRY_DSN

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.SENTRY_ENVIRONMENT || process.env.NODE_ENV || 'dev',
    tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
  })
}
