"""
chat_tools/people.py — 人员与部门维度查询 Tools
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.models.user import User
from app.services.chat_tools import tool


def _range(days: int) -> tuple[date, date]:
    today = date.today()
    days = max(1, min(days, 90))  # 限定 1-90 天
    return today - timedelta(days=days - 1), today


@tool(description="表现最好的 N 个员工(高分 + 高提交率综合)")
async def top_performers(
    db: AsyncSession,
    days: int = 7,
    limit: int = 5,
    department: str = "",
) -> dict:
    """
    Args:
        days: 评估窗口天数,默认 7
        limit: 返回前 N 名
        department: 限定部门,空=全部
    """
    start, end = _range(days)
    expected_days = (end - start).days + 1

    stmt = (
        select(
            User.id,
            User.name,
            User.department,
            func.avg(DailyReport.ai_score).label("avg_score"),
            func.count(DailyReport.id).label("submitted_days"),
        )
        .join(DailyReport, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.ai_score.isnot(None),
                DailyReport.deleted_at.is_(None),  # V2.4 Stage 3 C1
            )
        )
        .group_by(User.id, User.name, User.department)
    )
    if department:
        stmt = stmt.where(User.department == department)

    # 综合分 = 平均分 * (提交率 0.5 + 0.5)  → 提交率越高加成越大,提交率 100% 时不打折
    rows = (await db.execute(stmt)).all()
    ranked = []
    for r in rows:
        avg = float(r.avg_score) if r.avg_score else 0
        submit_rate = (r.submitted_days or 0) / expected_days
        composite = avg * (0.5 + 0.5 * min(submit_rate, 1.0))
        ranked.append(
            {
                "user": r.name,
                "department": r.department,
                "avg_score": round(avg, 1),
                "submit_rate": round(submit_rate, 2),
                "composite_score": round(composite, 1),
                "submitted_days": int(r.submitted_days),
            }
        )
    ranked.sort(key=lambda x: x["composite_score"], reverse=True)
    return {
        "window_days": expected_days,
        "ranking": ranked[:limit],
    }


@tool(description="表现需要关注的 N 个员工(低分 / 缺勤多 / 卡点持续)")
async def bottom_performers(
    db: AsyncSession,
    days: int = 7,
    limit: int = 5,
    department: str = "",
) -> dict:
    """
    Args:
        days: 评估窗口天数,默认 7
        limit: 返回需要关注的前 N 名
        department: 限定部门,空=全部
    """
    start, end = _range(days)
    expected_days = (end - start).days + 1

    stmt = (
        select(
            User.id,
            User.name,
            User.department,
            func.avg(DailyReport.ai_score).label("avg_score"),
            func.count(DailyReport.id).label("submitted_days"),
        )
        .outerjoin(
            DailyReport,
            and_(
                DailyReport.user_id == User.id,
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
            ),
        )
        .where(User.is_active.is_(True))
        .group_by(User.id, User.name, User.department)
    )
    if department:
        stmt = stmt.where(User.department == department)

    rows = (await db.execute(stmt)).all()
    flagged = []
    for r in rows:
        avg = float(r.avg_score) if r.avg_score else 0
        submitted = int(r.submitted_days or 0)
        submit_rate = submitted / expected_days
        # 风险综合分(越低越糟)
        composite = avg * (0.3 + 0.7 * submit_rate)
        flagged.append(
            {
                "user": r.name,
                "department": r.department,
                "avg_score": round(avg, 1) if avg else None,
                "submit_rate": round(submit_rate, 2),
                "submitted_days": submitted,
                "missed_days": expected_days - submitted,
                "risk_score": round(composite, 1),
            }
        )
    # 风险分升序,提交率低、分数低的排前
    flagged.sort(key=lambda x: (x["risk_score"], x["submit_rate"]))
    return {
        "window_days": expected_days,
        "needs_attention": flagged[:limit],
    }


@tool(description="员工档案:查询某员工近期表现(评分趋势 + 提交率 + 主要卡点)")
async def user_snapshot(
    db: AsyncSession,
    user_name: str,
    days: int = 14,
) -> dict:
    """
    Args:
        user_name: 员工姓名
        days: 时间窗口,默认 14
    """
    if not user_name:
        return {"error": "user_name 不能为空"}

    user = (await db.execute(select(User).where(User.name == user_name).limit(1))).scalar_one_or_none()
    if not user:
        return {"error": f"未找到员工『{user_name}』"}

    start, end = _range(days)
    stmt = (
        select(
            DailyReport.report_date,
            DailyReport.ai_score,
            DailyReport.pass_check,
            DailyReport.parsed_content,
        )
        .where(
            and_(
                DailyReport.user_id == user.id,
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
            )
        )
        .order_by(DailyReport.report_date)
    )
    rows = (await db.execute(stmt)).all()
    trend = [
        {
            "date": r.report_date.isoformat(),
            "score": r.ai_score,
            "passed": bool(r.pass_check),
            "progress": (r.parsed_content or {}).get("progress"),
            "blocker": (r.parsed_content or {}).get("blocker") or None,
        }
        for r in rows
    ]
    avg = sum(t["score"] or 0 for t in trend) / max(len([t for t in trend if t["score"]]), 1)
    blockers = [t["blocker"] for t in trend if t["blocker"] and t["blocker"] != "无"]

    return {
        "user": user.name,
        "department": user.department,
        "role": user.role.value,
        "job_title": user.job_title,
        "window_days": days,
        "submitted_days": len(trend),
        "missed_days": days - len(trend),
        "avg_score": round(avg, 1) if avg else None,
        "trend": trend,
        "recent_blockers": list(dict.fromkeys(blockers))[:5],  # 去重保前 5
    }
