"""Phase 12 T-1201: AI 对话历史持久化(ChatSession + ChatMessage + chat_role ENUM)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-05-30 12:52:00

T-1201 多轮对话 + 历史保存:
  - 新建 chat_role PG ENUM 类型(user/assistant/tool/system)
  - 新建 chat_sessions 表 + 3 索引(user_id / 复合 user_active / 复合 tenant_user_active)
  - 新建 chat_messages 表 + 2 索引(session_id / 复合 session_created)
  - 双表 FK ON DELETE CASCADE,session 删除自动清 message
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_enums = {
        row[0] for row in bind.execute(sa.text("SELECT typname FROM pg_type WHERE typtype='e'")).fetchall()
    }
    chat_role_enum = postgresql.ENUM(
        "user",
        "assistant",
        "tool",
        "system",
        name="chat_role",
        create_type=False,
    )
    if "chat_role" not in existing_enums:
        chat_role_enum.create(bind, checkfirst=False)

    if "chat_sessions" not in inspector.get_table_names():
        op.create_table(
            "chat_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("title", sa.String(length=120), nullable=False),
            sa.Column("message_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                name="fk_chat_sessions_user_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["created_by"],
                ["users.id"],
                name="fk_chat_sessions_created_by",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    session_indexes = set()
    if "chat_sessions" in inspector.get_table_names():
        session_indexes = {idx["name"] for idx in inspector.get_indexes("chat_sessions")}
    if "ix_chat_sessions_user_id" not in session_indexes:
        op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    if "ix_chat_sessions_tenant_id" not in session_indexes:
        op.create_index("ix_chat_sessions_tenant_id", "chat_sessions", ["tenant_id"])
    if "ix_chat_sessions_user_active" not in session_indexes:
        op.create_index("ix_chat_sessions_user_active", "chat_sessions", ["user_id", "last_message_at"])
    if "ix_chat_sessions_tenant_user_active" not in session_indexes:
        op.create_index(
            "ix_chat_sessions_tenant_user_active",
            "chat_sessions",
            ["tenant_id", "user_id", "deleted_at"],
        )

    if "chat_messages" not in inspector.get_table_names():
        op.create_table(
            "chat_messages",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "role",
                postgresql.ENUM(name="chat_role", create_type=False),
                nullable=False,
            ),
            sa.Column("content", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("tool_calls", postgresql.JSONB(), nullable=True),
            sa.Column("tool_call_id", sa.String(length=128), nullable=True),
            sa.Column("token_count", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(
                ["session_id"],
                ["chat_sessions.id"],
                name="fk_chat_messages_session_id",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["created_by"],
                ["users.id"],
                name="fk_chat_messages_created_by",
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    message_indexes = set()
    if "chat_messages" in inspector.get_table_names():
        message_indexes = {idx["name"] for idx in inspector.get_indexes("chat_messages")}
    if "ix_chat_messages_session_id" not in message_indexes:
        op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    if "ix_chat_messages_tenant_id" not in message_indexes:
        op.create_index("ix_chat_messages_tenant_id", "chat_messages", ["tenant_id"])
    if "ix_chat_messages_session_created" not in message_indexes:
        op.create_index(
            "ix_chat_messages_session_created",
            "chat_messages",
            ["session_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "chat_messages" in inspector.get_table_names():
        existing = {idx["name"] for idx in inspector.get_indexes("chat_messages")}
        for name in (
            "ix_chat_messages_session_created",
            "ix_chat_messages_tenant_id",
            "ix_chat_messages_session_id",
        ):
            if name in existing:
                op.drop_index(name, table_name="chat_messages")
        op.drop_table("chat_messages")

    if "chat_sessions" in inspector.get_table_names():
        existing = {idx["name"] for idx in inspector.get_indexes("chat_sessions")}
        for name in (
            "ix_chat_sessions_tenant_user_active",
            "ix_chat_sessions_user_active",
            "ix_chat_sessions_tenant_id",
            "ix_chat_sessions_user_id",
        ):
            if name in existing:
                op.drop_index(name, table_name="chat_sessions")
        op.drop_table("chat_sessions")

    existing_enums = {
        row[0] for row in bind.execute(sa.text("SELECT typname FROM pg_type WHERE typtype='e'")).fetchall()
    }
    if "chat_role" in existing_enums:
        sa.Enum(name="chat_role").drop(bind, checkfirst=False)
