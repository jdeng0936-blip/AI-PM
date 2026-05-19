"""
app/models/notification.py — 通知推送历史表

每次 NotificationService.notify() 调用都会落一条记录,
便于审计、重试、统计触达率。
"""
import uuid
import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, DateTime, Enum, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.base_mixin import BaseMixin


class NotificationChannel(str, enum.Enum):
    wechat = "wechat"          # 企微应用消息(精准到人)
    wechat_bot = "wechat_bot"  # 企微群机器人(群推)
    dingtalk = "dingtalk"      # 钉钉应用消息(精准到人)
    dingtalk_bot = "dingtalk_bot"  # 钉钉群机器人(群推)
    email = "email"
    in_app = "in_app"          # 系统内站内信


class NotificationStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"        # 渠道未配置 / 用户无目标地址


class NotificationTemplate(str, enum.Enum):
    """模板枚举,新增模板时同时更新 services/notification_service.py 的 TEMPLATES"""
    report_rejected = "report_rejected"     # 质检驳回
    report_passed = "report_passed"         # 评分通过
    daily_briefing = "daily_briefing"       # 战情日报
    risk_alert = "risk_alert"               # 风险预警
    reminder_soft = "reminder_soft"         # 友好催报(17:30)
    reminder_hard = "reminder_hard"         # 二次催促(20:00)
    reminder_missed = "reminder_missed"     # 缺勤通知(22:00)
    sprint_review = "sprint_review"         # Sprint 回顾
    weekly_report = "weekly_report"         # 周报


class Notification(BaseMixin, Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # 接收人(可为空,表示群推)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )

    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel), nullable=False, index=True
    )
    template: Mapped[NotificationTemplate] = mapped_column(
        Enum(NotificationTemplate), nullable=False, index=True
    )
    status: Mapped[NotificationStatus] = mapped_column(
        Enum(NotificationStatus), nullable=False, default=NotificationStatus.pending,
        index=True,
    )

    # 渲染后的最终消息内容
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 模板上下文(原始数据,便于重试)
    context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # 关联业务对象(可选,如 report_id / risk_alert_id)
    related_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    related_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # 失败原因
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<Notification channel={self.channel} "
            f"template={self.template} status={self.status}>"
        )
