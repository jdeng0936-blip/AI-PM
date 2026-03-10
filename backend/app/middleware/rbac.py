"""
app/middleware/rbac.py — RBAC 权限中间件

用法（在路由函数中注入）：
    from app.middleware.rbac import require_role
    from app.models.user import UserRole

    @router.get("/admin/stats")
    async def admin_stats(user = Depends(require_role(UserRole.admin))):
        ...
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt

from app.config import settings
from app.database import get_db
from app.models.user import User, UserRole

security = HTTPBearer()

ALGORITHM = "HS256"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """解析 JWT Token，返回当前登录用户对象"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="认证失败，请检查 Token 是否有效或已过期",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[ALGORITHM],
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


def require_role(*roles: UserRole):
    """
    工厂函数：生成指定角色的权限守卫依赖。
    支持传入多个角色（OR 逻辑）。

    示例：
        Depends(require_role(UserRole.admin))
        Depends(require_role(UserRole.admin, UserRole.manager))
    """
    async def _checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"该操作需要以下权限之一：{[r.value for r in roles]}",
            )
        return current_user
    return _checker


def create_access_token(user_id: str, role: str = "employee") -> str:
    """生成 JWT Token（用于管理后台登录），payload 含 role"""
    from datetime import datetime, timedelta, timezone
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": user_id, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=ALGORITHM)
