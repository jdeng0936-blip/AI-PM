"""
app/services/milestone_service.py — Phase 14 里程碑与贡献积分核心服务
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.milestone_allocation import AllocationStatus, MilestoneAllocation
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.project_milestone import MilestoneStatus, ProjectMilestone
from app.models.user import User
from app.models.user_points_ledger import LedgerDirection, UserPointsLedger
from app.schemas.milestone import (
    AllocationProposalRequest,
    ContributionSummary,
    LedgerEntryOut,
    MilestoneApprovalRequest,
    MilestoneNodeIn,
    PeriodLiteral,
)


def _rounded_points(points: int, ratio: Decimal) -> int:
    return int((Decimal(points) * ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


async def seed_project_milestones(
    db: AsyncSession,
    project_id: uuid.UUID,
    nodes: list[MilestoneNodeIn],
    actor: User,
) -> list[ProjectMilestone]:
    existing = await db.execute(
        select(func.count(ProjectMilestone.id)).where(ProjectMilestone.project_id == project_id)
    )
    if existing.scalar_one() > 0:
        raise ValueError("项目已存在里程碑,不可重复 seed")

    created: list[ProjectMilestone] = []
    for node in nodes:
        milestone = ProjectMilestone(
            project_id=project_id,
            node_type=node.node_type,
            title=node.title,
            description=node.description,
            node_order=node.node_order,
            initial_points=node.initial_points,
            target_date=node.target_date,
            status=MilestoneStatus.pending,
            created_by=actor.id,
            tenant_id=actor.tenant_id,
        )
        db.add(milestone)
        created.append(milestone)
    await db.flush()

    for milestone, node in zip(created, nodes):
        if node.planned_allocations:
            await propose_allocations(
                db,
                milestone.id,
                AllocationProposalRequest(allocations=node.planned_allocations),
                proposer=actor,
            )
    return created


async def list_project_milestones(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> list[ProjectMilestone]:
    result = await db.execute(
        select(ProjectMilestone)
        .where(ProjectMilestone.project_id == project_id)
        .where(ProjectMilestone.deleted_at.is_(None))
        .order_by(ProjectMilestone.node_order.asc(), ProjectMilestone.created_at.asc())
    )
    return list(result.scalars().all())


async def propose_allocations(
    db: AsyncSession,
    milestone_id: uuid.UUID,
    payload: AllocationProposalRequest,
    proposer: User,
) -> list[MilestoneAllocation]:
    milestone = await db.get(ProjectMilestone, milestone_id, with_for_update=True)
    if milestone is None or milestone.deleted_at is not None:
        raise ValueError("milestone 不存在")
    if milestone.status not in (MilestoneStatus.pending, MilestoneStatus.in_review):
        raise ValueError(f"milestone status={milestone.status},不在 pending/in_review 状态")

    await db.execute(
        delete(MilestoneAllocation)
        .where(MilestoneAllocation.milestone_id == milestone_id)
        .where(MilestoneAllocation.status == AllocationStatus.pending)
    )

    user_ids = [item.user_id for item in payload.allocations]
    members_result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == milestone.project_id)
        .where(ProjectMember.user_id.in_(user_ids))
        .where(ProjectMember.left_at.is_(None))
        .where(ProjectMember.tenant_id == proposer.tenant_id)
    )
    member_user_ids = {member.user_id for member in members_result.scalars().all()}
    missing = set(user_ids) - member_user_ids
    if missing:
        raise ValueError(f"以下 user_id 不是项目活跃成员:{missing}")

    now = datetime.now(timezone.utc)
    created: list[MilestoneAllocation] = []
    for item in payload.allocations:
        allocation = MilestoneAllocation(
            milestone_id=milestone_id,
            user_id=item.user_id,
            contribution_ratio=item.contribution_ratio,
            initial_points=_rounded_points(milestone.initial_points, item.contribution_ratio),
            status=AllocationStatus.pending,
            proposed_by=proposer.id,
            proposed_at=now,
            created_by=proposer.id,
            tenant_id=proposer.tenant_id,
        )
        db.add(allocation)
        created.append(allocation)
    await db.flush()
    return created


async def approve_milestone(
    db: AsyncSession,
    milestone_id: uuid.UUID,
    payload: MilestoneApprovalRequest,
    approver: User,
) -> tuple[ProjectMilestone, list[MilestoneAllocation], int]:
    milestone = await db.get(ProjectMilestone, milestone_id, with_for_update=True)
    if milestone is None or milestone.deleted_at is not None:
        raise ValueError("milestone 不存在")
    if milestone.status != MilestoneStatus.in_review:
        raise ValueError(f"milestone status={milestone.status},不在 in_review")
    if milestone.target_date is not None and milestone.target_date < date.today() and payload.final_points != 0:
        raise ValueError("里程碑已超出目标完成时间，按规则不得分；final_points 必须为 0")

    delta = payload.final_points - milestone.initial_points
    if delta != 0 and (not payload.adjustment_reason or not payload.adjustment_reason.strip()):
        raise ValueError("final_points 与 initial_points 不一致时必须填写 adjustment_reason")

    allocations_result = await db.execute(
        select(MilestoneAllocation)
        .where(MilestoneAllocation.milestone_id == milestone_id)
        .where(MilestoneAllocation.status == AllocationStatus.pending)
        .order_by(MilestoneAllocation.created_at.asc(), MilestoneAllocation.id.asc())
        .with_for_update()
    )
    allocations = list(allocations_result.scalars().all())
    if not allocations:
        raise ValueError("milestone 下无 pending allocations,无法终批")

    total_ratio = sum(allocation.contribution_ratio for allocation in allocations)
    if abs(total_ratio - Decimal("1")) > Decimal("0.0001"):
        raise ValueError(f"allocations 的 ratio 总和 != 1.0(实际:{total_ratio})")

    now = datetime.now(timezone.utc)
    milestone.status = MilestoneStatus.approved
    milestone.final_points = payload.final_points
    milestone.adjustment_reason = payload.adjustment_reason if delta != 0 else None
    milestone.approved_by = approver.id
    milestone.approved_at = now

    ledger_count = 0
    allocated_points = 0
    for index, allocation in enumerate(allocations):
        if index == len(allocations) - 1:
            allocation_final = payload.final_points - allocated_points
        else:
            allocation_final = _rounded_points(payload.final_points, allocation.contribution_ratio)
            allocated_points += allocation_final

        allocation.status = AllocationStatus.approved
        allocation.final_points = allocation_final

        if allocation_final == 0:
            continue

        ratio_pct = allocation.contribution_ratio * Decimal("100")
        ledger = UserPointsLedger(
            user_id=allocation.user_id,
            milestone_id=milestone.id,
            allocation_id=allocation.id,
            direction=LedgerDirection.income,
            amount=allocation_final,
            occurred_at=now,
            reason=f"里程碑[{milestone.title}]终批入账(比例 {ratio_pct:.2f}%)",
            created_by=approver.id,
            tenant_id=approver.tenant_id,
        )
        db.add(ledger)
        ledger_count += 1

    await db.flush()
    return milestone, allocations, ledger_count


async def revert_allocation(
    db: AsyncSession,
    allocation_id: uuid.UUID,
    reason: str,
    actor: User,
) -> tuple[MilestoneAllocation, UserPointsLedger]:
    allocation = await db.get(MilestoneAllocation, allocation_id, with_for_update=True)
    if allocation is None:
        raise ValueError("allocation 不存在")
    if allocation.status != AllocationStatus.approved:
        raise ValueError(f"仅 approved 状态可冲销;当前 status={allocation.status}")
    if allocation.final_points is None or allocation.final_points == 0:
        raise ValueError("final_points 为空或 0,无可冲销金额")

    now = datetime.now(timezone.utc)
    allocation.status = AllocationStatus.reverted
    allocation.reverted_at = now
    allocation.revert_reason = reason

    ledger = UserPointsLedger(
        user_id=allocation.user_id,
        milestone_id=allocation.milestone_id,
        allocation_id=allocation.id,
        direction=LedgerDirection.refund,
        amount=-allocation.final_points,
        occurred_at=now,
        reason=f"分配冲销:{reason}",
        created_by=actor.id,
        tenant_id=actor.tenant_id,
    )
    db.add(ledger)
    await db.flush()
    return allocation, ledger


async def get_user_contribution(
    db: AsyncSession,
    user_id: uuid.UUID,
    period: PeriodLiteral,
) -> ContributionSummary:
    window_start = _compute_period_start(period)

    total_query = select(func.coalesce(func.sum(UserPointsLedger.amount), 0)).where(UserPointsLedger.user_id == user_id)
    if window_start is not None:
        total_query = total_query.where(UserPointsLedger.occurred_at >= window_start)
    total_points = int((await db.execute(total_query)).scalar_one())

    by_direction_query = (
        select(
            UserPointsLedger.direction,
            func.coalesce(func.sum(UserPointsLedger.amount), 0).label("sum_amount"),
        )
        .where(UserPointsLedger.user_id == user_id)
        .group_by(UserPointsLedger.direction)
    )
    if window_start is not None:
        by_direction_query = by_direction_query.where(UserPointsLedger.occurred_at >= window_start)
    by_direction_rows = (await db.execute(by_direction_query)).all()
    by_direction = {row.direction: int(row.sum_amount) for row in by_direction_rows}

    milestone_count_query = (
        select(func.count(func.distinct(UserPointsLedger.milestone_id)))
        .where(UserPointsLedger.user_id == user_id)
        .where(UserPointsLedger.milestone_id.isnot(None))
    )
    if window_start is not None:
        milestone_count_query = milestone_count_query.where(UserPointsLedger.occurred_at >= window_start)
    milestone_count = int((await db.execute(milestone_count_query)).scalar_one())

    return ContributionSummary(
        user_id=user_id,
        period=period,
        total_points=total_points,
        income_points=by_direction.get(LedgerDirection.income, 0),
        refund_points=by_direction.get(LedgerDirection.refund, 0),
        adjustment_points=by_direction.get(LedgerDirection.adjustment, 0),
        milestone_count=milestone_count,
    )


def _compute_period_start(period: PeriodLiteral) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    if period == "all":
        return None
    if period == "year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "quarter":
        quarter_month = ((now.month - 1) // 3) * 3 + 1
        return now.replace(month=quarter_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


async def list_user_ledger(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 20,
    cursor: Optional[str] = None,
) -> tuple[list[LedgerEntryOut], Optional[str]]:
    query = (
        select(
            UserPointsLedger,
            ProjectMilestone.title.label("milestone_title"),
            ProjectMilestone.project_id.label("project_id"),
            Project.name.label("project_name"),
        )
        .outerjoin(ProjectMilestone, UserPointsLedger.milestone_id == ProjectMilestone.id)
        .outerjoin(Project, ProjectMilestone.project_id == Project.id)
        .where(UserPointsLedger.user_id == user_id)
        .order_by(UserPointsLedger.occurred_at.desc(), UserPointsLedger.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        try:
            query = query.where(UserPointsLedger.occurred_at < datetime.fromisoformat(cursor))
        except ValueError:
            pass

    rows = (await db.execute(query)).all()
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1][0].occurred_at.isoformat()
        rows = rows[:limit]

    items = [
        LedgerEntryOut(
            id=row[0].id,
            user_id=row[0].user_id,
            milestone_id=row[0].milestone_id,
            milestone_title=row[1],
            project_id=row[2],
            project_name=row[3],
            allocation_id=row[0].allocation_id,
            direction=row[0].direction,
            amount=row[0].amount,
            occurred_at=row[0].occurred_at,
            reason=row[0].reason,
        )
        for row in rows
    ]
    return items, next_cursor
