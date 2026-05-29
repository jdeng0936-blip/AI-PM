"""
app/schemas/project.py — IPD 项目相关 Pydantic V2 Schemas
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ── 项目成员初始化(立项时一站式批量插入,T-1105 新增) ──────────
class ProjectMemberInit(BaseModel):
    """立项时一次性指派的项目成员。不带 project_id(由 URL 上下文注入),
    其余字段与 ProjectMemberAdd 对齐 1:1。"""

    user_id: uuid.UUID
    track: str = Field(..., description="hardware / software / both")
    role_in_project: Optional[str] = Field(None, max_length=64)


# ── 项目创建 ──────────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str = Field(..., max_length=128, description="项目名称，如'206样机研发及落地'")
    code: Optional[str] = Field(None, max_length=16, description="项目编号，如'P2026-001'，如果不填则自动生成")
    description: Optional[str] = Field(None, max_length=512)
    track: str = Field("dual", description="dual / software / hardware / support / other")
    planned_launch_date: Optional[date] = None
    budget_total: Optional[Decimal] = Field(None, description="总预算（元）")
    budget_alert_threshold: float = Field(0.8, ge=0.0, le=1.0, description="预算预警阈值")
    # V2.3 临时工单项目：勾上后跳过 5 阶段初始化，自动建一个 Backlog 虚拟 Sprint
    is_temporary: bool = Field(False, description="是否为临时工单项目(V2.3)：跳过 IPD 5 阶段初始化")
    # T-1105 立项时一站式指派成员(可选,默认 None 等价于"零成员"现状)
    members: Optional[list[ProjectMemberInit]] = Field(
        None,
        max_length=50,
        description="立项时一次性指派的项目成员(0..50);None / [] 时走零成员路径,与现状 100% 兼容",
    )


# ── 项目更新（PATCH）──────────────────────────────────────────────
class ProjectUpdate(BaseModel):
    """所有字段可选；仅传入的字段会被更新。"""

    name: Optional[str] = Field(None, max_length=128)
    description: Optional[str] = Field(None, max_length=512)
    track: Optional[str] = Field(None, description="dual / software / hardware / support / other")
    planned_launch_date: Optional[date] = None
    budget_total: Optional[Decimal] = None
    budget_alert_threshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: Optional[str] = Field(None, description="active / paused / completed / cancelled")
    # T-1106 临时工单处理结果(仅 is_temporary=True 完工时强制,主干项目永远 NULL)
    resolution_summary: Optional[str] = Field(
        None,
        max_length=2048,
        description="临时工单处理结果归集(T-1106):仅 is_temporary=True 流转 status='completed' 时强制",
    )


# ── T-1106 临时工单完工(强制结果填写) ─────────────────────────
class ProjectComplete(BaseModel):
    """临时工单流转 'completed' 时的强制结果填写 payload(供 router 守卫使用)。

    本 schema 不直接绑定到端点,仅作 router 内字段语义锚点。
    实际端点(PATCH /projects/{id})继续用 ProjectUpdate,守卫逻辑在 router 层。
    """

    resolution_summary: str = Field(..., min_length=1, max_length=2048)


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
    retrospective: dict = Field(..., description="Sprint 回顾三问：{went_well:[], improve:[], action_items:[]}")


# ── 项目成员分配 ─────────────────────────────────────────────────
class ProjectMemberAdd(BaseModel):
    project_id: uuid.UUID
    user_id: uuid.UUID
    track: str = Field(..., description="hardware / software / both")
    role_in_project: Optional[str] = Field(None, max_length=64)


# ── T-1106 项目跟进记录(轻量时间轴) ──────────────────────────
class ProjectFollowUpCreate(BaseModel):
    """成员追加跟进记录的 payload(POST /projects/{id}/followups)。"""

    content: str = Field(..., min_length=1, max_length=1024, description="跟进文本内容,1-1024 字")


class ProjectFollowUpOut(BaseModel):
    """跟进记录返回(GET /projects/{id}/followups list item)。"""

    id: str
    project_id: str
    content: str
    created_by: Optional[str]
    created_by_name: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


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
