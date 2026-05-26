"""
app/services/scheduler.py — APScheduler 定时任务调度中心

所有 cron job 已包裹 services/distributed_lock.with_distributed_lock,
多实例部署时同一 cron 不会被每个进程重复触发(Redis SETNX 互斥);
Redis 不可用时 graceful 降级为单实例语义,不阻塞业务。

定时任务列表：
  - 00:05      请假/出差到期自动恢复 active
  - 00:30      跨日健康度全量重算
  - 09:00      晨报 AI 生成 + 推送
  - 17:30      催报（友好提醒）
  - 20:00      催报（二次催促）
  - 22:00      催报截止（标记未提交 + 通知总经理）
  - 周一 08:30 资源水位刷新 + 过载预警(Week 8)
  - 周一 09:00 上周管理周报 AI 生成 + 推送给管理层
  - 每日 18:00 Sprint 燃尽快照(Week 7)
  - 每日 01:30 删除治理 dry-run(V2.6)
  - 每月 1 日  季度 OKR 汇总归档
  - 每月 1 日 02:00 审计日志月度归档(>12 个月) (Stage 1)
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.services.distributed_lock import with_distributed_lock

logger = logging.getLogger("aipm.scheduler")

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


def start_scheduler() -> None:
    """注册所有定时任务并启动调度器(每个 job 自动包裹分布式锁)"""
    from app.services.capacity_engine import run_weekly_capacity_refresh
    from app.services.scheduled_tasks import (
        archive_old_audit_logs,
        auto_recover_expired_status,
        remind_unreported_deadline,
        remind_unreported_friendly,
        remind_unreported_urgent,
        run_deletion_cleanup_dry_run,
        run_health_refresh_all,
        run_morning_briefing,
        run_quarterly_okr_summary,
        run_weekly_report,
    )
    from app.services.sprint_aggregator import run_daily_burndown_snapshots

    # 分布式锁默认 TTL:30 分钟(覆盖最长任务的实际执行时间;到期自动释放避免卡死)
    _LOCK_TTL = 30 * 60

    # ── 催报机制（三级） ──────────────────────────────────────────
    scheduler.add_job(
        with_distributed_lock("remind_17_30", _LOCK_TTL)(remind_unreported_friendly),
        CronTrigger(hour=17, minute=30),
        id="remind_17_30",
        name="催报-友好提醒",
        replace_existing=True,
    )
    scheduler.add_job(
        with_distributed_lock("remind_20_00", _LOCK_TTL)(remind_unreported_urgent),
        CronTrigger(hour=20, minute=0),
        id="remind_20_00",
        name="催报-二次催促",
        replace_existing=True,
    )
    scheduler.add_job(
        with_distributed_lock("remind_22_00", _LOCK_TTL)(remind_unreported_deadline),
        CronTrigger(hour=22, minute=0),
        id="remind_22_00",
        name="催报-截止标记",
        replace_existing=True,
    )

    # ── 每日 00:05 请假/出差状态到期自动恢复 ──────────────────────
    scheduler.add_job(
        with_distributed_lock("auto_recover_status", _LOCK_TTL)(auto_recover_expired_status),
        CronTrigger(hour=0, minute=5),
        id="auto_recover_status",
        name="请假状态到期恢复",
        replace_existing=True,
    )

    # ── 跨日健康度重算 ────────────────────────────────────────────
    scheduler.add_job(
        with_distributed_lock("health_refresh", _LOCK_TTL)(run_health_refresh_all),
        CronTrigger(hour=0, minute=30),
        id="health_refresh",
        name="健康度全量重算",
        replace_existing=True,
    )

    # ── V2.6 删除治理 dry-run(观察期内只统计/通知,不硬删)────────────
    scheduler.add_job(
        with_distributed_lock("deletion_cleanup_dry_run", _LOCK_TTL)(run_deletion_cleanup_dry_run),
        CronTrigger(hour=1, minute=30),
        id="deletion_cleanup_dry_run",
        name="删除治理dry-run",
        replace_existing=True,
    )

    # ── 晨报自动推送 ──────────────────────────────────────────────
    scheduler.add_job(
        with_distributed_lock("morning_briefing", _LOCK_TTL)(run_morning_briefing),
        CronTrigger(hour=9, minute=0),
        id="morning_briefing",
        name="晨报AI推送",
        replace_existing=True,
    )

    # ── 周一 09:00 自动生成上周管理周报 ───────────────────────────
    scheduler.add_job(
        with_distributed_lock("weekly_report_monday", _LOCK_TTL)(run_weekly_report),
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="weekly_report_monday",
        name="周一周报AI生成",
        replace_existing=True,
    )

    # ── 每月 1 日 09:30 检查季度末 OKR 归档(只在季度首日触发) ──
    scheduler.add_job(
        with_distributed_lock("quarterly_okr_summary", _LOCK_TTL)(run_quarterly_okr_summary),
        CronTrigger(day=1, hour=9, minute=30),
        id="quarterly_okr_summary",
        name="季度OKR汇总归档",
        replace_existing=True,
    )

    # ── 每日 18:00 Sprint 燃尽快照(Week 7)───────────────────────
    scheduler.add_job(
        with_distributed_lock("sprint_burndown_snapshot", _LOCK_TTL)(run_daily_burndown_snapshots),
        CronTrigger(hour=18, minute=0),
        id="sprint_burndown_snapshot",
        name="Sprint燃尽快照",
        replace_existing=True,
    )

    # ── 周一 08:30 资源水位刷新 + 过载预警(Week 8)──────────────
    scheduler.add_job(
        with_distributed_lock("weekly_capacity_refresh", _LOCK_TTL)(run_weekly_capacity_refresh),
        CronTrigger(day_of_week="mon", hour=8, minute=30),
        id="weekly_capacity_refresh",
        name="资源水位刷新",
        replace_existing=True,
    )

    # ── 每月 1 日 02:00 审计日志归档(Stage 1) ─────────────────────
    scheduler.add_job(
        with_distributed_lock("archive_audit_logs", _LOCK_TTL)(archive_old_audit_logs),
        CronTrigger(day=1, hour=2, minute=0),
        id="archive_audit_logs",
        name="审计日志月度归档(>12 个月)",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("⏰ APScheduler 已启动，注册了 %d 个定时任务", len(scheduler.get_jobs()))


def stop_scheduler() -> None:
    """关闭调度器"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("⏰ APScheduler 已关闭")
