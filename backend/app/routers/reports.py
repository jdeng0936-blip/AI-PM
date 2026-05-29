"""
app/routers/reports.py — 日报 CRUD API

提供管理后台查询、手动创建、导出等功能。
员工提交走企微网关（wechat.py），此路由供管理端使用。
"""

import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user
from app.models.daily_report import DailyReport, PlannedStatus, ReportType
from app.models.daily_supervised_task import DailySupervisedTask, SupervisedStatus
from app.models.notification import NotificationChannel, NotificationTemplate
from app.models.project import Project, ProjectStatus
from app.models.project_followup import ProjectFollowUp
from app.models.project_member import ProjectMember
from app.models.risk_alert import RiskAlert
from app.models.sprint import Sprint
from app.models.sprint_task import SprintTask, TaskStatus
from app.models.user import User, UserRole
from app.schemas.morning_evening import (
    EveningBatchRequest,
    EveningBatchResponse,
    MorningBatchRequest,
    MorningBatchResponse,
    MyActiveProjectItem,
    MyActiveProjectsResponse,
    MyActiveTaskItem,
    PendingFollowUpItem,
    PendingFollowUpsResponse,
)
from app.services.ai_engine import parse_report_with_ai
from app.services.deletion_history import mark_soft_delete_restored, record_soft_delete
from app.services.kr_progress_extractor import extract_and_update_kr_progress_safe
from app.services.notification_service import notify_safe
from app.services.token_guard import check_daily_quota, log_token_usage

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"], redirect_slashes=False)


# V2.4 Stage 2 批量软删请求体
class BatchDeleteBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200, description="待软删的日报 ID 列表")


# V2.4 Stage 3 C3:批量恢复请求体(撤销 / 回收站共用)
class BatchRestoreBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200, description="待恢复的日报 ID 列表")


class WebReportRequest(BaseModel):
    """Web 端日报请求体"""

    raw_text: str
    report_date: Optional[date] = None
    project_id: Optional[uuid.UUID] = None
    sprint_task_id: Optional[uuid.UUID] = None


async def _validate_project_task_consistency(
    db: AsyncSession,
    current_user: User,
    project_id: Optional[uuid.UUID],
    sprint_task_id: Optional[uuid.UUID],
) -> Optional[uuid.UUID]:
    """校验项目/任务关系；只传任务时反推并返回任务所属项目。"""
    if project_id is not None:
        project_conditions = [
            Project.id == project_id,
            Project.deleted_at.is_(None),
            Project.tenant_id == current_user.tenant_id,
        ]
        if current_user.role == UserRole.employee:
            visible_project_ids = (
                select(ProjectMember.project_id)
                .where(
                    ProjectMember.user_id == current_user.id,
                    ProjectMember.left_at.is_(None),
                    ProjectMember.tenant_id == current_user.tenant_id,
                )
                .scalar_subquery()
            )
            project_conditions.append(Project.id.in_(visible_project_ids))
        project_exists = (await db.execute(select(Project.id).where(and_(*project_conditions)))).scalar_one_or_none()
        if project_exists is None:
            raise HTTPException(404, detail="项目不存在")

    if sprint_task_id is None:
        return project_id

    result = await db.execute(
        select(Sprint.project_id)
        .join(SprintTask, SprintTask.sprint_id == Sprint.id)
        .where(
            SprintTask.id == sprint_task_id,
            SprintTask.deleted_at.is_(None),
            SprintTask.tenant_id == current_user.tenant_id,
            Sprint.tenant_id == current_user.tenant_id,
        )
    )
    task_project_id = result.scalar_one_or_none()
    if task_project_id is None:
        raise HTTPException(status_code=404, detail="Sprint 任务不存在")
    if project_id is not None and task_project_id != project_id:
        raise HTTPException(status_code=400, detail="Sprint 任务不属于所选项目，请重新选择")
    if current_user.role == UserRole.employee:
        member = (
            await db.execute(
                select(ProjectMember.id).where(
                    ProjectMember.project_id == task_project_id,
                    ProjectMember.user_id == current_user.id,
                    ProjectMember.left_at.is_(None),
                    ProjectMember.tenant_id == current_user.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if member is None:
            raise HTTPException(status_code=403, detail="无权关联未参与的项目任务")
    return task_project_id


@router.post("/web-submit")
async def web_submit_daily_report(
    req: WebReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Web 端提交日报（通过 JWT 自动识别用户）。
    """
    project_id = await _validate_project_task_consistency(db, current_user, req.project_id, req.sprint_task_id)

    report_date = req.report_date or date.today()
    dup_check = await db.execute(
        select(DailyReport.id)
        .where(
            and_(
                DailyReport.user_id == current_user.id,
                DailyReport.tenant_id == current_user.tenant_id,
                DailyReport.report_date == report_date,
                DailyReport.raw_input_text == req.raw_text,
                DailyReport.deleted_at.is_(None),
            )
        )
        .limit(1)
    )
    if dup_check.scalar():
        raise HTTPException(
            status_code=409,
            detail="该内容今天已经提交过，请勿重复提交。如需修改，请更新内容后再提交。",
        )

    allowed = await check_daily_quota(db)
    if not allowed:
        raise HTTPException(status_code=429, detail="今日 AI 处理配额已满，请稍后再试。")

    ai_result, p_tokens, c_tokens = await parse_report_with_ai(
        req.raw_text,
        [],
        job_title=current_user.job_title,
        department=current_user.department,
    )
    await log_token_usage(db, str(current_user.id), p_tokens, c_tokens)

    if not ai_result.pass_check:
        await notify_safe(
            db,
            template=NotificationTemplate.report_rejected,
            context={
                "name": current_user.name,
                "reason": ai_result.reject_reason or "",
                "guidance": ai_result.suggested_guidance or "",
            },
            channels=[
                NotificationChannel.in_app,
                NotificationChannel.wechat,
                NotificationChannel.dingtalk,
            ],
            user=current_user,
            related_type="report_rejected",
        )
        await db.commit()
        return {
            "status": "rejected",
            "user_name": current_user.name,
            "department": current_user.department,
            "ai_score": ai_result.ai_score,
            "pass_check": False,
            "ai_comment": ai_result.ai_comment,
            "reject_reason": ai_result.reject_reason,
            "suggested_guidance": ai_result.suggested_guidance,
            "parsed_content": ai_result.parsed_content.model_dump(mode="json"),
            "management_alert": ai_result.management_alert,
            "tokens_used": {"prompt": p_tokens, "completion": c_tokens},
        }

    report = DailyReport(
        user_id=current_user.id,
        report_date=report_date,
        raw_input_text=req.raw_text,
        media_urls=[],
        parsed_content=ai_result.parsed_content.model_dump(mode="json"),
        pass_check=ai_result.pass_check,
        reject_reason=ai_result.reject_reason,
        suggested_guidance=ai_result.suggested_guidance,
        ai_score=ai_result.ai_score,
        ai_comment=ai_result.ai_comment,
        management_alert=ai_result.management_alert,
        project_id=project_id,
        sprint_task_id=req.sprint_task_id,
        tenant_id=current_user.tenant_id,
        created_by=current_user.id,
    )
    db.add(report)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="该内容今天已经提交过，请勿重复提交。如需修改，请更新内容后再提交。",
        )

    if ai_result.management_alert and ai_result.parsed_content.blocker:
        alert = RiskAlert(
            report_id=report.id,
            user_id=current_user.id,
            alert_type="blocker",
            description=ai_result.management_alert,
            tenant_id=current_user.tenant_id,
            created_by=current_user.id,
        )
        db.add(alert)

        await notify_safe(
            db,
            template=NotificationTemplate.risk_alert,
            context={
                "name": current_user.name,
                "department": current_user.department,
                "alert_type": "blocker",
                "description": ai_result.management_alert,
                "days_unresolved": 1,
            },
            channels=[
                NotificationChannel.wechat_bot,
                NotificationChannel.dingtalk_bot,
            ],
            user=current_user,
            related_type="risk_alert",
            related_id=str(report.id),
        )

    await notify_safe(
        db,
        template=NotificationTemplate.report_passed,
        context={
            "name": current_user.name,
            "score": ai_result.ai_score,
            "comment": ai_result.ai_comment or "",
        },
        channels=[NotificationChannel.in_app],
        user=current_user,
        related_type="report_passed",
        related_id=str(report.id),
    )

    kr_updates = await extract_and_update_kr_progress_safe(
        db,
        report=report,
        raw_text=req.raw_text,
    )

    await db.commit()

    return {
        "status": "ok",
        "report_id": str(report.id),
        "user_name": current_user.name,
        "department": current_user.department,
        "ai_score": ai_result.ai_score,
        "pass_check": True,
        "ai_comment": ai_result.ai_comment,
        "parsed_content": ai_result.parsed_content.model_dump(mode="json"),
        "management_alert": ai_result.management_alert,
        "tokens_used": {"prompt": p_tokens, "completion": c_tokens},
        "kr_updates": kr_updates,
        "project_id": str(report.project_id) if report.project_id else None,
        "sprint_task_id": str(report.sprint_task_id) if report.sprint_task_id else None,
    }


@router.get("")
@router.get("/")
async def list_reports(
    report_date: Optional[date] = Query(None, description="按日期筛选"),
    user_name: Optional[str] = Query(None, description="按姓名模糊搜索"),
    pass_check: Optional[str] = Query(None, description="按质检结果筛选: true/false"),
    include_deleted: bool = Query(False, description="V2.4 Stage 3 C4:仅 admin,true 时仅返回已软删的"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    分页查询日报列表：
    - 管理员/经理：查看所有人的日报
    - 普通员工：只能查看自己的日报
    - V2.4 Stage 3 C4:admin 可传 include_deleted=true 仅看已软删(回收站)
    """
    from sqlalchemy import func

    # V2.4 Stage 3 C4:include_deleted=true 仅 admin 生效;非 admin 强制 fallback
    show_deleted = include_deleted and current_user.role == UserRole.admin
    # 显式类型注释,避免 SQLAlchemy ColumnElement / BinaryExpression 推断混杂导致 mypy 不让 append
    conditions: list[Any] = (
        [DailyReport.deleted_at.is_not(None)] if show_deleted else [DailyReport.deleted_at.is_(None)]
    )  # V2.4 Stage 2:默认过滤软删
    conditions.append(DailyReport.tenant_id == current_user.tenant_id)
    conditions.append(User.tenant_id == current_user.tenant_id)
    # 员工只能看自己的
    if current_user.role == UserRole.employee:
        conditions.append(DailyReport.user_id == current_user.id)
    if report_date:
        conditions.append(DailyReport.report_date == report_date)
    if pass_check is not None and pass_check != "":
        conditions.append(DailyReport.pass_check == (pass_check == "true"))

    # 基础查询 — V2.2 起 LEFT JOIN projects + sprint_tasks 拿名称
    stmt = (
        select(
            DailyReport,
            User.name,
            User.department,
            Project.name.label("project_name"),
            Project.code.label("project_code"),
            SprintTask.title.label("sprint_task_title"),
        )
        .join(User, DailyReport.user_id == User.id)
        .outerjoin(Project, and_(DailyReport.project_id == Project.id, Project.tenant_id == current_user.tenant_id))
        .outerjoin(
            SprintTask,
            and_(DailyReport.sprint_task_id == SprintTask.id, SprintTask.tenant_id == current_user.tenant_id),
        )
    )
    count_stmt = (
        select(func.count(DailyReport.id))
        .join(User, DailyReport.user_id == User.id)
        .where(
            DailyReport.deleted_at.is_not(None) if show_deleted else DailyReport.deleted_at.is_(None)
        )  # V2.4 Stage 3 C4:依赖同样的 include_deleted 判断
    )
    if user_name:
        stmt = stmt.where(User.name.ilike(f"%{user_name}%"))
        count_stmt = count_stmt.where(User.name.ilike(f"%{user_name}%"))
    if conditions:
        stmt = stmt.where(and_(*conditions))
        count_stmt = count_stmt.where(and_(*conditions))

    # 总数
    total = (await db.execute(count_stmt)).scalar() or 0

    # 分页数据
    stmt = (
        stmt.order_by(DailyReport.report_date.desc(), DailyReport.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = (await db.execute(stmt)).all()
    items = [
        {
            "id": str(r.DailyReport.id),
            "member": r.name,
            "user_name": r.name,
            "department": r.department,
            "report_date": r.DailyReport.report_date,
            "pass_check": r.DailyReport.pass_check,
            "ai_score": r.DailyReport.ai_score,
            "parsed_content": r.DailyReport.parsed_content,
            "ai_comment": r.DailyReport.ai_comment,
            "raw_input_text": r.DailyReport.raw_input_text,
            "media_urls": r.DailyReport.media_urls,
            "created_at": r.DailyReport.created_at.isoformat() if r.DailyReport.created_at else None,
            # V2.2 结构化关联
            "project_id": str(r.DailyReport.project_id) if r.DailyReport.project_id else None,
            "project_name": r.project_name,
            "project_code": r.project_code,
            "sprint_task_id": str(r.DailyReport.sprint_task_id) if r.DailyReport.sprint_task_id else None,
            "sprint_task_title": r.sprint_task_title,
        }
        for r in rows
    ]
    return {"items": items, "total": total}


# V2.4 Stage 2:批量软删日报
@router.delete("/batch")
async def batch_soft_delete_reports(
    body: BatchDeleteBody = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量软删除日报(SET deleted_at = now())。

    权限规则:
    - admin / manager 可以删任意人的日报
    - employee 只能删自己的(server 端再校验一次,不信前端)

    返回:实际成功标记软删的条数(已被删的不会重复 deleted_at)
    """
    # 拼条件:已经软删过的不再动(避免覆盖时间戳)
    cond = and_(
        DailyReport.id.in_(body.ids),
        DailyReport.deleted_at.is_(None),
        DailyReport.tenant_id == current_user.tenant_id,
    )
    if current_user.role == UserRole.employee:
        # 员工只能删自己的
        cond = and_(cond, DailyReport.user_id == current_user.id)

    deleted_at = datetime.now(timezone.utc)
    result = await db.execute(update(DailyReport).where(cond).values(deleted_at=deleted_at).returning(DailyReport.id))
    deleted_ids = [r[0] for r in result.all()]
    if deleted_ids:
        await db.execute(
            update(RiskAlert)
            .where(
                RiskAlert.report_id.in_(deleted_ids),
                RiskAlert.deleted_at.is_(None),
                RiskAlert.tenant_id == current_user.tenant_id,
            )
            .values(deleted_at=deleted_at)
        )
    await record_soft_delete(
        db,
        actor_id=current_user.id,
        table_name="daily_reports",
        record_ids=deleted_ids,
        deleted_at=deleted_at,
        tenant_id=current_user.tenant_id,
    )
    await db.commit()

    return {
        "requested": len(body.ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": [str(i) for i in deleted_ids],
    }


# V2.4 Stage 3 C3:批量恢复日报
@router.patch("/batch-restore")
async def batch_restore_reports(
    body: BatchRestoreBody = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量恢复已软删日报(SET deleted_at = NULL)。

    权限规则:
    - admin / manager 可恢复任意人的日报
    - employee 只能恢复自己的(server 端再校验一次,不信前端)

    返回:实际成功恢复的条数(已 deleted_at IS NULL 的不会被重复恢复)
    """
    cond = and_(
        DailyReport.id.in_(body.ids),
        DailyReport.deleted_at.is_not(None),
        DailyReport.tenant_id == current_user.tenant_id,
    )
    if current_user.role == UserRole.employee:
        cond = and_(cond, DailyReport.user_id == current_user.id)

    result = await db.execute(update(DailyReport).where(cond).values(deleted_at=None).returning(DailyReport.id))
    restored_ids = [r[0] for r in result.all()]
    if restored_ids:
        await db.execute(
            update(RiskAlert)
            .where(
                RiskAlert.report_id.in_(restored_ids),
                RiskAlert.deleted_at.is_not(None),
                RiskAlert.tenant_id == current_user.tenant_id,
            )
            .values(deleted_at=None)
        )
    await mark_soft_delete_restored(
        db,
        table_name="daily_reports",
        record_ids=restored_ids,
        restored_by=current_user.id,
        tenant_id=current_user.tenant_id,
    )
    await db.commit()

    return {
        "requested": len(body.ids),
        "restored_count": len(restored_ids),
        "restored_ids": [str(i) for i in restored_ids],
    }


@router.get("/today-plan")
async def get_today_plan(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    T-1301:当前用户今日的晨规划列表(report_type='morning_plan')。

    向后兼容旧前端的 plan 字段,同时新增 items 数组供晚复核逐项对账。
    """

    today = date.today()
    rows = (
        await db.execute(
            select(
                DailyReport,
                Project.name.label("project_name"),
                SprintTask.title.label("sprint_task_title"),
            )
            .outerjoin(Project, and_(DailyReport.project_id == Project.id, Project.tenant_id == current_user.tenant_id))
            .outerjoin(
                SprintTask,
                and_(DailyReport.sprint_task_id == SprintTask.id, SprintTask.tenant_id == current_user.tenant_id),
            )
            .where(
                DailyReport.user_id == current_user.id,
                DailyReport.tenant_id == current_user.tenant_id,
                DailyReport.report_date == today,
                DailyReport.report_type == ReportType.morning_plan,
                DailyReport.deleted_at.is_(None),
            )
            .order_by(DailyReport.created_at.asc())
        )
    ).all()
    items = [
        {
            "id": str(row.DailyReport.id),
            "report_date": row.DailyReport.report_date,
            "project_id": str(row.DailyReport.project_id) if row.DailyReport.project_id else None,
            "project_name": row.project_name,
            "sprint_task_id": str(row.DailyReport.sprint_task_id) if row.DailyReport.sprint_task_id else None,
            "sprint_task_title": row.sprint_task_title,
            "work_tags": row.DailyReport.work_tags or [],
            "parsed_content": row.DailyReport.parsed_content,
            "raw_input_text": row.DailyReport.raw_input_text,
            "ai_score": row.DailyReport.ai_score,
            "ai_comment": row.DailyReport.ai_comment,
            "created_at": row.DailyReport.created_at.isoformat() if row.DailyReport.created_at else None,
        }
        for row in rows
    ]
    return {"plan": items[-1] if items else None, "items": items}


@router.get("/projects/my-active", response_model=MyActiveProjectsResponse)
async def get_my_active_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """T-1301:当前员工参与的 active 项目与进行中任务."""
    project_rows = (
        await db.execute(
            select(Project, ProjectMember.track, ProjectMember.role_in_project)
            .join(
                ProjectMember,
                and_(
                    ProjectMember.project_id == Project.id,
                    ProjectMember.user_id == current_user.id,
                    ProjectMember.left_at.is_(None),
                    ProjectMember.tenant_id == current_user.tenant_id,
                ),
            )
            .where(
                Project.status == ProjectStatus.active,
                Project.deleted_at.is_(None),
                Project.tenant_id == current_user.tenant_id,
            )
            .order_by(Project.is_temporary.desc(), Project.code.asc())
        )
    ).all()
    if not project_rows:
        return MyActiveProjectsResponse(projects=[], total_projects=0, total_tasks=0)

    project_ids = [row.Project.id for row in project_rows]
    task_rows = (
        await db.execute(
            select(SprintTask, Sprint.project_id)
            .join(Sprint, SprintTask.sprint_id == Sprint.id)
            .where(
                Sprint.project_id.in_(project_ids),
                SprintTask.assignee_id == current_user.id,
                SprintTask.status.in_([TaskStatus.todo, TaskStatus.in_progress, TaskStatus.blocked]),
                SprintTask.deleted_at.is_(None),
                SprintTask.tenant_id == current_user.tenant_id,
                Sprint.tenant_id == current_user.tenant_id,
            )
            .order_by(SprintTask.priority.asc(), SprintTask.planned_end.asc().nulls_last())
        )
    ).all()

    tasks_by_project: dict[uuid.UUID, list[MyActiveTaskItem]] = {}
    for row in task_rows:
        task = row.SprintTask
        tasks_by_project.setdefault(row.project_id, []).append(
            MyActiveTaskItem(
                id=task.id,
                title=task.title,
                status=task.status.value,
                priority=task.priority.value,
                story_points=task.story_points,
                planned_end=task.planned_end,
                is_on_critical_path=task.is_on_critical_path,
            )
        )

    projects = [
        MyActiveProjectItem(
            id=row.Project.id,
            code=row.Project.code,
            name=row.Project.name,
            health_status=row.Project.health_status.value,
            is_temporary=row.Project.is_temporary,
            member_track=row.track.value if hasattr(row.track, "value") else str(row.track),
            role_in_project=row.role_in_project,
            tasks=tasks_by_project.get(row.Project.id, []),
        )
        for row in project_rows
    ]
    total_tasks = sum(len(project.tasks) for project in projects)
    return MyActiveProjectsResponse(projects=projects, total_projects=len(projects), total_tasks=total_tasks)


@router.post("/morning-batch", response_model=MorningBatchResponse)
async def submit_morning_batch(
    body: MorningBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """T-1301:零选择晨规划批量提交."""
    inserted_ids: list[uuid.UUID] = []
    for item in body.items:
        project_id = await _validate_project_task_consistency(
            db,
            current_user,
            item.project_id,
            item.sprint_task_id,
        )
        raw_text = (
            f"[晨规划] {item.note or ''}".strip()
            if project_id or item.sprint_task_id
            else f"[晨规划/计划外] {item.note}"
        )
        report = DailyReport(
            user_id=current_user.id,
            report_date=body.report_date,
            raw_input_text=raw_text,
            media_urls=[],
            parsed_content={"tasks": item.note or "", "progress": 0, "report_type": "晨规划"},
            pass_check=True,
            ai_score=None,
            ai_comment=None,
            report_type=ReportType.morning_plan,
            work_tags=item.work_tags or [],
            project_id=project_id,
            sprint_task_id=item.sprint_task_id,
            tenant_id=current_user.tenant_id,
            created_by=current_user.id,
        )
        db.add(report)
        await db.flush()
        inserted_ids.append(report.id)
    await db.commit()
    return MorningBatchResponse(inserted=len(inserted_ids), report_ids=inserted_ids)


@router.post("/evening-batch", response_model=EveningBatchResponse)
async def submit_evening_batch(
    body: EveningBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """T-1301:晚复核对账、督导推送与旧督导闭环."""
    review_ids: list[uuid.UUID] = []
    extra_ids: list[uuid.UUID] = []
    supervised_created = 0
    supervised_closed = 0

    for review in body.reviews:
        parent_plan = await _load_owned_morning_plan(db, review.parent_report_id, current_user)
        review_report = DailyReport(
            user_id=current_user.id,
            report_date=body.report_date,
            raw_input_text=f"[晚复盘] {review.actual_note or ''}".strip(),
            media_urls=[],
            parsed_content={
                "tasks": review.actual_note or "",
                "progress": 100 if review.planned_status == PlannedStatus.done else 50,
                "report_type": "晚复盘",
            },
            pass_check=True,
            report_type=ReportType.evening_review,
            parent_plan_id=parent_plan.id,
            planned_status=review.planned_status,
            project_id=parent_plan.project_id,
            sprint_task_id=parent_plan.sprint_task_id,
            work_tags=parent_plan.work_tags or [],
            tenant_id=current_user.tenant_id,
            created_by=current_user.id,
        )
        db.add(review_report)
        await db.flush()
        review_ids.append(review_report.id)

        if review.planned_status in (PlannedStatus.partial, PlannedStatus.delayed):
            followup_id: uuid.UUID | None = None
            if parent_plan.project_id is not None:
                followup = ProjectFollowUp(
                    project_id=parent_plan.project_id,
                    content=f"[督导] {current_user.name}:{review.actual_note or '(无备注)'} — 来自 {body.report_date} 晚复核",
                    tenant_id=current_user.tenant_id,
                    created_by=current_user.id,
                )
                db.add(followup)
                await db.flush()
                followup_id = followup.id
            supervised = DailySupervisedTask(
                user_id=current_user.id,
                project_id=parent_plan.project_id,
                sprint_task_id=parent_plan.sprint_task_id,
                source_report_id=review_report.id,
                project_followup_id=followup_id,
                status=SupervisedStatus.open,
                tenant_id=current_user.tenant_id,
                created_by=current_user.id,
            )
            db.add(supervised)
            supervised_created += 1
        elif review.planned_status == PlannedStatus.done:
            match_conditions = []
            if parent_plan.sprint_task_id is not None:
                match_conditions.append(DailySupervisedTask.sprint_task_id == parent_plan.sprint_task_id)
            if parent_plan.project_id is not None:
                match_conditions.append(DailySupervisedTask.project_id == parent_plan.project_id)
            if match_conditions:
                stale_rows = (
                    (
                        await db.execute(
                            select(DailySupervisedTask).where(
                                DailySupervisedTask.user_id == current_user.id,
                                DailySupervisedTask.tenant_id == current_user.tenant_id,
                                DailySupervisedTask.status == SupervisedStatus.open,
                                or_(*match_conditions),
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                for stale in stale_rows:
                    stale.status = SupervisedStatus.closed
                    stale.closed_at = datetime.now(timezone.utc)
                    stale.closed_by_report_id = review_report.id
                    supervised_closed += 1

    for extra in body.extras:
        project_id = await _validate_project_task_consistency(
            db,
            current_user,
            extra.project_id,
            extra.sprint_task_id,
        )
        report = DailyReport(
            user_id=current_user.id,
            report_date=body.report_date,
            raw_input_text=f"[晚复盘/自主新增] {extra.note}",
            media_urls=[],
            parsed_content={"tasks": extra.note, "progress": 100, "report_type": "晚复盘"},
            pass_check=True,
            report_type=ReportType.ad_hoc,
            project_id=project_id,
            sprint_task_id=extra.sprint_task_id,
            work_tags=extra.work_tags or [],
            tenant_id=current_user.tenant_id,
            created_by=current_user.id,
        )
        db.add(report)
        await db.flush()
        extra_ids.append(report.id)

    await db.commit()
    return EveningBatchResponse(
        review_count=len(review_ids),
        extra_count=len(extra_ids),
        supervised_created=supervised_created,
        supervised_closed=supervised_closed,
        evening_report_ids=review_ids + extra_ids,
    )


@router.get("/pending-follow-ups", response_model=PendingFollowUpsResponse)
async def list_pending_follow_ups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """T-1301:次日晨规划顶置督导列表."""
    rows = (
        await db.execute(
            select(
                DailySupervisedTask,
                DailyReport,
                Project.name.label("project_name"),
                SprintTask.title.label("sprint_task_title"),
            )
            .join(DailyReport, DailySupervisedTask.source_report_id == DailyReport.id)
            .outerjoin(
                Project, and_(DailySupervisedTask.project_id == Project.id, Project.tenant_id == current_user.tenant_id)
            )
            .outerjoin(
                SprintTask,
                and_(
                    DailySupervisedTask.sprint_task_id == SprintTask.id, SprintTask.tenant_id == current_user.tenant_id
                ),
            )
            .where(
                DailySupervisedTask.user_id == current_user.id,
                DailySupervisedTask.tenant_id == current_user.tenant_id,
                DailySupervisedTask.status == SupervisedStatus.open,
            )
            .order_by(DailySupervisedTask.created_at.asc())
        )
    ).all()
    items = [
        PendingFollowUpItem(
            supervised_id=row.DailySupervisedTask.id,
            project_id=row.DailySupervisedTask.project_id,
            project_name=row.project_name,
            sprint_task_id=row.DailySupervisedTask.sprint_task_id,
            sprint_task_title=row.sprint_task_title,
            source_report_id=row.DailySupervisedTask.source_report_id,
            source_planned_status=row.DailyReport.planned_status or PlannedStatus.partial,
            source_note=row.DailyReport.raw_input_text,
            created_at=row.DailySupervisedTask.created_at,
        )
        for row in rows
    ]
    return PendingFollowUpsResponse(items=items, total=len(items))


async def _load_owned_morning_plan(
    db: AsyncSession,
    plan_id: uuid.UUID,
    user: User,
) -> DailyReport:
    """加载本人未删除的晨规划行;失败返回 404."""
    plan = (
        await db.execute(
            select(DailyReport).where(
                DailyReport.id == plan_id,
                DailyReport.user_id == user.id,
                DailyReport.tenant_id == user.tenant_id,
                DailyReport.report_type == ReportType.morning_plan,
                DailyReport.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if plan is None:
        raise HTTPException(status_code=404, detail="晨规划记录不存在或无权访问")
    return plan


@router.get("/{report_id}")
async def get_report_detail(
    report_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取单条日报详情（员工查自己的 / 管理层查任意人）。
    """
    result = await db.execute(
        select(
            DailyReport,
            User.name,
            User.department,
            Project.name.label("project_name"),
            Project.code.label("project_code"),
            SprintTask.title.label("sprint_task_title"),
        )
        .join(User, DailyReport.user_id == User.id)
        .outerjoin(Project, and_(DailyReport.project_id == Project.id, Project.tenant_id == current_user.tenant_id))
        .outerjoin(
            SprintTask,
            and_(DailyReport.sprint_task_id == SprintTask.id, SprintTask.tenant_id == current_user.tenant_id),
        )
        .where(
            DailyReport.id == report_id,
            DailyReport.tenant_id == current_user.tenant_id,
            User.tenant_id == current_user.tenant_id,
            DailyReport.deleted_at.is_(None),  # V2.4 Stage 2:软删的也不能查
        )
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="日报不存在")

    # 员工只能查自己的报告
    if current_user.role == UserRole.employee and row.DailyReport.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权查看他人日报")

    return {
        "id": str(row.DailyReport.id),
        "member": row.name,
        "department": row.department,
        "report_date": row.DailyReport.report_date,
        "raw_input_text": row.DailyReport.raw_input_text,
        "media_urls": row.DailyReport.media_urls,
        "parsed_content": row.DailyReport.parsed_content,
        "pass_check": row.DailyReport.pass_check,
        "reject_reason": row.DailyReport.reject_reason,
        "suggested_guidance": row.DailyReport.suggested_guidance,
        "ai_score": row.DailyReport.ai_score,
        "ai_comment": row.DailyReport.ai_comment,
        "management_alert": row.DailyReport.management_alert,
        "created_at": row.DailyReport.created_at.isoformat() if row.DailyReport.created_at else None,
        # V2.2 结构化关联
        "project_id": str(row.DailyReport.project_id) if row.DailyReport.project_id else None,
        "project_name": row.project_name,
        "project_code": row.project_code,
        "sprint_task_id": str(row.DailyReport.sprint_task_id) if row.DailyReport.sprint_task_id else None,
        "sprint_task_title": row.sprint_task_title,
    }
