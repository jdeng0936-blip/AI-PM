"""
app/routers/projects.py — 项目生命周期管理 API

核心端点：
  POST   /api/v1/projects/           立项（自动初始化5个 IPD 阶段）
  GET    /api/v1/projects/           项目列表
  GET    /api/v1/projects/overview   宏观总览（红绿黄健康矩阵）
  GET    /api/v1/projects/{id}       项目详情（含全部阶段）
  GET    /api/v1/projects/{id}/gantt 甘特图数据
  PATCH  /api/v1/stages/{id}         更新阶段进度/里程碑
  POST   /api/v1/projects/{id}/members 添加项目成员
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.milestone_allocation import AllocationStatus, MilestoneAllocation
from app.models.project import Project, ProjectHealthStatus, ProjectStatus
from app.models.project_followup import ProjectFollowUp
from app.models.project_member import MemberProjectRole, ProjectMember
from app.models.project_milestone import MilestoneStatus, ProjectMilestone
from app.models.project_stage import STAGE_DEFINITIONS_BY_TRACK, ProjectStage
from app.models.sprint import Sprint, SprintStatus
from app.models.user import User, UserRole
from app.schemas.project import (
    GanttStage,
    ProjectComplete,
    ProjectCreate,
    ProjectFollowUpCreate,
    ProjectFollowUpOut,
    ProjectMemberAdd,
    ProjectMemberInit,  # T-1105 新增
    ProjectMemberUpdate,
    ProjectUpdate,
    StageUpdate,
)
from app.services.deletion_history import mark_soft_delete_restored, record_soft_delete
from app.services.health_engine import refresh_project_health

router = APIRouter(prefix="/api/v1/projects", tags=["Projects (IPD)"])
stages_router = APIRouter(prefix="/api/v1/stages", tags=["Stages"])

_mgr = require_role(UserRole.manager, UserRole.admin)


def _enum_value(value):
    return getattr(value, "value", value)


def _project_visible_condition(current_user: User):
    conditions = [
        Project.tenant_id == current_user.tenant_id,
        Project.deleted_at.is_(None),
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
        conditions.append(Project.id.in_(visible_project_ids))
    return and_(*conditions)


async def _get_visible_project(
    db: AsyncSession,
    project_id: uuid.UUID,
    current_user: User,
    *,
    include_deleted: bool = False,
) -> Project:
    conditions = [
        Project.id == project_id,
        Project.tenant_id == current_user.tenant_id,
    ]
    if not include_deleted:
        conditions.append(Project.deleted_at.is_(None))
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
        conditions.append(Project.id.in_(visible_project_ids))

    project = (await db.execute(select(Project).where(and_(*conditions)))).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "项目不存在")
    return project


# V2.4 Stage 2 批量软删请求体
class ProjectBatchDeleteBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50, description="待软删的项目 ID 列表")


# V2.4 Stage 3 C3:批量恢复(仅临时项目)— 撤销 / 回收站共用
class ProjectBatchRestoreBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=50, description="待恢复的项目 ID 列表")


# V2.4 Stage 2:批量软删项目(仅允许临时工单项目;主干项目走 archive 路径)
@router.delete("/batch")
async def batch_soft_delete_projects(
    body: ProjectBatchDeleteBody = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(_mgr),
):
    """
    批量软删除项目。**严格只允许临时工单项目(is_temporary=true)**;
    若 ids 里含任何主干项目,整个请求被拒绝(400)避免歧义 — 主干项目
    请用 /api/v1/projects/{id} 单条 archive 接口。

    返回 deleted_count / non_temp_ids(被拒绝的主干 id 列表方便前端提示)
    """
    # 1. 检查 ids 中是否有非临时项目
    check = await db.execute(
        select(Project.id, Project.is_temporary, Project.deleted_at).where(
            Project.id.in_(body.ids),
            Project.tenant_id == user.tenant_id,
        )
    )
    rows = check.all()
    if not rows:
        raise HTTPException(404, "传入的项目 ID 都不存在")

    non_temp = [str(r[0]) for r in rows if not r[1]]
    if non_temp:
        raise HTTPException(
            400,
            {
                "message": "存在主干项目,不允许批量删除;请逐个走归档(archive)流程",
                "non_temp_ids": non_temp,
            },
        )

    # 2. 软删(已删的跳过)
    deleted_at = datetime.now(timezone.utc)
    result = await db.execute(
        update(Project)
        .where(
            Project.id.in_(body.ids),
            Project.is_temporary.is_(True),
            Project.deleted_at.is_(None),
            Project.tenant_id == user.tenant_id,
        )
        .values(deleted_at=deleted_at)
        .returning(Project.id)
    )
    deleted_ids = [r[0] for r in result.all()]
    await record_soft_delete(
        db,
        actor_id=user.id,
        table_name="projects",
        record_ids=deleted_ids,
        deleted_at=deleted_at,
        tenant_id=user.tenant_id,
    )
    await db.commit()

    return {
        "requested": len(body.ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": [str(i) for i in deleted_ids],
    }


# V2.4 Stage 3 C3:批量恢复已软删的临时项目
@router.patch("/batch-restore")
async def batch_restore_projects(
    body: ProjectBatchRestoreBody = Body(...),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_role(UserRole.admin)),
):
    """
    批量恢复已软删的临时项目(SET deleted_at = NULL)。
    仅 admin 可调;主干项目的"撤销归档"复用 unarchive_project 端点。
    """
    result = await db.execute(
        update(Project)
        .where(
            Project.id.in_(body.ids),
            Project.deleted_at.is_not(None),
            Project.is_temporary.is_(True),
            Project.tenant_id == admin.tenant_id,
        )
        .values(deleted_at=None)
        .returning(Project.id)
    )
    restored_ids = [r[0] for r in result.all()]
    await mark_soft_delete_restored(
        db,
        table_name="projects",
        record_ids=restored_ids,
        restored_by=admin.id,
        tenant_id=admin.tenant_id,
    )
    await db.commit()

    return {
        "requested": len(body.ids),
        "restored_count": len(restored_ids),
        "restored_ids": [str(i) for i in restored_ids],
    }


# V2.4 Stage 3 C4:回收站 — 列出已软删的临时项目(admin only)
@router.get("/deleted")
async def list_deleted_projects(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.admin)),
):
    """
    回收站列表:已软删的临时工单项目(deleted_at IS NOT NULL AND is_temporary=true)。
    主干项目的"已归档"由 /overview?include_archived=true 提供,不在此处。
    """
    rows = await db.execute(
        select(Project)
        .where(
            Project.deleted_at.is_not(None),
            Project.is_temporary.is_(True),
            Project.tenant_id == _admin.tenant_id,
        )
        .order_by(Project.deleted_at.desc())
    )
    items = rows.scalars().all()
    return {
        "items": [
            {
                "project_id": str(p.id),
                "name": p.name,
                "code": p.code,
                "track": p.track.value if p.track else None,
                "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None,
                "is_temporary": p.is_temporary,
            }
            for p in items
        ],
        "total": len(items),
    }


# ── 立项（自动初始化5个 IPD 阶段）────────────────────────────────
@router.post("/", include_in_schema=True)
@router.post("", include_in_schema=False)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    creator=Depends(_mgr),
):
    """
    立项并自动展开5个 IPD 阶段节点。
    每个阶段的计划时间从 planned_launch_date 倒推分配。
    """
    if data.planned_launch_date is None:
        raise HTTPException(400, "项目截止时间必填")
    if data.planned_launch_date < date.today():
        raise HTTPException(400, "项目截止时间不能早于今天")

    if not data.code:
        # 自动生成项目编号:
        #   主干项目: P{YYYY}-001 / P{YYYY}-002 ...
        #   临时工单项目(V2.3): P{YYYY}-T01 / P{YYYY}-T02 ...
        current_year = date.today().year
        if data.is_temporary:
            prefix = f"P{current_year}-T"
            stmt = (
                select(Project.code)
                .where(Project.code.like(f"{prefix}%"), Project.tenant_id == creator.tenant_id)
                .order_by(Project.code.desc())
                .limit(1)
            )
            res = await db.execute(stmt)
            max_code = res.scalar_one_or_none()
            if max_code:
                try:
                    num = int(max_code.split("-T")[1])
                    data.code = f"{prefix}{num + 1:02d}"
                except Exception:
                    data.code = f"{prefix}01"
            else:
                data.code = f"{prefix}01"
        else:
            prefix = f"P{current_year}-"
            stmt = (
                select(Project.code)
                .where(Project.code.like(f"{prefix}%"), Project.tenant_id == creator.tenant_id)
                .where(~Project.code.like(f"{prefix}T%"))  # 排除临时项目编号
                .order_by(Project.code.desc())
                .limit(1)
            )
            res = await db.execute(stmt)
            max_code = res.scalar_one_or_none()
            if max_code:
                try:
                    num = int(max_code.split("-")[1])
                    data.code = f"{prefix}{num + 1:03d}"
                except Exception:
                    data.code = f"{prefix}001"
            else:
                data.code = f"{prefix}001"
    else:
        # 防重复编号
        existing = await db.execute(
            select(Project).where(Project.code == data.code, Project.tenant_id == creator.tenant_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(400, f"项目编号 {data.code} 已存在")

    project = Project(
        name=data.name,
        code=data.code,
        description=data.description,
        track=data.track,
        planned_launch_date=data.planned_launch_date,
        budget_total=data.budget_total,
        contribution_total_points=data.contribution_total_points,
        budget_alert_threshold=data.budget_alert_threshold,
        is_temporary=data.is_temporary,
        # 健康度默认 green(主干项目首日就是 green;临时项目永远 green)
        health_status=ProjectHealthStatus.green,
        created_by=creator.id,
        tenant_id=creator.tenant_id,
    )
    db.add(project)
    await db.flush()  # 获取 project.id

    # T-1105 立项时一站式指派成员(主干 + 临时项目共享路径)
    # data.members 为 None / [] 时跳过,沿用零成员路径(向后兼容)
    if data.members:
        project_members: list[ProjectMemberInit] = data.members
        # 1. payload 内 user_id dedup 校验(同一 user_id 出现 2 次 -> 400)
        seen_user_ids: set[uuid.UUID] = set()
        for m in project_members:
            if m.user_id in seen_user_ids:
                await db.rollback()
                raise HTTPException(400, f"成员列表中重复的 user_id: {m.user_id}")
            seen_user_ids.add(m.user_id)

        # 2. 一次性校验 user_id 全部存在且同 tenant_id(零部分插入)
        existing_user_ids_q = await db.execute(
            select(User.id).where(
                User.id.in_(list(seen_user_ids)),
                User.tenant_id == creator.tenant_id,
            )
        )
        existing_user_ids = {row[0] for row in existing_user_ids_q.all()}
        missing_user_ids = seen_user_ids - existing_user_ids
        if missing_user_ids:
            await db.rollback()
            raise HTTPException(
                400,
                f"以下 user_id 不存在或不属于当前 tenant: {sorted(str(u) for u in missing_user_ids)}",
            )

        # 3. 批量插入 ProjectMember(单事务,失败整体 rollback)
        for m in project_members:
            db.add(
                ProjectMember(
                    project_id=project.id,
                    user_id=m.user_id,
                    track=m.track,
                    member_role=MemberProjectRole(m.member_role),
                    role_in_project=m.role_in_project,
                    tenant_id=creator.tenant_id,
                    created_by=creator.id,
                )
            )
        await db.flush()  # 让 partial UNIQUE (T-1002) 触发 IntegrityError 落到 router 异常处理

    if data.seed_milestones:
        from app.models.project import ProjectTrack
        from app.schemas.milestone import MilestoneNodeIn
        from app.services.milestone_service import seed_project_milestones
        from app.services.milestone_template_service import get_standard_template

        try:
            project_track = ProjectTrack(data.track)
        except ValueError as exc:
            await db.rollback()
            raise HTTPException(400, f"无效 track，允许值：{sorted(_VALID_TRACKS)}") from exc

        template_nodes = get_standard_template(project_track, data.is_temporary)
        nodes_in = [
            MilestoneNodeIn(
                node_type=node.node_type,
                title=node.title,
                node_order=node.node_order,
                initial_points=node.suggested_initial_points,
            )
            for node in template_nodes
        ]
        await seed_project_milestones(db, project.id, nodes_in, actor=creator)

    # ── V2.3 临时工单项目:走轻量路径 ──────────────────────────
    # 跳过 5 阶段 + 里程碑模板,只建一个 sprint_number=0 的虚拟"Backlog" Sprint
    # 让日报的 sprint_task_id 也能有归属(虽然实际任务为空)
    if data.is_temporary:
        today = date.today()
        backlog_sprint = Sprint(
            project_id=project.id,
            stage_id=None,  # 临时项目无 stage
            sprint_number=0,
            goal="Backlog (临时工单归集池)",
            start_date=today,
            end_date=today + timedelta(days=365),
            status=SprintStatus.active,
            created_by=creator.id,
            tenant_id=creator.tenant_id,
        )
        db.add(backlog_sprint)
        await db.commit()
        return {
            "message": "临时工单项目创建成功(轻量模式,无 IPD 阶段)",
            "project_id": str(project.id),
            "code": project.code,
            "is_temporary": True,
            "backlog_sprint_id": str(backlog_sprint.id),
            "members_added": len(data.members) if data.members else 0,  # T-1105 新增
            "contribution_total_points": project.contribution_total_points,
        }

    # ── 各阶段默认里程碑模板（按轨道区分）──────────────────
    DEFAULT_MILESTONES = {
        "software": {
            1: ["需求收集完成", "可行性分析", "立项评审 (G0)"],
            2: ["技术方案评审", "架构设计完成", "需求评审 (G1)", "设计评审 (G2)"],
            3: ["核心模块开发完成", "功能联调", "V1.0 内部发布", "中期检查"],
            4: ["集成测试完成", "Bug 清零", "试产评审 (G3)"],
            5: ["版本发布", "客户验收", "结项评审 (G4)", "项目归档"],
        },
        "hardware": {
            1: ["需求收集完成", "可行性分析", "立项评审 (G0)"],
            2: ["原理图评审", "BOM 定版", "需求评审 (G1)", "设计评审 (G2)"],
            3: ["PCB 打样完成", "贴片组装完成", "硬件调试通过", "中期检查"],
            4: ["整机测试完成", "认证送检", "试产评审 (G3)"],
            5: ["量产首批", "客户验收", "结项评审 (G4)", "项目归档"],
        },
        "dual": {
            1: ["需求收集完成", "可行性分析", "立项评审 (G0)"],
            2: ["技术方案评审", "原理图/架构设计完成", "需求评审 (G1)", "设计评审 (G2)"],
            3: ["软件V1.0完成", "硬件打样完成", "软硬联调", "中期检查"],
            4: ["集成测试完成", "问题清零", "试产评审 (G3)"],
            5: ["量产首批/版本发布", "客户验收", "结项评审 (G4)", "项目归档"],
        },
    }

    # 自动初始化5个阶段（按典型工期倒推日期，按轨道选择阶段名称）
    track_key = data.track if data.track in STAGE_DEFINITIONS_BY_TRACK else "dual"
    stage_defs = STAGE_DEFINITIONS_BY_TRACK[track_key]
    total_days = sum(d for _, _, _, d in stage_defs)
    stage_start = data.planned_launch_date - timedelta(days=total_days) if data.planned_launch_date else date.today()

    for num, name, track_str, duration in stage_defs:
        stage_end = stage_start + timedelta(days=duration - 1)

        # 为该阶段生成里程碑（日期均匀分布在阶段时间段内）
        ms_names = DEFAULT_MILESTONES[track_key].get(num, [])
        milestones = []
        for i, ms_name in enumerate(ms_names):
            if len(ms_names) > 1:
                offset = int(duration * (i + 1) / (len(ms_names) + 1))
            else:
                offset = duration // 2
            ms_date = stage_start + timedelta(days=offset)
            milestones.append(
                {
                    "name": ms_name,
                    "planned_date": ms_date.isoformat(),
                    "actual_date": None,
                    "status": "pending",
                }
            )

        stage = ProjectStage(
            project_id=project.id,
            stage_number=num,
            stage_name=name,
            track=track_str,
            planned_start=stage_start,
            planned_end=stage_end,
            health_status="green" if num == 1 else "locked",  # 仅第1阶段解锁
            milestones=milestones,
            tenant_id=creator.tenant_id,
        )
        db.add(stage)
        stage_start = stage_end + timedelta(days=1)

    await db.commit()
    return {
        "message": "项目创建成功，已自动初始化5个 IPD 阶段及里程碑",
        "project_id": str(project.id),
        "code": project.code,
        "members_added": len(data.members) if data.members else 0,  # T-1105 新增
        "contribution_total_points": project.contribution_total_points,
    }


# ── 项目总览（红绿黄健康矩阵）────────────────────────────────────
@router.get("/overview")
async def projects_overview(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    include_archived: bool = Query(default=False, description="是否包含已归档(cancelled)和已完成(completed)项目"),
    include_temporary: bool = Query(
        default=False,
        description="是否包含临时工单项目(V2.3,默认过滤,避免污染红黄绿矩阵)",
    ),
    health_status: Optional[str] = Query(default=None, description="按健康度过滤:green / yellow / red"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    管理层宏观视图：项目健康矩阵。
    默认展示 active + paused（仍在活跃管理的项目），不含临时工单项目。
    传 include_archived=true 可附带 cancelled + completed。
    传 include_temporary=true 可附带临时工单项目(用于"全部项目"视图,如 submit-report 下拉)。
    可选 health_status 按 green/yellow/red 过滤具体项目列表;
    三色计数始终基于"当前可见范围内的全表"统计，不受 health_status 影响。
    """
    from sqlalchemy import func

    # ── 1. status 过滤(可见范围)──────────────────────────────
    visible_statuses = [ProjectStatus.active, ProjectStatus.paused]
    if include_archived:
        visible_statuses += [ProjectStatus.cancelled, ProjectStatus.completed]

    # V2.4 Stage 2:overview 默认过滤掉软删项目(deleted_at IS NULL)
    # 三色聚合 + 列表查询都共用同一个 base_filter,自动继承
    base_filter = and_(
        Project.status.in_(visible_statuses),
        _project_visible_condition(current_user),
    )
    if not include_temporary:
        base_filter = and_(base_filter, Project.is_temporary.is_(False))

    # ── 2. 全表三色聚合(GROUP BY health_status)─────────────
    color_rows = await db.execute(
        select(Project.health_status, func.count(Project.id)).where(base_filter).group_by(Project.health_status)
    )
    color_map = {str(getattr(k, "value", k)): v for k, v in color_rows.all()}
    green_count = color_map.get("green", 0)
    yellow_count = color_map.get("yellow", 0)
    red_count = color_map.get("red", 0)
    total = (
        green_count
        + yellow_count
        + red_count
        + sum(v for k, v in color_map.items() if k not in {"green", "yellow", "red"})
    )

    # ── 3. 列表查询：可选 health_status 过滤 ───────────────────
    list_filter = base_filter
    if health_status:
        if health_status not in {"green", "yellow", "red"}:
            raise HTTPException(400, "health_status 仅支持 green / yellow / red")
        list_filter = and_(base_filter, Project.health_status == ProjectHealthStatus(health_status))

    offset = (page - 1) * page_size
    result = await db.execute(
        select(Project)
        .where(list_filter)
        .order_by(Project.health_score.asc())  # 最差的排最前
        .offset(offset)
        .limit(page_size)
    )
    projects = result.scalars().all()

    items = []
    for p in projects:
        # 拉取当前阶段信息
        stage_result = await db.execute(
            select(ProjectStage).where(
                and_(
                    ProjectStage.project_id == p.id,
                    ProjectStage.stage_number == p.current_stage,
                )
            )
        )
        stage = stage_result.scalar_one_or_none()

        today = date.today()
        days_to_deadline = (p.planned_launch_date - today).days if p.planned_launch_date else None
        delivery_overdue_days = abs(days_to_deadline) if days_to_deadline is not None and days_to_deadline < 0 else 0
        budget_pct = float(p.budget_spent / p.budget_total * 100) if p.budget_total and p.budget_spent else None
        member_rows = (
            await db.execute(
                select(ProjectMember, User.name, User.department, User.job_title)
                .join(User, ProjectMember.user_id == User.id)
                .where(
                    and_(
                        ProjectMember.project_id == p.id,
                        ProjectMember.left_at.is_(None),
                        ProjectMember.tenant_id == current_user.tenant_id,
                        User.tenant_id == current_user.tenant_id,
                    )
                )
                .order_by(ProjectMember.joined_at.asc())
            )
        ).all()
        member_items = [
            {
                "user_id": str(row.ProjectMember.user_id),
                "name": row.name,
                "department": row.department,
                "job_title": row.job_title,
                "track": _enum_value(row.ProjectMember.track),
                "role_in_project": row.ProjectMember.role_in_project,
                "member_role": _enum_value(row.ProjectMember.member_role),
            }
            for row in member_rows
        ]

        def is_project_owner(row) -> bool:
            member = row.ProjectMember
            if member.member_role in (MemberProjectRole.owner, MemberProjectRole.tech_lead):
                return True
            role_text = (member.role_in_project or "").lower()
            return any(token in role_text for token in ("负责人", "项目经理", "技术负责人", "owner", "lead", "pm"))

        owner_rows = [row for row in member_rows if is_project_owner(row)]
        owner_names = [row.name for row in owner_rows]

        milestone_rows = (
            (
                await db.execute(
                    select(ProjectMilestone)
                    .where(
                        and_(
                            ProjectMilestone.project_id == p.id,
                            ProjectMilestone.tenant_id == current_user.tenant_id,
                            ProjectMilestone.deleted_at.is_(None),
                        )
                    )
                    .order_by(ProjectMilestone.node_order.asc())
                )
            )
            .scalars()
            .all()
        )
        active_milestones = [m for m in milestone_rows if m.status != MilestoneStatus.void]
        open_milestones = [
            m for m in active_milestones if m.status in (MilestoneStatus.pending, MilestoneStatus.in_review)
        ]
        overdue_milestones = [m for m in open_milestones if m.target_date and m.target_date < today]
        current_node = None
        if open_milestones:
            current_node = sorted(
                open_milestones,
                key=lambda m: (
                    0 if m in overdue_milestones else 1 if m.status == MilestoneStatus.in_review else 2,
                    m.target_date or date.max,
                    m.node_order,
                ),
            )[0]

        current_node_payload = None
        if current_node:
            node_days_left = (current_node.target_date - today).days if current_node.target_date else None
            node_overdue_days = abs(node_days_left) if node_days_left is not None and node_days_left < 0 else 0
            allocation_rows = (
                await db.execute(
                    select(User.name)
                    .join(MilestoneAllocation, MilestoneAllocation.user_id == User.id)
                    .where(
                        and_(
                            MilestoneAllocation.milestone_id == current_node.id,
                            MilestoneAllocation.status != AllocationStatus.reverted,
                            MilestoneAllocation.tenant_id == current_user.tenant_id,
                            User.tenant_id == current_user.tenant_id,
                        )
                    )
                    .order_by(User.department.asc(), User.name.asc())
                )
            ).all()
            node_owner_names = [row.name for row in allocation_rows]
            current_node_payload = {
                "id": str(current_node.id),
                "title": current_node.title,
                "status": _enum_value(current_node.status),
                "target_date": current_node.target_date,
                "days_left": node_days_left,
                "overdue_days": node_overdue_days,
                "owner_names": node_owner_names,
            }

        items.append(
            {
                "project_id": str(p.id),
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "current_stage": p.current_stage,
                "stage_name": stage.stage_name if stage else "—",
                "track": p.track,
                "health_status": p.health_status,
                "health_score": p.health_score,
                "progress_pct": stage.progress_pct if stage else 0,
                "planned_launch_date": p.planned_launch_date,
                "days_to_deadline": days_to_deadline,
                "delivery_overdue_days": delivery_overdue_days,
                "budget_total": (
                    str(p.budget_total)
                    if p.budget_total and current_user.role in (UserRole.admin, UserRole.manager)
                    else None
                ),
                "budget_usage_pct": (
                    round(budget_pct, 1)
                    if budget_pct and current_user.role in (UserRole.admin, UserRole.manager)
                    else None
                ),
                "contribution_total_points": p.contribution_total_points,
                "status": p.status,
                "is_temporary": p.is_temporary,
                "owner_names": owner_names,
                "members": member_items,
                "member_names": [member["name"] for member in member_items],
                "member_count": len(member_items),
                "milestone_summary": {
                    "total": len(active_milestones),
                    "approved": sum(1 for m in active_milestones if m.status == MilestoneStatus.approved),
                    "in_review": sum(1 for m in active_milestones if m.status == MilestoneStatus.in_review),
                    "pending": sum(1 for m in active_milestones if m.status == MilestoneStatus.pending),
                    "overdue": len(overdue_milestones),
                },
                "current_node": current_node_payload,
            }
        )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "red_count": red_count,
        "yellow_count": yellow_count,
        "green_count": green_count,
        "projects": items,
    }


# ── 项目详情 ──────────────────────────────────────────────────────
@router.get("/{project_id}")
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = await _get_visible_project(db, project_id, current_user)

    stages_result = await db.execute(
        select(ProjectStage)
        .where(ProjectStage.project_id == project_id, ProjectStage.tenant_id == current_user.tenant_id)
        .order_by(ProjectStage.stage_number)
    )
    stages = stages_result.scalars().all()

    return {
        "project": {
            "id": str(project.id),
            "code": project.code,
            "name": project.name,
            "description": project.description,
            "track": project.track,
            "current_stage": project.current_stage,
            "health_status": project.health_status,
            "health_score": project.health_score,
            "planned_launch_date": project.planned_launch_date,
            "budget_total": (
                str(project.budget_total)
                if project.budget_total and current_user.role in (UserRole.admin, UserRole.manager)
                else None
            ),
            "budget_spent": (
                str(project.budget_spent)
                if project.budget_spent and current_user.role in (UserRole.admin, UserRole.manager)
                else None
            ),
            "contribution_total_points": project.contribution_total_points,
            "status": project.status,
            "is_temporary": project.is_temporary,
        },
        "stages": [
            {
                "id": str(s.id),
                "stage_number": s.stage_number,
                "stage_name": s.stage_name,
                "track": s.track,
                "planned_start": s.planned_start,
                "planned_end": s.planned_end,
                "actual_start": s.actual_start,
                "actual_end": s.actual_end,
                "health_status": s.health_status,
                "progress_pct": s.progress_pct,
                "health_score": s.health_score,
                "gate_passed": s.gate_passed,
                "milestones": s.milestones or [],
            }
            for s in stages
        ],
    }


# ── 项目编辑（改名 / 改预算 / 改日期 / 改状态）─────────────────────
_VALID_STATUSES = {s.value for s in ProjectStatus}
_VALID_TRACKS = {"dual", "software", "hardware", "support", "other"}


@router.patch("/{project_id}")
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """
    更新项目基础信息。manager+ 权限。
    只更新传入的字段（部分更新语义）。
    """
    # V2.4 Stage 2:软删项目不能编辑
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.deleted_at.is_(None),
            Project.tenant_id == _user.tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    updates = data.model_dump(exclude_unset=True)

    if "status" in updates and updates["status"] not in _VALID_STATUSES:
        raise HTTPException(400, f"无效 status，允许值：{sorted(_VALID_STATUSES)}")
    if "track" in updates and updates["track"] not in _VALID_TRACKS:
        raise HTTPException(400, f"无效 track，允许值：{sorted(_VALID_TRACKS)}")

    target_status = updates.get("status")
    if "resolution_summary" in updates and updates["resolution_summary"] is not None:
        updates["resolution_summary"] = updates["resolution_summary"].strip()

    if not project.is_temporary and "resolution_summary" in updates:
        del updates["resolution_summary"]

    if project.is_temporary and target_status == ProjectStatus.completed.value:
        resolution_summary = updates.get("resolution_summary") or project.resolution_summary
        if not resolution_summary:
            raise HTTPException(400, "临时工单完工必须填写处理结果 resolution_summary")
        ProjectComplete(resolution_summary=resolution_summary)

    for k, v in updates.items():
        setattr(project, k, v)

    await db.commit()
    await db.refresh(project)
    if project.is_temporary and ("status" in updates or "resolution_summary" in updates):
        await refresh_project_health(db, project_id)
        await db.refresh(project)
    return {
        "message": "项目已更新",
        "project_id": str(project.id),
        "updated_fields": list(updates.keys()),
        "status": project.status,
    }


# ── 项目归档（软删除：status → cancelled）─────────────────────────
@router.delete("/{project_id}")
async def archive_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """
    归档（软删除）项目：将 status 置为 cancelled。
    保留所有历史数据（阶段、成员、日报关联等）。manager+ 权限。

    注:V2.4 Stage 2 起,主干项目仍走"归档(status=cancelled)"路径不动;
    临时工单项目走 deleted_at 软删,不走本接口。
    """
    # V2.4 Stage 2:已经被软删的项目不能再归档
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.deleted_at.is_(None),
            Project.tenant_id == _user.tenant_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    if project.status == ProjectStatus.cancelled:
        raise HTTPException(400, "项目已归档")

    project.status = ProjectStatus.cancelled
    await db.commit()
    return {"message": "项目已归档", "project_id": str(project_id)}


# ── 甘特图数据 ───────────────────────────────────────────────────
@router.get("/{project_id}/gantt")
async def get_gantt_data(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """
    返回可直接供前端甘特图组件使用的阶段+里程碑数据。
    推荐前端搭配 react-gantt-chart 或 dhtmlx-gantt 使用。
    """
    await _get_visible_project(db, project_id, _user)
    stages_result = await db.execute(
        select(ProjectStage)
        .where(ProjectStage.project_id == project_id, ProjectStage.tenant_id == _user.tenant_id)
        .order_by(ProjectStage.stage_number)
    )
    stages = stages_result.scalars().all()

    return [
        GanttStage(
            stage_number=s.stage_number,
            stage_name=s.stage_name,
            track=s.track,
            planned_start=s.planned_start,
            planned_end=s.planned_end,
            actual_start=s.actual_start,
            actual_end=s.actual_end,
            progress_pct=s.progress_pct,
            health_status=s.health_status,
            gate_passed=s.gate_passed,
            milestones=s.milestones or [],
        )
        for s in stages
    ]


# ── 项目跟进记录(T-1106) ─────────────────────────────────────────
@router.post("/{project_id}/followups", status_code=201)
async def create_project_followup(
    project_id: uuid.UUID,
    data: ProjectFollowUpCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await _get_visible_project(db, project_id, user)
    content = data.content.strip()
    if not content:
        raise HTTPException(400, "跟进内容不能为空")

    followup = ProjectFollowUp(
        project_id=project.id,
        content=content,
        tenant_id=user.tenant_id,
        created_by=user.id,
    )
    db.add(followup)
    await db.commit()
    await db.refresh(followup)

    if project.is_temporary:
        await refresh_project_health(db, project_id)

    return {
        "message": "跟进记录已创建",
        "id": str(followup.id),
        "project_id": str(followup.project_id),
        "content": followup.content,
        "created_by": str(followup.created_by) if followup.created_by else None,
        "created_at": followup.created_at,
    }


@router.get("/{project_id}/followups", response_model=list[ProjectFollowUpOut])
async def list_project_followups(
    project_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_visible_project(db, project_id, user)
    result = await db.execute(
        select(ProjectFollowUp, User.name)
        .outerjoin(User, ProjectFollowUp.created_by == User.id)
        .where(
            and_(
                ProjectFollowUp.project_id == project_id,
                ProjectFollowUp.tenant_id == user.tenant_id,
            )
        )
        .order_by(ProjectFollowUp.created_at.desc())
        .limit(limit)
    )
    return [
        ProjectFollowUpOut(
            id=str(followup.id),
            project_id=str(followup.project_id),
            content=followup.content,
            created_by=str(followup.created_by) if followup.created_by else None,
            created_by_name=created_by_name,
            created_at=followup.created_at,
        )
        for followup, created_by_name in result.all()
    ]


# ── 添加项目成员 ──────────────────────────────────────────────────
@router.post("/{project_id}/members")
async def add_project_member(
    project_id: uuid.UUID,
    data: ProjectMemberAdd,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    if data.project_id != project_id:
        raise HTTPException(400, "project_id 不一致")
    project = (
        await db.execute(
            select(Project).where(
                Project.id == project_id,
                Project.deleted_at.is_(None),
                Project.tenant_id == _user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if project is None:
        raise HTTPException(404, "项目不存在")
    target_user = (
        await db.execute(select(User).where(User.id == data.user_id, User.tenant_id == _user.tenant_id))
    ).scalar_one_or_none()
    if target_user is None:
        raise HTTPException(404, "用户不存在")
    existing = (
        await db.execute(
            select(ProjectMember.id).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == data.user_id,
                ProjectMember.left_at.is_(None),
                ProjectMember.tenant_id == _user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "该用户已在项目成员列表中")
    member = ProjectMember(
        project_id=project_id,
        user_id=data.user_id,
        track=data.track,
        member_role=MemberProjectRole(data.member_role),
        role_in_project=data.role_in_project,
        tenant_id=_user.tenant_id,
        created_by=_user.id,
    )
    db.add(member)
    await db.commit()
    return {"message": "成员已加入项目", "member_id": str(member.id)}


@router.patch("/{project_id}/members/{member_id}")
async def update_project_member(
    project_id: uuid.UUID,
    member_id: uuid.UUID,
    data: ProjectMemberUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    member = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.id == member_id,
                ProjectMember.project_id == project_id,
                ProjectMember.left_at.is_(None),
                ProjectMember.tenant_id == _user.tenant_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(404, "项目成员不存在")

    if data.track is not None:
        member.track = data.track
    if data.member_role is not None:
        member.member_role = MemberProjectRole(data.member_role)
    if data.role_in_project is not None:
        member.role_in_project = data.role_in_project.strip() or None

    await db.commit()
    return {
        "message": "成员角色已更新",
        "member_id": str(member.id),
        "member_role": _enum_value(member.member_role),
        "track": _enum_value(member.track),
        "role_in_project": member.role_in_project,
    }


# V2.5 Stage 2:批量移出项目成员(软退场 — SET left_at = today())
class BatchRemoveMembersBody(BaseModel):
    member_ids: list[uuid.UUID] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="待移出的 ProjectMember.id 列表(不是 user_id)",
    )


@router.delete("/{project_id}/members/batch")
async def batch_remove_members(
    project_id: uuid.UUID,
    body: BatchRemoveMembersBody = Body(...),
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """
    批量移出项目成员(软退场,SET left_at = today())。

    设计:
    - 用 ProjectMember.id(不是 user_id)— 同一用户可能挂多个 track 的成员关系,
      逐 row 处理更精确
    - 严格限定 project_id,防越权移其他项目成员
    - 已离场(left_at IS NOT NULL)的不重复处理,避免覆盖原始离场时间
    - 不动 daily_report.user_id / sprint_task.assignee_id 等历史关联,保留审计链
    - RBAC 即时收敛:所有 health_engine / gates / capacity 查询都已 left_at IS NULL 过滤,
      离场后该用户的日报立即不再聚合进项目健康度
    """
    cond = and_(
        ProjectMember.id.in_(body.member_ids),
        ProjectMember.project_id == project_id,
        ProjectMember.left_at.is_(None),
        ProjectMember.tenant_id == _user.tenant_id,
    )
    result = await db.execute(
        update(ProjectMember).where(cond).values(left_at=date.today()).returning(ProjectMember.id)
    )
    removed_ids = [r[0] for r in result.all()]
    await db.commit()
    return {
        "requested": len(body.member_ids),
        "removed_count": len(removed_ids),
        "removed_member_ids": [str(i) for i in removed_ids],
    }


@router.get("/{project_id}/members")
async def list_project_members(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    """项目团队成员列表"""
    from app.models.user import User

    await _get_visible_project(db, project_id, _user)
    result = await db.execute(
        select(ProjectMember, User.name, User.department)
        .join(User, ProjectMember.user_id == User.id)
        .where(
            and_(
                ProjectMember.project_id == project_id,
                ProjectMember.left_at.is_(None),
                ProjectMember.tenant_id == _user.tenant_id,
                User.tenant_id == _user.tenant_id,
            )
        )
        .order_by(ProjectMember.joined_at)
    )
    return [
        {
            "id": str(r.ProjectMember.id),
            "user_id": str(r.ProjectMember.user_id),
            "name": r.name,
            "department": r.department,
            "track": r.ProjectMember.track,
            "role_in_project": r.ProjectMember.role_in_project,
            "member_role": _enum_value(r.ProjectMember.member_role),
            "joined_at": str(r.ProjectMember.joined_at),
        }
        for r in result.all()
    ]


# ── 更新阶段进度/里程碑 ───────────────────────────────────────────
@stages_router.patch("/{stage_id}")
async def update_stage(
    stage_id: uuid.UUID,
    data: StageUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_mgr),
):
    result = await db.execute(
        select(ProjectStage).where(ProjectStage.id == stage_id, ProjectStage.tenant_id == _user.tenant_id)
    )
    stage = result.scalar_one_or_none()
    if not stage:
        raise HTTPException(404, "阶段不存在")

    if data.progress_pct is not None:
        stage.progress_pct = data.progress_pct
    if data.milestones is not None:
        stage.milestones = [m.model_dump(mode="json") for m in data.milestones]
        # 如果没有手动传 progress_pct，则根据里程碑完成状态自动计算
        if data.progress_pct is None and len(stage.milestones) > 0:
            done_count = sum(1 for m in stage.milestones if m.get("status") == "done")
            stage.progress_pct = int((done_count / len(stage.milestones)) * 100)
    if data.actual_start is not None:
        stage.actual_start = data.actual_start
    if data.actual_end is not None:
        stage.actual_end = data.actual_end

    await db.commit()

    # 如果阶段达到 100%，自动触发“轻量级敏捷流”：过门禁并解锁下一阶段，并将当前阶段健康状态置为完美绿色
    if stage.progress_pct == 100:
        # ORM column 推为 Enum union;运行时 SQLAlchemy 接受 str→Enum 自动转换
        stage.health_status = "green"  # type: ignore[assignment]
        stage.health_score = 100
        project_result = await db.execute(
            select(Project).where(Project.id == stage.project_id, Project.tenant_id == _user.tenant_id)
        )
        project = project_result.scalar_one_or_none()

        # 1. 自动写入对应的 GateReview 为 pass (假设门禁号和阶段号对应)
        from app.models.gate_review import GateReview

        existing_gate = await db.execute(
            select(GateReview).where(
                (GateReview.project_id == stage.project_id)
                & (GateReview.gate_number == stage.stage_number)
                & (GateReview.tenant_id == _user.tenant_id)
            )
        )
        if not existing_gate.scalar_one_or_none():
            db.add(
                GateReview(
                    project_id=stage.project_id,
                    gate_number=stage.stage_number,
                    gate_name=f"G{stage.stage_number} 自动评审",
                    decision="pass",
                    decision_notes="进度达到100%，轻量级敏捷流自动放行",
                    ai_summary="（系统自动流转）",
                    tenant_id=_user.tenant_id,
                    created_by=_user.id,
                )
            )

        # 2. 解锁下一阶段 (如果存在)
        if stage.stage_number < 5:
            next_stage_result = await db.execute(
                select(ProjectStage).where(
                    (ProjectStage.project_id == stage.project_id)
                    & (ProjectStage.stage_number == stage.stage_number + 1)
                    & (ProjectStage.tenant_id == _user.tenant_id)
                )
            )
            next_stage = next_stage_result.scalar_one_or_none()
            if next_stage and next_stage.health_status == "locked":
                next_stage.health_status = "green"  # type: ignore[assignment]

        # 3. 如果正在当前阶段，则自动把项目指针推向下一阶段
        if project and project.current_stage == stage.stage_number and project.current_stage < 5:
            project.current_stage += 1

        await db.commit()

    # 重算项目整体健康度
    await refresh_project_health(db, stage.project_id)

    return {"message": "阶段已更新", "stage_id": str(stage_id)}
