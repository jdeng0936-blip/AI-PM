"""
app/models/department.py — 部门主表(Phase 10 落地)

对应 plan §10 L755-759 原文设计的独立 departments 表,作为部门分组、
对外 /api/v1/admin/departments 端点(T-1004)、按部门分组报表(T-1005)的底座。

V2.0 历史上仅有 User.department: String(64) 字符串字段,无独立部门表/无 manager 关联;
T-1003 仅落地表 + ORM + 7 seed,不动 User.department 字段(FK 化迁移延后到 Phase 11+)。

字段对齐 plan §10 L755-759 + Rule 01-Stack-Database 通用字段要求。
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class Department(BaseMixin, Base):
    """部门主表 —— 7 seed(技术部/生产部/采购部/财务部/商务部/销售部/仓储部)由 migration 写入。"""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="部门名称,与 User.department 字符串字段对齐;UNIQUE 防重",
    )

    manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="部门负责人,FK→users.id;经理离职时置 NULL,部门不连带删除",
    )

    # NOTE: created_at / updated_at / created_by / tenant_id 由 BaseMixin 自动注入

    def __repr__(self) -> str:
        return f"<Department name={self.name} manager_id={self.manager_id}>"
