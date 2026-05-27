"""Phase 10 / T-1003: 新建 departments 表 + 7 seed

实际背景
========
T-1001 §10 勘察确认 departments 独立表 / ORM / migration 在 V2.0 中尚未落地,
plan §10 L755-759 原文设计的"部门枚举"独立表与 manager_id FK 关联均缺失。当前
仅有 User.department: String(64) 字符串字段,无 manager 关联、无对外管理端点。

变更
====
- 新建 departments 表:id UUID PK / name VARCHAR(64) UNIQUE NOT NULL /
  manager_id UUID FK->users.id ON DELETE SET NULL nullable + index /
  BaseMixin 4 字段(created_at / updated_at / created_by FK->users.id / tenant_id index)。
- bulk_insert 7 seed:技术部 / 生产部 / 采购部 / 财务部 / 商务部 / 销售部 / 仓储部,
  manager_id 全 NULL,tenant_id="default"。
- 同步 ORM 文件 backend/app/models/department.py 以及
  backend/app/models/__init__.py 的 Department 暴露与 __all__ 注册。

实现说明
========
- manager_id 选 ON DELETE SET NULL:经理离职/删除时部门 outlive,不连带删除整张部门。
- name 长度选 String(64) 对齐 User.department: String(64),便于 Phase 11+
  反向校验;目前两表并存,Phase 11+ 再做 FK 化迁移。
- 7 seed 用 op.bulk_insert + sa.table()/sa.column() 体例,id 由 Python 端 uuid.uuid4()
  预生成,绕过数据库端 UUID extension 依赖。
- 不动 users.department 字段、不动任何现有数据;upgrade 失败时停手报告,
  不在 migration 里写数据清洗 SQL。

Revision ID: b58bb129c24b
Revises: 4f8e370435ea
Create Date: 2026-05-27 19:14:00.000000+08:00
"""

import uuid as _uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b58bb129c24b"
down_revision: Union[str, None] = "4f8e370435ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_DEPARTMENTS: list[str] = [
    "技术部",
    "生产部",
    "采购部",
    "财务部",
    "商务部",
    "销售部",
    "仓储部",
]


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "name",
            sa.String(length=64),
            nullable=False,
            comment="部门名称,与 User.department 字符串字段对齐;UNIQUE 防重",
        ),
        sa.Column(
            "manager_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="部门负责人,FK→users.id;经理离职时置 NULL,部门不连带删除",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="记录创建时间",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
            comment="记录最后更新时间",
        ),
        sa.Column(
            "created_by",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            comment="创建者 user.id",
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            nullable=False,
            server_default="default",
            comment="租户隔离标识",
        ),
        sa.UniqueConstraint("name", name="uq_departments_name"),
    )
    op.create_index("ix_departments_manager_id", "departments", ["manager_id"])
    op.create_index("ix_departments_tenant_id", "departments", ["tenant_id"])

    op.bulk_insert(
        sa.table(
            "departments",
            sa.column("id", sa.UUID()),
            sa.column("name", sa.String()),
            sa.column("manager_id", sa.UUID()),
            sa.column("tenant_id", sa.String()),
        ),
        [
            {
                "id": _uuid.uuid4(),
                "name": dept_name,
                "manager_id": None,
                "tenant_id": "default",
            }
            for dept_name in SEED_DEPARTMENTS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_departments_tenant_id", table_name="departments")
    op.drop_index("ix_departments_manager_id", table_name="departments")
    op.drop_table("departments")
