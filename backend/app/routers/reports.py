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
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user
from app.models.daily_report import DailyReport
from app.models.project import Project
from app.models.sprint_task import SprintTask
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"], redirect_slashes=False)


# V2.4 Stage 2 批量软删请求体
class BatchDeleteBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200, description="待软删的日报 ID 列表")


# V2.4 Stage 3 C3:批量恢复请求体(撤销 / 回收站共用)
class BatchRestoreBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200, description="待恢复的日报 ID 列表")


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
        .outerjoin(Project, DailyReport.project_id == Project.id)
        .outerjoin(SprintTask, DailyReport.sprint_task_id == SprintTask.id)
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
    )
    if current_user.role == UserRole.employee:
        # 员工只能删自己的
        cond = and_(cond, DailyReport.user_id == current_user.id)

    result = await db.execute(
        update(DailyReport).where(cond).values(deleted_at=datetime.now(timezone.utc)).returning(DailyReport.id)
    )
    deleted_ids = [r[0] for r in result.all()]
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
    )
    if current_user.role == UserRole.employee:
        cond = and_(cond, DailyReport.user_id == current_user.id)

    result = await db.execute(update(DailyReport).where(cond).values(deleted_at=None).returning(DailyReport.id))
    restored_ids = [r[0] for r in result.all()]
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
    获取当前用户今日的晨规划记录（最近一条）。
    用于晚复核时展示对应的计划内容作为参考。
    """

    today = date.today()
    result = await db.execute(
        select(DailyReport)
        .where(
            and_(
                DailyReport.user_id == current_user.id,
                DailyReport.report_date == today,
                DailyReport.raw_input_text.like("[晨规划]%"),
                DailyReport.pass_check == True,
                DailyReport.deleted_at.is_(None),  # V2.4 Stage 2
            )
        )
        .order_by(DailyReport.created_at.desc())
        .limit(1)
    )
    plan = result.scalar_one_or_none()

    if not plan:
        return {"plan": None}

    return {
        "plan": {
            "id": str(plan.id),
            "report_date": plan.report_date,
            "parsed_content": plan.parsed_content,
            "raw_input_text": plan.raw_input_text,
            "ai_score": plan.ai_score,
            "ai_comment": plan.ai_comment,
            "created_at": plan.created_at.isoformat() if plan.created_at else None,
            # V2.2 结构化关联(供晚复核继承晨规划的项目/任务)
            "project_id": str(plan.project_id) if plan.project_id else None,
            "sprint_task_id": str(plan.sprint_task_id) if plan.sprint_task_id else None,
        }
    }


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
        .outerjoin(Project, DailyReport.project_id == Project.id)
        .outerjoin(SprintTask, DailyReport.sprint_task_id == SprintTask.id)
        .where(
            DailyReport.id == report_id,
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
