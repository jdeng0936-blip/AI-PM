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
                phone=u.phone, department=u.department,
                role=u.role.value, is_active=u.is_active,
                created_at=u.created_at,
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
        role=UserRole(req.role),
        hashed_password=hash_password(req.password),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserOut(
        id=str(user.id), name=user.name, wechat_userid=user.wechat_userid,
        phone=user.phone, department=user.department,
        role=user.role.value, is_active=user.is_active,
        created_at=user.created_at,
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
    if req.role is not None:
        user.role = UserRole(req.role)
    if req.is_active is not None:
        user.is_active = req.is_active

    await db.commit()
    await db.refresh(user)

    return UserOut(
        id=str(user.id), name=user.name, wechat_userid=user.wechat_userid,
        phone=user.phone, department=user.department,
        role=user.role.value, is_active=user.is_active,
        created_at=user.created_at,
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
