"""
app/main.py — FastAPI 应用入口
注册所有路由、CORS、启动/关闭事件。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import (
    admin_reports,
    analytics,
    auth,
    dashboard,
    departments,
    erp,
    export,
    gates,
    kpi,
    me_deletions,
    reports,
    sprints,
    users,
    wechat,
)
from app.routers import projects as projects_router_module


def _looks_like_placeholder_secret(value: str) -> bool:
    lowered = (value or "").strip().lower()
    return (
        not lowered
        or len(lowered) < 32
        or "change-me" in lowered
        or "placeholder" in lowered
        or lowered.startswith("your_")
        or lowered.startswith("ci-test")
    )


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

    env = settings.aipm_env

    if env != "dev":
        insecure_settings = []
        if _looks_like_placeholder_secret(settings.jwt_secret_key):
            insecure_settings.append("JWT_SECRET_KEY")
        if _looks_like_placeholder_secret(settings.erp_webhook_secret):
            insecure_settings.append("ERP_WEBHOOK_SECRET")
        if insecure_settings:
            names = ", ".join(insecure_settings)
            raise RuntimeError(f"{names} 未配置安全随机值 — 生产环境必须使用至少 32 字符的真实密钥。")

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
app.include_router(me_deletions.router)
app.include_router(export.router)
app.include_router(analytics.router)
app.include_router(kpi.router)
app.include_router(departments.router)
app.include_router(admin_reports.router)
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
if settings.aipm_env == "dev" and settings.enable_dev_simulation:
    from app.routers import simulate

    app.include_router(simulate.router)


@app.get("/health")
async def health_check():
    """Liveness probe — 仅验进程活,不依赖任何外部资源。

    Docker / K8s 用本端点判断"是否需要重启容器"。**不能**做 DB / Redis
    检查,否则外部资源短暂抖动会导致整个容器被无谓重启。
    """
    return {"status": "ok", "service": "huiyuancheng-ai-pm"}


# V2.5 Stage 1 P1 #7:alembic head revision 缓存(读 alembic 脚本目录一次)
from functools import lru_cache
from pathlib import Path

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


@lru_cache(maxsize=1)
def _alembic_head_revision() -> str | None:
    """读 alembic 脚本目录的 head revision;无法读取返回 None(健康检查 fallback)。"""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(_ALEMBIC_INI))
        script = ScriptDirectory.from_config(cfg)
        return script.get_current_head()
    except Exception:
        return None


async def _check_alembic_version(db) -> dict:
    """对比 DB alembic_version vs 脚本 head — schema 不匹配视为未就绪。"""
    from sqlalchemy import text

    head = _alembic_head_revision()
    if head is None:
        # 脚本目录读不出 head(本地 / 测试环境):跳过该 check,不视为不健康
        return {"ok": True, "head": None, "current": None, "skipped": True}
    try:
        row = (await db.execute(text("SELECT version_num FROM alembic_version"))).first()
        current = row[0] if row else None
    except Exception as e:
        return {"ok": False, "error": f"alembic_version 表不可读: {str(e)[:120]}"}
    if current != head:
        return {"ok": False, "head": head, "current": current, "error": "schema 未升级到 head"}
    return {"ok": True, "head": head, "current": current}


@app.get("/health/ready")
async def health_ready():
    """Readiness probe — DB + Redis + alembic schema 都 ok 才返 200。

    任一关键依赖失败 → 503 + 详细 reason。Docker / K8s 用本端点决定
    "是否把流量路由进来"。schema 未升级 / DB 挂 / Redis 挂均视为未就绪。

    V2.5 Stage 1 P1 #7:补 Stage 2 之前的 docker healthcheck 盲点
    (生产容器即使迁移未跑也被视为健康)。
    """
    import time

    import redis.asyncio as redis_async
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    from app.database import AsyncSessionLocal

    checks: dict = {}
    ready = True

    # DB
    t0 = time.perf_counter()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            # alembic 版本对比(同一 session 复用)
            checks["alembic"] = await _check_alembic_version(db)
        checks["database"] = {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
        if not checks["alembic"]["ok"]:
            ready = False
    except Exception as e:
        checks["database"] = {"ok": False, "error": str(e)[:200]}
        checks["alembic"] = {"ok": False, "skipped": True, "error": "依赖 DB"}
        ready = False

    # Redis(分布式锁 + 缓存)
    t0 = time.perf_counter()
    try:
        r = redis_async.from_url(settings.redis_url, socket_timeout=2, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        checks["redis"] = {"ok": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 2)}
    except Exception as e:
        checks["redis"] = {"ok": False, "error": str(e)[:200]}
        ready = False

    body = {"status": "ready" if ready else "not_ready", "checks": checks}
    return JSONResponse(content=body, status_code=200 if ready else 503)


@app.get("/health/detailed")
async def health_detailed():
    """生产监控用的多维度健康检查 — DB / Redis / Sentry / Scheduler / alembic。

    返回每个依赖的 ok/down + 关键指标。任何 down 整体 status="degraded"。
    canary / oncall / Sentry 关联告警可基于本端点轮询。

    与 /health/ready 区别:本端点用于 observability(永远返回 200 + 详情);
    /health/ready 用于 k8s readiness 路由判断(失败返 503)。
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

    # ─── DB ping + alembic 版本对比 ────────────────────────────────
    t0 = time.perf_counter()
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            result["checks"]["alembic"] = await _check_alembic_version(db)
        result["checks"]["database"] = {
            "ok": True,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
        if not result["checks"]["alembic"]["ok"]:
            result["status"] = "degraded"
    except Exception as e:
        result["checks"]["database"] = {"ok": False, "error": str(e)[:200]}
        result["checks"]["alembic"] = {"ok": False, "skipped": True, "error": "依赖 DB"}
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
