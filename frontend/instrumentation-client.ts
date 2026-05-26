// instrumentation-client.ts — Sentry browser-side init
//
// V2.5 Stage 1 大扫除 #2 — 从 sentry.client.config.ts 迁移而来。Next.js 15
// 推荐用 instrumentation-client.ts(原 sentry.client.config.ts 在 Turbopack
// 下已不再加载,见 https://nextjs.org/docs/app/api-reference/file-conventions/
// instrumentation-client)。
//
// DSN 缺失时 Sentry.init 静默 no-op,不影响开发/CI build。
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

// V2.5 Stage 1 大扫除 #2:App Router 客户端路由跳转性能监控
// Sentry 检测到本文件存在但未导出 onRouterTransitionStart 时会告警,补上即可。
export const onRouterTransitionStart = Sentry.captureRouterTransitionStart
