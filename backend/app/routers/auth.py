from __future__ import annotations

"""
app/routers/auth.py — 认证路由
POST /auth/login    — 登录
GET  /auth/me       — 当前用户信息
POST /auth/change-password — 修改密码
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.rbac import create_access_token, get_current_user
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.user import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    UserOut,
)

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str | None) -> bool:
    """校验密码。开发绕过必须显式开启 ENABLE_DEV_AUTH_BYPASS。"""
    if is_dev_auth_bypass_password(plain):
        return True
    if not hashed:
        return is_dev_auth_bypass_enabled()
    return pwd_context.verify(plain, hashed)


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def is_dev_auth_bypass_enabled() -> bool:
    return settings.aipm_env == "dev" and settings.enable_dev_auth_bypass


def is_dev_auth_bypass_password(plain: str) -> bool:
    return is_dev_auth_bypass_enabled() and plain == "dev"


async def find_login_user(db: AsyncSession, username: str) -> User | None:
    """
    Resolve demo-friendly login names deterministically.

    Some local demo databases may contain legacy inactive rows whose
    wechat_userid equals a display name such as "张毅". Prefer active exact
    identifiers, then active display-name matches, and only fall back to
    inactive rows so the caller can return the normal disabled-account error.
    """
    active_exact = await db.execute(
        select(User)
        .where(
            or_(
                User.wechat_userid == username,
                User.phone == username,
            ),
            User.is_active.is_(True),
        )
        .order_by(User.created_at.desc())
        .limit(1)
    )
    user = active_exact.scalars().first()
    if user:
        return user

    active_name = await db.execute(
        select(User).where(User.name == username, User.is_active.is_(True)).order_by(User.created_at.desc()).limit(1)
    )
    user = active_name.scalars().first()
    if user:
        return user

    inactive_match = await db.execute(
        select(User)
        .where(
            or_(
                User.wechat_userid == username,
                User.phone == username,
                User.name == username,
            )
        )
        .order_by(User.created_at.desc())
        .limit(1)
    )
    return inactive_match.scalars().first()


@router.post("/login", response_model=LoginResponse)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    用户名+密码登录。
    支持 wechat_userid / phone / name 匹配。
    """
    user = await find_login_user(db, req.username)

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

    if user.must_change_password and is_dev_auth_bypass_password(req.password):
        user.must_change_password = False

    # 更新最近登录时间
    user.last_login_at = datetime.now(timezone.utc).replace(tzinfo=None)

    # 写入审计日志
    client_ip = request.client.host if request.client else "unknown"
    audit = AuditLog(
        user_id=user.id,
        action="login",
        ip_address=client_ip,
        detail={"username": req.username},
    )
    db.add(audit)
    await db.commit()

    token = create_access_token(str(user.id), role=user.role.value)

    return LoginResponse(
        access_token=token,
        user=UserOut(
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
        email=current_user.email,
        department=current_user.department,
        job_title=current_user.job_title,
        role=current_user.role.value,
        is_active=current_user.is_active,
        must_change_password=current_user.must_change_password,
        created_at=current_user.created_at,
        last_login_at=current_user.last_login_at,
        status=(current_user.status.value if hasattr(current_user.status, "value") else str(current_user.status)),
        status_until=current_user.status_until,
    )


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
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
    current_user.must_change_password = False  # 改密后清除强制标记

    # 审计日志
    client_ip = request.client.host if request.client else "unknown"
    db.add(
        AuditLog(
            user_id=current_user.id,
            action="change_password",
            ip_address=client_ip,
        )
    )
    await db.commit()
    return {"message": "密码修改成功"}
