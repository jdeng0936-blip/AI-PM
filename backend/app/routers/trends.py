"""
app/routers/trends.py — 趋势统计 API

个人评分趋势、部门对比、自动周报生成。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role, get_current_user
from app.models.daily_report import DailyReport
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/trends", tags=["Trends & Analytics"])


@router.get("/my-scores")
async def my_score_trend(
    days: int = Query(default=30, ge=7, le=90, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    当前登录员工近 N 天的评分趋势。
    返回逐日评分数据 + 统计摘要。
    """
    since = date.today() - timedelta(days=days)

    stmt = (
        select(
            DailyReport.report_date,
            DailyReport.ai_score,
            DailyReport.pass_check,
        )
        .where(and_(
            DailyReport.user_id == current_user.id,
            DailyReport.report_date >= since,
        ))
        .order_by(DailyReport.report_date)
    )
    rows = (await db.execute(stmt)).all()

    scores = [r.ai_score for r in rows if r.ai_score is not None]
    passed = sum(1 for r in rows if r.pass_check)

    return {
        "user_name": current_user.name,
        "department": current_user.department,
        "period_days": days,
        "summary": {
            "total_reports": len(rows),
            "avg_score": round(sum(scores) / max(len(scores), 1), 1),
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "pass_rate": round(passed / max(len(rows), 1) * 100, 1),
        },
        "daily": [
            {
                "date": str(r.report_date),
                "score": r.ai_score,
                "pass_check": r.pass_check,
            }
            for r in rows
        ],
    }


@router.get("/department-stats")
async def department_stats(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """
    各部门平均评分 + 提交率对比。
    """
    since = date.today() - timedelta(days=days)

    # 按部门聚合
    stmt = (
        select(
            User.department,
            func.count(DailyReport.id).label("report_count"),
            func.coalesce(func.avg(DailyReport.ai_score), 0).label("avg_score"),
            func.count().filter(DailyReport.pass_check == True).label("pass_count"),
        )
        .join(User, DailyReport.user_id == User.id)
        .where(DailyReport.report_date >= since)
        .group_by(User.department)
        .order_by(func.avg(DailyReport.ai_score).desc())
    )
    rows = (await db.execute(stmt)).all()

    # 每个部门的活跃人数
    dept_users = await db.execute(
        select(User.department, func.count(User.id))
        .where(User.is_active == True)
        .group_by(User.department)
    )
    dept_user_count = {r[0]: r[1] for r in dept_users.all()}

    return {
        "period_days": days,
        "departments": [
            {
                "department": r.department,
                "total_members": dept_user_count.get(r.department, 0),
                "report_count": r.report_count,
                "avg_score": round(float(r.avg_score), 1),
                "pass_count": r.pass_count,
                "pass_rate": round(r.pass_count / max(r.report_count, 1) * 100, 1),
            }
            for r in rows
        ],
    }


@router.get("/weekly-report")
async def generate_weekly_report(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(UserRole.admin)),
):
    """
    AI 自动生成本周周报。
    汇总全员日报关键信息，调用 LLM 生成 Markdown 格式周报。
    """
    end = date.today()
    start = end - timedelta(days=6)

    stmt = (
        select(DailyReport, User.name, User.department)
        .join(User, DailyReport.user_id == User.id)
        .where(and_(
            DailyReport.report_date >= start,
            DailyReport.report_date <= end,
        ))
        .order_by(DailyReport.report_date, User.department)
    )
    rows = (await db.execute(stmt)).all()

    if not rows:
        return {"week": f"{start} ~ {end}", "report": "本周无日报数据。"}

    # 构造汇总文本
    lines = []
    for r in rows:
        pc = r.DailyReport.parsed_content or {}
        lines.append(
            f"[{r.DailyReport.report_date}] {r.name}({r.department}) "
            f"评分{r.DailyReport.ai_score} | "
            f"任务: {pc.get('tasks', '无')[:50]} | "
            f"卡点: {pc.get('blocker', '无')}"
        )

    try:
        from app.services.ai_engine import generate_morning_briefing
        # 复用晨报生成函数，prompt 足够通用
        ai_report = await generate_morning_briefing(
            f"以下是 {start} 至 {end} 一整周的全员日报汇总，"
            f"请生成管理层周报（Markdown 格式）：\n\n" + "\n".join(lines)
        )
    except Exception as e:
        ai_report = f"AI 生成失败: {str(e)[:200]}\n\n原始数据已保留。"

    return {
        "week": f"{start} ~ {end}",
        "total_reports": len(rows),
        "report": ai_report,
    }
