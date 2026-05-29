"""Pydantic V2 schemas for T-1301 morning-evening close loop."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.daily_report import PlannedStatus


class MyActiveTaskItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str
    priority: str
    story_points: int
    planned_end: Optional[date]
    is_on_critical_path: bool


class MyActiveProjectItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    health_status: str
    is_temporary: bool
    member_track: str
    role_in_project: Optional[str]
    tasks: list[MyActiveTaskItem] = Field(default_factory=list)


class MyActiveProjectsResponse(BaseModel):
    projects: list[MyActiveProjectItem]
    total_projects: int
    total_tasks: int


WORK_TAG_CHOICES = (
    "研发",
    "测试",
    "评审",
    "部署",
    "沟通",
    "调研",
    "文档",
    "学习",
)


class MorningPlanCardIn(BaseModel):
    project_id: Optional[uuid.UUID] = None
    sprint_task_id: Optional[uuid.UUID] = None
    work_tags: list[str] = Field(default_factory=list, max_length=8)
    note: Optional[str] = Field(None, max_length=500, description="员工对该任务的当日备注")

    @model_validator(mode="after")
    def _at_least_one_anchor(self) -> "MorningPlanCardIn":
        if self.project_id is None and self.sprint_task_id is None and not (self.note and self.note.strip()):
            raise ValueError("计划外任务卡必须填写 note")
        return self


class MorningBatchRequest(BaseModel):
    items: list[MorningPlanCardIn] = Field(..., min_length=1, max_length=30)
    report_date: Optional[date] = None

    @model_validator(mode="after")
    def _normalize_date(self) -> "MorningBatchRequest":
        if self.report_date is None:
            self.report_date = date.today()
        return self


class MorningBatchResponse(BaseModel):
    inserted: int
    report_ids: list[uuid.UUID]


class EveningReviewCardIn(BaseModel):
    parent_report_id: uuid.UUID
    planned_status: PlannedStatus
    actual_note: Optional[str] = Field(None, max_length=500)


class EveningAdHocCardIn(BaseModel):
    project_id: Optional[uuid.UUID] = None
    sprint_task_id: Optional[uuid.UUID] = None
    work_tags: list[str] = Field(default_factory=list, max_length=8)
    note: str = Field(..., min_length=1, max_length=500)


class EveningBatchRequest(BaseModel):
    reviews: list[EveningReviewCardIn] = Field(default_factory=list, max_length=30)
    extras: list[EveningAdHocCardIn] = Field(default_factory=list, max_length=10)
    report_date: Optional[date] = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "EveningBatchRequest":
        if not self.reviews and not self.extras:
            raise ValueError("晚复核至少需要一条 review 或 extra")
        if self.report_date is None:
            self.report_date = date.today()
        return self


class EveningBatchResponse(BaseModel):
    review_count: int
    extra_count: int
    supervised_created: int
    supervised_closed: int
    evening_report_ids: list[uuid.UUID]


class PendingFollowUpItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    supervised_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    project_name: Optional[str]
    sprint_task_id: Optional[uuid.UUID]
    sprint_task_title: Optional[str]
    source_report_id: uuid.UUID
    source_planned_status: PlannedStatus
    source_note: Optional[str]
    created_at: datetime


class PendingFollowUpsResponse(BaseModel):
    items: list[PendingFollowUpItem]
    total: int
