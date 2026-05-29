"""
app/routers/milestones.py — Phase 14 里程碑与贡献积分 API
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.milestone_allocation import MilestoneAllocation
from app.models.project import Project, ProjectTrack
from app.models.project_member import MemberProjectRole, ProjectMember
from app.models.project_milestone import MilestoneStatus, ProjectMilestone
from app.models.user import User, UserRole
from app.schemas.milestone import (
    AllocationOut,
    AllocationProposalRequest,
    AllocationProposalResponse,
    AllocationRevertRequest,
    AllocationRevertResponse,
    LedgerEntryOut,
    LedgerHistoryResponse,
    MilestoneApprovalRequest,
    MilestoneApprovalResponse,
    MilestoneListResponse,
    MilestoneNodeIn,
    MilestoneOut,
    MilestonePatchRequest,
    MilestoneSeedRequest,
    MilestoneSeedResponse,
    MilestoneTemplateResponse,
    PeriodLiteral,
    UserContributionResponse,
)
from app.services.milestone_service import (
    approve_milestone,
    get_user_contribution,
    list_project_milestones,
    list_user_ledger,
    propose_allocations,
    revert_allocation,
    seed_project_milestones,
)
from app.services.milestone_template_service import get_standard_template

admin_router = APIRouter(prefix="/api/v1/admin/milestones", tags=["Milestones"])
project_router = APIRouter(prefix="/api/v1/projects", tags=["Milestones"])
me_router = APIRouter(prefix="/api/v1/me", tags=["Milestones"])

_admin_or_manager = require_role(UserRole.admin, UserRole.manager)
_admin_only = require_role(UserRole.admin)


def _service_error(exc: ValueError) -> HTTPException:
    detail = str(exc)
    if "不存在" in detail:
        return HTTPException(404, detail)
    if "重复" in detail or "已存在" in detail:
        return HTTPException(409, detail)
    return HTTPException(400, detail)


async def _load_project(db: AsyncSession, project_id: uuid.UUID, user: User) -> Project:
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.tenant_id == user.tenant_id,
                Project.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "项目不存在")
    return project


async def _load_milestone(
    db: AsyncSession,
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    user: User,
    *,
    for_update: bool = False,
) -> ProjectMilestone:
    await _load_project(db, project_id, user)
    query = select(ProjectMilestone).where(
        ProjectMilestone.id == milestone_id,
        ProjectMilestone.project_id == project_id,
        ProjectMilestone.deleted_at.is_(None),
    )
    if for_update:
        query = query.with_for_update()
    milestone = (await db.execute(query)).scalar_one_or_none()
    if milestone is None:
        raise HTTPException(404, "milestone 不存在")
    return milestone


async def _require_project_member(db: AsyncSession, project_id: uuid.UUID, user: User) -> Optional[ProjectMember]:
    await _load_project(db, project_id, user)
    if user.role in (UserRole.admin, UserRole.manager):
        return None

    member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
                ProjectMember.left_at.is_(None),
                ProjectMember.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(403, "仅项目成员可访问该里程碑")
    return member


async def _require_tech_lead(db: AsyncSession, project_id: uuid.UUID, user: User) -> None:
    await _load_project(db, project_id, user)
    if user.role == UserRole.admin:
        return

    member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user.id,
                ProjectMember.member_role == MemberProjectRole.tech_lead,
                ProjectMember.left_at.is_(None),
                ProjectMember.tenant_id == user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(403, "仅项目 tech_lead 或 admin 可分配贡献比例")


@admin_router.get("/templates", response_model=MilestoneTemplateResponse)
async def get_milestone_template(
    track: ProjectTrack = Query(...),
    is_temporary: bool = Query(False),
    _user: User = Depends(_admin_or_manager),
) -> MilestoneTemplateResponse:
    nodes = get_standard_template(track, is_temporary)
    return MilestoneTemplateResponse(track=track.value, is_temporary=is_temporary, nodes=nodes)


@admin_router.get("")
async def list_admin_milestones(
    status_filter: Optional[MilestoneStatus] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_admin_or_manager),
):
    query = (
        select(ProjectMilestone, Project.name.label("project_name"))
        .join(Project, ProjectMilestone.project_id == Project.id)
        .where(Project.tenant_id == admin.tenant_id)
        .where(Project.deleted_at.is_(None))
        .where(ProjectMilestone.deleted_at.is_(None))
        .order_by(ProjectMilestone.created_at.desc())
        .limit(200)
    )
    if status_filter is not None:
        query = query.where(ProjectMilestone.status == status_filter)

    rows = (await db.execute(query)).all()
    return {
        "items": [
            {
                **MilestoneOut.model_validate(row[0]).model_dump(mode="json"),
                "project_name": row[1],
            }
            for row in rows
        ]
    }


@project_router.post("/{project_id}/milestones/seed", response_model=MilestoneSeedResponse)
async def seed_milestones(
    project_id: uuid.UUID,
    payload: MilestoneSeedRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_admin_or_manager),
) -> MilestoneSeedResponse:
    await _load_project(db, project_id, user)
    try:
        milestones = await seed_project_milestones(db, project_id, payload.nodes, actor=user)
    except ValueError as exc:
        raise _service_error(exc) from exc
    await db.commit()
    return MilestoneSeedResponse(
        project_id=project_id,
        created=len(milestones),
        milestones=[MilestoneOut.model_validate(milestone) for milestone in milestones],
    )


@project_router.get("/{project_id}/milestones", response_model=MilestoneListResponse)
async def get_project_milestones(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MilestoneListResponse:
    await _require_project_member(db, project_id, user)
    milestones = await list_project_milestones(db, project_id)
    return MilestoneListResponse(
        project_id=project_id,
        items=[MilestoneOut.model_validate(milestone) for milestone in milestones],
    )


@project_router.post("/{project_id}/milestones", response_model=MilestoneOut)
async def create_project_milestone(
    project_id: uuid.UUID,
    payload: MilestoneNodeIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_admin_or_manager),
) -> ProjectMilestone:
    await _load_project(db, project_id, user)
    milestone = ProjectMilestone(
        project_id=project_id,
        node_type=payload.node_type,
        title=payload.title,
        description=payload.description,
        node_order=payload.node_order,
        initial_points=payload.initial_points,
        target_date=payload.target_date,
        status=MilestoneStatus.pending,
        created_by=user.id,
        tenant_id=user.tenant_id,
    )
    db.add(milestone)
    await db.commit()
    await db.refresh(milestone)
    return milestone


@project_router.patch("/{project_id}/milestones/{milestone_id}", response_model=MilestoneOut)
async def update_project_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: MilestonePatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_admin_or_manager),
) -> ProjectMilestone:
    milestone = await _load_milestone(db, project_id, milestone_id, user, for_update=True)
    if milestone.status != MilestoneStatus.pending:
        raise HTTPException(400, "仅 pending 里程碑可编辑")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(milestone, key, value)

    await db.commit()
    await db.refresh(milestone)
    return milestone


@project_router.delete("/{project_id}/milestones/{milestone_id}")
async def delete_project_milestone(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_admin_only),
):
    milestone = await _load_milestone(db, project_id, milestone_id, admin, for_update=True)
    if milestone.status not in (MilestoneStatus.pending, MilestoneStatus.void):
        raise HTTPException(400, "仅 pending/void 里程碑可作废")

    milestone.status = MilestoneStatus.void
    milestone.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {"message": "里程碑已作废", "milestone_id": str(milestone_id)}


@project_router.post("/{project_id}/milestones/{milestone_id}/request-review", response_model=MilestoneOut)
async def request_milestone_review(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectMilestone:
    await _require_project_member(db, project_id, user)
    milestone = await _load_milestone(db, project_id, milestone_id, user, for_update=True)
    if milestone.status != MilestoneStatus.pending:
        raise HTTPException(400, "仅 pending 里程碑可发起验收")

    milestone.status = MilestoneStatus.in_review
    milestone.requested_by = user.id
    milestone.requested_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(milestone)
    return milestone


@project_router.post(
    "/{project_id}/milestones/{milestone_id}/allocations",
    response_model=AllocationProposalResponse,
)
async def propose_milestone_allocations(
    project_id: uuid.UUID,
    milestone_id: uuid.UUID,
    payload: AllocationProposalRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AllocationProposalResponse:
    await _require_tech_lead(db, project_id, user)
    await _load_milestone(db, project_id, milestone_id, user)
    try:
        allocations = await propose_allocations(db, milestone_id, payload, proposer=user)
    except ValueError as exc:
        raise _service_error(exc) from exc
    await db.commit()
    return AllocationProposalResponse(
        milestone_id=milestone_id,
        allocations=[AllocationOut.model_validate(allocation) for allocation in allocations],
    )


@admin_router.post("/{milestone_id}/approve", response_model=MilestoneApprovalResponse)
async def approve_milestone_endpoint(
    milestone_id: uuid.UUID,
    payload: MilestoneApprovalRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_admin_only),
) -> MilestoneApprovalResponse:
    milestone = await db.get(ProjectMilestone, milestone_id)
    if milestone is None or milestone.deleted_at is not None:
        raise HTTPException(404, "milestone 不存在")

    project = await _load_project(db, milestone.project_id, admin)
    if project.tenant_id != admin.tenant_id:
        raise HTTPException(404, "milestone 不存在")

    try:
        approved, allocations, ledger_count = await approve_milestone(db, milestone_id, payload, approver=admin)
    except ValueError as exc:
        raise _service_error(exc) from exc
    await db.commit()
    return MilestoneApprovalResponse(
        milestone=MilestoneOut.model_validate(approved),
        allocations=[AllocationOut.model_validate(allocation) for allocation in allocations],
        ledger_entries_created=ledger_count,
    )


@admin_router.post("/allocations/{allocation_id}/revert", response_model=AllocationRevertResponse)
async def revert_milestone_allocation(
    allocation_id: uuid.UUID,
    payload: AllocationRevertRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(_admin_only),
) -> AllocationRevertResponse:
    allocation = await db.get(MilestoneAllocation, allocation_id)
    if allocation is None:
        raise HTTPException(404, "allocation 不存在")
    milestone = await db.get(ProjectMilestone, allocation.milestone_id)
    if milestone is None:
        raise HTTPException(404, "milestone 不存在")
    project = await _load_project(db, milestone.project_id, admin)

    try:
        reverted, ledger = await revert_allocation(db, allocation_id, payload.reason, actor=admin)
    except ValueError as exc:
        raise _service_error(exc) from exc
    await db.commit()

    ledger_out = LedgerEntryOut(
        id=ledger.id,
        user_id=ledger.user_id,
        milestone_id=ledger.milestone_id,
        milestone_title=milestone.title,
        project_id=milestone.project_id,
        project_name=project.name,
        allocation_id=ledger.allocation_id,
        direction=ledger.direction,
        amount=ledger.amount,
        occurred_at=ledger.occurred_at,
        reason=ledger.reason,
    )
    return AllocationRevertResponse(
        allocation=AllocationOut.model_validate(reverted),
        ledger_entry=ledger_out,
    )


@me_router.get("/contribution", response_model=UserContributionResponse)
async def get_my_contribution(
    period: PeriodLiteral = Query("all"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserContributionResponse:
    summary = await get_user_contribution(db, user.id, period)
    recent_ledger, _ = await list_user_ledger(db, user.id, limit=10)
    return UserContributionResponse(summary=summary, recent_ledger=recent_ledger)


@me_router.get("/contribution/ledger", response_model=LedgerHistoryResponse)
async def get_my_ledger(
    limit: int = Query(20, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> LedgerHistoryResponse:
    items, next_cursor = await list_user_ledger(db, user.id, limit=limit, cursor=cursor)
    return LedgerHistoryResponse(items=items, next_cursor=next_cursor)
