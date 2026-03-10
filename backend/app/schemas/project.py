"""
app/schemas/project.py — IPD 项目相关 Pydantic V2 Schemas
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ── 项目创建 ──────────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=128, description="项目名称，如'206样机研发及落地'")
    code: str = Field(..., max_length=16, description="项目编号，如'P2026-001'")
    description: Optional[str] = Field(None, max_length=512)
    track: str = Field("dual", description="dual / software / hardware")
    planned_launch_date: Optional[date] = None
    budget_total: Optional[Decimal] = Field(None, description="总预算（元）")
    budget_alert_threshold: float = Field(0.8, ge=0.0, le=1.0, description="预算预警阈值")


# ── 里程碑节点（JSONB 内元素）────────────────────────────────────
class Milestone(BaseModel):
    name: str
    planned_date: date
    actual_date: Optional[date] = None
    status: str = "pending"  # pending / in_progress / done / blocked


# ── 阶段更新（进度/里程碑） ───────────────────────────────────────
class StageUpdate(BaseModel):
    progress_pct: Optional[int] = Field(None, ge=0, le=100)
    milestones: Optional[list[Milestone]] = None
    actual_start: Optional[date] = None
    actual_end: Optional[date] = None


# ── 关卡评审提交 ──────────────────────────────────────────────────
class GateReviewCreate(BaseModel):
    project_id: uuid.UUID
    gate_number: int = Field(..., ge=1, le=4, description="关卡编号 1-4")
    decision: str = Field(..., description="pass / fail / conditional_pass")
    decision_notes: Optional[str] = None
    remediation_items: Optional[str] = Field(None, description="有条件通过时的整改项")


# ── Sprint 创建 ───────────────────────────────────────────────────
class SprintCreate(BaseModel):
    project_id: uuid.UUID
    stage_id: Optional[uuid.UUID] = None
    sprint_number: int = Field(..., ge=1)
    goal: Optional[str] = Field(None, max_length=256)
    start_date: date
    end_date: date
    planned_story_points: int = Field(0, ge=0)


# ── Sprint 完成（填写回顾） ───────────────────────────────────────
class SprintComplete(BaseModel):
    completed_story_points: int = Field(..., ge=0)
    retrospective: dict = Field(
        ...,
        description="Sprint 回顾三问：{went_well:[], improve:[], action_items:[]}"
    )


# ── 项目成员分配 ─────────────────────────────────────────────────
class ProjectMemberAdd(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    track: str = Field(..., description="hardware / software / both")
    role_in_project: Optional[str] = Field(None, max_length=64)


# ── API 响应：项目总览（红绿黄矩阵） ─────────────────────────────
class ProjectOverviewItem(BaseModel):
    project_id: str
    code: str
    name: str
    current_stage: int
    stage_name: str
    track: str
    health_status: str
    health_score: int
    progress_pct: int
    planned_launch_date: Optional[date]
    days_to_deadline: Optional[int]
    budget_usage_pct: Optional[float]
    status: str

    model_config = {"from_attributes": True}


# ── API 响应：甘特图数据 ──────────────────────────────────────────
class GanttStage(BaseModel):
    stage_number: int
    stage_name: str
    track: str
    planned_start: Optional[date]
    planned_end: Optional[date]
    actual_start: Optional[date]
    actual_end: Optional[date]
    progress_pct: int
    health_status: str
    gate_passed: bool
    milestones: list[dict]

    model_config = {"from_attributes": True}
