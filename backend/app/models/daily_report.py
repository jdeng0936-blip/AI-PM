"""
app/models/daily_report.py — AI 日报主表

parsed_content JSONB 结构（严格对齐原始 Excel 列）：
{
  "tasks":                "今日任务描述",
  "acceptance_criteria":  "验收标准",
  "support_needed":       "所需支持",
  "progress":             85,          ← 完成进度 %（整数0-100）
  "reviewer":             "验收人姓名",
  "git_version":          "v1.2.3 / abc1234",
  "blocker":              "核心卡点描述",
  "next_step":            "解决方案",
  "eta":                  "2026-02-28"  ← 预计解决时间
}
"""

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class DailyReport(BaseMixin, Base):
    __tablename__ = "daily_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    report_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)

    # ── 原始输入（员工在企微发送的内容）─────────────────────────────
    raw_input_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 企微图片/文件经转存后的持久化 OSS URL 列表
    media_urls: Mapped[Optional[list]] = mapped_column(ARRAY(String), default=list)

    # ── AI 解析结果（JSONB，对应 Excel 全部字段）─────────────────────
    parsed_content: Mapped[Optional[dict]] = mapped_column(JSONB)

    # ── 质检结果 ──────────────────────────────────────────────────
    pass_check: Mapped[Optional[bool]] = mapped_column(Boolean)
    reject_reason: Mapped[Optional[str]] = mapped_column(Text)
    suggested_guidance: Mapped[Optional[str]] = mapped_column(Text)
    ai_score: Mapped[Optional[int]] = mapped_column(Integer)
    ai_comment: Mapped[Optional[str]] = mapped_column(Text)

    # 跨部门卡点 / 管理层预警（送往 risk_alerts 表的摘要）
    management_alert: Mapped[Optional[str]] = mapped_column(Text)

    # Sprint 任务关联(Week 7):AI 或手工指定该日报推进了哪些 task
    # V2.2 起,主任务用 sprint_task_id 单 FK;本字段保留作为"次要多任务关联"
    mentioned_task_ids: Mapped[Optional[list]] = mapped_column(
        ARRAY(String),
        default=list,
        comment="该日报关联的 SprintTask UUID 列表(字符串形式)",
    )

    # ── V2.2 结构化关联(主任务 + 项目)──────────────────────────────
    # 员工在晨规划/日报表单提交时显式选择,前端联动校验 task ∈ project
    # 通过 sprint_task.kr_id 间接关联到 OKR KR,无需再加 kr_id 字段
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="日报关联的项目(可选)",
    )
    sprint_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sprint_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="日报关联的主任务(可选,通过 task→kr 间接挂 OKR)",
    )

    # ── V2.4 Stage 2 软删标识 ──────────────────────────────────────
    # 非 NULL 代表已被软删除;list query 默认过滤 IS NULL
    # 不真删避免破坏 ai_score / RiskAlert / Capacity 等历史聚合
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="软删除时间(V2.4):非 NULL 表示已删除,list 默认过滤",
    )

    def __repr__(self) -> str:
        return f"<DailyReport user_id={self.user_id} date={self.report_date} score={self.ai_score}>"
