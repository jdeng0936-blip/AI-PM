"""
app/routers/users.py — 用户管理 CRUD（仅 admin）
GET    /users           — 用户列表（分页 + 搜索）
POST   /users           — 新增用户
PUT    /users/{id}      — 修改用户
DELETE /users/{id}      — 停用用户（软删除）
POST   /users/{id}/reset-password — 重置密码
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import (
    UserCreate, UserUpdate, UserOut, UserListResponse,
)
from app.middleware.rbac import require_role
from app.routers.auth import hash_password

router = APIRouter(prefix="/api/v1/users", tags=["用户管理"])


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query("", description="按姓名/部门/企微ID模糊搜索"),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    """用户列表，分页 + 搜索"""
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

    # 总数
    count_q = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    rows = await db.execute(
        base_query
        .order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    users = rows.scalars().all()

    return UserListResponse(
        items=[
            UserOut(
                id=str(u.id), name=u.name, wechat_userid=u.wechat_userid,
                phone=u.phone, department=u.department, job_title=u.job_title,
                role=u.role.value, is_active=u.is_active,
                must_change_password=u.must_change_password,
                created_at=u.created_at, last_login_at=u.last_login_at,
            )
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    """新增用户"""
    # 检查 wechat_userid 唯一
    existing = await db.execute(
        select(User).where(User.wechat_userid == req.wechat_userid)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"企微ID '{req.wechat_userid}' 已存在",
        )

    # 检查 phone 唯一
    if req.phone:
        existing_phone = await db.execute(
            select(User).where(User.phone == req.phone)
        )
        if existing_phone.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"手机号 '{req.phone}' 已被使用",
            )

    user = User(
        name=req.name,
        wechat_userid=req.wechat_userid,
        phone=req.phone,
        department=req.department,
        job_title=req.job_title,
        role=UserRole(req.role),
        hashed_password=hash_password(req.password),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserOut(
        id=str(user.id), name=user.name, wechat_userid=user.wechat_userid,
        phone=user.phone, department=user.department, job_title=user.job_title,
        role=user.role.value, is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at, last_login_at=user.last_login_at,
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
        id=str(user.id), name=user.name, wechat_userid=user.wechat_userid,
        phone=user.phone, department=user.department, job_title=user.job_title,
        role=user.role.value, is_active=user.is_active,
        must_change_password=user.must_change_password,
        created_at=user.created_at, last_login_at=user.last_login_at,
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


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_role(UserRole.admin)),
):
    """管理员重置用户密码为默认 aipm2026"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.hashed_password = hash_password("aipm2026")
    await db.commit()
    return {"message": f"用户 '{user.name}' 密码已重置为默认密码"}


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
    from app.models.user import UserStatus
    from datetime import date

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
    from app.models.sprint import Sprint
    from app.models.project_member import ProjectMember
    from datetime import date

    users_result = await db.execute(
        select(User).where(User.is_active == True).order_by(User.department)
    )
    users = users_result.scalars().all()

    today = date.today()
    load_data = []
    for u in users:
        # 计算当前 Sprint 已分配点数（简化：按项目成员数估算）
        member_result = await db.execute(
            select(func.count(ProjectMember.id)).where(
                ProjectMember.user_id == u.id
            )
        )
        active_projects = member_result.scalar() or 0
        estimated_load = active_projects * 3  # 简化估算：每项目 3 点

        load_data.append({
            "user_id": str(u.id),
            "name": u.name,
            "department": u.department,
            "job_title": u.job_title,
            "status": u.status.value if hasattr(u.status, 'value') else str(u.status),
            "capacity": u.story_points_capacity,
            "estimated_load": estimated_load,
            "load_pct": round(estimated_load / max(u.story_points_capacity, 1) * 100, 1),
            "overloaded": estimated_load > u.story_points_capacity,
        })

    overloaded_count = sum(1 for d in load_data if d["overloaded"])
    return {
        "total_members": len(load_data),
        "overloaded_count": overloaded_count,
        "members": load_data,
    }
