"""
app/services/admin_reports_service.py — Phase 10 对外分组聚合服务层

职责:
  - group_reports_by_department(): 按 User.department 聚合
  - group_reports_by_project(): 按 Project.id 聚合(自动 join Project,过滤已软删项目)

错误模型:
  - 不抛 Web 层异常(职责留给 router 层)
  - 仅 raise ValueError + str:
    - "date_range_invalid" → 400(start_date > end_date)
  - 数据库错误不在本服务捕获(让 SQLAlchemy 异常透传到全局 handler)

约束:
  - 全异步 AsyncSession
  - tenant_id 由 router 从当前用户注入,服务层不依赖全局租户常量。
  - 返回 Schema GroupedReportsResponse 实例(不暴露 ORM)
  - SQL 体例对齐 trends.py L77-122 的 4 项聚合 + dashboard.py L300-323 的 join 链
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.models.project import Project
from app.models.user import User
from app.schemas.admin_reports import GroupedReportsResponse, ReportGroupRow


def _validate_date_range(start_date: date, end_date: date) -> None:
    if start_date > end_date:
        raise ValueError("date_range_invalid")


def _row_to_group(key: str, report_count: int, avg_score: float, pass_count: int) -> ReportGroupRow:
    pass_rate = round(pass_count / max(report_count, 1) * 100, 1)
    return ReportGroupRow(
        key=key,
        report_count=int(report_count),
        avg_score=round(float(avg_score), 1),
        pass_count=int(pass_count),
        pass_rate=pass_rate,
    )


async def group_reports_by_department(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    project_id: Optional[uuid.UUID],
    tenant_id: str,
) -> GroupedReportsResponse:
    _validate_date_range(start_date, end_date)

    conditions = [
        DailyReport.report_date >= start_date,
        DailyReport.report_date <= end_date,
        DailyReport.deleted_at.is_(None),
        DailyReport.tenant_id == tenant_id,
        User.tenant_id == tenant_id,
    ]
    if project_id is not None:
        conditions.append(DailyReport.project_id == project_id)

    stmt = (
        select(
            User.department.label("key"),
            func.count(DailyReport.id).label("report_count"),
            func.coalesce(func.avg(DailyReport.ai_score), 0).label("avg_score"),
            func.count().filter(DailyReport.pass_check.is_(True)).label("pass_count"),
        )
        .join(User, DailyReport.user_id == User.id)
        .where(and_(*conditions))
        .group_by(User.department)
        .order_by(func.coalesce(func.avg(DailyReport.ai_score), 0).desc())
    )
    rows = (await db.execute(stmt)).all()
    groups = [_row_to_group(row.key or "", row.report_count, row.avg_score, row.pass_count) for row in rows]

    return GroupedReportsResponse(
        group_by="department",
        start_date=start_date,
        end_date=end_date,
        project_id=project_id,
        groups=groups,
    )


async def group_reports_by_project(
    db: AsyncSession,
    start_date: date,
    end_date: date,
    project_id: Optional[uuid.UUID],
    tenant_id: str,
) -> GroupedReportsResponse:
    _validate_date_range(start_date, end_date)

    conditions = [
        DailyReport.report_date >= start_date,
        DailyReport.report_date <= end_date,
        DailyReport.deleted_at.is_(None),
        DailyReport.tenant_id == tenant_id,
        Project.tenant_id == tenant_id,
        Project.deleted_at.is_(None),
    ]
    if project_id is not None:
        conditions.append(Project.id == project_id)

    stmt = (
        select(
            Project.id.label("key"),
            func.count(DailyReport.id).label("report_count"),
            func.coalesce(func.avg(DailyReport.ai_score), 0).label("avg_score"),
            func.count().filter(DailyReport.pass_check.is_(True)).label("pass_count"),
        )
        .join(Project, DailyReport.project_id == Project.id)
        .where(and_(*conditions))
        .group_by(Project.id)
        .order_by(func.coalesce(func.avg(DailyReport.ai_score), 0).desc())
    )
    rows = (await db.execute(stmt)).all()
    groups = [_row_to_group(str(row.key), row.report_count, row.avg_score, row.pass_count) for row in rows]

    return GroupedReportsResponse(
        group_by="project",
        start_date=start_date,
        end_date=end_date,
        project_id=project_id,
        groups=groups,
    )
