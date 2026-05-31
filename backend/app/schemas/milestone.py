"""
app/schemas/milestone.py — Phase 14 T-1401 里程碑与积分贡献 Pydantic schemas
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.milestone_allocation import AllocationStatus
from app.models.project_milestone import MilestoneNodeType, MilestoneStatus
from app.models.user_points_ledger import LedgerDirection


class MilestoneTemplateNode(BaseModel):
    node_type: MilestoneNodeType
    title: str = Field(..., max_length=128)
    suggested_initial_points: int = Field(default=0, ge=0)
    node_order: int = Field(default=0, ge=0)


class MilestoneTemplateResponse(BaseModel):
    track: Literal["software", "hardware", "dual", "support", "other"]
    is_temporary: bool
    nodes: list[MilestoneTemplateNode]


class AllocationItem(BaseModel):
    user_id: uuid.UUID
    contribution_ratio: Decimal = Field(..., ge=0, le=1, max_digits=5, decimal_places=4)


class MilestoneNodeIn(BaseModel):
    node_type: MilestoneNodeType
    title: str = Field(..., max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    node_order: int = Field(default=0, ge=0)
    initial_points: int = Field(default=0, ge=0)
    target_date: Optional[date] = None
    planned_allocations: Optional[list[AllocationItem]] = Field(
        default=None,
        max_length=20,
        description="立项时预分配到该贡献节点的成员与比例；用于把工作内容和人员绑定",
    )

    @model_validator(mode="after")
    def check_planned_allocation_sum(self) -> "MilestoneNodeIn":
        if not self.planned_allocations:
            return self
        total = sum(item.contribution_ratio for item in self.planned_allocations)
        if abs(total - Decimal("1")) > Decimal("0.0001"):
            raise ValueError(f"planned_allocations contribution_ratio 总和必须等于 1.0(实际:{total})")
        user_ids = [item.user_id for item in self.planned_allocations]
        if len(set(user_ids)) != len(user_ids):
            raise ValueError("同一 user_id 不可在 planned_allocations 中重复出现")
        return self


class MilestoneSeedRequest(BaseModel):
    nodes: list[MilestoneNodeIn] = Field(..., min_length=1, max_length=20)


class MilestoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    node_type: MilestoneNodeType
    title: str
    description: Optional[str]
    node_order: int
    initial_points: int
    final_points: Optional[int]
    adjustment_reason: Optional[str]
    target_date: Optional[date]
    status: MilestoneStatus
    requested_by: Optional[uuid.UUID]
    requested_at: Optional[datetime]
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    created_at: datetime


class MilestoneSeedResponse(BaseModel):
    project_id: uuid.UUID
    created: int
    milestones: list[MilestoneOut]


class MilestonePatchRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    node_order: Optional[int] = Field(default=None, ge=0)
    initial_points: Optional[int] = Field(default=None, ge=0)
    target_date: Optional[date] = None


class MilestoneListResponse(BaseModel):
    project_id: uuid.UUID
    items: list[MilestoneOut]


class AllocationProposalRequest(BaseModel):
    allocations: list[AllocationItem] = Field(..., min_length=1, max_length=20)

    @model_validator(mode="after")
    def check_ratio_sum(self) -> "AllocationProposalRequest":
        total = sum(item.contribution_ratio for item in self.allocations)
        if abs(total - Decimal("1")) > Decimal("0.0001"):
            raise ValueError(f"contribution_ratio 总和必须等于 1.0(实际:{total})")

        user_ids = [item.user_id for item in self.allocations]
        if len(set(user_ids)) != len(user_ids):
            raise ValueError("同一 user_id 不可在 allocations 中重复出现")
        return self


class AllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    milestone_id: uuid.UUID
    user_id: uuid.UUID
    contribution_ratio: Decimal
    initial_points: int
    final_points: Optional[int]
    status: AllocationStatus
    proposed_by: Optional[uuid.UUID]
    proposed_at: Optional[datetime]
    reverted_at: Optional[datetime]
    revert_reason: Optional[str]
    created_at: datetime


class AllocationProposalResponse(BaseModel):
    milestone_id: uuid.UUID
    allocations: list[AllocationOut]


class MilestoneApprovalRequest(BaseModel):
    final_points: int = Field(..., ge=0)
    adjustment_reason: Optional[str] = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def check_reason_when_delta(self) -> "MilestoneApprovalRequest":
        if self.adjustment_reason is not None and not self.adjustment_reason.strip():
            raise ValueError("adjustment_reason 若提供则不可为空白")
        return self


class MilestoneApprovalResponse(BaseModel):
    milestone: MilestoneOut
    allocations: list[AllocationOut]
    ledger_entries_created: int


class AllocationRevertRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2048)


class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    milestone_id: Optional[uuid.UUID]
    milestone_title: Optional[str]
    project_id: Optional[uuid.UUID]
    project_name: Optional[str]
    allocation_id: Optional[uuid.UUID]
    direction: LedgerDirection
    amount: int
    occurred_at: datetime
    reason: str


class AllocationRevertResponse(BaseModel):
    allocation: AllocationOut
    ledger_entry: LedgerEntryOut


class LedgerHistoryResponse(BaseModel):
    items: list[LedgerEntryOut]
    next_cursor: Optional[str]


PeriodLiteral = Literal["all", "year", "quarter", "month"]


class ContributionSummary(BaseModel):
    user_id: uuid.UUID
    period: PeriodLiteral
    total_points: int
    income_points: int
    refund_points: int
    adjustment_points: int
    milestone_count: int


class UserContributionResponse(BaseModel):
    summary: ContributionSummary
    recent_ledger: list[LedgerEntryOut]


MilestoneSeedResponse.model_rebuild()
AllocationRevertResponse.model_rebuild()
