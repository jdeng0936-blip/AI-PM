"""
chat_tools/reports.py — 日报相关查询 Tools

提供给 LLM 调用的报表查询能力。所有 SQL 必读不写,绝不暴露给 LLM
任意的表名/字段名 — 一律走预定义聚合。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.models.user import User
from app.services.chat_tools import tool

# ────────────────────────────────────────────────────────────────
# 辅助:把自然语言时间段解析成 (start_date, end_date)
# ────────────────────────────────────────────────────────────────


def _resolve_range(date_range: Optional[str], days: int) -> tuple[date, date]:
    """
    date_range 枚举: today / yesterday / this_week / last_week / last_7_days / last_30_days
    若给定 days 优先生效(向前 N 天,包含今天)。
    """
    today = date.today()
    if days and days > 0:
        return today - timedelta(days=days - 1), today

    if not date_range:
        return today - timedelta(days=6), today  # 默认近 7 天

    dr = date_range.lower().strip()
    if dr == "today":
        return today, today
    if dr == "yesterday":
        d = today - timedelta(days=1)
        return d, d
    if dr in ("this_week", "本周"):
        start = today - timedelta(days=today.weekday())
        return start, today
    if dr in ("last_week", "上周"):
        this_week_start = today - timedelta(days=today.weekday())
        last_week_start = this_week_start - timedelta(days=7)
        return last_week_start, this_week_start - timedelta(days=1)
    if dr == "last_7_days":
        return today - timedelta(days=6), today
    if dr == "last_30_days":
        return today - timedelta(days=29), today
    # 兜底:近 7 天
    return today - timedelta(days=6), today


# ────────────────────────────────────────────────────────────────
# Tools
# ────────────────────────────────────────────────────────────────


@tool(description="按时间段查询日报,可按部门/用户过滤,返回汇总统计 + 前 N 条明细")
async def query_reports(
    db: AsyncSession,
    date_range: str = "last_7_days",
    days: int = 0,
    department: str = "",
    user_name: str = "",
    only_passed: bool = False,
    limit: int = 20,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        date_range: 时间段枚举(today/yesterday/this_week/last_week/last_7_days/last_30_days)
        days: 向前 N 天(如填 14 表示近 14 天),传 0 表示用 date_range
        department: 限定某部门,如「采购部」「软件研发部」,空字符串=全部
        user_name: 限定某员工姓名,空字符串=全部
        only_passed: 是否只统计质检通过的日报
        limit: 返回明细条数上限,默认 20
    """
    start, end = _resolve_range(date_range, days)

    stmt = (
        select(
            DailyReport.id,
            DailyReport.report_date,
            DailyReport.ai_score,
            DailyReport.pass_check,
            DailyReport.parsed_content,
            User.name,
            User.department,
        )
        .join(User, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.deleted_at.is_(None),
                DailyReport.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
            )
        )
    )
    if department:
        stmt = stmt.where(User.department == department)
    if user_name:
        stmt = stmt.where(User.name == user_name)
    if only_passed:
        stmt = stmt.where(DailyReport.pass_check.is_(True))

    stmt = stmt.order_by(desc(DailyReport.report_date), desc(DailyReport.ai_score)).limit(limit)
    rows = (await db.execute(stmt)).all()

    items = []
    for r in rows:
        pc = r.parsed_content or {}
        items.append(
            {
                "user": r.name,
                "department": r.department,
                "date": r.report_date.isoformat(),
                "score": r.ai_score,
                "passed": bool(r.pass_check),
                "progress": pc.get("progress"),
                "tasks_brief": (pc.get("tasks") or "")[:60],
                "blocker": (pc.get("blocker") or "")[:60],
            }
        )

    # 总数 + 均分(独立 query 避免被 limit 影响)
    agg_stmt = (
        select(
            func.count(DailyReport.id).label("cnt"),
            func.avg(DailyReport.ai_score).label("avg_score"),
        )
        .join(User, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.deleted_at.is_(None),
                DailyReport.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
            )
        )
    )
    if department:
        agg_stmt = agg_stmt.where(User.department == department)
    if user_name:
        agg_stmt = agg_stmt.where(User.name == user_name)
    agg = (await db.execute(agg_stmt)).one()
    avg_score = float(agg.avg_score) if agg.avg_score is not None else None

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "filter": {"department": department or None, "user_name": user_name or None},
        "total_count": int(agg.cnt or 0),
        "avg_score": round(avg_score, 1) if avg_score is not None else None,
        "items": items,
    }


@tool(description="统计某时间段内『延期/有卡点』的人员排行,按卡点天数降序")
async def count_delayed(
    db: AsyncSession,
    date_range: str = "this_week",
    days: int = 0,
    limit: int = 10,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        date_range: 时间段(参见 query_reports)
        days: 向前 N 天(优先于 date_range)
        limit: 返回前 N 人,默认 10
    """
    start, end = _resolve_range(date_range, days)

    # 用 parsed_content->>'blocker' 非空判定有卡点
    blocker_text = DailyReport.parsed_content.op("->>")("blocker")

    stmt = (
        select(
            User.name,
            User.department,
            func.count(DailyReport.id).label("blocker_days"),
            func.avg(DailyReport.ai_score).label("avg_score"),
        )
        .join(User, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.deleted_at.is_(None),
                DailyReport.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
                blocker_text.isnot(None),
                blocker_text != "",
                blocker_text != "无",
            )
        )
        .group_by(User.id, User.name, User.department)
        .order_by(desc("blocker_days"))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "ranking": [
            {
                "user": r.name,
                "department": r.department,
                "blocker_days": int(r.blocker_days),
                "avg_score": round(float(r.avg_score), 1) if r.avg_score else None,
            }
            for r in rows
        ],
    }


@tool(description="评分排行榜,按时间段内平均分降序,可选取最高/最低")
async def score_ranking(
    db: AsyncSession,
    date_range: str = "last_7_days",
    days: int = 0,
    department: str = "",
    direction: str = "top",
    limit: int = 10,
    tenant_id: str = "default",
) -> dict:
    """
    Args:
        date_range: 时间段
        days: 向前 N 天
        department: 限定部门,空=全部
        direction: top(最高分) | bottom(最低分)
        limit: 返回 N 人
    """
    start, end = _resolve_range(date_range, days)

    stmt = (
        select(
            User.name,
            User.department,
            func.avg(DailyReport.ai_score).label("avg_score"),
            func.count(DailyReport.id).label("report_count"),
        )
        .join(User, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.ai_score.isnot(None),
                DailyReport.deleted_at.is_(None),
                DailyReport.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
            )
        )
        .group_by(User.id, User.name, User.department)
    )
    if department:
        stmt = stmt.where(User.department == department)

    if direction.lower() == "bottom":
        stmt = stmt.order_by("avg_score")
    else:
        stmt = stmt.order_by(desc("avg_score"))
    stmt = stmt.limit(limit)

    rows = (await db.execute(stmt)).all()
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "direction": direction.lower(),
        "ranking": [
            {
                "user": r.name,
                "department": r.department,
                "avg_score": round(float(r.avg_score), 1) if r.avg_score else None,
                "report_count": int(r.report_count),
            }
            for r in rows
        ],
    }


@tool(description="按部门聚合的平均评分 + 提交率(每个部门一行)")
async def avg_score_by_department(
    db: AsyncSession,
    date_range: str = "last_7_days",
    days: int = 0,
) -> dict:
    """
    Args:
        date_range: 时间段
        days: 向前 N 天
    """
    start, end = _resolve_range(date_range, days)

    stmt = (
        select(
            User.department,
            func.avg(DailyReport.ai_score).label("avg_score"),
            func.count(DailyReport.id).label("report_count"),
        )
        .join(User, DailyReport.user_id == User.id)
        .where(and_(DailyReport.report_date >= start, DailyReport.report_date <= end))
        .group_by(User.department)
        .order_by(desc("avg_score"))
    )
    rows = (await db.execute(stmt)).all()
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "departments": [
            {
                "department": r.department or "(未分组)",
                "avg_score": round(float(r.avg_score), 1) if r.avg_score else None,
                "report_count": int(r.report_count),
            }
            for r in rows
        ],
    }


@tool(description="今日未提交日报的员工名单(管理层关心『谁没交』)")
async def list_missing_today(db: AsyncSession) -> dict:
    """
    Args:
        (no args)
    """
    today = date.today()
    submitted_stmt = select(DailyReport.user_id).where(
        DailyReport.report_date == today,
        DailyReport.deleted_at.is_(None),  # V2.4 Stage 3 C1
    )
    submitted_ids = {row[0] for row in (await db.execute(submitted_stmt)).all()}

    users_stmt = select(User).where(User.is_active.is_(True))
    users = (await db.execute(users_stmt)).scalars().all()

    missing = [
        {"user": u.name, "department": u.department, "role": u.role.value} for u in users if u.id not in submitted_ids
    ]
    return {
        "date": today.isoformat(),
        "total_users": len(users),
        "submitted_count": len(users) - len(missing),
        "missing_count": len(missing),
        "missing": missing,
    }
