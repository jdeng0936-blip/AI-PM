"""
app/schemas/department.py — Phase 10 部门 Pydantic V2 Schemas

对应 ORM Model（app/models/department.py）字段约束:
  - name: String(64) UNIQUE NOT NULL
  - manager_id: UUID FK→users.id ON DELETE SET NULL nullable
  - BaseMixin 4 字段:created_at / updated_at / created_by / tenant_id

成员反查口径:
  - 从 User.department: String(64) 字符串字段按 name 等值匹配反查
  - 仅返回 is_active=True 的活跃用户(本仓库 User 软删除信号 = is_active=False,无 deleted_at 字段;
    User 模型不继承 BaseMixin,见 backend/app/models/user.py L4-7 注释)
  - 字段裁剪到 id / name / role / department,不暴露密码/手机号等敏感字段
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.user import UserRole


class DepartmentIn(BaseModel):
    """POST /admin/departments/ 请求体。"""

    name: str = Field(..., min_length=1, max_length=64, description="部门名称")
    manager_id: Optional[uuid.UUID] = Field(None, description="部门负责人 user.id;可选")


class DepartmentUpdate(BaseModel):
    """PATCH /admin/departments/{id} 请求体,字段全 optional。"""

    name: Optional[str] = Field(None, min_length=1, max_length=64, description="部门名称")
    manager_id: Optional[uuid.UUID] = Field(None, description="部门负责人 user.id")


class DepartmentOut(BaseModel):
    """通用响应模型。"""

    id: uuid.UUID
    name: str
    manager_id: Optional[uuid.UUID]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    created_by: Optional[uuid.UUID]
    tenant_id: str

    model_config = ConfigDict(from_attributes=True)


class DepartmentMember(BaseModel):
    """成员反查时的精简用户视图。"""

    id: uuid.UUID
    name: str
    role: UserRole
    department: str

    model_config = ConfigDict(from_attributes=True)


class DepartmentWithMembers(DepartmentOut):
    """GET /admin/departments/{id}/members 响应。"""

    members: list[DepartmentMember]
