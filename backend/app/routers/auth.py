"""
app/routers/auth.py — 认证路由
POST /auth/login    — 登录
GET  /auth/me       — 当前用户信息
POST /auth/change-password — 修改密码
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext

from app.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import (
    LoginRequest, LoginResponse, ChangePasswordRequest, UserOut,
)
from app.middleware.rbac import create_access_token, get_current_user
from app.config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str | None) -> bool:
    """校验密码，hashed 为空时在 dev 模式放行"""
    if not hashed:
        return settings.aipm_env == "dev"
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    用户名+密码登录。
    支持 wechat_userid / phone / name 匹配。
    """
    result = await db.execute(
        select(User).where(
            or_(
                User.wechat_userid == req.username,
                User.phone == req.username,
                User.name == req.username,
            )
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在，请检查用户名",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被停用，请联系管理员",
        )

    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="密码错误",
        )

    token = create_access_token(str(user.id), role=user.role.value)

    return LoginResponse(
        access_token=token,
        user=UserOut(
            id=str(user.id),
            name=user.name,
            wechat_userid=user.wechat_userid,
            phone=user.phone,
            department=user.department,
            role=user.role.value,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserOut(
        id=str(current_user.id),
        name=current_user.name,
        wechat_userid=current_user.wechat_userid,
        phone=current_user.phone,
        department=current_user.department,
        role=current_user.role.value,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改当前用户密码"""
    # 如果当前有密码，需先验证旧密码
    if current_user.hashed_password:
        if not pwd_context.verify(req.old_password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="旧密码不正确",
            )

    current_user.hashed_password = hash_password(req.new_password)
    await db.commit()
    return {"message": "密码修改成功"}
