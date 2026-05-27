"""
app/schemas/admin_reports.py — Phase 10 对外分组聚合 Pydantic V2 Schemas

服务于 GET /api/v1/admin/reports?group_by=department|project,统一前端 Tabs 切换器。

聚合指标对齐 trends.py /department-stats (L92-101) 的 4 项:
  - report_count: 该窗口内日报数(过滤 deleted_at IS NULL)
  - avg_score: AVG(ai_score),COALESCE 0
  - pass_count: COUNT() FILTER (pass_check = True)
  - pass_rate: pass_count / max(report_count, 1) * 100,保留 1 位小数

key 语义:
  - group_by=department: key = User.department: str(部门名称,空串表示未挂部门)
  - group_by=project: key = str(Project.id) UUID 字符串(便于前端 routing)
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

GroupBy = Literal["department", "project"]


class ReportGroupRow(BaseModel):
    """单个分组行。"""

    key: str = Field(..., description="分组键:部门名或 project_id 字符串")
    report_count: int = Field(..., ge=0, description="该窗口内日报数")
    avg_score: float = Field(..., ge=0, description="AI 评分均值,COALESCE 0")
    pass_count: int = Field(..., ge=0, description="质检通过日报数")
    pass_rate: float = Field(..., ge=0, le=100, description="通过率百分比 0-100,保留 1 位小数")

    model_config = ConfigDict(from_attributes=True)


class GroupedReportsResponse(BaseModel):
    """GET /api/v1/admin/reports 响应。"""

    group_by: GroupBy
    start_date: date
    end_date: date
    project_id: Optional[uuid.UUID]
    groups: list[ReportGroupRow]

    model_config = ConfigDict(from_attributes=True)
