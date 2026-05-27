"""
app/services/deletion_cleanup.py — V2.6 软删过期清理 dry-run

Stage 3 只做 dry-run:统计 30 天过期软删对象与 FK 影响,写 audit_log 并通知 admin。
真正硬删要等 dry-run 观察期结束后再切换。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TypedDict

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.models.deletion_history import DeletionHistory
from app.models.knowledge import KnowledgeItem
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.risk_alert import RiskAlert
from app.models.sprint_task import SprintTask

DELETION_CLEANUP_RETENTION_DAYS = 30


class TableCounts(TypedDict):
    daily_reports: int
    projects: int
    sprint_tasks: int
    risk_alerts: int
    knowledge_items: int


class CascadeImpacts(TypedDict):
    risk_alerts_cascade_from_daily_reports: int
    daily_reports_detach_from_projects: int
    knowledge_items_detach_from_projects: int
    project_members_cascade_from_projects: int
    daily_reports_detach_from_sprint_tasks: int


class DeletionCleanupStats(TypedDict):
    mode: str
    retention_days: int
    generated_at: str
    cutoff: str
    tables: TableCounts
    impacts: CascadeImpacts
    open_history_batches: int
    total_candidates: int


async def _count(db: AsyncSession, stmt: Select[tuple[int]]) -> int:
    return int((await db.execute(stmt)).scalar() or 0)


def _count_stmt(model, *conditions) -> Select[tuple[int]]:
    return select(func.count()).select_from(model).where(*conditions)


async def build_deletion_cleanup_dry_run(
    db: AsyncSession,
    *,
    retention_days: int = DELETION_CLEANUP_RETENTION_DAYS,
    now: Optional[datetime] = None,
) -> DeletionCleanupStats:
    """返回 dry-run 统计结果;不修改任何业务表。"""
    effective_now = now or datetime.now(timezone.utc)
    cutoff = effective_now - timedelta(days=retention_days)

    report_candidates = select(DailyReport.id).where(
        DailyReport.deleted_at.is_not(None), DailyReport.deleted_at < cutoff
    )
    project_candidates = select(Project.id).where(
        Project.deleted_at.is_not(None),
        Project.deleted_at < cutoff,
        Project.is_temporary.is_(True),
    )
    task_candidates = select(SprintTask.id).where(SprintTask.deleted_at.is_not(None), SprintTask.deleted_at < cutoff)

    tables: TableCounts = {
        "daily_reports": await _count(
            db,
            _count_stmt(DailyReport, DailyReport.deleted_at.is_not(None), DailyReport.deleted_at < cutoff),
        ),
        "projects": await _count(
            db,
            _count_stmt(
                Project,
                Project.deleted_at.is_not(None),
                Project.deleted_at < cutoff,
                Project.is_temporary.is_(True),
            ),
        ),
        "sprint_tasks": await _count(
            db,
            _count_stmt(SprintTask, SprintTask.deleted_at.is_not(None), SprintTask.deleted_at < cutoff),
        ),
        "risk_alerts": await _count(
            db,
            _count_stmt(RiskAlert, RiskAlert.deleted_at.is_not(None), RiskAlert.deleted_at < cutoff),
        ),
        "knowledge_items": await _count(
            db,
            _count_stmt(KnowledgeItem, KnowledgeItem.deleted_at.is_not(None), KnowledgeItem.deleted_at < cutoff),
        ),
    }

    impacts: CascadeImpacts = {
        "risk_alerts_cascade_from_daily_reports": await _count(
            db,
            _count_stmt(RiskAlert, RiskAlert.report_id.in_(report_candidates)),
        ),
        "daily_reports_detach_from_projects": await _count(
            db,
            _count_stmt(DailyReport, DailyReport.project_id.in_(project_candidates)),
        ),
        "knowledge_items_detach_from_projects": await _count(
            db,
            _count_stmt(KnowledgeItem, KnowledgeItem.project_id.in_(project_candidates)),
        ),
        "project_members_cascade_from_projects": await _count(
            db,
            _count_stmt(ProjectMember, ProjectMember.project_id.in_(project_candidates)),
        ),
        "daily_reports_detach_from_sprint_tasks": await _count(
            db,
            _count_stmt(DailyReport, DailyReport.sprint_task_id.in_(task_candidates)),
        ),
    }

    open_history_batches = await _count(
        db,
        _count_stmt(
            DeletionHistory,
            DeletionHistory.expires_at < effective_now,
            DeletionHistory.restored_at.is_(None),
            DeletionHistory.hard_deleted_at.is_(None),
        ),
    )

    return {
        "mode": "dry_run",
        "retention_days": retention_days,
        "generated_at": effective_now.isoformat(),
        "cutoff": cutoff.isoformat(),
        "tables": tables,
        "impacts": impacts,
        "open_history_batches": open_history_batches,
        "total_candidates": (
            tables["daily_reports"]
            + tables["projects"]
            + tables["sprint_tasks"]
            + tables["risk_alerts"]
            + tables["knowledge_items"]
        ),
    }


def render_deletion_cleanup_dry_run_markdown(stats: dict[str, Any]) -> str:
    """把 dry-run 统计渲染成 admin 通知用 Markdown。"""
    tables = stats["tables"]
    impacts = stats["impacts"]
    return (
        "### 删除治理 Dry-run\n\n"
        f"**模式**: dry-run,不会硬删数据\n\n"
        f"**保留期**: {stats['retention_days']} 天\n\n"
        f"**候选截止时间**: `{stats['cutoff']}`\n\n"
        "#### 将清理对象\n\n"
        f"- 日报: {tables['daily_reports']} 条\n"
        f"- 临时项目: {tables['projects']} 个\n"
        f"- Sprint 任务: {tables['sprint_tasks']} 个\n"
        f"- 风险预警: {tables['risk_alerts']} 条\n"
        f"- 知识条目: {tables['knowledge_items']} 条\n"
        f"- 未恢复 deletion_history 批次: {stats['open_history_batches']} 批\n\n"
        "#### 关联影响\n\n"
        f"- 日报硬删将级联 RiskAlert: {impacts['risk_alerts_cascade_from_daily_reports']} 条\n"
        f"- 项目硬删将解绑日报项目关联: {impacts['daily_reports_detach_from_projects']} 条\n"
        f"- 项目硬删将解绑知识项目关联: {impacts['knowledge_items_detach_from_projects']} 条\n"
        f"- 项目硬删将级联项目成员关系: {impacts['project_members_cascade_from_projects']} 条\n"
        f"- 任务硬删将解绑日报任务关联: {impacts['daily_reports_detach_from_sprint_tasks']} 条\n\n"
        "观察期内请只看日志和审计记录,确认级联影响符合预期后再切真删。"
    )
