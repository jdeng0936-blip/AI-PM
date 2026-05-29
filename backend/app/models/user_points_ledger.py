"""
app/models/user_points_ledger.py — Phase 14 用户贡献积分流水
"""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class LedgerDirection(str, enum.Enum):
    income = "income"
    refund = "refund"
    adjustment = "adjustment"


class UserPointsLedger(BaseMixin, Base):
    __tablename__ = "user_points_ledger"
    __table_args__ = (
        Index("ix_user_points_ledger_user_occurred", "user_id", "occurred_at"),
        Index("ix_user_points_ledger_milestone_direction", "milestone_id", "direction"),
        CheckConstraint("amount != 0", name="ck_user_points_ledger_amount_non_zero"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_ledger_user"),
        index=True,
        nullable=False,
    )
    milestone_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="SET NULL", name="fk_ledger_milestone"),
        nullable=True,
    )
    allocation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("milestone_allocations.id", ondelete="SET NULL", name="fk_ledger_allocation"),
        nullable=True,
    )
    direction: Mapped[LedgerDirection] = mapped_column(
        Enum(LedgerDirection, name="ledger_direction", native_enum=True),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<UserPointsLedger user={self.user_id} amount={self.amount} direction={self.direction}>"
