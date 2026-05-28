"""
app/routers/departments.py — Phase 10 部门 REST API

端点(全部 admin + manager RBAC):
  - GET    /api/v1/admin/departments/                —— 列出全部部门
  - POST   /api/v1/admin/departments/                —— 新建部门
  - GET    /api/v1/admin/departments/{id}/members    —— 查部门 + 反查成员
  - PATCH  /api/v1/admin/departments/{id}            —— 部分更新
  - DELETE /api/v1/admin/departments/{id}            —— 硬删除

错误码映射(service raise ValueError(str)):
  - "not_found"         → 404 "部门不存在"
  - "name_conflict"     → 409 "部门名称已存在"
  - "manager_not_found" → 400 "manager_id 对应的用户不存在或已删除"
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.user import User, UserRole
from app.schemas.department import (
    DepartmentIn,
    DepartmentOut,
    DepartmentUpdate,
    DepartmentWithMembers,
)
from app.services.department_service import (
    create_department,
    delete_department,
    get_department_with_members,
    list_departments,
    update_department,
)

router = APIRouter(prefix="/api/v1/admin/departments", tags=["Departments"])
_mgr_or_admin = require_role(UserRole.admin, UserRole.manager)


def _map_value_error(exc: ValueError) -> HTTPException:
    # Service ValueError code -> router HTTP status/detail mapping.
    code = str(exc)
    if code == "not_found":
        return HTTPException(status_code=404, detail="部门不存在")
    if code == "name_conflict":
        return HTTPException(status_code=409, detail="部门名称已存在")
    if code == "manager_not_found":
        return HTTPException(status_code=400, detail="manager_id 对应的用户不存在或已删除")
    return HTTPException(status_code=500, detail="未知错误")


@router.get("/", response_model=list[DepartmentOut])
async def list_all(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> list[DepartmentOut]:
    return await list_departments(db, tenant_id=_user.tenant_id)


@router.post("/", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def create(
    payload: DepartmentIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(_mgr_or_admin),
) -> DepartmentOut:
    try:
        return await create_department(db, payload, actor)
    except ValueError as e:
        raise _map_value_error(e) from None


@router.get("/{dept_id}/members", response_model=DepartmentWithMembers)
async def get_members(
    dept_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> DepartmentWithMembers:
    try:
        return await get_department_with_members(db, dept_id, tenant_id=_user.tenant_id)
    except ValueError as e:
        raise _map_value_error(e) from None


@router.patch("/{dept_id}", response_model=DepartmentOut)
async def update(
    dept_id: uuid.UUID,
    payload: DepartmentUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(_mgr_or_admin),
) -> DepartmentOut:
    try:
        return await update_department(db, dept_id, payload, actor)
    except ValueError as e:
        raise _map_value_error(e) from None


@router.delete("/{dept_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete(
    dept_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> Response:
    try:
        await delete_department(db, dept_id, tenant_id=_user.tenant_id)
    except ValueError as e:
        raise _map_value_error(e) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
