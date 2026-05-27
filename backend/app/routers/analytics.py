"""
app/routers/analytics.py — Phase 7 历史趋势分析 API

面向管理看板的数据接口。用户/部门趋势优先读取 Phase 7 预聚合
Materialized Views;项目健康和 Sprint 效率基于现有业务表按需聚合。
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Numeric, and_, cast, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.daily_report import DailyReport
from app.models.project import Project
from app.models.sprint import Sprint, SprintStatus
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

_mgr_or_admin = require_role(UserRole.manager, UserRole.admin)


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _round_float(value: Any, ndigits: int = 1) -> float:
    converted = _float_or_none(value)
    return round(converted, ndigits) if converted is not None else 0.0


async def _get_target_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "用户不存在")
    return user


@router.get("/user-trend")
async def user_trend(
    user_id: uuid.UUID | None = Query(default=None, description="目标用户 ID;不传则查当前用户"),
    days: int = Query(default=30, ge=7, le=365, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """个人近 N 天评分趋势。员工只能查看自己;manager/admin 可指定任意用户。"""
    target_user_id = user_id or current_user.id
    if current_user.role == UserRole.employee and target_user_id != current_user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "员工只能查看自己的趋势数据")

    target_user = await _get_target_user(db, target_user_id)
    since = date.today() - timedelta(days=days - 1)

    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT
                    report_date,
                    report_count,
                    avg_score,
                    max_score,
                    min_score,
                    pass_count,
                    pass_check,
                    submitted,
                    last_submitted_at,
                    submit_delay_minutes
                FROM mv_daily_user_stats
                WHERE user_id = :user_id
                  AND report_date >= :since
                ORDER BY report_date
                """
                ),
                {"user_id": target_user_id, "since": since},
            )
        )
        .mappings()
        .all()
    )

    scores = [_float_or_none(row["avg_score"]) for row in rows if row["avg_score"] is not None]
    pass_count = sum(int(row["pass_count"] or 0) for row in rows)
    report_count = sum(int(row["report_count"] or 0) for row in rows)

    return {
        "user_id": str(target_user.id),
        "user_name": target_user.name,
        "department": target_user.department,
        "period_days": days,
        "summary": {
            "report_days": len(rows),
            "total_reports": report_count,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "pass_rate": round(pass_count / max(report_count, 1) * 100, 1),
        },
        "daily": [
            {
                "date": row["report_date"].isoformat(),
                "report_count": row["report_count"],
                "avg_score": _round_float(row["avg_score"]),
                "max_score": row["max_score"],
                "min_score": row["min_score"],
                "pass_check": row["pass_check"],
                "submitted": row["submitted"],
                "last_submitted_at": row["last_submitted_at"].isoformat() if row["last_submitted_at"] else None,
                "submit_delay_minutes": _float_or_none(row["submit_delay_minutes"]),
            }
            for row in rows
        ],
    }


@router.get("/department-compare")
async def department_compare(
    period: str = Query(default="week", description="当前仅支持 week"),
    weeks: int = Query(default=8, ge=1, le=52, description="最近 N 周"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
):
    """部门周维度对比:提交人数覆盖率、平均分、质检通过率。"""
    if period != "week":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "period 当前仅支持 week")

    since = date.today() - timedelta(weeks=weeks)
    rows = (
        (
            await db.execute(
                text(
                    """
                SELECT
                    department,
                    week_start,
                    total_reports,
                    active_users,
                    total_users,
                    avg_score,
                    pass_count,
                    pass_rate,
                    submitter_rate
                FROM mv_weekly_dept_stats
                WHERE week_start >= :since
                ORDER BY week_start, department
                """
                ),
                {"since": since},
            )
        )
        .mappings()
        .all()
    )

    departments: dict[str, dict[str, Any]] = {}
    weeks_seen: set[str] = set()
    for row in rows:
        week_start = row["week_start"].isoformat()
        weeks_seen.add(week_start)
        dept = departments.setdefault(
            row["department"],
            {
                "department": row["department"],
                "total_users": row["total_users"],
                "latest_avg_score": 0.0,
                "latest_pass_rate": 0.0,
                "latest_submitter_rate": 0.0,
                "trend": [],
            },
        )
        point = {
            "week_start": week_start,
            "total_reports": row["total_reports"],
            "active_users": row["active_users"],
            "total_users": row["total_users"],
            "avg_score": _round_float(row["avg_score"]),
            "pass_count": row["pass_count"],
            "pass_rate": _round_float(row["pass_rate"]),
            "submitter_rate": _round_float(row["submitter_rate"]),
        }
        dept["trend"].append(point)
        dept["total_users"] = row["total_users"]
        dept["latest_avg_score"] = point["avg_score"]
        dept["latest_pass_rate"] = point["pass_rate"]
        dept["latest_submitter_rate"] = point["submitter_rate"]

    return {
        "period": period,
        "weeks": sorted(weeks_seen),
        "departments": sorted(departments.values(), key=lambda item: item["latest_avg_score"], reverse=True),
    }


@router.get("/project-health")
async def project_health(
    project_id: uuid.UUID = Query(..., description="项目 ID"),
    days: int = Query(default=90, ge=7, le=365, description="查询天数"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
):
    """项目健康趋势:基于关联日报按日聚合评分、通过率和进度。"""
    project = await db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在")

    since = date.today() - timedelta(days=days - 1)
    rows = (
        await db.execute(
            select(
                DailyReport.report_date,
                func.count(DailyReport.id).label("report_count"),
                func.coalesce(func.avg(DailyReport.ai_score), 0).label("avg_score"),
                func.count().filter(DailyReport.pass_check == True).label("pass_count"),
                func.coalesce(
                    func.avg(cast(func.nullif(DailyReport.parsed_content["progress"].astext, ""), Numeric)),
                    0,
                ).label("avg_progress"),
            )
            .where(
                and_(
                    DailyReport.project_id == project_id,
                    DailyReport.report_date >= since,
                    DailyReport.deleted_at.is_(None),
                )
            )
            .group_by(DailyReport.report_date)
            .order_by(DailyReport.report_date)
        )
    ).all()

    return {
        "project_id": str(project.id),
        "project_code": project.code,
        "project_name": project.name,
        "current_health_score": project.health_score,
        "current_health_status": project.health_status.value if project.health_status else None,
        "period_days": days,
        "daily": [
            {
                "date": row.report_date.isoformat(),
                "report_count": row.report_count,
                "avg_score": _round_float(row.avg_score),
                "pass_rate": round(row.pass_count / max(row.report_count, 1) * 100, 1),
                "avg_progress": _round_float(row.avg_progress),
            }
            for row in rows
        ],
    }


@router.get("/sprint-efficiency")
async def sprint_efficiency(
    project_id: uuid.UUID | None = Query(default=None, description="可选项目 ID"),
    last_n: int = Query(default=10, ge=1, le=50, description="最近 N 个已完成 Sprint"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
):
    """Sprint 效率指标:计划点、完成点、完成率和平均 velocity。"""
    if project_id is not None:
        project = await db.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "项目不存在")

    stmt = (
        select(Sprint, Project)
        .join(Project, Sprint.project_id == Project.id)
        .where(
            Sprint.status == SprintStatus.completed,
            Project.deleted_at.is_(None),
        )
        .order_by(desc(Sprint.end_date))
        .limit(last_n)
    )
    if project_id is not None:
        stmt = stmt.where(Sprint.project_id == project_id)

    rows = (await db.execute(stmt)).all()
    items = []
    for sprint, project in reversed(rows):
        planned = sprint.planned_story_points or 0
        completed = sprint.completed_story_points or 0
        duration_days = max((sprint.end_date - sprint.start_date).days + 1, 1)
        items.append(
            {
                "project_id": str(project.id),
                "project_code": project.code,
                "project_name": project.name,
                "sprint_id": str(sprint.id),
                "sprint_number": sprint.sprint_number,
                "start_date": sprint.start_date.isoformat(),
                "end_date": sprint.end_date.isoformat(),
                "planned_story_points": planned,
                "completed_story_points": completed,
                "completion_rate": round(completed / max(planned, 1) * 100, 1),
                "velocity": completed,
                "points_per_day": round(completed / duration_days, 2),
                "health_score": sprint.health_score,
            }
        )

    avg_velocity = round(sum(item["velocity"] for item in items) / len(items), 1) if items else 0.0
    avg_completion_rate = round(sum(item["completion_rate"] for item in items) / len(items), 1) if items else 0.0

    return {
        "project_id": str(project_id) if project_id else None,
        "count": len(items),
        "summary": {
            "avg_velocity": avg_velocity,
            "avg_completion_rate": avg_completion_rate,
        },
        "sprints": items,
    }
