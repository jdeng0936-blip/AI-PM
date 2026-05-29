"""
app/models/milestone_allocation.py — Phase 14 里程碑积分分配明细
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Numeric, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class AllocationStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    reverted = "reverted"


class MilestoneAllocation(BaseMixin, Base):
    __tablename__ = "milestone_allocations"
    __table_args__ = (
        Index(
            "ix_milestone_allocations_milestone_user_active",
            "milestone_id",
            "user_id",
            unique=True,
            postgresql_where=text("status != 'reverted'"),
        ),
        Index("ix_milestone_allocations_user_status_created", "user_id", "status", "created_at"),
        CheckConstraint(
            "contribution_ratio >= 0 AND contribution_ratio <= 1",
            name="ck_milestone_allocations_ratio_between_0_and_1",
        ),
        CheckConstraint("initial_points >= 0", name="ck_milestone_allocations_initial_points_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="CASCADE", name="fk_allocations_milestone"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_allocations_user"),
        index=True,
        nullable=False,
    )
    contribution_ratio: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    initial_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    final_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[AllocationStatus] = mapped_column(
        Enum(AllocationStatus, name="allocation_status", native_enum=True),
        nullable=False,
        default=AllocationStatus.pending,
        server_default="pending",
        index=True,
    )
    proposed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_allocations_proposed_by"),
        nullable=True,
    )
    proposed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reverted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revert_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<MilestoneAllocation milestone={self.milestone_id} user={self.user_id} status={self.status}>"
