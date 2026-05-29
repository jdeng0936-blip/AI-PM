"""T-1401 tests: milestones and contribution points."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from importlib import import_module
from typing import Any, AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.middleware.rbac import create_access_token
from app.models.milestone_allocation import AllocationStatus, MilestoneAllocation
from app.models.project import Project, ProjectHealthStatus, ProjectStatus, ProjectTrack
from app.models.project_member import MemberProjectRole, MemberTrack, ProjectMember
from app.models.project_milestone import MilestoneNodeType, MilestoneStatus, ProjectMilestone
from app.models.user import User, UserRole
from app.models.user_points_ledger import LedgerDirection, UserPointsLedger
from app.schemas.milestone import (
    AllocationProposalRequest,
    MilestoneApprovalRequest,
    MilestoneNodeIn,
)
from app.services.milestone_service import (
    approve_milestone,
    get_user_contribution,
    list_user_ledger,
    propose_allocations,
    revert_allocation,
    seed_project_milestones,
)
from app.services.milestone_template_service import get_standard_template
from tests._db_url import derive_test_database_url

pytestmark = pytest.mark.asyncio

TENANT_ID = "default"
OTHER_TENANT_ID = "phase14_other"
PHASE14_PREFIX = "phase14"
TEST_DATABASE_URL = derive_test_database_url(settings.database_url)


async def _phase14_prepare_schema(conn: Any) -> None:
    await conn.execute(
        text(
            """
            DO $$ BEGIN
                CREATE TYPE member_project_role AS ENUM ('tech_lead', 'owner', 'member');
            EXCEPTION WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    await conn.execute(
        text(
            """
            ALTER TABLE IF EXISTS project_members
            ADD COLUMN IF NOT EXISTS member_role member_project_role NOT NULL DEFAULT 'member'
            """
        )
    )
    await conn.execute(
        text("CREATE INDEX IF NOT EXISTS ix_project_members_member_role ON project_members(member_role)")
    )


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _phase14_prepare_schema(conn)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        await _cleanup_phase14_test_data(session)
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()
            await _cleanup_phase14_test_data(session)
            await session.commit()
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app = import_module("app.main").app
    test_app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=cast(Any, test_app))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    test_app.dependency_overrides.clear()


async def _cleanup_phase14_test_data(db_session: AsyncSession) -> None:
    user_ids = select(User.id).where(User.wechat_userid.like(f"{PHASE14_PREFIX}_%"))
    project_ids = select(Project.id).where(Project.code.like(f"{PHASE14_PREFIX}_%"))
    milestone_ids = select(ProjectMilestone.id).where(ProjectMilestone.project_id.in_(project_ids))
    allocation_ids = select(MilestoneAllocation.id).where(MilestoneAllocation.milestone_id.in_(milestone_ids))

    await db_session.execute(
        delete(UserPointsLedger).where(
            or_(
                UserPointsLedger.user_id.in_(user_ids),
                UserPointsLedger.milestone_id.in_(milestone_ids),
                UserPointsLedger.allocation_id.in_(allocation_ids),
            )
        )
    )
    await db_session.execute(delete(MilestoneAllocation).where(MilestoneAllocation.id.in_(allocation_ids)))
    await db_session.execute(delete(ProjectMilestone).where(ProjectMilestone.id.in_(milestone_ids)))
    await db_session.execute(
        delete(ProjectMember).where(
            or_(
                ProjectMember.user_id.in_(user_ids),
                ProjectMember.project_id.in_(project_ids),
            )
        )
    )
    await db_session.execute(delete(Project).where(Project.id.in_(project_ids)))
    await db_session.execute(delete(User).where(User.id.in_(user_ids)))
    await db_session.flush()


def _phase14_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


async def _phase14_make_user(
    db_session: AsyncSession,
    *,
    suffix: str,
    role: UserRole = UserRole.employee,
    tenant_id: str = TENANT_ID,
) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"{PHASE14_PREFIX}_{suffix}",
        name=f"{PHASE14_PREFIX}_{suffix}",
        department="phase14_dept",
        job_title="工程师",
        role=role,
        is_active=True,
        tenant_id=tenant_id,
        must_change_password=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


async def _phase14_make_project(
    db_session: AsyncSession,
    *,
    creator: User,
    code: str,
    track: ProjectTrack = ProjectTrack.dual,
    tenant_id: str = TENANT_ID,
) -> Project:
    safe_code = code if len(code) <= 16 else f"{PHASE14_PREFIX}_{uuid.uuid4().hex[:8]}"
    project = Project(
        id=uuid.uuid4(),
        name=f"{safe_code}_project",
        code=safe_code,
        description="phase14 project",
        track=track,
        status=ProjectStatus.active,
        health_status=ProjectHealthStatus.green,
        health_score=100,
        tenant_id=tenant_id,
        created_by=creator.id,
    )
    db_session.add(project)
    await db_session.flush()
    await db_session.refresh(project)
    return project


async def _phase14_make_member(
    db_session: AsyncSession,
    *,
    project: Project,
    user: User,
    creator: User,
    member_role: MemberProjectRole = MemberProjectRole.member,
    tenant_id: str = TENANT_ID,
) -> ProjectMember:
    member = ProjectMember(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=user.id,
        track=MemberTrack.both,
        role_in_project="phase14_member",
        member_role=member_role,
        tenant_id=tenant_id,
        created_by=creator.id,
    )
    db_session.add(member)
    await db_session.flush()
    await db_session.refresh(member)
    return member


async def _phase14_make_milestone(
    db_session: AsyncSession,
    *,
    project: Project,
    creator: User,
    status: MilestoneStatus = MilestoneStatus.pending,
    initial_points: int = 100,
    tenant_id: str = TENANT_ID,
) -> ProjectMilestone:
    milestone = ProjectMilestone(
        id=uuid.uuid4(),
        project_id=project.id,
        node_type=MilestoneNodeType.software_mvp,
        title=f"{PHASE14_PREFIX}_milestone",
        node_order=1,
        initial_points=initial_points,
        status=status,
        tenant_id=tenant_id,
        created_by=creator.id,
    )
    db_session.add(milestone)
    await db_session.flush()
    await db_session.refresh(milestone)
    return milestone


async def _phase14_seed_ready_review(
    db_session: AsyncSession,
    *,
    suffix: str,
) -> tuple[User, User, User, Project, ProjectMilestone]:
    admin = await _phase14_make_user(db_session, suffix=f"{suffix}_admin", role=UserRole.admin)
    tech = await _phase14_make_user(db_session, suffix=f"{suffix}_tech")
    member = await _phase14_make_user(db_session, suffix=f"{suffix}_member")
    project = await _phase14_make_project(db_session, creator=admin, code=f"{PHASE14_PREFIX}_{suffix}")
    await _phase14_make_member(
        db_session, project=project, user=tech, creator=admin, member_role=MemberProjectRole.tech_lead
    )
    await _phase14_make_member(db_session, project=project, user=member, creator=admin)
    milestone = await _phase14_make_milestone(
        db_session, project=project, creator=admin, status=MilestoneStatus.in_review
    )
    return admin, tech, member, project, milestone


async def test_project_milestone_check_initial_points_non_negative(db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin = await _phase14_make_user(db_session, suffix="model_admin", role=UserRole.admin)
    project = await _phase14_make_project(db_session, creator=admin, code="phase14_model_a")
    bad = await _phase14_make_milestone(db_session, project=project, creator=admin)
    bad.initial_points = -1
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_milestone_allocation_ratio_check_between_0_and_1(db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin, tech, _, _, milestone = await _phase14_seed_ready_review(db_session, suffix="model_b")
    allocation = MilestoneAllocation(
        id=uuid.uuid4(),
        milestone_id=milestone.id,
        user_id=tech.id,
        contribution_ratio=Decimal("1.2000"),
        initial_points=120,
        status=AllocationStatus.pending,
        tenant_id=TENANT_ID,
        created_by=admin.id,
    )
    db_session.add(allocation)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_user_points_ledger_amount_check_not_zero(db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin = await _phase14_make_user(db_session, suffix="model_c", role=UserRole.admin)
    ledger = UserPointsLedger(
        id=uuid.uuid4(),
        user_id=admin.id,
        direction=LedgerDirection.income,
        amount=0,
        reason="zero",
        tenant_id=TENANT_ID,
        created_by=admin.id,
    )
    db_session.add(ledger)
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_member_project_role_enum_values_serialize() -> None:
    assert {role.value for role in MemberProjectRole} == {"tech_lead", "owner", "member"}


async def test_standard_template_software_returns_4_nodes() -> None:
    nodes = get_standard_template(ProjectTrack.software, is_temporary=False)
    assert [node.title for node in nodes] == ["需求文档完成", "MVP 完成", "功能验证通过", "正式上线/客户验收"]
    assert sum(node.suggested_initial_points for node in nodes) == 100


async def test_standard_template_dual_returns_7_nodes_with_offset_order() -> None:
    nodes = get_standard_template(ProjectTrack.dual, is_temporary=False)
    assert len(nodes) == 7
    assert [node.node_order for node in nodes] == [1, 2, 3, 4, 5, 6, 7]


async def test_standard_template_temporary_overrides_track() -> None:
    nodes = get_standard_template(ProjectTrack.dual, is_temporary=True)
    assert len(nodes) == 1
    assert nodes[0].node_type == MilestoneNodeType.temporary_done


async def test_seed_project_milestones_single_transaction(db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin = await _phase14_make_user(db_session, suffix="seed_admin", role=UserRole.admin)
    project = await _phase14_make_project(db_session, creator=admin, code="phase14_seed")
    nodes = [
        MilestoneNodeIn(node_type=MilestoneNodeType.software_req, title="需求", node_order=1, initial_points=10),
        MilestoneNodeIn(node_type=MilestoneNodeType.software_mvp, title="MVP", node_order=2, initial_points=30),
    ]
    created = await seed_project_milestones(db_session, project.id, nodes, actor=admin)
    await db_session.flush()
    count = await db_session.scalar(
        select(func.count()).select_from(ProjectMilestone).where(ProjectMilestone.project_id == project.id)
    )
    assert len(created) == 2
    assert int(count or 0) == 2


async def test_propose_allocations_rejects_sum_not_100() -> None:
    with pytest.raises(ValidationError):
        AllocationProposalRequest(
            allocations=[
                {"user_id": uuid.uuid4(), "contribution_ratio": Decimal("0.5000")},
                {"user_id": uuid.uuid4(), "contribution_ratio": Decimal("0.4000")},
            ]
        )


async def test_approve_milestone_writes_ledger_atomically(db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin, tech, member, _, milestone = await _phase14_seed_ready_review(db_session, suffix="approve_service")
    payload = AllocationProposalRequest(
        allocations=[
            {"user_id": tech.id, "contribution_ratio": Decimal("0.6000")},
            {"user_id": member.id, "contribution_ratio": Decimal("0.4000")},
        ]
    )
    await propose_allocations(db_session, milestone.id, payload, proposer=tech)
    approved, allocations, ledger_count = await approve_milestone(
        db_session,
        milestone.id,
        MilestoneApprovalRequest(final_points=120, adjustment_reason="超额完成"),
        approver=admin,
    )
    assert approved.status == MilestoneStatus.approved
    assert sum(allocation.final_points or 0 for allocation in allocations) == 120
    assert ledger_count == 2


async def test_revert_allocation_writes_refund(db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin, tech, member, _, milestone = await _phase14_seed_ready_review(db_session, suffix="revert_service")
    await propose_allocations(
        db_session,
        milestone.id,
        AllocationProposalRequest(
            allocations=[
                {"user_id": tech.id, "contribution_ratio": Decimal("0.5000")},
                {"user_id": member.id, "contribution_ratio": Decimal("0.5000")},
            ]
        ),
        proposer=tech,
    )
    _, allocations, _ = await approve_milestone(
        db_session,
        milestone.id,
        MilestoneApprovalRequest(final_points=100),
        approver=admin,
    )
    reverted, ledger = await revert_allocation(db_session, allocations[0].id, "录入错误", actor=admin)
    assert reverted.status == AllocationStatus.reverted
    assert ledger.direction == LedgerDirection.refund
    assert ledger.amount == -(allocations[0].final_points or 0)


async def test_cross_tenant_isolation_for_milestones(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin = await _phase14_make_user(db_session, suffix="tenant_admin", role=UserRole.admin)
    other = await _phase14_make_user(db_session, suffix="tenant_other", role=UserRole.admin, tenant_id=OTHER_TENANT_ID)
    project = await _phase14_make_project(db_session, creator=admin, code="phase14_tenant")
    await db_session.commit()
    response = await client.get(f"/api/v1/projects/{project.id}/milestones", headers=_phase14_headers(other))
    assert response.status_code == 404


async def test_get_templates_rbac_admin_only_returns_403_for_member(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase14_test_data(db_session)
    member = await _phase14_make_user(db_session, suffix="rbac_member")
    await db_session.commit()
    response = await client.get(
        "/api/v1/admin/milestones/templates?track=software&is_temporary=false",
        headers=_phase14_headers(member),
    )
    assert response.status_code == 403


async def test_post_seed_409_if_already_seeded(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin = await _phase14_make_user(db_session, suffix="seed_409", role=UserRole.admin)
    project = await _phase14_make_project(db_session, creator=admin, code="phase14_seed_409")
    await _phase14_make_milestone(db_session, project=project, creator=admin)
    await db_session.commit()
    response = await client.post(
        f"/api/v1/projects/{project.id}/milestones/seed",
        headers=_phase14_headers(admin),
        json={"nodes": [{"node_type": "software_req", "title": "需求", "node_order": 1, "initial_points": 10}]},
    )
    assert response.status_code == 409


async def test_patch_milestone_rejects_when_status_not_pending(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin = await _phase14_make_user(db_session, suffix="patch_admin", role=UserRole.admin)
    project = await _phase14_make_project(db_session, creator=admin, code="phase14_patch")
    milestone = await _phase14_make_milestone(
        db_session, project=project, creator=admin, status=MilestoneStatus.in_review
    )
    await db_session.commit()
    response = await client.patch(
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}",
        headers=_phase14_headers(admin),
        json={"title": "新标题"},
    )
    assert response.status_code == 400


async def test_request_review_only_project_member_can(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin = await _phase14_make_user(db_session, suffix="review_admin", role=UserRole.admin)
    outsider = await _phase14_make_user(db_session, suffix="review_outsider")
    project = await _phase14_make_project(db_session, creator=admin, code="phase14_review")
    milestone = await _phase14_make_milestone(db_session, project=project, creator=admin)
    await db_session.commit()
    response = await client.post(
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}/request-review",
        headers=_phase14_headers(outsider),
    )
    assert response.status_code == 403


async def test_propose_allocations_only_tech_lead_can_403_member(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin, _, member, project, milestone = await _phase14_seed_ready_review(db_session, suffix="lead_only")
    await db_session.commit()
    response = await client.post(
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}/allocations",
        headers=_phase14_headers(member),
        json={"allocations": [{"user_id": str(member.id), "contribution_ratio": "1.0000"}]},
    )
    assert admin.id
    assert response.status_code == 403


async def test_propose_allocations_422_if_sum_not_100(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    _, tech, member, project, milestone = await _phase14_seed_ready_review(db_session, suffix="sum_422")
    await db_session.commit()
    response = await client.post(
        f"/api/v1/projects/{project.id}/milestones/{milestone.id}/allocations",
        headers=_phase14_headers(tech),
        json={
            "allocations": [
                {"user_id": str(tech.id), "contribution_ratio": "0.5000"},
                {"user_id": str(member.id), "contribution_ratio": "0.4000"},
            ]
        },
    )
    assert response.status_code == 422


async def test_approve_milestone_requires_adjustment_reason_when_delta(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin, tech, member, project, milestone = await _phase14_seed_ready_review(db_session, suffix="reason")
    await propose_allocations(
        db_session,
        milestone.id,
        AllocationProposalRequest(
            allocations=[
                {"user_id": tech.id, "contribution_ratio": Decimal("0.5000")},
                {"user_id": member.id, "contribution_ratio": Decimal("0.5000")},
            ]
        ),
        proposer=tech,
    )
    await db_session.commit()
    assert project.id
    response = await client.post(
        f"/api/v1/admin/milestones/{milestone.id}/approve",
        headers=_phase14_headers(admin),
        json={"final_points": 120},
    )
    assert response.status_code == 400


async def test_approve_milestone_writes_ledger_for_all_members(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin, tech, member, _, milestone = await _phase14_seed_ready_review(db_session, suffix="approve_router")
    await propose_allocations(
        db_session,
        milestone.id,
        AllocationProposalRequest(
            allocations=[
                {"user_id": tech.id, "contribution_ratio": Decimal("0.5000")},
                {"user_id": member.id, "contribution_ratio": Decimal("0.5000")},
            ]
        ),
        proposer=tech,
    )
    await db_session.commit()
    response = await client.post(
        f"/api/v1/admin/milestones/{milestone.id}/approve",
        headers=_phase14_headers(admin),
        json={"final_points": 100},
    )
    assert response.status_code == 200
    assert response.json()["ledger_entries_created"] == 2


async def test_get_me_contribution_returns_period_total(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    admin, tech, member, _, milestone = await _phase14_seed_ready_review(db_session, suffix="me_summary")
    await propose_allocations(
        db_session,
        milestone.id,
        AllocationProposalRequest(
            allocations=[
                {"user_id": tech.id, "contribution_ratio": Decimal("0.7000")},
                {"user_id": member.id, "contribution_ratio": Decimal("0.3000")},
            ]
        ),
        proposer=tech,
    )
    await approve_milestone(db_session, milestone.id, MilestoneApprovalRequest(final_points=100), approver=admin)
    await db_session.commit()
    response = await client.get("/api/v1/me/contribution?period=all", headers=_phase14_headers(tech))
    assert response.status_code == 200
    assert response.json()["summary"]["total_points"] == 70


async def test_get_me_contribution_ledger_pagination_with_cursor(client: AsyncClient, db_session: AsyncSession) -> None:
    await _cleanup_phase14_test_data(db_session)
    user = await _phase14_make_user(db_session, suffix="ledger_user")
    for index in range(3):
        db_session.add(
            UserPointsLedger(
                id=uuid.uuid4(),
                user_id=user.id,
                direction=LedgerDirection.income,
                amount=index + 1,
                occurred_at=datetime.now(timezone.utc) + timedelta(seconds=index),
                reason=f"ledger {index}",
                tenant_id=TENANT_ID,
                created_by=user.id,
            )
        )
    await db_session.commit()
    first = await client.get("/api/v1/me/contribution/ledger?limit=2", headers=_phase14_headers(user))
    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]
    second = await client.get(
        "/api/v1/me/contribution/ledger",
        headers=_phase14_headers(user),
        params={"limit": 2, "cursor": body["next_cursor"]},
    )
    assert second.status_code == 200
    assert len(second.json()["items"]) >= 1
