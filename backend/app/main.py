"""
app/main.py — FastAPI 应用入口
注册所有路由、CORS、启动/关闭事件。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import wechat, dashboard, erp, reports, auth, users, export
from app.routers import projects as projects_router_module
from app.routers import gates, sprints
from app.config import settings


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
from app.routers import trends, chat, okr, knowledge
app.include_router(trends.router)
app.include_router(chat.router)
# ── OKR & 知识库 ─────────────────────────────────
app.include_router(okr.router)
app.include_router(knowledge.router)
# ── DEV 模拟端点（仅开发环境） ────────────────────
if settings.aipm_env == "dev":
    from app.routers import simulate
    app.include_router(simulate.router)


@app.get("/health")
async def health_check():
    """健康检查接口，供 Docker health check 使用"""
    return {"status": "ok", "service": "huiyuancheng-ai-pm"}
