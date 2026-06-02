"""
app/routers/dashboard.py — 管理看板核心数据 API

对应管理层每日必看的"晨报视图"，是 Excel 所有行数据的可视化升级版。
需要 manager 或 admin 角色才可访问。
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.audit_log import AuditLog
from app.models.daily_report import DailyReport
from app.models.milestone_allocation import AllocationStatus, MilestoneAllocation
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.project_milestone import MilestoneStatus, ProjectMilestone
from app.models.risk_alert import RiskAlert
from app.models.sprint_task import SprintTask, TaskStatus
from app.models.user import User, UserRole
from app.models.user_points_ledger import LedgerDirection, UserPointsLedger
from app.services.deletion_history import mark_soft_delete_restored, record_soft_delete

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

# 管理层才能访问的端点依然用这个
_mgr_or_admin = require_role(UserRole.manager, UserRole.admin)


def _probe_status(
    missing_days: int,
    fail_count: int,
    blocker_count: int,
    open_risk_count: int,
    overdue_task_count: int,
) -> str:
    if open_risk_count > 0 or blocker_count > 0 or overdue_task_count >= 3 or missing_days >= 3:
        return "risk"
    if overdue_task_count >= 2 or missing_days >= 2 or fail_count >= 2:
        return "needs_talk"
    if overdue_task_count >= 1 or missing_days >= 1 or fail_count >= 1:
        return "watch"
    return "normal"


def _probe_note(
    status: str,
    missing_days: int,
    fail_count: int,
    blocker_count: int,
    open_risk_count: int,
    overdue_task_count: int,
    max_overdue_days: int,
) -> str:
    if open_risk_count > 0:
        return f"{open_risk_count} 个未解决卡点"
    if overdue_task_count > 0:
        return f"{overdue_task_count} 个超时任务，最长 {max_overdue_days} 天"
    if blocker_count > 0:
        return f"{blocker_count} 次日报提到卡点"
    if missing_days > 0:
        return f"{missing_days} 天未汇报"
    if fail_count > 0:
        return f"{fail_count} 次日报退回"
    if status == "normal":
        return "节奏正常"
    return "建议关注"


def _period_start(period: str) -> date | None:
    today = date.today()
    if period == "all":
        return None
    if period == "month":
        return today.replace(day=1)
    if period == "quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        return today.replace(month=quarter_month, day=1)
    if period == "year":
        return today.replace(month=1, day=1)
    return today.replace(day=1)


def _period_start_at(period: str) -> datetime | None:
    start = _period_start(period)
    if start is None:
        return None
    return datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


@router.get("/morning-briefing")
async def get_morning_briefing(
    report_date: date = Query(default=None, description="查询日期，不传则为今日"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_mgr_or_admin),
):
    """
    晨报总览：
    - 仅管理层看全部人的汇报、缺报名单和预警摘要
    """
    if report_date is None:
        report_date = date.today()

    # 拉取当日所有日报
    stmt = (
        select(DailyReport, User.name, User.department)
        .join(User, DailyReport.user_id == User.id)
        .where(
            DailyReport.report_date == report_date,
            DailyReport.tenant_id == current_user.tenant_id,
            User.tenant_id == current_user.tenant_id,
            User.role != UserRole.admin,
            DailyReport.deleted_at.is_(None),  # V2.4 Stage 2
        )
        .order_by(DailyReport.ai_score.desc().nulls_last())
    )
    rows = (await db.execute(stmt)).all()

    # 所有员工（用于识别未汇报人员）
    all_users_result = await db.execute(
        select(User).where(
            User.tenant_id == current_user.tenant_id,
            User.is_active.is_(True),
            User.role != UserRole.admin,
        )
    )
    all_users = all_users_result.scalars().all()
    reported_user_ids = {str(r.DailyReport.user_id) for r in rows}
    missing_members = [
        {"name": u.name, "department": u.department} for u in all_users if str(u.id) not in reported_user_ids
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
            "avg_score": round(sum(r.DailyReport.ai_score or 0 for r in rows) / max(len(rows), 1), 1),
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
                "id": str(r.DailyReport.id),  # V2.4 Stage 2:供前端多选批量软删用
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


@router.get("/personnel-probes")
async def get_personnel_probes(
    days: int = Query(default=7, ge=1, le=365, description="统计窗口天数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_mgr_or_admin),
):
    """
    总经理人员状态探针：
    - 按窗口聚合日报连续性、质量、卡点与贡献入账
    - 只返回管理需要的异常信号，不做排行榜
    """
    today = date.today()
    start_date = today - timedelta(days=days - 1)
    start_at = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)

    users = (
        (
            await db.execute(
                select(User)
                .where(
                    User.tenant_id == current_user.tenant_id,
                    User.is_active.is_(True),
                    User.role != UserRole.admin,
                )
                .order_by(User.department.asc(), User.name.asc())
            )
        )
        .scalars()
        .all()
    )
    user_map = {u.id: u for u in users}
    stats: dict[uuid.UUID, dict] = {
        u.id: {
            "report_dates": set(),
            "report_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "score_sum": 0,
            "score_count": 0,
            "blocker_count": 0,
            "latest_report_at": None,
            "points_income": 0,
            "points_pending_adjustment": 0,
            "open_risk_count": 0,
            "max_risk_days": 0,
            "overdue_task_count": 0,
            "max_overdue_days": 0,
        }
        for u in users
    }

    report_rows = (
        await db.execute(
            select(DailyReport).where(
                DailyReport.tenant_id == current_user.tenant_id,
                DailyReport.deleted_at.is_(None),
                DailyReport.report_date >= start_date,
                DailyReport.report_date <= today,
                DailyReport.user_id.in_(list(user_map.keys())) if user_map else False,
            )
        )
    ).scalars()
    for report in report_rows:
        item = stats.get(report.user_id)
        if item is None:
            continue
        item["report_dates"].add(report.report_date)
        item["report_count"] += 1
        if report.pass_check:
            item["pass_count"] += 1
        else:
            item["fail_count"] += 1
        if report.ai_score is not None:
            item["score_sum"] += report.ai_score
            item["score_count"] += 1
        blocker = (report.parsed_content or {}).get("blocker")
        if blocker:
            item["blocker_count"] += 1
        if report.created_at and (item["latest_report_at"] is None or report.created_at > item["latest_report_at"]):
            item["latest_report_at"] = report.created_at

    risk_rows = (
        await db.execute(
            select(RiskAlert).where(
                RiskAlert.tenant_id == current_user.tenant_id,
                RiskAlert.deleted_at.is_(None),
                RiskAlert.status == "unresolved",
                RiskAlert.user_id.in_(list(user_map.keys())) if user_map else False,
            )
        )
    ).scalars()
    for alert in risk_rows:
        item = stats.get(alert.user_id)
        if item is None:
            continue
        item["open_risk_count"] += 1
        item["max_risk_days"] = max(item["max_risk_days"], alert.days_unresolved or 0)

    ledger_rows = (
        await db.execute(
            select(UserPointsLedger).where(
                UserPointsLedger.tenant_id == current_user.tenant_id,
                UserPointsLedger.occurred_at >= start_at,
                UserPointsLedger.user_id.in_(list(user_map.keys())) if user_map else False,
            )
        )
    ).scalars()
    for row in ledger_rows:
        item = stats.get(row.user_id)
        if item is None:
            continue
        if row.direction == LedgerDirection.income:
            item["points_income"] += row.amount
        else:
            item["points_pending_adjustment"] += row.amount

    overdue_rows = (
        await db.execute(
            select(SprintTask).where(
                SprintTask.tenant_id == current_user.tenant_id,
                SprintTask.deleted_at.is_(None),
                SprintTask.assignee_id.in_(list(user_map.keys())) if user_map else False,
                SprintTask.planned_end.is_not(None),
                SprintTask.planned_end < today,
                SprintTask.status.notin_([TaskStatus.done, TaskStatus.cancelled]),
            )
        )
    ).scalars()
    for task in overdue_rows:
        if task.assignee_id is None:
            continue
        item = stats.get(task.assignee_id)
        if item is None:
            continue
        overdue_days = (today - task.planned_end).days if task.planned_end else 0
        item["overdue_task_count"] += 1
        item["max_overdue_days"] = max(item["max_overdue_days"], overdue_days)

    probes = []
    summary = {"normal": 0, "watch": 0, "needs_talk": 0, "risk": 0}
    for user in users:
        item = stats[user.id]
        submitted_days = len(item["report_dates"])
        missing_days = max(days - submitted_days, 0)
        avg_score = round(item["score_sum"] / item["score_count"], 1) if item["score_count"] else None
        pass_rate = round(item["pass_count"] / item["report_count"] * 100, 1) if item["report_count"] else None
        status = _probe_status(
            missing_days,
            item["fail_count"],
            item["blocker_count"],
            item["open_risk_count"],
            item["overdue_task_count"],
        )
        summary[status] += 1
        probes.append(
            {
                "user_id": str(user.id),
                "name": user.name,
                "department": user.department,
                "role": user.role,
                "job_title": user.job_title,
                "work_status": user.status,
                "status_until": user.status_until,
                "probe_status": status,
                "note": _probe_note(
                    status,
                    missing_days,
                    item["fail_count"],
                    item["blocker_count"],
                    item["open_risk_count"],
                    item["overdue_task_count"],
                    item["max_overdue_days"],
                ),
                "submitted_days": submitted_days,
                "missing_days": missing_days,
                "report_count": item["report_count"],
                "pass_rate": pass_rate,
                "avg_score": avg_score,
                "fail_count": item["fail_count"],
                "blocker_count": item["blocker_count"],
                "open_risk_count": item["open_risk_count"],
                "max_risk_days": item["max_risk_days"],
                "overdue_task_count": item["overdue_task_count"],
                "max_overdue_days": item["max_overdue_days"],
                "points_income": item["points_income"],
                "points_adjustment": item["points_pending_adjustment"],
                "latest_report_at": item["latest_report_at"],
            }
        )

    order = {"risk": 0, "needs_talk": 1, "watch": 2, "normal": 3}
    probes.sort(
        key=lambda p: (
            order[p["probe_status"]],
            -p["overdue_task_count"],
            -p["missing_days"],
            -p["open_risk_count"],
            p["department"],
            p["name"],
        )
    )

    return {
        "window_days": days,
        "start_date": start_date,
        "end_date": today,
        "summary": summary,
        "items": probes,
    }


@router.get("/people-contribution")
async def get_people_contribution(
    period: str = Query(default="month", pattern="^(month|quarter|year|all)$"),
    department: Optional[str] = Query(default=None),
    project_id: Optional[uuid.UUID] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_mgr_or_admin),
):
    """
    总经理人员贡献与进度总览。

    聚合口径:
    - 已入账积分: user_points_ledger 在 period 内的净额
    - 待验收积分: 当前 pending 的 milestone allocation 初始积分
    - 进度: 当前未作废贡献节点的 approved/allocation 总数
    - 风险: 当前未解决风险 + 逾期贡献节点
    """
    period_start = _period_start(period)
    period_start_at = _period_start_at(period)
    today = date.today()

    user_query = select(User).where(
        User.tenant_id == current_user.tenant_id,
        User.is_active.is_(True),
        User.role != UserRole.admin,
    )
    if department:
        user_query = user_query.where(User.department == department)
    if project_id:
        project_member_user_ids = (
            select(ProjectMember.user_id)
            .join(Project, ProjectMember.project_id == Project.id)
            .where(
                ProjectMember.project_id == project_id,
                ProjectMember.left_at.is_(None),
                ProjectMember.tenant_id == current_user.tenant_id,
                Project.tenant_id == current_user.tenant_id,
                Project.deleted_at.is_(None),
            )
        )
        user_query = user_query.where(User.id.in_(project_member_user_ids))
    users = (await db.execute(user_query.order_by(User.department.asc(), User.name.asc()))).scalars().all()
    user_ids = [user.id for user in users]

    stats = {
        user.id: {
            "earned_points": 0,
            "pending_points": 0,
            "project_ids": set(),
            "milestone_count": 0,
            "completed_milestone_count": 0,
            "overdue_milestone_count": 0,
            "report_count": 0,
            "score_sum": 0,
            "score_count": 0,
            "open_risk_count": 0,
        }
        for user in users
    }

    if user_ids:
        project_member_query = (
            select(ProjectMember.user_id, ProjectMember.project_id)
            .join(
                Project,
                ProjectMember.project_id == Project.id,
            )
            .where(
                ProjectMember.user_id.in_(user_ids),
                ProjectMember.left_at.is_(None),
                ProjectMember.tenant_id == current_user.tenant_id,
                Project.tenant_id == current_user.tenant_id,
                Project.deleted_at.is_(None),
            )
        )
        if project_id:
            project_member_query = project_member_query.where(ProjectMember.project_id == project_id)
        for row in (await db.execute(project_member_query)).all():
            stats[row.user_id]["project_ids"].add(row.project_id)

        allocation_query = (
            select(MilestoneAllocation, ProjectMilestone)
            .join(ProjectMilestone, MilestoneAllocation.milestone_id == ProjectMilestone.id)
            .join(Project, ProjectMilestone.project_id == Project.id)
            .where(
                MilestoneAllocation.user_id.in_(user_ids),
                MilestoneAllocation.status != AllocationStatus.reverted,
                MilestoneAllocation.tenant_id == current_user.tenant_id,
                ProjectMilestone.deleted_at.is_(None),
                Project.tenant_id == current_user.tenant_id,
                Project.deleted_at.is_(None),
            )
        )
        if project_id:
            allocation_query = allocation_query.where(Project.id == project_id)
        for allocation, milestone in (await db.execute(allocation_query)).all():
            item = stats[allocation.user_id]
            item["milestone_count"] += 1
            if allocation.status == AllocationStatus.approved:
                item["completed_milestone_count"] += 1
            if allocation.status == AllocationStatus.pending:
                item["pending_points"] += allocation.initial_points
            if (
                milestone.target_date
                and milestone.target_date < today
                and milestone.status in (MilestoneStatus.pending, MilestoneStatus.in_review)
            ):
                item["overdue_milestone_count"] += 1

        ledger_query = select(UserPointsLedger).where(
            UserPointsLedger.user_id.in_(user_ids),
            UserPointsLedger.tenant_id == current_user.tenant_id,
        )
        if period_start_at:
            ledger_query = ledger_query.where(UserPointsLedger.occurred_at >= period_start_at)
        if project_id:
            ledger_query = ledger_query.join(
                ProjectMilestone, UserPointsLedger.milestone_id == ProjectMilestone.id
            ).where(ProjectMilestone.project_id == project_id)
        for row in (await db.execute(ledger_query)).scalars():
            stats[row.user_id]["earned_points"] += row.amount

        report_query = select(DailyReport).where(
            DailyReport.user_id.in_(user_ids),
            DailyReport.tenant_id == current_user.tenant_id,
            DailyReport.deleted_at.is_(None),
        )
        if period_start:
            report_query = report_query.where(DailyReport.report_date >= period_start)
        if project_id:
            report_query = report_query.where(DailyReport.project_id == project_id)
        for report in (await db.execute(report_query)).scalars():
            item = stats[report.user_id]
            item["report_count"] += 1
            if report.ai_score is not None:
                item["score_sum"] += report.ai_score
                item["score_count"] += 1

        risk_query = select(RiskAlert).where(
            RiskAlert.user_id.in_(user_ids),
            RiskAlert.tenant_id == current_user.tenant_id,
            RiskAlert.deleted_at.is_(None),
            RiskAlert.status == "unresolved",
        )
        for alert in (await db.execute(risk_query)).scalars():
            stats[alert.user_id]["open_risk_count"] += 1

    rows = []
    for user in users:
        item = stats[user.id]
        milestone_count = item["milestone_count"]
        progress_pct = round(item["completed_milestone_count"] / milestone_count * 100, 1) if milestone_count else 0
        avg_score = round(item["score_sum"] / item["score_count"], 1) if item["score_count"] else None
        risk_level = "normal"
        if item["open_risk_count"] > 0 or item["overdue_milestone_count"] >= 2:
            risk_level = "risk"
        elif item["overdue_milestone_count"] > 0 or item["pending_points"] > 0:
            risk_level = "watch"

        rows.append(
            {
                "user_id": str(user.id),
                "name": user.name,
                "department": user.department,
                "job_title": user.job_title,
                "role": _enum_value(user.role),
                "earned_points": item["earned_points"],
                "pending_points": item["pending_points"],
                "project_count": len(item["project_ids"]),
                "milestone_count": milestone_count,
                "completed_milestone_count": item["completed_milestone_count"],
                "overdue_milestone_count": item["overdue_milestone_count"],
                "progress_pct": progress_pct,
                "report_count": item["report_count"],
                "avg_report_score": avg_score,
                "open_risk_count": item["open_risk_count"],
                "risk_level": risk_level,
            }
        )

    rows.sort(
        key=lambda row: ({"risk": 0, "watch": 1, "normal": 2}[row["risk_level"]], -row["pending_points"], row["name"])
    )
    return {
        "period": period,
        "start_date": period_start,
        "end_date": today,
        "summary": {
            "people_count": len(rows),
            "earned_points": sum(row["earned_points"] for row in rows),
            "pending_points": sum(row["pending_points"] for row in rows),
            "overdue_milestone_count": sum(row["overdue_milestone_count"] for row in rows),
            "risk_people_count": sum(1 for row in rows if row["risk_level"] == "risk"),
        },
        "items": rows,
    }


@router.get("/people-contribution/{user_id}")
async def get_people_contribution_detail(
    user_id: uuid.UUID,
    period: str = Query(default="month", pattern="^(month|quarter|year|all)$"),
    project_id: Optional[uuid.UUID] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_mgr_or_admin),
):
    period_start = _period_start(period)
    period_start_at = _period_start_at(period)
    target = (
        await db.execute(
            select(User).where(
                User.id == user_id,
                User.tenant_id == current_user.tenant_id,
                User.role != UserRole.admin,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(404, "用户不存在")

    project_query = (
        select(ProjectMember, Project)
        .join(Project, ProjectMember.project_id == Project.id)
        .where(
            ProjectMember.user_id == user_id,
            ProjectMember.left_at.is_(None),
            ProjectMember.tenant_id == current_user.tenant_id,
            Project.tenant_id == current_user.tenant_id,
            Project.deleted_at.is_(None),
        )
        .order_by(Project.code.asc())
    )
    if project_id:
        project_query = project_query.where(Project.id == project_id)
    project_rows = (await db.execute(project_query)).all()

    milestone_query = (
        select(MilestoneAllocation, ProjectMilestone, Project)
        .join(ProjectMilestone, MilestoneAllocation.milestone_id == ProjectMilestone.id)
        .join(Project, ProjectMilestone.project_id == Project.id)
        .where(
            MilestoneAllocation.user_id == user_id,
            MilestoneAllocation.status != AllocationStatus.reverted,
            MilestoneAllocation.tenant_id == current_user.tenant_id,
            ProjectMilestone.deleted_at.is_(None),
            Project.tenant_id == current_user.tenant_id,
            Project.deleted_at.is_(None),
        )
        .order_by(Project.code.asc(), ProjectMilestone.node_order.asc())
    )
    if project_id:
        milestone_query = milestone_query.where(Project.id == project_id)
    milestone_rows = (await db.execute(milestone_query)).all()

    ledger_query = (
        select(UserPointsLedger, ProjectMilestone, Project)
        .outerjoin(ProjectMilestone, UserPointsLedger.milestone_id == ProjectMilestone.id)
        .outerjoin(Project, ProjectMilestone.project_id == Project.id)
        .where(
            UserPointsLedger.user_id == user_id,
            UserPointsLedger.tenant_id == current_user.tenant_id,
        )
        .order_by(UserPointsLedger.occurred_at.desc())
        .limit(50)
    )
    if period_start_at:
        ledger_query = ledger_query.where(UserPointsLedger.occurred_at >= period_start_at)
    if project_id:
        ledger_query = ledger_query.where(ProjectMilestone.project_id == project_id)
    ledger_rows = (await db.execute(ledger_query)).all()

    report_query = (
        select(DailyReport)
        .where(
            DailyReport.user_id == user_id,
            DailyReport.tenant_id == current_user.tenant_id,
            DailyReport.deleted_at.is_(None),
        )
        .order_by(DailyReport.report_date.desc(), DailyReport.created_at.desc())
        .limit(20)
    )
    if period_start:
        report_query = report_query.where(DailyReport.report_date >= period_start)
    if project_id:
        report_query = report_query.where(DailyReport.project_id == project_id)
    report_rows = (await db.execute(report_query)).scalars().all()

    return {
        "period": period,
        "start_date": period_start,
        "end_date": date.today(),
        "user": {
            "user_id": str(target.id),
            "name": target.name,
            "department": target.department,
            "job_title": target.job_title,
            "role": _enum_value(target.role),
        },
        "projects": [
            {
                "project_id": str(project.id),
                "code": project.code,
                "name": project.name,
                "health_status": _enum_value(project.health_status),
                "track": _enum_value(project.track),
                "role_in_project": member.role_in_project,
                "member_track": _enum_value(member.track),
            }
            for member, project in project_rows
        ],
        "milestones": [
            {
                "allocation_id": str(allocation.id),
                "milestone_id": str(milestone.id),
                "project_id": str(project.id),
                "project_code": project.code,
                "project_name": project.name,
                "title": milestone.title,
                "node_order": milestone.node_order,
                "target_date": milestone.target_date,
                "milestone_status": _enum_value(milestone.status),
                "allocation_status": _enum_value(allocation.status),
                "initial_points": allocation.initial_points,
                "final_points": allocation.final_points,
                "overdue": bool(
                    milestone.target_date
                    and milestone.target_date < date.today()
                    and milestone.status in (MilestoneStatus.pending, MilestoneStatus.in_review)
                ),
            }
            for allocation, milestone, project in milestone_rows
        ],
        "ledger": [
            {
                "ledger_id": str(ledger.id),
                "milestone_id": str(ledger.milestone_id) if ledger.milestone_id else None,
                "milestone_title": milestone.title if milestone else None,
                "project_id": str(project.id) if project else None,
                "project_name": project.name if project else None,
                "direction": _enum_value(ledger.direction),
                "amount": ledger.amount,
                "occurred_at": ledger.occurred_at,
                "reason": ledger.reason,
            }
            for ledger, milestone, project in ledger_rows
        ],
        "reports": [
            {
                "report_id": str(report.id),
                "report_date": report.report_date,
                "project_id": str(report.project_id) if report.project_id else None,
                "ai_score": report.ai_score,
                "pass_check": report.pass_check,
                "tasks": (report.parsed_content or {}).get("tasks"),
                "progress": (report.parsed_content or {}).get("progress"),
                "blocker": (report.parsed_content or {}).get("blocker"),
            }
            for report in report_rows
        ],
    }


@router.get("/risk-alerts")
async def get_risk_alerts(
    status: Optional[str] = Query(default="unresolved"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(_mgr_or_admin),
):
    """
    卡点预警墙（按未解决天数降序排列，最严重的排最前）
    对应 Excel 中所有 '核心卡点' 非空行的聚合视图。
    """
    stmt = (
        select(RiskAlert, User.name, User.department)
        .join(User, RiskAlert.user_id == User.id)
        .join(DailyReport, RiskAlert.report_id == DailyReport.id)
        .where(
            RiskAlert.status == status,
            RiskAlert.tenant_id == current_user.tenant_id,
            User.tenant_id == current_user.tenant_id,
            DailyReport.tenant_id == current_user.tenant_id,
            RiskAlert.deleted_at.is_(None),  # V2.5 Stage 3:软删过滤
            DailyReport.deleted_at.is_(None),
        )
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


# ────────────────────────────────────────────────────────────────
# V2.5 Stage 3:RiskAlert 批量软删 / 恢复 / 回收站
# ────────────────────────────────────────────────────────────────


class RiskAlertBatchBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200, description="待操作的预警 ID 列表")


@router.delete("/risk-alerts/batch")
async def batch_soft_delete_risk_alerts(
    body: RiskAlertBatchBody = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_mgr_or_admin),
):
    """V2.5 Stage 3:批量软删风险预警。

    - 仅对当前未软删的目标生效(idempotent — 已删的会被跳过)
    - 历史 ai_score / report_id / ERP 解卡记录均不受影响
    - dashboard / health / weekly / chat / retro / ERP 读取处下次刷新自动排除
    """
    deleted_at = datetime.now(timezone.utc)
    result = await db.execute(
        update(RiskAlert)
        .where(and_(RiskAlert.id.in_(body.ids), RiskAlert.deleted_at.is_(None), RiskAlert.tenant_id == user.tenant_id))
        .values(deleted_at=deleted_at)
        .returning(RiskAlert.id)
    )
    deleted_ids = [r[0] for r in result.all()]
    await record_soft_delete(
        db,
        actor_id=user.id,
        table_name="risk_alerts",
        record_ids=deleted_ids,
        deleted_at=deleted_at,
        tenant_id=user.tenant_id,
    )
    await db.commit()
    return {
        "requested": len(body.ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": [str(i) for i in deleted_ids],
    }


@router.patch("/risk-alerts/batch-restore")
async def batch_restore_risk_alerts(
    body: RiskAlertBatchBody = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    """V2.5 Stage 3:管理员从回收站批量恢复软删的预警(SET deleted_at = NULL)。"""
    result = await db.execute(
        update(RiskAlert)
        .where(
            and_(RiskAlert.id.in_(body.ids), RiskAlert.deleted_at.is_not(None), RiskAlert.tenant_id == user.tenant_id)
        )
        .values(deleted_at=None)
        .returning(RiskAlert.id)
    )
    restored_ids = [r[0] for r in result.all()]
    await mark_soft_delete_restored(
        db,
        table_name="risk_alerts",
        record_ids=restored_ids,
        restored_by=user.id,
        tenant_id=user.tenant_id,
    )
    await db.commit()
    return {
        "requested": len(body.ids),
        "restored_count": len(restored_ids),
        "restored_ids": [str(i) for i in restored_ids],
    }


@router.get("/risk-alerts/deleted")
async def list_deleted_risk_alerts(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.admin)),
):
    """V2.5 Stage 3:管理员回收站 — 已软删的预警列表(按删除时间倒序)。"""
    stmt = (
        select(RiskAlert, User.name, User.department)
        .join(User, RiskAlert.user_id == User.id)
        .where(RiskAlert.deleted_at.is_not(None))
        .order_by(RiskAlert.deleted_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    items = [
        {
            "alert_id": str(r.RiskAlert.id),
            "member": r.name,
            "department": r.department,
            "type": r.RiskAlert.alert_type,
            "description": r.RiskAlert.description,
            "days_unresolved": r.RiskAlert.days_unresolved,
            "status": r.RiskAlert.status,
            "created_at": r.RiskAlert.created_at.isoformat() if r.RiskAlert.created_at else None,
            "deleted_at": r.RiskAlert.deleted_at.isoformat() if r.RiskAlert.deleted_at else None,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/token-usage")
async def get_token_usage(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(UserRole.admin)),
):
    """今日 Token 消耗统计（仅 admin 可见）"""
    from app.config import settings
    from app.services.token_guard import get_daily_usage

    used = await get_daily_usage(db)
    return {
        "date": date.today(),
        "used_tokens": used,
        "limit_tokens": settings.daily_token_limit,
        "usage_pct": round(used / settings.daily_token_limit * 100, 1),
        "is_throttled": used >= settings.daily_token_limit,
    }


# ────────────────────────────────────────────────────────────────
# V2.3 临时工单看板(月度预聚合)
# ────────────────────────────────────────────────────────────────


@router.get("/temp-ticket-summary")
async def get_temp_ticket_summary(
    month_start: Optional[str] = Query(None, description="ISO 日期 YYYY-MM-DD,默认 30 天前"),
    month_end: Optional[str] = Query(None, description="ISO 日期 YYYY-MM-DD,默认今天"),
    top_n: int = Query(5, ge=1, le=20, description="TOP N 员工(默认 5)"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
):
    """
    V2.3 临时工单 Dashboard 卡片预聚合:
    - 本月临时工单工时 TOP N 员工
    - 临时工单工时 vs 主干项目工时 占比

    工时口径与 /api/v1/capacity/project/{id}/summary 一致:
    每条日报 ≈ 0.5 工日 = 4 小时(mode=report_count)
    """
    from datetime import datetime

    HOURS_PER_REPORT = 4
    today = date.today()
    end_d = datetime.fromisoformat(month_end).date() if month_end else today
    start_d = datetime.fromisoformat(month_start).date() if month_start else (end_d - timedelta(days=30))

    # 1) 该窗口内"挂在临时项目下"的日报,按 user 聚合 → TOP N
    top_rows = (
        await db.execute(
            select(
                DailyReport.user_id,
                User.name,
                User.department,
                func.count(DailyReport.id).label("report_count"),
            )
            .join(User, DailyReport.user_id == User.id)
            .join(Project, DailyReport.project_id == Project.id)
            .where(
                and_(
                    Project.is_temporary.is_(True),
                    Project.deleted_at.is_(None),  # V2.4 Stage 2
                    DailyReport.deleted_at.is_(None),
                    DailyReport.report_date >= start_d,
                    DailyReport.report_date <= end_d,
                )
            )
            .group_by(DailyReport.user_id, User.name, User.department)
            .order_by(func.count(DailyReport.id).desc())
            .limit(top_n)
        )
    ).all()

    top_members = [
        {
            "user_id": str(uid),
            "user_name": name,
            "department": dept,
            "report_count": int(rc),
            "hours_estimated": int(rc) * HOURS_PER_REPORT,
        }
        for uid, name, dept, rc in top_rows
    ]

    # 2) 临时 vs 主干 工时占比(基于该窗口内所有挂了项目的日报)
    ratio_rows = (
        await db.execute(
            select(
                Project.is_temporary,
                func.count(DailyReport.id).label("report_count"),
            )
            .join(Project, DailyReport.project_id == Project.id)
            .where(
                and_(
                    DailyReport.report_date >= start_d,
                    DailyReport.report_date <= end_d,
                    DailyReport.deleted_at.is_(None),  # V2.4 Stage 2
                    Project.deleted_at.is_(None),
                )
            )
            .group_by(Project.is_temporary)
        )
    ).all()

    temp_hours = 0
    main_hours = 0
    for is_temp, rc in ratio_rows:
        hours = int(rc) * HOURS_PER_REPORT
        if is_temp:
            temp_hours += hours
        else:
            main_hours += hours

    total_hours = temp_hours + main_hours
    temp_pct = round(temp_hours / total_hours * 100, 1) if total_hours > 0 else 0.0
    main_pct = round(main_hours / total_hours * 100, 1) if total_hours > 0 else 0.0

    return {
        "window": {"start": start_d.isoformat(), "end": end_d.isoformat()},
        "mode": "report_count",
        "hours_per_report": HOURS_PER_REPORT,
        "top_members": top_members,
        "ratio": {
            "temp_hours": temp_hours,
            "main_hours": main_hours,
            "total_hours": total_hours,
            "temp_pct": temp_pct,
            "main_pct": main_pct,
        },
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
        .where(
            and_(
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.deleted_at.is_(None),  # V2.4 Stage 2
            )
        )
        .group_by(DailyReport.report_date)
        .order_by(DailyReport.report_date)
    )
    rows = (await db.execute(stmt)).all()

    # 总人数
    total_users_result = await db.execute(select(func.count()).select_from(User).where(User.is_active == True))
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
        result.append(
            daily.get(
                d,
                {
                    "date": d,
                    "count": 0,
                    "avg_score": 0,
                    "pass_count": 0,
                    "pass_rate": 0,
                },
            )
        )

    return {
        "total_users": total_users,
        "days": result,
    }


# ────────────────────────────────────────────────────────────────
# V2.6 数据生命周期治理 (Dry-Run 指标)
# ────────────────────────────────────────────────────────────────


@router.get("/deletion-governance")
async def get_deletion_governance(
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr_or_admin),
):
    """
    V2.6: 获取近 14 天数据治理 (Dry-Run) 趋势与今日详情
    """
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=14)

    stmt = (
        select(AuditLog)
        .where(
            and_(
                AuditLog.action == "deletion_cleanup_dry_run",
                AuditLog.created_at >= start,
                AuditLog.created_at <= end,
            )
        )
        .order_by(AuditLog.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        return {
            "latest": {
                "total_candidates": 0,
                "open_history_batches": 0,
                "tables": {
                    "daily_reports": 0,
                    "projects": 0,
                    "sprint_tasks": 0,
                    "risk_alerts": 0,
                    "knowledge_items": 0,
                },
                "cascade_impacts": {},
                "timestamp": end.isoformat(),
            },
            "trend_14d": [],
        }

    latest_log = rows[0]
    latest_detail = latest_log.detail or {}

    trend = []
    # 按照 created_at 从旧到新排序(原 rows 是从新到旧)
    for row in reversed(rows):
        detail = row.detail or {}
        trend.append(
            {
                "date": row.created_at.date().isoformat() if row.created_at else "",
                "total_candidates": detail.get("total_candidates", 0),
            }
        )

    return {
        "latest": {
            "total_candidates": latest_detail.get("total_candidates", 0),
            "open_history_batches": latest_detail.get("open_history_batches", 0),
            "tables": latest_detail.get("tables", {}),
            "cascade_impacts": latest_detail.get("cascade_impacts", {}),
            "timestamp": latest_log.created_at.isoformat() if latest_log.created_at else None,
        },
        "trend_14d": trend,
    }
