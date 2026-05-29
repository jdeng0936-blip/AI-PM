"""
app/services/department_service.py — Phase 10 部门服务层

职责:
  - CRUD: list / create / update / delete (4 个写读函数)
  - 反查: get_with_members(从 User.department 字符串字段反查成员)

错误模型:
  - 不抛 Web 层异常(职责留给 router 层)
  - 用 ValueError + str 区分错误类型,router 按字面量映射 4xx 状态码:
    - "not_found"        → 404
    - "name_conflict"    → 409
    - "manager_not_found" → 400
  - 数据库 IntegrityError 在 service 内捕获并转 ValueError("name_conflict")

约束:
  - 全异步 AsyncSession
  - tenant_id 由 router 从当前用户注入。
  - 返回 Schema Out 实例(不暴露 ORM)
"""

from __future__ import annotations

import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department import Department
from app.models.user import User
from app.schemas.department import (
    DepartmentIn,
    DepartmentMember,
    DepartmentOut,
    DepartmentUpdate,
    DepartmentWithMembers,
)


async def _get_department_or_raise(db: AsyncSession, dept_id: uuid.UUID, tenant_id: str) -> Department:
    stmt = select(Department).where(
        Department.id == dept_id,
        Department.tenant_id == tenant_id,
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if result is None:
        raise ValueError("not_found")
    return result


async def _verify_manager_exists(db: AsyncSession, manager_id: uuid.UUID, tenant_id: str) -> None:
    """校验 manager_id 对应 user 存在且活跃(is_active=True)。

    本仓库 User 的软删除信号 = is_active=False(见 backend/app/routers/users.py:223)。
    """
    stmt = select(User.id).where(
        User.id == manager_id,
        User.tenant_id == tenant_id,
        User.is_active.is_(True),
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise ValueError("manager_not_found")


async def list_departments(db: AsyncSession, *, tenant_id: str) -> list[DepartmentOut]:
    stmt = select(Department).where(Department.tenant_id == tenant_id).order_by(Department.name.asc())
    rows = (await db.execute(stmt)).scalars().all()
    return [DepartmentOut.model_validate(row) for row in rows]


async def create_department(
    db: AsyncSession,
    payload: DepartmentIn,
    actor: User,
) -> DepartmentOut:
    if payload.manager_id is not None:
        await _verify_manager_exists(db, payload.manager_id, actor.tenant_id)

    dept = Department(
        name=payload.name.strip(),
        manager_id=payload.manager_id,
        created_by=actor.id,
        tenant_id=actor.tenant_id,
    )
    db.add(dept)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("name_conflict") from None
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


async def update_department(
    db: AsyncSession,
    dept_id: uuid.UUID,
    payload: DepartmentUpdate,
    actor: User,
) -> DepartmentOut:
    dept = await _get_department_or_raise(db, dept_id, actor.tenant_id)

    update_data = payload.model_dump(exclude_unset=True)
    if "manager_id" in update_data and update_data["manager_id"] is not None:
        await _verify_manager_exists(db, update_data["manager_id"], actor.tenant_id)

    if "name" in update_data and update_data["name"] is not None:
        dept.name = update_data["name"].strip()
    if "manager_id" in update_data:
        dept.manager_id = update_data["manager_id"]

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("name_conflict") from None
    await db.commit()
    await db.refresh(dept)
    return DepartmentOut.model_validate(dept)


async def delete_department(db: AsyncSession, dept_id: uuid.UUID, *, tenant_id: str) -> None:
    dept = await _get_department_or_raise(db, dept_id, tenant_id)
    await db.delete(dept)
    await db.commit()


async def get_department_with_members(db: AsyncSession, dept_id: uuid.UUID, *, tenant_id: str) -> DepartmentWithMembers:
    dept = await _get_department_or_raise(db, dept_id, tenant_id)

    member_stmt = (
        select(User)
        .where(
            or_(
                User.department_id == dept.id,
                and_(User.department_id.is_(None), User.department == dept.name),
            ),
            User.is_active.is_(True),
            User.tenant_id == tenant_id,
        )
        .order_by(User.name.asc())
    )
    member_rows = (await db.execute(member_stmt)).scalars().all()
    members = [DepartmentMember.model_validate(user) for user in member_rows]

    base = DepartmentOut.model_validate(dept).model_dump()
    return DepartmentWithMembers(**base, members=members)
