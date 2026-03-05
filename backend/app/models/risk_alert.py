"""
app/models/risk_alert.py — 全局卡点与预警表

当 AI 解析日报发现 management_alert 非空时，自动写入本表。
管理层可通过 /dashboard/risk-alerts 接口实时查看所有未解决卡点。
ERP Webhook 可自动将 status 从 unresolved → resolved。
"""
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # 来源日报（可追溯）
    report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False
    )
    # 当事人（方便按部门/人员筛选）
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # 预警类型：blocker（硬卡）/ dependency（跨部门依赖）/ recurring（连续未解决）
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False, default="blocker")

    description: Mapped[str] = mapped_column(Text, nullable=False)

    # 状态：unresolved（待处理）/ resolved（已解决）/ escalated（已升级）
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unresolved")

    # 连续未解决天数（Celery 定时任务每日递增，≥5 自动升级为 recurring）
    days_unresolved: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<RiskAlert type={self.alert_type} status={self.status} days={self.days_unresolved}>"
