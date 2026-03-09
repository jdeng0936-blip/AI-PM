"""
app/services/scheduled_tasks.py — 定时任务实现

所有定时执行的业务逻辑集中在此文件。
每个任务自行管理数据库会话（不依赖 FastAPI 的 Depends 注入）。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, func, and_

from app.database import AsyncSessionLocal
from app.models.daily_report import DailyReport
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.services.health_engine import refresh_project_health

logger = logging.getLogger("aipm.tasks")


# ═══════════════════════════════════════════════════════════════════
# 催报机制
# ═══════════════════════════════════════════════════════════════════

async def _get_unreported_users(today: Optional[date] = None) -> list:
    """查询今日未提交日报的活跃用户"""
    if today is None:
        today = date.today()

    async with AsyncSessionLocal() as db:
        # 今日已提交的 user_id 集合
        reported = await db.execute(
            select(DailyReport.user_id).where(
                DailyReport.report_date == today
            )
        )
        reported_ids = {row[0] for row in reported.all()}

        # 所有活跃用户中未提交的
        all_users_result = await db.execute(
            select(User).where(User.is_active == True)
        )
        all_users = all_users_result.scalars().all()

        return [u for u in all_users if u.id not in reported_ids]


async def remind_unreported_friendly() -> None:
    """17:30 — 友好提醒"""
    logger.info("⏰ [17:30] 催报-友好提醒")
    unreported = await _get_unreported_users()
    if not unreported:
        logger.info("   所有人已提交日报 ✅")
        return

    try:
        from app.services.wechat_api import send_text_message
        for user in unreported:
            if user.wechat_userid:
                await send_text_message(
                    user.wechat_userid,
                    f"🔔 {user.name}，今天的日报还没交哦，别忘了～\n"
                    f"截止时间：22:00",
                )
        logger.info("   已提醒 %d 人", len(unreported))
    except Exception as e:
        logger.error("   催报推送失败: %s", e)


async def remind_unreported_urgent() -> None:
    """20:00 — 二次催促"""
    logger.info("⏰ [20:00] 催报-二次催促")
    unreported = await _get_unreported_users()
    if not unreported:
        return

    try:
        from app.services.wechat_api import send_text_message
        for user in unreported:
            if user.wechat_userid:
                await send_text_message(
                    user.wechat_userid,
                    f"⚠️ {user.name}，日报截止时间快到了（22:00），请尽快提交！",
                )
        logger.info("   已催促 %d 人", len(unreported))
    except Exception as e:
        logger.error("   催报推送失败: %s", e)


async def remind_unreported_deadline() -> None:
    """22:00 — 截止标记 + 通知总经理"""
    logger.info("⏰ [22:00] 催报-截止标记")
    unreported = await _get_unreported_users()
    if not unreported:
        logger.info("   所有人已提交 ✅")
        return

    names = [u.name for u in unreported]
    logger.warning("   未提交日报: %s", ", ".join(names))

    try:
        from app.services.wechat_api import send_text_message

        # 通知总经理（admin 角色）
        async with AsyncSessionLocal() as db:
            admins_result = await db.execute(
                select(User).where(
                    and_(User.role == "admin", User.is_active == True)
                )
            )
            admins = admins_result.scalars().all()

        absent_list = "\n".join(f"  · {n}" for n in names)
        summary = (
            f"📋 今日日报缺勤报告\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"日期：{date.today()}\n"
            f"未提交人数：{len(names)}\n"
            f"名单：\n{absent_list}\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"请关注以上人员的工作状态。"
        )

        for admin in admins:
            if admin.wechat_userid:
                await send_text_message(admin.wechat_userid, summary)

        logger.info("   已通知 %d 位管理员", len(admins))
    except Exception as e:
        logger.error("   截止通知失败: %s", e)


# ═══════════════════════════════════════════════════════════════════
# 跨日健康度全量重算
# ═══════════════════════════════════════════════════════════════════

async def run_health_refresh_all() -> None:
    """00:30 — 重算所有活跃项目健康度"""
    logger.info("⏰ [00:30] 健康度全量重算")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Project.id).where(Project.status == ProjectStatus.active)
        )
        project_ids = [row[0] for row in result.all()]

    count = 0
    for pid in project_ids:
        try:
            async with AsyncSessionLocal() as db:
                await refresh_project_health(db, pid)
            count += 1
        except Exception as e:
            logger.error("   项目 %s 重算失败: %s", pid, e)

    logger.info("   已重算 %d / %d 个项目", count, len(project_ids))


# ═══════════════════════════════════════════════════════════════════
# 晨报 AI 自动生成 + 推送
# ═══════════════════════════════════════════════════════════════════

async def run_morning_briefing() -> None:
    """09:00 — AI 生成晨报 + 推送给管理层"""
    logger.info("⏰ [09:00] 晨报 AI 生成")
    yesterday = date.today() - timedelta(days=1)

    try:
        async with AsyncSessionLocal() as db:
            # 拉取昨日所有日报摘要
            stmt = (
                select(DailyReport, User.name, User.department)
                .join(User, DailyReport.user_id == User.id)
                .where(DailyReport.report_date == yesterday)
                .order_by(DailyReport.ai_score.desc())
            )
            rows = (await db.execute(stmt)).all()

        if not rows:
            logger.info("   昨日无日报，跳过晨报生成")
            return

        # 汇总文本
        lines = []
        for r in rows:
            pc = r.DailyReport.parsed_content or {}
            lines.append(
                f"【{r.name}·{r.department}】评分{r.DailyReport.ai_score} | "
                f"进度{pc.get('progress', '?')}% | "
                f"任务: {pc.get('tasks', '无')} | "
                f"卡点: {pc.get('blocker', '无')}"
            )
        summary_text = "\n".join(lines)

        # 调 AI 生成晨报
        from app.services.ai_engine import generate_morning_briefing
        briefing = await generate_morning_briefing(summary_text)

        # 推送给管理层
        from app.services.wechat_api import send_markdown_message
        async with AsyncSessionLocal() as db:
            admins_result = await db.execute(
                select(User).where(
                    User.role.in_(["admin", "manager"]),
                    User.is_active == True,
                )
            )
            admins = admins_result.scalars().all()

        for admin in admins:
            if admin.wechat_userid:
                await send_markdown_message(admin.wechat_userid, briefing)

        logger.info("   晨报已推送给 %d 位管理层", len(admins))

    except Exception as e:
        logger.error("   晨报生成失败: %s", e)
