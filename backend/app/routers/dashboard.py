"""
app/routers/dashboard.py — 管理看板核心数据 API

对应管理层每日必看的"晨报视图"，是 Excel 所有行数据的可视化升级版。
需要 manager 或 admin 角色才可访问。
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.daily_report import DailyReport
from app.models.project import Project
from app.models.risk_alert import RiskAlert
from app.models.user import User, UserRole
from app.services.deletion_history import mark_soft_delete_restored, record_soft_delete

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])

# 管理层才能访问的端点依然用这个
_mgr_or_admin = require_role(UserRole.manager, UserRole.admin)


@router.get("/morning-briefing")
async def get_morning_briefing(
    report_date: date = Query(default=None, description="查询日期，不传则为今日"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    晨报总览：
    - 管理层看全部人的汇报
    - 员工只看自己的汇报
    """
    if report_date is None:
        report_date = date.today()

    # 拉取当日所有日报
    stmt = (
        select(DailyReport, User.name, User.department)
        .join(User, DailyReport.user_id == User.id)
        .where(DailyReport.report_date == report_date)
        .where(DailyReport.deleted_at.is_(None))  # V2.4 Stage 2
        .order_by(DailyReport.ai_score.desc().nulls_last())
    )
    # 员工只看自己的
    if current_user.role == UserRole.employee:
        stmt = stmt.where(DailyReport.user_id == current_user.id)
    rows = (await db.execute(stmt)).all()

    # 所有员工（用于识别未汇报人员）
    all_users_result = await db.execute(select(User))
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


@router.get("/risk-alerts")
async def get_risk_alerts(
    status: Optional[str] = Query(default="unresolved"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    卡点预警墙（按未解决天数降序排列，最严重的排最前）
    对应 Excel 中所有 '核心卡点' 非空行的聚合视图。
    """
    stmt = (
        select(RiskAlert, User.name, User.department)
        .join(User, RiskAlert.user_id == User.id)
        .where(
            RiskAlert.status == status,
            RiskAlert.deleted_at.is_(None),  # V2.5 Stage 3:软删过滤
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
        .where(and_(RiskAlert.id.in_(body.ids), RiskAlert.deleted_at.is_(None)))
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
        .where(and_(RiskAlert.id.in_(body.ids), RiskAlert.deleted_at.is_not(None)))
        .values(deleted_at=None)
        .returning(RiskAlert.id)
    )
    restored_ids = [r[0] for r in result.all()]
    await mark_soft_delete_restored(
        db,
        table_name="risk_alerts",
        record_ids=restored_ids,
        restored_by=user.id,
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
