"""
app/services/health_engine.py — 日报→项目健康度聚合引擎

这是 AI-PM 系统从"微观日报"到"宏观项目状态"的核心桥梁。

调用时机：
  1. 每次日报通过质检落库后，异步触发（实时性好）
  2. Celery Beat 每日 00:30 全量重算所有活跃项目（保证一致性）

健康度计算公式（权重可在 .env 中配置）：
  health_score = avg(ai_score) × 0.50
               + avg(progress_pct) × 0.30
               + no_blocker_rate × 0.20

健康状态阈值：
  green  ≥ 75 且 无连续5天未解决的卡点
  yellow 50-74 或 存在连续3-4天未解决的卡点
  red    < 50  或 存在连续≥5天未解决的卡点
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.models.project import Project, ProjectHealthStatus
from app.models.project_member import ProjectMember
from app.models.project_stage import ProjectStage, StageHealthStatus
from app.models.risk_alert import RiskAlert
from app.models.sprint import Sprint


# ── 阈值常量 ─────────────────────────────────────────────────────
SCORE_GREEN_THRESHOLD  = 75
SCORE_YELLOW_THRESHOLD = 50
BLOCKER_YELLOW_DAYS    = 3   # 连续≥3天未解决 → yellow
BLOCKER_RED_DAYS       = 5   # 连续≥5天未解决 → red

# 健康度计算权重
W_AI_SCORE    = 0.50
W_PROGRESS    = 0.30
W_NO_BLOCKER  = 0.20


def _compute_health(
    avg_ai_score: float,
    avg_progress: float,
    no_blocker_rate: float,
    max_days_unresolved: int,
) -> tuple[int, ProjectHealthStatus]:
    """
    输入原始指标，返回 (health_score, health_status)
    """
    score = int(
        avg_ai_score    * W_AI_SCORE
        + avg_progress  * W_PROGRESS
        + no_blocker_rate * 100 * W_NO_BLOCKER
    )
    score = max(0, min(100, score))

    # 卡点天数优先降级
    if max_days_unresolved >= BLOCKER_RED_DAYS:
        return score, ProjectHealthStatus.red
    elif max_days_unresolved >= BLOCKER_YELLOW_DAYS:
        return score, ProjectHealthStatus.yellow
    # 分数阈值
    if score >= SCORE_GREEN_THRESHOLD:
        return score, ProjectHealthStatus.green
    elif score >= SCORE_YELLOW_THRESHOLD:
        return score, ProjectHealthStatus.yellow
    else:
        return score, ProjectHealthStatus.red


async def compute_stage_health(
    db: AsyncSession,
    stage: ProjectStage,
    window_days: int = 7,
) -> tuple[int, StageHealthStatus]:
    """
    基于最近 window_days 天，此阶段内所有成员日报，计算阶段健康度。
    返回 (health_score, health_status)
    """
    since = date.today() - timedelta(days=window_days)

    # 找出该项目此阶段的所有成员
    members_result = await db.execute(
        select(ProjectMember.user_id).where(
            ProjectMember.project_id == stage.project_id
        )
    )
    member_ids = [row[0] for row in members_result.all()]

    if not member_ids:
        return 100, StageHealthStatus.green

    # 聚合这些成员近期日报
    agg_result = await db.execute(
        select(
            func.avg(DailyReport.ai_score),
            func.avg(
                func.cast(
                    func.jsonb_extract_path_text(DailyReport.parsed_content, "progress"),
                    "float"
                )
            ),
            func.count(DailyReport.id),
            func.sum(
                func.cast(DailyReport.pass_check, "int")
            ),
        ).where(
            and_(
                DailyReport.user_id.in_(member_ids),
                DailyReport.report_date >= since,
                DailyReport.pass_check.is_not(None),
            )
        )
    )
    row = agg_result.first()
    avg_ai_score = float(row[0] or 0)
    avg_progress = float(row[1] or 0)
    total_reports = int(row[2] or 0)
    passed_reports = int(row[3] or 0)
    no_blocker_rate = passed_reports / max(total_reports, 1)

    # 查询未解决卡点中最长持续天数
    alert_result = await db.execute(
        select(func.max(RiskAlert.days_unresolved)).where(
            and_(
                RiskAlert.user_id.in_(member_ids),
                RiskAlert.status == "unresolved",
            )
        )
    )
    max_days = int(alert_result.scalar() or 0)

    health_score, health_status = _compute_health(
        avg_ai_score, avg_progress, no_blocker_rate, max_days
    )

    return health_score, StageHealthStatus(health_status.value)


async def refresh_project_health(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> None:
    """
    重新计算并持久化某个项目的健康度。
    1. 重算当前阶段的 health_score / health_status
    2. 将项目整体 health 设为当前阶段的健康度
    3. 检查预算是否超阈值
    """
    # 取当前阶段
    project_result = await db.execute(
        select(Project).where(Project.id == project_id)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        return

    stage_result = await db.execute(
        select(ProjectStage).where(
            and_(
                ProjectStage.project_id == project_id,
                ProjectStage.stage_number == project.current_stage,
            )
        )
    )
    stage = stage_result.scalar_one_or_none()
    if not stage:
        return

    # 重算阶段健康度
    score, health = await compute_stage_health(db, stage)
    stage.health_score = score
    stage.health_status = health

    # 更新项目健康度
    project.health_score = score
    project.health_status = ProjectHealthStatus(health.value)

    # 预算预警（超阈值时强制 yellow）
    if (project.budget_total and project.budget_spent
            and project.budget_spent / project.budget_total >= project.budget_alert_threshold
            and project.health_status == ProjectHealthStatus.green):
        project.health_status = ProjectHealthStatus.yellow

    await db.commit()


async def refresh_sprint_health(
    db: AsyncSession,
    sprint_id: uuid.UUID,
) -> None:
    """
    重算某个 Sprint 的健康度（基于 Sprint 期间成员日报聚合）。
    """
    sprint_result = await db.execute(select(Sprint).where(Sprint.id == sprint_id))
    sprint = sprint_result.scalar_one_or_none()
    if not sprint:
        return

    # 该 Sprint 期间所有软件轨成员
    members_result = await db.execute(
        select(ProjectMember.user_id).where(
            and_(
                ProjectMember.project_id == sprint.project_id,
                ProjectMember.track.in_(["software", "both"]),
            )
        )
    )
    member_ids = [row[0] for row in members_result.all()]
    if not member_ids:
        return

    agg_result = await db.execute(
        select(func.avg(DailyReport.ai_score)).where(
            and_(
                DailyReport.user_id.in_(member_ids),
                DailyReport.report_date >= sprint.start_date,
                DailyReport.report_date <= sprint.end_date,
            )
        )
    )
    avg_score = float(agg_result.scalar() or 100)
    sprint.health_score = int(min(100, max(0, avg_score)))
    await db.commit()
