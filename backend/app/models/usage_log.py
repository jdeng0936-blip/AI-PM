"""
app/models/usage_log.py — 大模型成本风控表

每次调用 AI 后写入本表。Token 熔断守卫（token_guard.py）
读取本表当日累计量，超过 DAILY_TOKEN_LIMIT 时拒绝服务。
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Integer, String, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.base_mixin import BaseMixin


class TenantUsageLog(BaseMixin, Base):
    __tablename__ = "tenant_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    log_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)

    # 调用者（用于分析哪个员工/模块消耗 Token 最多）
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)

    # 本次调用的 Token 用量（来自 API 响应的 usage 字段）
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)

    # 调用来源模块标识（daily_report / morning_briefing / weekly_report 等）
    source: Mapped[str] = mapped_column(String(32), default="daily_report")

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
