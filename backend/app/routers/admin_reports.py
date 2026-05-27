"""
app/routers/admin_reports.py — Phase 10 对外分组聚合 REST API

单端点:
  - GET /api/v1/admin/reports?group_by=department|project&project_id=&start_date=&end_date=

默认窗口:end_date 缺省 today();start_date 缺省 today() - 30 天。

错误码映射(service raise ValueError(str)):
  - "date_range_invalid" → 400 "start_date 不能晚于 end_date"
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.user import User, UserRole
from app.schemas.admin_reports import GroupBy, GroupedReportsResponse
from app.services.admin_reports_service import group_reports_by_department, group_reports_by_project

router = APIRouter(prefix="/api/v1/admin/reports", tags=["Admin Reports"])
_mgr_or_admin = require_role(UserRole.admin, UserRole.manager)


def _map_value_error(exc: ValueError) -> HTTPException:
    code = str(exc)
    if code == "date_range_invalid":
        return HTTPException(status_code=400, detail="start_date 不能晚于 end_date")
    return HTTPException(status_code=500, detail="未知错误")


@router.get("/", response_model=GroupedReportsResponse)
async def grouped_reports(
    group_by: GroupBy = Query(..., description="department 或 project"),
    project_id: Optional[uuid.UUID] = Query(None, description="可选项目过滤"),
    start_date: Optional[date] = Query(None, description="窗口起始日(含),默认 today-30"),
    end_date: Optional[date] = Query(None, description="窗口结束日(含),默认 today"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> GroupedReportsResponse:
    end_d = end_date or date.today()
    start_d = start_date or (end_d - timedelta(days=30))

    try:
        if group_by == "department":
            return await group_reports_by_department(db, start_d, end_d, project_id)
        return await group_reports_by_project(db, start_d, end_d, project_id)
    except ValueError as e:
        raise _map_value_error(e) from None
