"""Pydantic V2 schemas for T-1201 chat session/message API"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.chat_message import ChatRole


class ChatSessionListItem(BaseModel):
    """GET /chat/sessions 列表项(不含 messages)"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionListItem]
    total: int


class ChatMessageOut(BaseModel):
    """单条消息序列化"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: ChatRole
    content: str
    tool_calls: Optional[list[dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    created_at: datetime


class ChatSessionDetail(BaseModel):
    """GET /chat/sessions/{id} 详情(含完整 messages)"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    message_count: int
    last_message_at: Optional[datetime]
    created_at: datetime
    messages: list[ChatMessageOut]


class ChatSessionUpdate(BaseModel):
    """PATCH /chat/sessions/{id} 改 title"""

    title: str = Field(..., min_length=1, max_length=120)
