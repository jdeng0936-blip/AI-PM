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

from sqlalchemy import ForeignKey, Text, Date, Boolean, Integer, DateTime
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
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

    # 记录创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<DailyReport user_id={self.user_id} date={self.report_date} score={self.ai_score}>"
