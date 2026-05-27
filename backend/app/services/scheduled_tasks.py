"""
app/services/scheduled_tasks.py — 定时任务实现

所有定时执行的业务逻辑集中在此文件。
每个任务自行管理数据库会话（不依赖 FastAPI 的 Depends 注入）。
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, select, text

from app.database import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.daily_report import DailyReport
from app.models.project import Project, ProjectStatus
from app.models.user import User, UserRole, UserStatus
from app.services.deletion_cleanup import (
    DELETION_CLEANUP_RETENTION_DAYS,
    build_deletion_cleanup_dry_run,
    render_deletion_cleanup_dry_run_markdown,
)
from app.services.health_engine import refresh_project_health

logger = logging.getLogger("aipm.tasks")


# ═══════════════════════════════════════════════════════════════════
# 催报机制
# ═══════════════════════════════════════════════════════════════════


async def _get_unreported_users(today: Optional[date] = None) -> list:
    """查询今日未提交日报的「在岗」用户。

    过滤条件:
      - is_active = True(未被停用)
      - status = active(未请假/出差/病假)
    """
    if today is None:
        today = date.today()

    async with AsyncSessionLocal() as db:
        # 今日已提交的 user_id 集合
        reported = await db.execute(
            select(DailyReport.user_id).where(
                DailyReport.report_date == today,
                DailyReport.deleted_at.is_(None),  # V2.4 Stage 2:软删的不算"已交"
            )
        )
        reported_ids = {row[0] for row in reported.all()}

        # 在岗且未提交的用户(排除 on_leave/on_travel/sick_leave)
        all_users_result = await db.execute(
            select(User).where(
                and_(
                    User.is_active == True,
                    User.status == UserStatus.active,
                )
            )
        )
        all_users = all_users_result.scalars().all()

        return [u for u in all_users if u.id not in reported_ids]


async def auto_recover_expired_status() -> None:
    """每日 00:05 — 把 status_until < 今日 的用户自动恢复为 active。

    例:员工请假到 5/22,5/23 早上首次催报前会先被这个任务恢复成 active,
    然后正常进入催报流程。
    """
    logger.info("⏰ [00:05] 请假/出差状态到期检查")
    today = date.today()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(
                and_(
                    User.status != UserStatus.active,
                    User.status_until.is_not(None),
                    User.status_until < today,
                )
            )
        )
        expired = result.scalars().all()
        if not expired:
            logger.info("   无到期状态需要恢复")
            return

        for u in expired:
            logger.info(
                "   恢复 %s: %s(截止 %s)→ active",
                u.name,
                u.status,
                u.status_until,
            )
            u.status = UserStatus.active
            u.status_until = None
        await db.commit()
        logger.info("   已恢复 %d 人", len(expired))


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
                select(User).where(and_(User.role.in_(["admin", "manager"]), User.is_active == True))
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
        result = await db.execute(select(Project.id).where(Project.status == ProjectStatus.active))
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
                .where(DailyReport.deleted_at.is_(None))  # V2.4 Stage 2
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
    from datetime import date as _date
    from datetime import timedelta

    yesterday = _date.today() - timedelta(days=1)
    if not _is_quarter_end(yesterday):
        logger.info("⏰ 今天不是季度首日,跳过 OKR 季度汇总")
        return

    logger.info("⏰ 季度末 OKR 汇总:%s", yesterday)

    from sqlalchemy import select as _select

    from app.models.notification import NotificationChannel, NotificationTemplate
    from app.models.okr import (
        KeyResult as _KR,
    )
    from app.models.okr import (
        Objective as _Obj,
    )
    from app.models.okr import (
        OKRCycle as _Cycle,
    )
    from app.models.okr import (
        OKRCycleType as _CT,
    )
    from app.models.okr import (
        OKRStatus as _Status,
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
            objs = (await db.execute(_select(_Obj).where(_Obj.cycle_id == cycle.id))).scalars().all()
            obj_ids = [o.id for o in objs]
            krs: list[Any] = []
            if obj_ids:
                krs = list((await db.execute(_select(_KR).where(_KR.objective_id.in_(obj_ids)))).scalars().all())

            avg_obj_progress = round(sum(o.progress for o in objs) / len(objs), 1) if objs else 0
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

            # 触发 AI 复盘生成(沉淀到知识库)— 失败不影响归档
            from app.services.retro import generate_retrospective_safe

            retro_result = await generate_retrospective_safe(
                db,
                scope="okr_cycle",
                target_id=str(cycle.id),
                persist=True,
            )

            # 推送给管理层
            admins = (
                (
                    await db.execute(
                        _select(User).where(
                            User.role.in_(["admin", "manager"]),
                            User.is_active == True,
                        )
                    )
                )
                .scalars()
                .all()
            )

            # 推送内容:简短的达成总结 + 复盘报告链接提示
            push_content = summary_md
            if retro_result and retro_result.knowledge_item_id:
                push_content += (
                    f"\n\n📖 **AI 复盘报告已沉淀到知识库**\n标题:{retro_result.title}\n前往「AI 复盘库」查看完整复盘"
                )

            for admin in admins:
                await notify_safe(
                    db,
                    template=NotificationTemplate.weekly_report,  # 复用周报模板槽位
                    context={"weekly_summary": push_content},
                    user=admin,
                    channels=[
                        NotificationChannel.wechat,
                        NotificationChannel.dingtalk,
                        NotificationChannel.in_app,
                    ],
                )

            await db.commit()

        logger.info(
            "   %s 已归档,推送 %d 位管理层 (objs=%d, krs=%d, retro=%s)",
            cycle.name,
            len(admins),
            len(objs),
            len(krs),
            "yes" if retro_result and retro_result.knowledge_item_id else "no",
        )

    except Exception as e:
        logger.exception("   季度 OKR 汇总失败: %s", e)


def _is_quarter_end(d) -> bool:
    """判断某天是否是季度最后一天(3.31 / 6.30 / 9.30 / 12.31)"""
    return (d.month, d.day) in {(3, 31), (6, 30), (9, 30), (12, 31)}


# ═══════════════════════════════════════════════════════════════════
# Phase 7 历史趋势 Materialized Views 刷新
# ═══════════════════════════════════════════════════════════════════


async def refresh_analytics_materialized_views() -> None:
    """每日凌晨 — 刷新历史趋势看板使用的 PostgreSQL Materialized Views。"""
    logger.info("⏰ [00:45] 刷新历史趋势 Materialized Views")

    views = ("mv_daily_user_stats", "mv_weekly_dept_stats")

    async with AsyncSessionLocal() as db:
        for view_name in views:
            relation = await db.scalar(text("SELECT to_regclass(:view_name)"), {"view_name": view_name})
            if relation is None:
                logger.warning("   %s 不存在,跳过刷新;请先执行 alembic upgrade head", view_name)
                continue

            try:
                await db.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"))
                await db.commit()
                logger.info("   %s 刷新完成", view_name)
            except Exception as exc:
                await db.rollback()
                logger.exception("   %s 并发刷新失败,回退到普通刷新: %s", view_name, exc)
                await db.execute(text(f"REFRESH MATERIALIZED VIEW {view_name}"))
                await db.commit()
                logger.info("   %s 普通刷新完成", view_name)


# ═══════════════════════════════════════════════════════════════════
# 审计日志归档(Stage 1)
# ═══════════════════════════════════════════════════════════════════


async def archive_old_audit_logs(retention_months: int = 12) -> None:
    """每月 1 日 02:00 — 把 retention_months 个月前的 audit_logs 迁移到 audit_logs_archive。

    使用 raw SQL 在单事务里 INSERT INTO ... SELECT + DELETE,保证原子性。
    """
    logger.info("⏰ [Day1 02:00] 审计日志归档(>%d 个月)", retention_months)

    async with AsyncSessionLocal() as db:
        # 1. 先查待归档数量,日志透明
        count_result = await db.execute(
            text("SELECT count(*) FROM audit_logs WHERE created_at < (now() - (:months || ' months')::interval)"),
            {"months": str(retention_months)},
        )
        to_archive = count_result.scalar() or 0

        if to_archive == 0:
            logger.info("   无待归档记录")
            return

        logger.info("   待归档 %d 条记录", to_archive)

        # 2. 单事务里 INSERT + DELETE(原子操作)
        await db.execute(
            text(
                """
                INSERT INTO audit_logs_archive (
                    id, user_id, action, ip_address, detail,
                    created_at, updated_at, created_by, tenant_id, archived_at
                )
                SELECT id, user_id, action, ip_address, detail,
                       created_at, updated_at, created_by, tenant_id, now()
                FROM audit_logs
                WHERE created_at < (now() - (:months || ' months')::interval)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {"months": str(retention_months)},
        )

        delete_result = await db.execute(
            text("DELETE FROM audit_logs WHERE created_at < (now() - (:months || ' months')::interval)"),
            {"months": str(retention_months)},
        )

        await db.commit()
        logger.info(
            "   已归档 %d 条,主表清理 %d 条",
            to_archive,
            # CursorResult.rowcount(text() 执行的 DELETE 仍是 CursorResult);
            # mypy 推断为 Result[Any](无 rowcount),运行时实际有
            delete_result.rowcount or 0,  # type: ignore[attr-defined]
        )


# ═══════════════════════════════════════════════════════════════════
# V2.6 删除治理 dry-run
# ═══════════════════════════════════════════════════════════════════


async def run_deletion_cleanup_dry_run(retention_days: int = DELETION_CLEANUP_RETENTION_DAYS) -> None:
    """每日 01:30 — 统计过期软删对象与 FK 影响,只记录/通知,不硬删。"""
    logger.info("⏰ [01:30] 删除治理 dry-run(>%d 天)", retention_days)

    from app.models.notification import NotificationChannel, NotificationTemplate
    from app.services.notification_service import notify_safe

    async with AsyncSessionLocal() as db:
        stats = await build_deletion_cleanup_dry_run(db, retention_days=retention_days)
        markdown = render_deletion_cleanup_dry_run_markdown(stats)

        admins_result = await db.execute(select(User).where(and_(User.role == UserRole.admin, User.is_active == True)))
        admins = admins_result.scalars().all()

        if admins:
            db.add(
                AuditLog(
                    user_id=admins[0].id,
                    action="deletion_cleanup_dry_run",
                    detail=stats,
                    created_by=admins[0].id,
                    created_at=datetime.now(timezone.utc),
                )
            )
        else:
            logger.warning("   未找到启用中的 admin,跳过 audit_log 写入")

        for admin in admins:
            await notify_safe(
                db,
                template=NotificationTemplate.weekly_report,
                context={"weekly_summary": markdown},
                user=admin,
                channels=[
                    NotificationChannel.wechat,
                    NotificationChannel.dingtalk,
                    NotificationChannel.in_app,
                ],
                related_type="deletion_cleanup",
            )

        await db.commit()
        logger.info(
            "   dry-run 完成:候选 %d 条,history 批次 %d,已通知 admin %d 人",
            stats["total_candidates"],
            stats["open_history_batches"],
            len(admins),
        )
