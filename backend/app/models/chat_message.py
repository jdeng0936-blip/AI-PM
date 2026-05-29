"""
app/models/chat_message.py — AI 对话消息(T-1201)

Append-only message 表。每次 /api/v1/chat/ask 调用会落盘 1 条 user message +
N 条 assistant/tool message(取决于 LLM tool calling 轮数)。

设计:
- role: 严格对齐 OpenAI Chat Completion API 四角(user / assistant / tool / system)
- tool_calls: JSONB nullable;仅 role=assistant 且包含 tool 调用时填充,
  存储 LLM 原始返回的 tool_calls 数组(含 id / function.name / function.arguments)
- tool_call_id: nullable;仅 role=tool 时填充,关联到上一条 assistant tool_calls 的某个 id
- token_count: 预留字段,T-1201 不实现统计(LLM SDK 未返回 usage),保留 nullable
- 复合索引 (session_id, created_at):会话详情按时间序加载
"""

from __future__ import annotations

import enum
import uuid
from typing import Any, Optional

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class ChatMessage(BaseMixin, Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index(
            "ix_chat_messages_session_created",
            "session_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="所属会话;session 删除时 CASCADE 删 messages",
    )

    role: Mapped[ChatRole] = mapped_column(
        Enum(ChatRole, name="chat_role", native_enum=True),
        nullable=False,
        comment="消息角色(OpenAI 四角)",
    )

    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="消息正文;role=assistant 且仅有 tool_calls 时可空字符串",
    )

    tool_calls: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="LLM 返回的 tool_calls 数组(仅 role=assistant 且本轮调用 tool 时填充)",
    )

    tool_call_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="tool 执行结果回填时关联的 tool_call.id(仅 role=tool 时填充)",
    )

    token_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="本条 message 估算 token 数(T-1201 预留,不实现统计)",
    )

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<ChatMessage session={self.session_id} role={self.role.value}>"
