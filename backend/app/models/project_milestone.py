"""
app/models/project_milestone.py — Phase 14 项目里程碑节点
"""

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class MilestoneNodeType(str, enum.Enum):
    software_req = "software_req"
    software_mvp = "software_mvp"
    software_validate = "software_validate"
    software_launch = "software_launch"
    hardware_review = "hardware_review"
    hardware_proto = "hardware_proto"
    hardware_finalize = "hardware_finalize"
    temporary_done = "temporary_done"
    custom = "custom"


class MilestoneStatus(str, enum.Enum):
    pending = "pending"
    in_review = "in_review"
    approved = "approved"
    void = "void"


class ProjectMilestone(BaseMixin, Base):
    __tablename__ = "project_milestones"
    __table_args__ = (
        Index("ix_project_milestones_project_status_order", "project_id", "status", "node_order"),
        Index("ix_project_milestones_project_status_target", "project_id", "status", "target_date"),
        CheckConstraint("initial_points >= 0", name="ck_project_milestones_initial_points_non_negative"),
        CheckConstraint(
            "(status != 'approved') OR (final_points IS NOT NULL)",
            name="ck_project_milestones_approved_requires_final_points",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_milestones_project"),
        index=True,
        nullable=False,
    )
    node_type: Mapped[MilestoneNodeType] = mapped_column(
        Enum(MilestoneNodeType, name="milestone_node_type", native_enum=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    node_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    initial_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    final_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    adjustment_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    status: Mapped[MilestoneStatus] = mapped_column(
        Enum(MilestoneStatus, name="milestone_status", native_enum=True),
        nullable=False,
        default=MilestoneStatus.pending,
        server_default="pending",
        index=True,
    )
    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_milestones_requested_by"),
        nullable=True,
    )
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_milestones_approved_by"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<ProjectMilestone project={self.project_id} type={self.node_type} status={self.status}>"
