"""
app/models/chat_session.py — AI 对话会话(T-1201)

每个 admin 用户的一次对话线程。首次 /api/v1/chat/ask 调用隐式创建,
后续追问携带 session_id 自动加载历史上下文。

设计:
- 软删:deleted_at 标记;DELETE /sessions/{id} 设置该字段
- 计数字段 message_count / last_message_at:routers/chat.py 写入路径维护,
  避免每次列表查询都 JOIN aggregate ChatMessage 表
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class ChatSession(BaseMixin, Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index(
            "ix_chat_sessions_user_active",
            "user_id",
            "last_message_at",
        ),
        Index(
            "ix_chat_sessions_tenant_user_active",
            "tenant_id",
            "user_id",
            "deleted_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="会话归属用户(admin 角色)",
    )

    title: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="会话标题(首次 ask 截取 user.content 前 30 字符)",
    )

    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="本会话累计 message 数(所有 role,含 tool message);维护字段",
    )

    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="最后一条 message 落盘时间;用于列表排序",
    )

    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="软删时间;非 NULL 表示已删除,列表查询自动过滤",
    )

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} user={self.user_id} title={self.title!r}>"
