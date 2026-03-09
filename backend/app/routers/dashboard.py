"""
app/routers/dashboard.py — 管理看板核心数据 API

对应管理层每日必看的"晨报视图"，是 Excel 所有行数据的可视化升级版。
需要 manager 或 admin 角色才可访问。
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, and_, Integer
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.daily_report import DailyReport
from app.models.risk_alert import RiskAlert
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

# 管理层才能访问
_mgr_or_admin = require_role(UserRole.manager, UserRole.admin)


@router.get("/morning-briefing")
async def get_morning_briefing(
    report_date: date = Query(default=None, description="查询日期，不传则为昨日"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr_or_admin),
):
    """
    晨报总览接口（对应 Excel 全部行数据的汇总仪表盘）。

    返回：
    - 汇报人数 / 通过率 / 平均分
    - 未通过成员列表（含 reject_reason）
    - 未汇报成员列表（对比 users 表）
    - 所有预警摘要（management_alert）
    - 各成员详细摘要行
    """
    # 默认查询昨日（因为晨报看的是昨天的汇报）
    if report_date is None:
        report_date = date.today() - timedelta(days=1)

    # 拉取当日所有日报
    stmt = (
        select(DailyReport, User.name, User.department)
        .join(User, DailyReport.user_id == User.id)
        .where(DailyReport.report_date == report_date)
        .order_by(DailyReport.ai_score.desc().nulls_last())
    )
    rows = (await db.execute(stmt)).all()

    # 所有员工（用于识别未汇报人员）
    all_users_result = await db.execute(select(User))
    all_users = all_users_result.scalars().all()
    reported_user_ids = {str(r.DailyReport.user_id) for r in rows}
    missing_members = [
        {"name": u.name, "department": u.department}
        for u in all_users
        if str(u.id) not in reported_user_ids
    ]

    passed = [r for r in rows if r.DailyReport.pass_check]
    not_passed = [r for r in rows if not r.DailyReport.pass_check]
    alerts = [r.DailyReport.management_alert for r in rows if r.DailyReport.management_alert]

    return {
        "report_date": report_date,
        "stats": {
            "total_reports": len(rows),
            "pass_count": len(passed),
            "fail_count": len(not_passed),
            "missing_count": len(missing_members),
            "pass_rate": round(len(passed) / max(len(rows), 1) * 100, 1),
            "avg_score": round(
                sum(r.DailyReport.ai_score or 0 for r in rows) / max(len(rows), 1), 1
            ),
        },
        "not_passed_members": [
            {
                "name": r.name,
                "department": r.department,
                "reject_reason": r.DailyReport.reject_reason,
                "ai_score": r.DailyReport.ai_score,
            }
            for r in not_passed
        ],
        "missing_members": missing_members,
        "management_alerts": alerts,
        "reports": [
            {
                "member": r.name,
                "department": r.department,
                # 对应 Excel 各列
                "tasks": (r.DailyReport.parsed_content or {}).get("tasks"),
                "progress": (r.DailyReport.parsed_content or {}).get("progress"),
                "blocker": (r.DailyReport.parsed_content or {}).get("blocker"),
                "next_step": (r.DailyReport.parsed_content or {}).get("next_step"),
                "eta": (r.DailyReport.parsed_content or {}).get("eta"),
                "git_version": (r.DailyReport.parsed_content or {}).get("git_version"),
                "reviewer": (r.DailyReport.parsed_content or {}).get("reviewer"),
                "ai_score": r.DailyReport.ai_score,
                "ai_comment": r.DailyReport.ai_comment,
                "pass_check": r.DailyReport.pass_check,
            }
            for r in rows
        ],
    }


@router.get("/risk-alerts")
async def get_risk_alerts(
    status: Optional[str] = Query(default="unresolved"),
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr_or_admin),
):
    """
    卡点预警墙（按未解决天数降序排列，最严重的排最前）
    对应 Excel 中所有 '核心卡点' 非空行的聚合视图。
    """
    stmt = (
        select(RiskAlert, User.name, User.department)
        .join(User, RiskAlert.user_id == User.id)
        .where(RiskAlert.status == status)
        .order_by(RiskAlert.days_unresolved.desc())
    )
    rows = (await db.execute(stmt)).all()

    return [
        {
            "alert_id": str(r.RiskAlert.id),
            "member": r.name,
            "department": r.department,
            "type": r.RiskAlert.alert_type,
            "description": r.RiskAlert.description,
            "days_unresolved": r.RiskAlert.days_unresolved,
            "status": r.RiskAlert.status,
            "created_at": r.RiskAlert.created_at.isoformat() if r.RiskAlert.created_at else None,
        }
        for r in rows
    ]


@router.get("/token-usage")
async def get_token_usage(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(UserRole.admin)),
):
    """今日 Token 消耗统计（仅 admin 可见）"""
    from app.services.token_guard import get_daily_usage
    from app.config import settings

    used = await get_daily_usage(db)
    return {
        "date": date.today(),
        "used_tokens": used,
        "limit_tokens": settings.daily_token_limit,
        "usage_pct": round(used / settings.daily_token_limit * 100, 1),
        "is_throttled": used >= settings.daily_token_limit,
    }


@router.get("/weekly-stats")
async def get_weekly_stats(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(UserRole.admin)),
):
    """近 7 天日报统计（逐日提交数、均分、通过率）"""
    end = date.today()
    start = end - timedelta(days=6)

    # 每日统计
    stmt = (
        select(
            DailyReport.report_date,
            func.count().label("count"),
            func.coalesce(func.avg(DailyReport.ai_score), 0).label("avg_score"),
            func.count().filter(DailyReport.pass_check == True).label("pass_count"),
        )
        .where(and_(
            DailyReport.report_date >= start,
            DailyReport.report_date <= end,
        ))
        .group_by(DailyReport.report_date)
        .order_by(DailyReport.report_date)
    )
    rows = (await db.execute(stmt)).all()

    # 总人数
    total_users_result = await db.execute(
        select(func.count()).select_from(User).where(User.is_active == True)
    )
    total_users = total_users_result.scalar() or 0

    # 填充无数据的日期
    daily = {}
    for r in rows:
        daily[str(r.report_date)] = {
            "date": str(r.report_date),
            "count": r.count,
            "avg_score": round(float(r.avg_score), 1),
            "pass_count": r.pass_count or 0,
            "pass_rate": round((r.pass_count or 0) / max(r.count, 1) * 100, 1),
        }

    result = []
    for i in range(7):
        d = str(start + timedelta(days=i))
        result.append(daily.get(d, {
            "date": d,
            "count": 0,
            "avg_score": 0,
            "pass_count": 0,
            "pass_rate": 0,
        }))

    return {
        "total_users": total_users,
        "days": result,
    }

