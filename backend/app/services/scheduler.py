"""
app/services/scheduler.py — APScheduler 定时任务调度中心

定时任务列表：
  - 17:30  催报（友好提醒）
  - 20:00  催报（二次催促）
  - 22:00  催报截止（标记未提交 + 通知总经理）
  - 00:30  跨日健康度全量重算
  - 09:00  晨报 AI 生成 + 推送
"""
from __future__ import annotations

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("aipm.scheduler")

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


def start_scheduler() -> None:
    """注册所有定时任务并启动调度器"""
    from app.services.scheduled_tasks import (
        remind_unreported_friendly,
        remind_unreported_urgent,
        remind_unreported_deadline,
        run_health_refresh_all,
        run_morning_briefing,
    )

    # ── 催报机制（三级） ──────────────────────────────────────────
    scheduler.add_job(
        remind_unreported_friendly,
        CronTrigger(hour=17, minute=30),
        id="remind_17_30",
        name="催报-友好提醒",
        replace_existing=True,
    )
    scheduler.add_job(
        remind_unreported_urgent,
        CronTrigger(hour=20, minute=0),
        id="remind_20_00",
        name="催报-二次催促",
        replace_existing=True,
    )
    scheduler.add_job(
        remind_unreported_deadline,
        CronTrigger(hour=22, minute=0),
        id="remind_22_00",
        name="催报-截止标记",
        replace_existing=True,
    )

    # ── 跨日健康度重算 ────────────────────────────────────────────
    scheduler.add_job(
        run_health_refresh_all,
        CronTrigger(hour=0, minute=30),
        id="health_refresh",
        name="健康度全量重算",
        replace_existing=True,
    )

    # ── 晨报自动推送 ──────────────────────────────────────────────
    scheduler.add_job(
        run_morning_briefing,
        CronTrigger(hour=9, minute=0),
        id="morning_briefing",
        name="晨报AI推送",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("⏰ APScheduler 已启动，注册了 %d 个定时任务", len(scheduler.get_jobs()))


def stop_scheduler() -> None:
    """关闭调度器"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("⏰ APScheduler 已关闭")
