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
        from app.models.notification import NotificationChannel, NotificationTemplate
        from app.services.notification_service import notify_safe

        async with AsyncSessionLocal() as db:
            for user in unreported:
                await notify_safe(
                    db,
                    template=NotificationTemplate.reminder_soft,
                    context={"name": user.name},
                    user=user,
                    channels=[
                        NotificationChannel.wechat,
                        NotificationChannel.dingtalk,
                        NotificationChannel.in_app,
                    ],
                )
            await db.commit()
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
        from app.models.notification import NotificationChannel, NotificationTemplate
        from app.services.notification_service import notify_safe

        async with AsyncSessionLocal() as db:
            for user in unreported:
                await notify_safe(
                    db,
                    template=NotificationTemplate.reminder_hard,
                    context={"name": user.name},
                    user=user,
                    channels=[
                        NotificationChannel.wechat,
                        NotificationChannel.dingtalk,
                        NotificationChannel.in_app,
                    ],
                )
            await db.commit()
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
        from app.models.notification import NotificationChannel, NotificationTemplate
        from app.services.notification_service import notify_safe

        absent_list = "\n".join(f"- {n}" for n in names)
        
        async with AsyncSessionLocal() as db:
            admins_result = await db.execute(
                select(User).where(
                    and_(User.role.in_(["admin", "manager"]), User.is_active == True)
                )
            )
            admins = admins_result.scalars().all()

            for admin in admins:
                await notify_safe(
                    db,
                    template=NotificationTemplate.reminder_missed,
                    context={"date": date.today().isoformat(), "missing_list": absent_list},
                    user=admin,
                    channels=[
                        NotificationChannel.wechat_bot,
                        NotificationChannel.dingtalk_bot,
                        NotificationChannel.in_app,
                    ],
                )
            await db.commit()

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


# ═══════════════════════════════════════════════════════════════════
# 周一 09:00 — 上周管理周报 AI 生成 + 推送
# ═══════════════════════════════════════════════════════════════════

async def run_weekly_report() -> None:
    """周一 09:00 自动生成上周管理周报 → 推送企微/钉钉给 admin/manager"""
    logger.info("⏰ [周一 09:00] 周报 AI 生成")

    try:
        from app.models.notification import NotificationChannel, NotificationTemplate
        from app.services.chat_tools.weekly_report import generate_weekly_report
        from app.services.notification_service import notify_safe

        async with AsyncSessionLocal() as db:
            result = await generate_weekly_report(db, scope="last_week")

            md = result.get("markdown") or "(本周无数据,跳过周报)"
            week = result.get("week_range", {})
            week_label = f"{week.get('start', '?')} → {week.get('end', '?')}"

            # 拉管理层(admin + manager)
            admins_result = await db.execute(
                select(User).where(
                    User.role.in_(["admin", "manager"]),
                    User.is_active == True,
                )
            )
            admins = admins_result.scalars().all()

            for admin in admins:
                await notify_safe(
                    db,
                    template=NotificationTemplate.weekly_report,
                    context={"weekly_summary": f"**周期: {week_label}**\n\n{md}"},
                    user=admin,
                    channels=[
                        NotificationChannel.wechat,
                        NotificationChannel.dingtalk,
                        NotificationChannel.in_app,
                    ],
                )
            await db.commit()

        logger.info(
            "   周报已生成并推送 %d 位管理层 (range=%s, reports=%d, risks=%d)",
            len(admins),
            week_label,
            result.get("stats", {}).get("report_count", 0),
            result.get("stats", {}).get("risk_count", 0),
        )

    except Exception as e:
        logger.error("   周报生成失败: %s", e)


# ═══════════════════════════════════════════════════════════════════
# 季度 OKR 汇总 + 自动归档
# ═══════════════════════════════════════════════════════════════════

async def run_quarterly_okr_summary() -> None:
    """
    每月 1 日 09:30 检查:如果昨天是季度末(3.31 / 6.30 / 9.30 / 12.31),
    则把刚结束的 active 季度 cycle 转为 completed,生成达成摘要并推送管理层。
    """
    from datetime import date as _date, timedelta

    yesterday = _date.today() - timedelta(days=1)
    if not _is_quarter_end(yesterday):
        logger.info("⏰ 今天不是季度首日,跳过 OKR 季度汇总")
        return

    logger.info("⏰ 季度末 OKR 汇总:%s", yesterday)

    from sqlalchemy import select as _select
    from app.models.notification import NotificationChannel, NotificationTemplate
    from app.models.okr import (
        KeyResult as _KR, OKRCycle as _Cycle,
        OKRCycleType as _CT, OKRStatus as _Status, Objective as _Obj,
    )
    from app.services.notification_service import notify_safe

    try:
        async with AsyncSessionLocal() as db:
            # 找上一个季度的 active cycle
            cycle = (
                await db.execute(
                    _select(_Cycle)
                    .where(
                        _Cycle.cycle_type == _CT.quarterly,
                        _Cycle.status == _Status.active,
                        _Cycle.end_date <= yesterday,
                    )
                    .order_by(_Cycle.end_date.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not cycle:
                logger.info("   未找到需要归档的季度 cycle")
                return

            # 聚合该 cycle 的统计
            objs = (
                await db.execute(
                    _select(_Obj).where(_Obj.cycle_id == cycle.id)
                )
            ).scalars().all()
            obj_ids = [o.id for o in objs]
            krs = []
            if obj_ids:
                krs = (
                    await db.execute(
                        _select(_KR).where(_KR.objective_id.in_(obj_ids))
                    )
                ).scalars().all()

            avg_obj_progress = (
                round(sum(o.progress for o in objs) / len(objs), 1) if objs else 0
            )
            kr_progresses = [k.progress for k in krs]
            achieved = sum(1 for p in kr_progresses if p >= 70)
            on_track = sum(1 for p in kr_progresses if 40 <= p < 70)
            behind = sum(1 for p in kr_progresses if p < 40)

            summary_md = (
                f"### 📊 {cycle.name} OKR 达成总结\n\n"
                f"**周期**: {cycle.start_date} → {cycle.end_date}\n\n"
                f"- 目标数: **{len(objs)}**\n"
                f"- 关键结果数: **{len(krs)}**\n"
                f"- 平均 O 进度: **{avg_obj_progress}%**\n\n"
                f"**KR 达成分布**:\n"
                f"- ✅ 已达成(≥70%): {achieved}\n"
                f"- 🟡 进行中(40-70%): {on_track}\n"
                f"- 🔴 滞后(<40%): {behind}\n"
            )

            # 归档 cycle
            cycle.status = _Status.completed

            # 推送给管理层
            admins = (
                await db.execute(
                    _select(User).where(
                        User.role.in_(["admin", "manager"]),
                        User.is_active == True,
                    )
                )
            ).scalars().all()
            for admin in admins:
                await notify_safe(
                    db,
                    template=NotificationTemplate.weekly_report,  # 复用周报模板槽位
                    context={"weekly_summary": summary_md},
                    user=admin,
                    channels=[
                        NotificationChannel.wechat,
                        NotificationChannel.dingtalk,
                        NotificationChannel.in_app,
                    ],
                )

            await db.commit()

        logger.info(
            "   %s 已归档,推送 %d 位管理层 (objs=%d, krs=%d)",
            cycle.name, len(admins), len(objs), len(krs),
        )

    except Exception as e:
        logger.exception("   季度 OKR 汇总失败: %s", e)


def _is_quarter_end(d) -> bool:
    """判断某天是否是季度最后一天(3.31 / 6.30 / 9.30 / 12.31)"""
    return (d.month, d.day) in {(3, 31), (6, 30), (9, 30), (12, 31)}
