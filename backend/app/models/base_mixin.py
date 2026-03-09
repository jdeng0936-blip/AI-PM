"""
app/models/base_mixin.py — 通用字段 Mixin

遵循 Rule 01-Stack-Database:
  所有核心表必须包含 created_at, updated_at, created_by, tenant_id。

用法：
    class MyModel(BaseMixin, Base):
        __tablename__ = "my_table"
        ...

注意：BaseMixin 必须放在 Base 前面（MRO 顺序）。
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func


class BaseMixin:
    """
    所有核心业务表的通用字段 Mixin。

    提供：
      - created_at:  记录创建时间（数据库 server_default）
      - updated_at:  记录更新时间（自动 onupdate）
      - created_by:  创建者 UUID（FK → users.id，允许 NULL）
      - tenant_id:   租户隔离标识（默认 "default"，indexed）
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="记录创建时间",
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
        comment="记录最后更新时间",
    )

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="创建者 user.id",
    )

    tenant_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="default",
        index=True,
        comment="租户隔离标识",
    )
