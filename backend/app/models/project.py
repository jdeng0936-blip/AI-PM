"""
app/models/project.py — 项目总表

一个"项目"代表一个完整的 IPD 研发周期（如"206样机研发及落地"）。
health_status 由 health_engine.py 每日自动聚合日报数据后更新。
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class ProjectTrack(str, enum.Enum):
    dual     = "dual"      # 软硬双轨（智能硬件类项目主模式）
    software = "software"  # 纯软件项目（纯敏捷 Sprints）
    hardware = "hardware"  # 纯硬件项目（纯瀑布里程碑）


class ProjectHealthStatus(str, enum.Enum):
    green  = "green"   # 健康，整体推进正常
    yellow = "yellow"  # 存在卡点，需关注
    red    = "red"     # 严重滞后或硬卡，需管理层介入


class ProjectStatus(str, enum.Enum):
    active    = "active"
    paused    = "paused"
    completed = "completed"
    cancelled = "cancelled"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # 基本信息
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)  # P2026-001
    description: Mapped[Optional[str]] = mapped_column(String(512))
    track: Mapped[ProjectTrack] = mapped_column(Enum(ProjectTrack), default=ProjectTrack.dual)

    # 生命周期状态
    current_stage: Mapped[int] = mapped_column(Integer, default=1)  # 1-5
    status: Mapped[ProjectStatus] = mapped_column(Enum(ProjectStatus), default=ProjectStatus.active)

    # 健康度（由 health_engine.py 每日自动更新）
    health_status: Mapped[ProjectHealthStatus] = mapped_column(
        Enum(ProjectHealthStatus), default=ProjectHealthStatus.green
    )
    health_score: Mapped[int] = mapped_column(Integer, default=100)  # 0-100

    # 时间节点
    planned_launch_date: Mapped[Optional[date]] = mapped_column(Date)
    actual_launch_date: Mapped[Optional[date]] = mapped_column(Date)

    # 预算管理（元）
    budget_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    budget_spent: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), default=0)
    budget_alert_threshold: Mapped[float] = mapped_column(default=0.8)  # 超过80%触发预警

    # 立项人
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Project code={self.code} stage={self.current_stage} health={self.health_status}>"
