"""
app/main.py — FastAPI 应用入口
注册所有路由、CORS、启动/关闭事件。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import auth, dashboard, erp, export, gates, reports, sprints, users, wechat
from app.routers import projects as projects_router_module

# ── Sentry 初始化(必须在 FastAPI app 创建之前 init,才能捕获启动期异常)──
if settings.sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            send_default_pii=False,  # 不上报用户 PII,合规默认
        )
        import logging

        logging.getLogger("aipm").info(
            "🛰️  Sentry 已启用 env=%s traces_sample_rate=%s",
            settings.sentry_environment,
            settings.sentry_traces_sample_rate,
        )
    except ImportError:
        # sentry-sdk 未安装时静默跳过(本地最小依赖场景)
        import logging

        logging.getLogger("aipm").warning("⚠️  SENTRY_DSN 已配置但 sentry-sdk 未安装,跳过初始化")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    ⚠️  建表策略说明：
    - 开发环境：init_db() 会调用 metadata.create_all()，自动建缺失的表（方便快速启动）
    - 生产环境：必须先运行 `alembic upgrade head`，init_db() 仅做连接验证
      启动前务必执行：
        docker exec -it aipm-backend alembic upgrade head
    """
    import logging

    logger = logging.getLogger("aipm")

    import os

    env = os.getenv("AIPM_ENV", "dev")

    if env == "dev":
        logger.warning("🔧 开发模式：自动创建缺失的数据库表（生产环境请用 alembic）")
        await init_db()
    else:
        logger.info("🏭 生产模式：跳过 init_db()，请确保已执行 alembic upgrade head")

    logger.info("✅ 徽远成 AI-PM 后端启动成功")

    # ── 启动定时任务调度器 ────────────────────────────────────────
    from app.services.scheduler import start_scheduler, stop_scheduler

    start_scheduler()

    yield

    stop_scheduler()
    logger.info("⏹️  徽远成 AI-PM 后端正在关闭...")


app = FastAPI(
    title="徽远成 AI-PM 后端",
    description="基于 FastAPI + Gemini 的智能项目管理系统",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,  # 禁止 307 重定向，避免 POST 丢失 Authorization header
)

# CORS 配置：dev 放行 localhost，prod 仅放行 .env 中配置的域名
_cors_origins = (
    ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"]
    if settings.aipm_env == "dev"
    else settings.cors_allowed_origins
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
# ── 认证 & 用户管理 ──────────────────────────────
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(export.router)
# ── 基础功能 ─────────────────────────────────────
app.include_router(wechat.router)
app.include_router(dashboard.router)
app.include_router(erp.router)
app.include_router(reports.router)
# ── IPD 门径管理 & 双轨敏捷 ───────────────────────
app.include_router(projects_router_module.router)
app.include_router(projects_router_module.stages_router)
app.include_router(gates.router)
app.include_router(sprints.router)
# ── 趋势分析 & AI 对话 ───────────────────────────
from app.routers import chat, knowledge, okr, trends

app.include_router(trends.router)
app.include_router(chat.router)
# ── OKR & 知识库 ─────────────────────────────────
app.include_router(okr.router)
app.include_router(knowledge.router)
# ── 通知推送 ─────────────────────────────────────
from app.routers import notifications as notifications_router

app.include_router(notifications_router.router)
# ── AI 复盘库(Week 6)──────────────────────────
from app.routers import retro as retro_router

app.include_router(retro_router.router)
# ── 资源水位(Week 8)──────────────────────────
from app.routers import capacity as capacity_router

app.include_router(capacity_router.router)
# ── 附件 + 语音 ASR ──────────────────────────────
from app.routers import asr as asr_router
from app.routers import attachments as attachments_router

app.include_router(attachments_router.router)
app.include_router(asr_router.router)
# ── DEV 模拟端点（仅开发环境） ────────────────────
if settings.aipm_env == "dev":
    from app.routers import simulate

    app.include_router(simulate.router)


@app.get("/health")
async def health_check():
    """健康检查接口，供 Docker health check 使用"""
    return {"status": "ok", "service": "huiyuancheng-ai-pm"}


@app.get("/health/detailed")
async def health_detailed():
    """生产监控用的多维度健康检查 — DB / Redis / Sentry / Scheduler。

    返回每个依赖的 ok/down + 关键指标。任何 down 整体 status="degraded"。
    canary / oncall / Sentry 关联告警可基于本端点轮询。
    """
    import time

    import redis.asyncio as redis_async
    from sqlalchemy import text

    from app.database import AsyncSessionLocal
    from app.services.scheduler import scheduler

    result: dict = {
        "status": "ok",
        "service": "huiyuancheng-ai-pm",
        "checks": {},
    }

    # ─── DB ping ──────────────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        result["checks"]["database"] = {
            "ok": True,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
    except Exception as e:
        result["checks"]["database"] = {"ok": False, "error": str(e)[:200]}
        result["status"] = "degraded"

    # ─── Redis ping(分布式锁 + 缓存依赖)───────────────────────
    t0 = time.perf_counter()
    try:
        r = redis_async.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        result["checks"]["redis"] = {
            "ok": True,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
    except Exception as e:
        result["checks"]["redis"] = {"ok": False, "error": str(e)[:200]}
        result["status"] = "degraded"

    # ─── Sentry 配置状态 ──────────────────────────────────────────
    result["checks"]["sentry"] = {
        "enabled": bool(settings.sentry_dsn),
        "environment": settings.sentry_environment if settings.sentry_dsn else None,
    }

    # ─── APScheduler 任务数 ──────────────────────────────────────
    try:
        jobs = scheduler.get_jobs() if scheduler.running else []
        result["checks"]["scheduler"] = {
            "running": scheduler.running,
            "job_count": len(jobs),
        }
        if not scheduler.running:
            result["status"] = "degraded"
    except Exception as e:
        result["checks"]["scheduler"] = {"running": False, "error": str(e)[:200]}
        result["status"] = "degraded"

    return result
