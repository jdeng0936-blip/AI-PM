"""
app/routers/notifications.py — 通知推送管理

提供:
- GET    /notifications/                  通知历史(分页+筛选,管理层看全部,员工只看自己)
- GET    /notifications/unread-count      站内信未读计数(当前用户)
- GET    /notifications/channels          查询各渠道配置/可用状态
- POST   /notifications/mark-read         批量标记已读(指定 ids 或 all)
- POST   /notifications/test              测试发送(admin 专属,用于调通配置)
- POST   /notifications/{id}/retry        失败重试(admin 专属)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
)
from app.models.user import User, UserRole
from app.services import dingtalk_api, wechat_api
from app.services.notification_service import notify

router = APIRouter(prefix="/api/v1/notifications", tags=["通知推送"])


# ────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────


class NotificationOut(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    channel: str
    template: str
    status: str
    title: Optional[str]
    body: str
    related_type: Optional[str]
    related_id: Optional[str]
    error_message: Optional[str]
    retry_count: int
    sent_at: Optional[datetime]
    read_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MarkReadRequest(BaseModel):
    ids: Optional[list[UUID]] = Field(
        default=None,
        description="要标记已读的通知 id 列表;为空且 all=True 表示标记当前用户所有站内信为已读",
    )
    all: bool = Field(default=False, description="true 时标记当前用户全部站内信已读")


class UnreadCountResponse(BaseModel):
    unread: int


class NotificationListResponse(BaseModel):
    total: int
    items: list[NotificationOut]


class ChannelStatusItem(BaseModel):
    channel: str
    configured: bool
    description: str


class TestSendRequest(BaseModel):
    channel: NotificationChannel
    template: NotificationTemplate = NotificationTemplate.report_passed
    user_id: Optional[UUID] = Field(
        default=None,
        description="精准推送渠道(wechat/dingtalk)必填;群机器人可省略",
    )
    context: dict = Field(
        default_factory=lambda: {
            "name": "测试用户",
            "score": 88,
            "comment": "通知通道联调成功 ✅",
        }
    )


# ────────────────────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────────────────────


@router.get("/", response_model=NotificationListResponse)
async def list_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    channel: Optional[NotificationChannel] = None,
    template: Optional[NotificationTemplate] = None,
    status_filter: Optional[NotificationStatus] = Query(None, alias="status"),
):
    """通知历史。员工只看自己,manager/admin 看全部。"""
    query = select(Notification).where(Notification.tenant_id == current_user.tenant_id)
    count_query = select(func.count(Notification.id)).where(Notification.tenant_id == current_user.tenant_id)

    if current_user.role == UserRole.employee:
        query = query.where(Notification.user_id == current_user.id)
        count_query = count_query.where(Notification.user_id == current_user.id)

    if channel:
        query = query.where(Notification.channel == channel)
        count_query = count_query.where(Notification.channel == channel)
    if template:
        query = query.where(Notification.template == template)
        count_query = count_query.where(Notification.template == template)
    if status_filter:
        query = query.where(Notification.status == status_filter)
        count_query = count_query.where(Notification.status == status_filter)

    total = (await db.execute(count_query)).scalar_one()

    query = query.order_by(desc(Notification.created_at)).offset((page - 1) * page_size).limit(page_size)
    items = (await db.execute(query)).scalars().all()

    return NotificationListResponse(
        total=total,
        items=[NotificationOut.model_validate(n) for n in items],
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前用户站内信未读数。仅统计 channel=in_app AND status=sent AND read_at IS NULL。"""
    query = select(func.count(Notification.id)).where(
        Notification.user_id == current_user.id,
        Notification.tenant_id == current_user.tenant_id,
        Notification.channel == NotificationChannel.in_app,
        Notification.status == NotificationStatus.sent,
        Notification.read_at.is_(None),
    )
    total = (await db.execute(query)).scalar_one()
    return UnreadCountResponse(unread=int(total or 0))


@router.post("/mark-read")
async def mark_read(
    payload: MarkReadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """标记当前用户的站内信为已读。

    - 传 ids: 仅标记指定 id(且必须属于当前用户)
    - 传 all=True: 标记当前用户所有未读站内信
    """
    from sqlalchemy import update

    if not payload.ids and not payload.all:
        raise HTTPException(400, "请提供 ids 或将 all 设为 true")

    stmt = (
        update(Notification)
        .where(
            Notification.user_id == current_user.id,
            Notification.tenant_id == current_user.tenant_id,
            Notification.channel == NotificationChannel.in_app,
            Notification.read_at.is_(None),
        )
        .values(read_at=datetime.now(timezone.utc))
    )
    if payload.ids:
        stmt = stmt.where(Notification.id.in_(payload.ids))

    result = await db.execute(stmt)
    await db.commit()
    return {"updated": result.rowcount or 0}


@router.get("/channels", response_model=list[ChannelStatusItem])
async def channel_status(_: User = Depends(get_current_user)):
    """查询各渠道配置/可用状态(用于前端展示配置完成度)。"""
    return [
        ChannelStatusItem(
            channel=NotificationChannel.wechat.value,
            configured=wechat_api.is_app_configured(),
            description="企微自建应用消息(精准到人)",
        ),
        ChannelStatusItem(
            channel=NotificationChannel.wechat_bot.value,
            configured=wechat_api.is_bot_configured(),
            description="企微群机器人(群推,无需精准 userid)",
        ),
        ChannelStatusItem(
            channel=NotificationChannel.dingtalk.value,
            configured=dingtalk_api.is_app_configured(),
            description="钉钉企业应用消息(精准到人)",
        ),
        ChannelStatusItem(
            channel=NotificationChannel.dingtalk_bot.value,
            configured=dingtalk_api.is_bot_configured(),
            description="钉钉群机器人(推荐,免开发)",
        ),
        ChannelStatusItem(
            channel=NotificationChannel.in_app.value,
            configured=True,
            description="系统内站内信",
        ),
        ChannelStatusItem(
            channel=NotificationChannel.email.value,
            configured=False,
            description="邮件(暂未接入)",
        ),
    ]


@router.post("/test", response_model=list[NotificationOut])
async def test_send(
    payload: TestSendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """测试发送一条通知。admin 专属,用于联调企微/钉钉配置。"""
    target_user: Optional[User] = None
    if payload.user_id:
        target_user = (
            await db.execute(select(User).where(User.id == payload.user_id, User.tenant_id == current_user.tenant_id))
        ).scalar_one_or_none()
        if not target_user:
            raise HTTPException(status_code=404, detail="目标用户不存在")

    records = await notify(
        db,
        template=payload.template,
        context=payload.context,
        channels=[payload.channel],
        user=target_user,
        related_type="test",
        related_id=None,
        tenant_id=current_user.tenant_id,
    )
    await db.commit()
    return [NotificationOut.model_validate(r) for r in records]


@router.post("/{notification_id}/retry", response_model=NotificationOut)
async def retry_notification(
    notification_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    """重试单条失败的通知。仅 admin 可用。"""
    record = (
        await db.execute(
            select(Notification).where(Notification.id == notification_id, Notification.tenant_id == current_user.tenant_id)
        )
    ).scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="通知记录不存在")
    if record.status == NotificationStatus.sent:
        raise HTTPException(status_code=400, detail="该通知已成功发送,无需重试")

    target_user: Optional[User] = None
    if record.user_id:
        target_user = (
            await db.execute(select(User).where(User.id == record.user_id, User.tenant_id == current_user.tenant_id))
        ).scalar_one_or_none()

    from app.services.notification_service import _dispatch_one

    status_, err = await _dispatch_one(
        NotificationChannel(record.channel),
        target_user,
        record.title or "",
        record.body,
    )
    record.status = status_
    record.error_message = err
    record.retry_count = (record.retry_count or 0) + 1
    if status_ == NotificationStatus.sent:
        record.sent_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(record)
    return NotificationOut.model_validate(record)
