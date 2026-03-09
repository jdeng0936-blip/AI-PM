# ════════════════════════════════════════════════════════════════
# 徽远成 AI-PM 前端 — 多阶段构建
# Stage 1: Node 构建 → 生产静态文件
# Stage 2: Nginx Alpine 轻量镜像托管
# ════════════════════════════════════════════════════════════════

# ── Stage 1: 构建层 ──────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /build

# 只复制依赖清单，利用 Docker 层缓存
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --prefer-offline 2>/dev/null || npm install

# 复制前端源码并构建
COPY frontend/ .
RUN npm run build

# ── Stage 2: Nginx 运行层 ────────────────────────────────────────
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /build/dist /usr/share/nginx/html

# 复制 Nginx 配置
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# 非 root 权限
RUN chown -R nginx:nginx /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q --spider http://localhost/health || exit 1
