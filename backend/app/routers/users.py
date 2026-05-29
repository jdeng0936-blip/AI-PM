"""
app/routers/users.py — 用户管理 CRUD（仅 admin）
GET    /users           — 用户列表（分页 + 搜索）
POST   /users           — 新增用户
PUT    /users/{id}      — 修改用户
DELETE /users/{id}      — 停用用户（软删除）
POST   /users/{id}/reset-password — 重置密码
"""

import secrets
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.user import User, UserRole
from app.routers.auth import hash_password
from app.schemas.user import (
    UserCreate,
    UserCreateResponse,
    UserListResponse,
    UserOut,
    UserUpdate,
)

router = APIRouter(prefix="/api/v1/users", tags=["用户管理"])


# V2.4 Stage 2 批量启/停用请求体
class UserBatchBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=100, description="待操作的用户 ID 列表")


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="按姓名/部门/企微ID模糊搜索"),
    role: str = Query("", description="按角色筛选: admin/manager/employee"),  # V2.4 Stage 3 C2
    department: str = Query("", description="按部门精确匹配"),  # V2.4 Stage 3 C2
    is_active: str = Query("", description="按在职筛选: true/false/(空)"),  # V2.4 Stage 3 C2
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    """用户列表，分页 + 搜索 + 多维筛选(V2.4 Stage 3 C2)"""
    base_query = select(User)
    if search:
        like_pat = f"%{search}%"
        base_query = base_query.where(
            or_(
                User.name.ilike(like_pat),
                User.department.ilike(like_pat),
                User.wechat_userid.ilike(like_pat),
            )
        )

    # V2.4 Stage 3 C2:多维 query 筛选(role / department 支持 CSV 多选)
    if role:
        try:
            role_values = [UserRole(r.strip()) for r in role.split(",") if r.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效角色值: {role}")
        if role_values:
            base_query = base_query.where(User.role.in_(role_values))
    if department:
        dept_values = [d.strip() for d in department.split(",") if d.strip()]
        if dept_values:
            base_query = base_query.where(User.department.in_(dept_values))
    if is_active in ("true", "false"):
        base_query = base_query.where(User.is_active.is_(is_active == "true"))

    # 总数
    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    rows = await db.execute(base_query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size))
    users = rows.scalars().all()

    return UserListResponse(
        items=[
            UserOut(
                id=str(u.id),
                name=u.name,
                wechat_userid=u.wechat_userid,
                phone=u.phone,
                email=u.email,
                department=u.department,
                job_title=u.job_title,
                role=u.role.value,
                is_active=u.is_active,
                must_change_password=u.must_change_password,
                created_at=u.created_at,
                last_login_at=u.last_login_at,
                status=(u.status.value if hasattr(u.status, "value") else str(u.status)),
                status_until=u.status_until,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    """新增用户"""
    # 检查 wechat_userid 唯一
    existing = await db.execute(select(User).where(User.wechat_userid == req.wechat_userid))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"企微ID '{req.wechat_userid}' 已存在",
        )

    # 检查 phone 唯一
    if req.phone:
        existing_phone = await db.execute(select(User).where(User.phone == req.phone))
        if existing_phone.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"手机号 '{req.phone}' 已被使用",
            )

    initial_password = req.password or secrets.token_urlsafe(12)
    user = User(
        name=req.name,
        wechat_userid=req.wechat_userid,
        phone=req.phone,
        email=req.email,
        department=req.department,
        job_title=req.job_title,
        role=UserRole(req.role),
        hashed_password=hash_password(initial_password),
        must_change_password=True,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserCreateResponse(
        id=str(user.id),
        name=user.name,
        wechat_userid=user.wechat_userid,
        phone=user.phone,
        email=user.email,
        department=user.department,
        job_title=user.job_title,
        role=user.role.value,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        status=(user.status.value if hasattr(user.status, "value") else str(user.status)),
        status_until=user.status_until,
        temporary_password=initial_password if req.password is None else None,
    )


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    req: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    """修改用户信息"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if req.name is not None:
        user.name = req.name
    if req.phone is not None:
        user.phone = req.phone
    if req.department is not None:
        user.department = req.department
    if req.job_title is not None:
        user.job_title = req.job_title
    if req.role is not None:
        user.role = UserRole(req.role)
    if req.is_active is not None:
        user.is_active = req.is_active

    await db.commit()
    await db.refresh(user)

    return UserOut(
        id=str(user.id),
        name=user.name,
        wechat_userid=user.wechat_userid,
        phone=user.phone,
        email=user.email,
        department=user.department,
        job_title=user.job_title,
        role=user.role.value,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        status=(user.status.value if hasattr(user.status, "value") else str(user.status)),
        status_until=user.status_until,
    )


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    """停用用户（软删除）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.is_active = False
    await db.commit()
    return {"message": f"用户 '{user.name}' 已停用"}


# V2.4 Stage 2:批量禁用 / 启用用户(不允许真删,避免破坏 daily_report.user_id FK)
@router.post("/batch-disable")
async def batch_disable_users(
    body: UserBatchBody = Body(...),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """批量停用用户(SET is_active=false);historical daily_reports 不受影响。"""
    result = await db.execute(
        update(User).where(User.id.in_(body.ids), User.is_active.is_(True)).values(is_active=False).returning(User.id)
    )
    disabled_ids = [r[0] for r in result.all()]
    await db.commit()
    return {
        "requested": len(body.ids),
        "disabled_count": len(disabled_ids),
        "disabled_ids": [str(i) for i in disabled_ids],
    }


@router.post("/batch-enable")
async def batch_enable_users(
    body: UserBatchBody = Body(...),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    """批量启用用户(SET is_active=true)。仅 admin。"""
    result = await db.execute(
        update(User).where(User.id.in_(body.ids), User.is_active.is_(False)).values(is_active=True).returning(User.id)
    )
    enabled_ids = [r[0] for r in result.all()]
    await db.commit()
    return {
        "requested": len(body.ids),
        "enabled_count": len(enabled_ids),
        "enabled_ids": [str(i) for i in enabled_ids],
    }


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    """管理员重置用户密码为随机临时密码，并要求用户下次登录后改密。"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    temporary_password = secrets.token_urlsafe(12)
    user.hashed_password = hash_password(temporary_password)
    user.must_change_password = True
    await db.commit()
    return {
        "message": f"用户 '{user.name}' 密码已重置，请通知其尽快登录并修改密码",
        "temporary_password": temporary_password,
        "must_change_password": True,
    }


# ═══════════════════════════════════════════════════════════════════
# 请假/出差状态管理
# ═══════════════════════════════════════════════════════════════════


@router.patch("/{user_id}/status")
async def update_user_status(
    user_id: str,
    status: str = Query(..., description="状态: active/on_leave/on_travel/sick_leave"),
    status_until: str = Query(None, description="截止日期 YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """更新员工出勤状态（请假/出差/病假）"""
    from datetime import date

    from app.models.user import UserStatus

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    try:
        user.status = UserStatus(status)
    except ValueError:
        raise HTTPException(400, f"无效状态: {status}，可选: active/on_leave/on_travel/sick_leave")

    if status_until:
        user.status_until = date.fromisoformat(status_until)
    elif status == "active":
        user.status_until = None

    await db.commit()
    return {
        "message": f"用户 '{user.name}' 状态已更新为 {status}",
        "status": status,
        "status_until": str(user.status_until) if user.status_until else None,
    }


# ═══════════════════════════════════════════════════════════════════
# 资源负载水位
# ═══════════════════════════════════════════════════════════════════


@router.get("/resource-load")
async def get_resource_load(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """获取全员资源负载水位（故事点容量 vs 已分配）"""

    from app.models.project_member import ProjectMember

    users_result = await db.execute(select(User).where(User.is_active == True).order_by(User.department))
    users = users_result.scalars().all()

    load_data = []
    for u in users:
        # 计算当前 Sprint 已分配点数（简化：按项目成员数估算）
        # V2.5 Stage 2:仅统计当前在职项目数(已离场不计入"项目负载")
        member_result = await db.execute(
            select(func.count(ProjectMember.id)).where(
                ProjectMember.user_id == u.id,
                ProjectMember.left_at.is_(None),
            )
        )
        active_projects = member_result.scalar() or 0
        estimated_load = active_projects * 3  # 简化估算：每项目 3 点

        load_data.append(
            {
                "user_id": str(u.id),
                "name": u.name,
                "department": u.department,
                "job_title": u.job_title,
                "status": u.status.value if hasattr(u.status, "value") else str(u.status),
                "capacity": u.story_points_capacity,
                "estimated_load": estimated_load,
                "load_pct": round(estimated_load / max(u.story_points_capacity, 1) * 100, 1),
                "overloaded": estimated_load > u.story_points_capacity,
            }
        )

    overloaded_count = sum(1 for d in load_data if d["overloaded"])
    return {
        "total_members": len(load_data),
        "overloaded_count": overloaded_count,
        "members": load_data,
    }


# T-1105 立项指派成员用户选择器(轻量 + manager 可访问)
class UserPickerItem(BaseModel):
    """精简字段 - 用于立项 Modal / 项目成员追加场景的下拉选择器。"""

    id: str
    name: str
    department: str = ""
    role: str
    is_active: bool


@router.get("/picker", response_model=list[UserPickerItem])
async def list_users_for_picker(
    search: str = Query("", description="按姓名 / 部门 / 企微ID 模糊搜索"),
    include_inactive: bool = Query(False, description="是否包含已停用用户(默认 False)"),
    db: AsyncSession = Depends(get_db),
    _mgr: User = Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """
    立项指派成员 / 项目成员追加场景用户选择器。

    设计:
    - 与 `GET /users` 现有 admin-only 端点解耦:本端点 RBAC = admin + manager,
      避免 manager 立项时无法列用户的 RBAC gap
    - 字段精简到 id / name / department / role / is_active,降低数据传输量
    - 同 tenant_id 隔离(沿用 require_role 注入的 _mgr.tenant_id)
    - 默认过滤 is_active=True(立项不应指派已停用员工);可选 include_inactive=True
    - 不分页(一站式立项指派场景通常 <= 几百用户,前端可本地过滤)
    """
    stmt = select(User).where(User.tenant_id == _mgr.tenant_id)
    if not include_inactive:
        stmt = stmt.where(User.is_active.is_(True))
    if search:
        like_pat = f"%{search}%"
        stmt = stmt.where(
            or_(
                User.name.ilike(like_pat),
                User.department.ilike(like_pat),
                User.wechat_userid.ilike(like_pat),
            )
        )
    stmt = stmt.order_by(User.name)
    rows = await db.execute(stmt)
    return [
        UserPickerItem(
            id=str(u.id),
            name=u.name,
            department=u.department or "",
            role=u.role.value,
            is_active=u.is_active,
        )
        for u in rows.scalars().all()
    ]
