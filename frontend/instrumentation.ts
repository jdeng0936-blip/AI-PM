// instrumentation.ts — Next.js 15 标准 hook,服务器启动时调用一次
//
// 按 runtime 加载对应的 Sentry 配置(server / edge 各自的 init)。
// 没配 DSN 时全部静默 no-op。
export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./sentry.server.config')
  }
  if (process.env.NEXT_RUNTIME === 'edge') {
    await import('./sentry.edge.config')
  }
}
