"""
T-1104 部门解析双轨读 helper:department_id FK 优先 + fallback 到 department VARCHAR。

3 任务渐进路径(T-1104 -> T-1105 -> T-1106):
  - T-1104(本任): 引入 department_id 列 + backfill + 此 helper 在 department_service 内首次接入
  - T-1105: 切剩余后端 routers/services 读路径用此 helper,frontend schema 扩 department_id output 字段
  - T-1106: drop column User.department + 删此 fallback 路径(此 helper 简化为直读 department_id)

调用方应使用 await resolve_user_department_name(db, user) 而非直接 user.department,
确保 T-1106 字段下线时调用面已统一切换。
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.user import User


async def resolve_user_department_name(
    db: AsyncSession,
    user: User,
) -> str:
    """返回 user 的部门名:department_id 优先 -> fallback 到 department VARCHAR。"""
    if user.department_id is not None:
        result = await db.execute(select(Department.name).where(Department.id == user.department_id))
        name = result.scalar_one_or_none()
        if name is not None:
            return name
    return user.department or ""


async def resolve_department_id_by_name(
    db: AsyncSession,
    name: str,
) -> Optional[uuid.UUID]:
    """根据 name 反查 department_id;T-1105 用于 users 写入路径。"""
    if not name:
        return None
    result = await db.execute(select(Department.id).where(Department.name == name))
    return result.scalar_one_or_none()
