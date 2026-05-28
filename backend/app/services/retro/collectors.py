"""
app/services/retro/collectors.py — 复盘数据聚合器

按四种 scope 收集业务数据,所有返回都是 JSON 可序列化的 dict,直接喂给 prompt。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.models.okr import (
    KeyResult,
    KRProgressLog,
    Objective,
    OKRCycle,
)
from app.models.project import Project
from app.models.risk_alert import RiskAlert
from app.models.user import User

# ────────────────────────────────────────────────────────────────
# 共用:某时间段日报 + 风险 + 部门聚合
# ────────────────────────────────────────────────────────────────


async def collect_period_basics(
    db: AsyncSession,
    start: date,
    end: date,
    *,
    dept: Optional[str] = None,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """收集时间段内的通用业务素材(供 monthly/incident/项目复盘 复用)"""
    # 日报汇总
    report_stmt = (
        select(
            User.name,
            User.department,
            DailyReport.report_date,
            DailyReport.ai_score,
            DailyReport.pass_check,
            DailyReport.parsed_content,
        )
        .join(User, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
                DailyReport.deleted_at.is_(None),
            )
        )
        .order_by(desc(DailyReport.report_date))
    )
    if dept:
        report_stmt = report_stmt.where(User.department == dept)
    reports = (await db.execute(report_stmt)).all()
    avg_score = (
        round(
            sum(r.ai_score for r in reports if r.ai_score is not None)
            / max(1, len([r for r in reports if r.ai_score is not None])),
            1,
        )
        if reports
        else None
    )

    # 风险
    risk_stmt = (
        select(
            User.name,
            User.department,
            RiskAlert.description,
            RiskAlert.alert_type,
            RiskAlert.days_unresolved,
            RiskAlert.status,
            RiskAlert.created_at,
        )
        .join(User, RiskAlert.user_id == User.id)
        .where(
            RiskAlert.tenant_id == tenant_id,
            User.tenant_id == tenant_id,
            RiskAlert.created_at >= start,
            RiskAlert.deleted_at.is_(None),  # V2.5 Stage 3:软删的预警不进复盘上下文
        )
        .order_by(desc(RiskAlert.days_unresolved))
        .limit(40)
    )
    if dept:
        risk_stmt = risk_stmt.where(User.department == dept)
    risks = (await db.execute(risk_stmt)).all()

    # 部门聚合
    dept_stmt = (
        select(
            User.department,
            func.avg(DailyReport.ai_score).label("avg_score"),
            func.count(DailyReport.id).label("submitted"),
        )
        .join(User, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
                DailyReport.deleted_at.is_(None),
            )
        )
        .group_by(User.department)
        .order_by(desc("avg_score"))
    )
    depts = [
        {
            "department": r.department or "(未分组)",
            "avg_score": round(float(r.avg_score), 1) if r.avg_score else 0,
            "submitted": int(r.submitted),
        }
        for r in (await db.execute(dept_stmt)).all()
    ]

    # 人员表现 Top/Bottom
    user_stmt = (
        select(
            User.name,
            User.department,
            func.avg(DailyReport.ai_score).label("avg_score"),
            func.count(DailyReport.id).label("submitted"),
        )
        .join(DailyReport, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.tenant_id == tenant_id,
                User.tenant_id == tenant_id,
                DailyReport.deleted_at.is_(None),  # V2.4 Stage 3 C1
            )
        )
        .group_by(User.id, User.name, User.department)
        .order_by(desc("avg_score"))
    )
    user_perf = [
        {
            "name": r.name,
            "department": r.department,
            "avg_score": round(float(r.avg_score), 1) if r.avg_score else 0,
            "submitted": int(r.submitted),
        }
        for r in (await db.execute(user_stmt)).all()
    ]

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "report_count": len(reports),
        "avg_score": avg_score,
        "departments": depts,
        "top_performers": user_perf[:5],
        "bottom_performers": list(reversed(user_perf))[:3] if len(user_perf) >= 3 else [],
        "risks": [
            {
                "user": r.name,
                "department": r.department,
                "description": r.description[:200],
                "type": r.alert_type,
                "days_unresolved": int(r.days_unresolved),
                "status": r.status,
            }
            for r in risks
        ],
    }


# ────────────────────────────────────────────────────────────────
# OKR 周期复盘
# ────────────────────────────────────────────────────────────────


async def collect_okr_cycle(db: AsyncSession, cycle_id: UUID, *, tenant_id: str = "default") -> dict[str, Any]:
    cycle = (
        await db.execute(select(OKRCycle).where(OKRCycle.id == cycle_id, OKRCycle.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if not cycle:
        return {"error": f"cycle {cycle_id} not found"}

    obj_rows = (
        await db.execute(
            select(Objective, User.name)
            .join(User, and_(Objective.owner_id == User.id, User.tenant_id == tenant_id), isouter=True)
            .where(Objective.cycle_id == cycle.id, Objective.tenant_id == tenant_id)
            .order_by(desc(Objective.weight))
        )
    ).all()
    obj_ids = [o.id for o, _ in obj_rows]
    krs: list[KeyResult] = []
    if obj_ids:
        krs = list(
            (
                await db.execute(
                    select(KeyResult).where(KeyResult.objective_id.in_(obj_ids), KeyResult.tenant_id == tenant_id)
                )
            )
            .scalars()
            .all()
        )

    # 进度日志聚合(AI 提取 vs 手工 vs 系统)
    logs_summary = {"manual": 0, "ai_extracted": 0, "sprint_close": 0, "system": 0}
    if [k.id for k in krs]:
        log_rows = (
            await db.execute(
                select(KRProgressLog.source, func.count(KRProgressLog.id))
                .where(KRProgressLog.kr_id.in_([k.id for k in krs]), KRProgressLog.tenant_id == tenant_id)
                .group_by(KRProgressLog.source)
            )
        ).all()
        for src, cnt in log_rows:
            key = src.value if hasattr(src, "value") else str(src)
            logs_summary[key] = int(cnt)

    objectives = []
    for obj, owner in obj_rows:
        obj_krs = [k for k in krs if k.objective_id == obj.id]
        objectives.append(
            {
                "title": obj.title,
                "owner": owner,
                "weight": obj.weight,
                "progress": obj.progress,
                "status": obj.status.value,
                "description": obj.description,
                "key_results": [
                    {
                        "title": k.title,
                        "target": k.target_value,
                        "current": k.current_value,
                        "unit": k.unit,
                        "progress": k.progress,
                        "confidence": k.confidence,
                        "owner_id": str(k.owner_id),
                    }
                    for k in obj_krs
                ],
            }
        )

    # 周期窗口内的业务数据
    period = await collect_period_basics(db, cycle.start_date, cycle.end_date, tenant_id=tenant_id)

    return {
        "cycle": {
            "id": str(cycle.id),
            "name": cycle.name,
            "type": cycle.cycle_type.value,
            "start": str(cycle.start_date),
            "end": str(cycle.end_date),
            "status": cycle.status.value,
        },
        "objectives": objectives,
        "kr_count": len(krs),
        "progress_log_summary": logs_summary,
        "period_basics": period,
    }


# ────────────────────────────────────────────────────────────────
# 项目复盘
# ────────────────────────────────────────────────────────────────


async def collect_project(db: AsyncSession, project_id: UUID, *, tenant_id: str = "default") -> dict[str, Any]:
    proj = (
        await db.execute(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if not proj:
        return {"error": f"project {project_id} not found"}

    start = proj.planned_launch_date or (proj.created_at.date() if proj.created_at else date.today())
    end = proj.actual_launch_date or date.today()

    period = await collect_period_basics(db, start, end, tenant_id=tenant_id)
    return {
        "project": {
            "code": proj.code,
            "name": proj.name,
            "track": proj.track.value if proj.track else None,
            "status": proj.status.value if proj.status else None,
            "current_stage": proj.current_stage,
            "health_status": proj.health_status.value if proj.health_status else None,
            "health_score": proj.health_score,
            "planned_launch_date": str(proj.planned_launch_date) if proj.planned_launch_date else None,
            "actual_launch_date": str(proj.actual_launch_date) if proj.actual_launch_date else None,
            "budget_total": float(proj.budget_total) if proj.budget_total else None,
            "budget_spent": float(proj.budget_spent) if proj.budget_spent else None,
        },
        "period_basics": period,
    }


# ────────────────────────────────────────────────────────────────
# 月度复盘
# ────────────────────────────────────────────────────────────────


async def collect_monthly(db: AsyncSession, year: int, month: int, *, tenant_id: str = "default") -> dict[str, Any]:
    start = date(year, month, 1)
    next_month = date(year + (month // 12), (month % 12) + 1, 1)
    end = next_month - timedelta(days=1)

    period = await collect_period_basics(db, start, end, tenant_id=tenant_id)

    # 月度新增 / 关闭项目
    proj_stmt = select(Project).where(
        and_(Project.created_at >= start, Project.created_at <= end, Project.tenant_id == tenant_id)
    )
    new_projects = (await db.execute(proj_stmt)).scalars().all()

    return {
        "month": {"year": year, "month": month, "start": str(start), "end": str(end)},
        "period_basics": period,
        "new_projects": [
            {"code": p.code, "name": p.name, "status": p.status.value if p.status else None} for p in new_projects
        ],
    }


# ────────────────────────────────────────────────────────────────
# 事故复盘(以单个 risk_alert 为锚点,聚合解决时间窗内的相关数据)
# ────────────────────────────────────────────────────────────────


async def collect_incident(db: AsyncSession, risk_id: UUID, *, tenant_id: str = "default") -> dict[str, Any]:
    alert = (
        await db.execute(select(RiskAlert).where(RiskAlert.id == risk_id, RiskAlert.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if not alert or alert.deleted_at is not None:  # V2.5 Stage 3:软删的事故无法再触发复盘
        return {"error": f"risk_alert {risk_id} not found"}

    user = (
        (
            await db.execute(select(User).where(User.id == alert.user_id, User.tenant_id == tenant_id))
        ).scalar_one_or_none()
        if alert.user_id
        else None
    )
    end = alert.resolved_at.date() if alert.resolved_at else date.today()
    start = alert.created_at.date() if alert.created_at else (end - timedelta(days=alert.days_unresolved or 1))

    # 当事人在该时段的日报
    report_stmt = (
        select(DailyReport)
        .where(
            and_(
                DailyReport.user_id == alert.user_id,
                DailyReport.tenant_id == tenant_id,
                DailyReport.report_date >= start,
                DailyReport.report_date <= end,
                DailyReport.deleted_at.is_(None),  # V2.4 Stage 3 C1
            )
        )
        .order_by(DailyReport.report_date)
    )
    rows = (await db.execute(report_stmt)).scalars().all()

    return {
        "incident": {
            "id": str(alert.id),
            "type": alert.alert_type,
            "description": alert.description,
            "days_unresolved": alert.days_unresolved,
            "status": alert.status,
            "raised_at": alert.created_at.isoformat() if alert.created_at else None,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "owner": {"name": user.name, "department": user.department} if user else None,
        },
        "context_reports": [
            {
                "date": r.report_date.isoformat(),
                "score": r.ai_score,
                "passed": bool(r.pass_check),
                "tasks": (r.parsed_content or {}).get("tasks", "")[:120],
                "blocker": (r.parsed_content or {}).get("blocker", "")[:120],
                "next_step": (r.parsed_content or {}).get("next_step", "")[:120],
            }
            for r in rows
        ],
    }
