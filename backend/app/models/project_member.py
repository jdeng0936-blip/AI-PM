"""
app/models/project_member.py — 项目成员分配表

将员工映射到具体项目的特定轨道（hardware / software）。
这是 health_engine 进行日报→健康度聚合的关键桥梁：
  通过 project_members 找到属于某项目+某轨的所有员工
  → 聚合这些员工的 daily_reports → 计算阶段健康度

徽远成成员分配示例（双轨并行开发期）：
  硬件轨：林跃文（采购/物料）、郑韬慧（贴片测试）
  软件轨：张毅（研发）、郭震（研发）、新雷（AI 集成）
"""
import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models.base_mixin import BaseMixin


class MemberTrack(str, enum.Enum):
    hardware = "hardware"
    software = "software"
    both     = "both"      # 如 PM / 技术负责人兼跨双轨


class ProjectMember(BaseMixin, Base):
    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    track: Mapped[MemberTrack] = mapped_column(Enum(MemberTrack), nullable=False)

    # 项目内角色（自由文本，如"硬件负责人"/"Sprint Lead"/"采购专员"）
    role_in_project: Mapped[Optional[str]] = mapped_column(String(64))

    joined_at: Mapped[date] = mapped_column(Date, default=date.today)
    left_at: Mapped[Optional[date]] = mapped_column(Date)  # 退出项目时间（null = 仍在）

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<ProjectMember user={self.user_id} track={self.track} role={self.role_in_project}>"
