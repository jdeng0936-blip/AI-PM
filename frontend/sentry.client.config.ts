// sentry.client.config.ts — 浏览器端 Sentry 初始化
//
// Stage 1 配置预留:DSN 缺失时 Sentry.init 静默 no-op,不影响开发/CI build。
// 实际启用步骤见 docs/SENTRY_SETUP.md。
import * as Sentry from '@sentry/nextjs'

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN

if (dsn) {
  Sentry.init({
    dsn,
    environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT || 'dev',
    // 性能采样率:dev 全采样,prod 建议 0.1
    tracesSampleRate: Number(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
    // 不上报 PII,合规默认
    sendDefaultPii: false,
    // dev 模式下打印 init 信息,prod 静默
    debug: process.env.NODE_ENV !== 'production',
  })
}
