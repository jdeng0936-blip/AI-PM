// instrumentation.ts — Next.js 15 标准 hook,服务器启动时调用一次
//
// 按 runtime 加载对应的 Sentry 配置(server / edge 各自的 init)。
// 没配 DSN 时全部静默 no-op。
//
// V2.5 Stage 1 大扫除 #2:同时导出 onRequestError(Sentry.captureRequestError),
// 用于捕获 nested React Server Components / route handlers 抛出的错误。
import * as Sentry from '@sentry/nextjs'

export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./sentry.server.config')
  }
  if (process.env.NEXT_RUNTIME === 'edge') {
    await import('./sentry.edge.config')
  }
}

export const onRequestError = Sentry.captureRequestError
