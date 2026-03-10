"""
app/routers/reports.py — 日报 CRUD API

提供管理后台查询、手动创建、导出等功能。
员工提交走企微网关（wechat.py），此路由供管理端使用。
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role, get_current_user
from app.models.daily_report import DailyReport
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


@router.get("/")
async def list_reports(
    report_date: Optional[date] = Query(None, description="按日期筛选"),
    user_name: Optional[str] = Query(None, description="按姓名模糊搜索"),
    pass_check: Optional[str] = Query(None, description="按质检结果筛选: true/false"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    分页查询日报列表：
    - 管理员/经理：查看所有人的日报
    - 普通员工：只能查看自己的日报
    """
    from sqlalchemy import func

    conditions = []
    # 员工只能看自己的
    if current_user.role == UserRole.employee:
        conditions.append(DailyReport.user_id == current_user.id)
    if report_date:
        conditions.append(DailyReport.report_date == report_date)
    if pass_check is not None and pass_check != '':
        conditions.append(DailyReport.pass_check == (pass_check == 'true'))

    # 基础查询
    stmt = (
        select(DailyReport, User.name, User.department)
        .join(User, DailyReport.user_id == User.id)
    )
    count_stmt = (
        select(func.count(DailyReport.id))
        .join(User, DailyReport.user_id == User.id)
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
        stmt
        .order_by(DailyReport.report_date.desc(), DailyReport.created_at.desc())
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
        }
        for r in rows
    ]
    return {"items": items, "total": total}


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
        select(DailyReport, User.name, User.department)
        .join(User, DailyReport.user_id == User.id)
        .where(DailyReport.id == report_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="日报不存在")

    # 员工只能查自己的报告
    if (current_user.role == UserRole.employee and
            row.DailyReport.user_id != current_user.id):
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
    }
