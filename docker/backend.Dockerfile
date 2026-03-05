# ════════════════════════════════════════════════════════════════
# 徽远成 AI-PM — 生产级多阶段 Dockerfile
# Stage 1: 安装依赖（有缓存层，重复构建极快）
# Stage 2: 精简运行镜像（不含构建工具，镜像体积最小）
# ════════════════════════════════════════════════════════════════

# ── Stage 1: 依赖构建层 ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# 只复制依赖清单，利用 Docker 层缓存
COPY requirements.txt .

# 安装到独立目录（后续只需复制该目录）
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: 精简运行层 ──────────────────────────────────────────
FROM python:3.11-slim

# 系统级依赖（libpq-dev 用于 asyncpg）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 从构建层复制已安装的 Python 包
COPY --from=builder /install /usr/local

# 复制应用代码
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# 非 root 用户运行（安全加固）
RUN useradd -m -u 1000 aipm && chown -R aipm:aipm /app
USER aipm

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 4 个 worker 适合 2-4 核生产服务器，按实际 CPU 核数调整
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--log-level", "info"]
