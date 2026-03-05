"""
app/models/gate_review.py — 关卡评审记录表

IPD 共设 4 道关卡（Gate），对应 5 个阶段之间的过渡节点：
  Gate 1: 概念→计划（立项评审：明确预算、时间线、商业标准）
  Gate 2: 计划→开发（设计评审：硬件原理图+软件接口定义必须"握手"）
  Gate 3: 开发→集成（发布就绪评审 TR6：各项性能指标100%达成）
  Gate 4: 集成→量产（量产放行：实体验收+并发测试全部通过）

只有 manager 或 admin 角色的评审人可以提交 gate_reviews。
decision='pass' 时，system 会自动将 project.current_stage += 1。
"""
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class GateDecision(str, enum.Enum):
    pass_            = "pass"             # 通过，下一阶段资源放行
    fail             = "fail"             # 不通过，当前阶段需整改
    conditional_pass = "conditional_pass" # 有条件通过（列出整改项后放行）


# 4 道关卡定义
GATE_DEFINITIONS = [
    (1, "立项评审 (Gate 1)",         "концепция已验证，预算/时间线/商业标准已确认"),
    (2, "设计评审 (Gate 2)",         "软硬件接口协议已握手，禁止采购和底层开发"),
    (3, "发布就绪评审 (Gate 3/TR6)", "所有立项性能指标100%达成"),
    (4, "量产放行 (Gate 4)",         "实体验收+并发测试全部通过"),
]


class GateReview(Base):
    __tablename__ = "gate_reviews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )

    gate_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-4
    gate_name: Mapped[str] = mapped_column(String(64), nullable=False)

    # 评审人（需 manager/admin 角色）
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # 决策
    decision: Mapped[GateDecision] = mapped_column(Enum(GateDecision), nullable=False)
    decision_notes: Mapped[Optional[str]] = mapped_column(Text)

    # AI 自动生成的阶段汇总（LLM 读取过去阶段所有日报后生成，供评审参考）
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)

    # 有条件通过时的整改项列表（自由文本）
    remediation_items: Mapped[Optional[str]] = mapped_column(Text)

    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<GateReview gate={self.gate_number} decision={self.decision}>"
