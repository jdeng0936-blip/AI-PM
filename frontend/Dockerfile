# ════════════════════════════════════════════════════════════════
# 徽远成 AI-PM 前端 Dockerfile (Next.js 15 standalone)
#
# 多阶段构建：
#   1. deps   — 安装 npm 依赖
#   2. build  — Next.js 生产构建
#   3. runner — 最小化运行镜像 (standalone output)
# ════════════════════════════════════════════════════════════════

# ── Stage 1: 依赖安装 ──
FROM node:20-alpine AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev

# ── Stage 2: 构建 ──
FROM node:20-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ── Stage 3: 生产运行 ──
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# 非 root 运行
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# 复制 standalone 输出
COPY --from=build /app/public ./public
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
