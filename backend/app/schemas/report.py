"""
app/schemas/report.py — Pydantic V2 数据校验模型

这是整个系统的"中枢契约"：
- AI 输出的 JSON 必须通过 AIParseResult 校验
- ParsedContent 严格对齐 Excel 原始12列字段
- 任何不符合规约的 AI 输出都会触发 ValidationError
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class ParsedContent(BaseModel):
    """
    对应 Excel 日报表的所有业务字段。
    每个字段均有中文注释，方便在 System Prompt 中引用。
    """
    # ── 汇报类型 ───────────────────────────────────────────────
    report_type: str = Field(
        "日报",
        description="汇报类型：晨规划 / 日报 / 晚复盘 / 其他"
    )

    # ── 核心任务信息 ───────────────────────────────────────────
    tasks: str = Field(..., description="今日任务（对应 Excel '今日任务' 列）")
    acceptance_criteria: Optional[str] = Field(
        None, description="验收标准（对应 Excel '验收标准' 列）"
    )
    support_needed: Optional[str] = Field(
        None, description="所需支持（对应 Excel '所需支持' 列）"
    )

    # ── 进度与交付 ─────────────────────────────────────────────
    progress: int = Field(
        ..., ge=0, le=100,
        description="完成进度 0-100（对应 Excel '完成进度' 列）"
    )
    deliverable: Optional[str] = Field(
        None, description="成果演示（对应 Excel '成果演示' 列，如：已部署到测试环境可验收）"
    )
    reviewer: Optional[str] = Field(
        None, description="验收人（对应 Excel '验收人' 列）"
    )
    git_version: Optional[str] = Field(
        None, description="代码归档 Git 版本号（对应 Excel '代码归档Git版本号' 列）"
    )

    # ── 卡点与解决方案 ─────────────────────────────────────────
    blocker: Optional[str] = Field(
        None, description="核心卡点（对应 Excel '核心卡点' 列）"
    )
    next_step: Optional[str] = Field(
        None, description="解决方案（对应 Excel '解决方案' 列）"
    )
    eta: Optional[date] = Field(
        None, description="预计解决时间（对应 Excel '预计解决时间' 列，格式 YYYY-MM-DD）"
    )

    @field_validator("progress", mode="before")
    @classmethod
    def coerce_progress(cls, v: object) -> int:
        """允许 AI 输出字符串 '85%' 或 '85'，自动转为整数"""
        if isinstance(v, str):
            return int(v.strip().rstrip("%"))
        return int(v)


class AIParseResult(BaseModel):
    """
    AI 质检与解析的完整输出结构。
    与 System Prompt 中定义的 JSON Schema 严格对齐。
    """
    parsed_content: ParsedContent
    pass_check: bool
    reject_reason: Optional[str] = Field(
        None, description="若不通过，温和指出缺失细节"
    )
    suggested_guidance: Optional[str] = Field(
        None, description="若不通过，给出可直接复制修改的标准汇报模板"
    )
    ai_score: int = Field(..., ge=0, le=100, description="综合评分 0-100")
    ai_comment: str = Field(..., max_length=200, description="50字内综合点评")
    management_alert: Optional[str] = Field(
        None, description="跨部门卡点或严重滞后预警；无则为 null"
    )


# ── 对外 API 响应 Schema ───────────────────────────────────────
class ReportListItem(BaseModel):
    """晨报列表中每个员工的摘要行"""
    report_id: str
    member_name: str
    department: str
    report_date: date
    progress: Optional[int]
    blocker: Optional[str]
    ai_score: Optional[int]
    pass_check: Optional[bool]

    model_config = {"from_attributes": True}
