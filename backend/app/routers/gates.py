"""
app/routers/gates.py — IPD 关卡评审 API

核心流程：
  POST /api/v1/gates/review
    → 检查评审人权限（manager/admin）
    → AI 自动生成阶段汇总摘要（LLM 读取该阶段所有日报）
    → 记录 gate_reviews 表
    → decision=pass → project.current_stage += 1，下一阶段解锁
    → decision=fail → 推送企微通知相关成员需整改
    → decision=conditional_pass → 记录整改项，允许推进
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role, get_current_user
from app.models.gate_review import GateReview, GATE_DEFINITIONS
from app.models.project import Project
from app.models.project_stage import ProjectStage, StageHealthStatus
from app.models.user import User, UserRole
from app.schemas.project import GateReviewCreate
from app.services.ai_engine import generate_morning_briefing
from app.services.health_engine import compute_stage_health

router = APIRouter(prefix="/api/v1/gates", tags=["Gate Reviews (IPD)"])


async def _generate_gate_ai_summary(
    db, project_id: uuid.UUID, stage_number: int
) -> str:
    """调用 LLM 生成该阶段整体汇总，供评审参考"""
    from app.models.daily_report import DailyReport
    from app.models.project_member import ProjectMember

    members = await db.execute(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    )
    member_ids = [r[0] for r in members.all()]

    if not member_ids:
        return "（暂无成员日报数据）"

    # 取最近 30 条日报摘要
    reports = await db.execute(
        select(
            DailyReport.report_date,
            DailyReport.parsed_content,
            DailyReport.ai_score,
            DailyReport.management_alert,
        )
        .where(DailyReport.user_id.in_(member_ids))
        .order_by(DailyReport.report_date.desc())
        .limit(30)
    )
    rows = reports.all()

    summary_text = "\n".join(
        f"[{r[0]}] 进度:{(r[1] or {}).get('progress','?')}% "
        f"评分:{r[2]} 预警:{r[3] or '无'}"
        for r in rows
    )

    try:
        ai_text = await generate_morning_briefing(
            f"以下是项目第{stage_number}阶段所有成员的日报摘要，\n"
            f"请生成一份200字以内的阶段综合评估（包含整体进展、主要卡点、是否建议通过关卡）：\n\n"
            + summary_text
        )
        return ai_text
    except Exception:
        return f"（AI摘要生成失败，已收集 {len(rows)} 条日报数据）"


@router.post("/review")
async def submit_gate_review(
    data: GateReviewCreate,
    db: AsyncSession = Depends(get_db),
    reviewer: User = Depends(require_role(UserRole.manager, UserRole.admin)),
):
    """
    提交关卡评审。
    - decision=pass → 当前阶段 gate_passed=True，项目进入下一阶段，下阶段解锁
    - decision=fail → 项目留在当前阶段，推送警告
    - decision=conditional_pass → 进入下一阶段，但整改项记录在案
    """
    # 验证 gate_number 合法性
    gate_names = {g[0]: g[1] for g in GATE_DEFINITIONS}
    gate_name = gate_names.get(data.gate_number)
    if not gate_name:
        raise HTTPException(400, f"gate_number 必须为 1-4，收到 {data.gate_number}")

    # 取项目
    project_result = await db.execute(select(Project).where(Project.id == data.project_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "项目不存在")

    # Gate N 只能在 Stage N 完成后提交
    expected_stage = data.gate_number
    if project.current_stage < expected_stage:
        raise HTTPException(
            400,
            f"Gate {data.gate_number} 尚未开放，当前阶段为 Stage {project.current_stage}"
        )

    # AI 生成阶段摘要（供评审参考）
    ai_summary = await _generate_gate_ai_summary(db, data.project_id, data.gate_number)

    # 创建评审记录
    review = GateReview(
        project_id=data.project_id,
        gate_number=data.gate_number,
        gate_name=gate_name,
        reviewer_id=reviewer.id,
        decision=data.decision,
        decision_notes=data.decision_notes,
        ai_summary=ai_summary,
        remediation_items=data.remediation_items,
    )
    db.add(review)

    # 决策后动作
    if data.decision in ("pass", "conditional_pass"):
        # 当前阶段标记为关卡通过
        current_stage_result = await db.execute(
            select(ProjectStage).where(
                and_(
                    ProjectStage.project_id == data.project_id,
                    ProjectStage.stage_number == data.gate_number,
                )
            )
        )
        current_stage = current_stage_result.scalar_one_or_none()
        if current_stage:
            from datetime import datetime
            current_stage.gate_passed = True
            current_stage.gate_passed_at = datetime.utcnow()

        # 项目推进到下一阶段（若非最后阶段）
        if project.current_stage < 5:
            project.current_stage += 1

            # 解锁下一阶段（health_status: locked → green）
            next_stage_result = await db.execute(
                select(ProjectStage).where(
                    and_(
                        ProjectStage.project_id == data.project_id,
                        ProjectStage.stage_number == project.current_stage,
                    )
                )
            )
            next_stage = next_stage_result.scalar_one_or_none()
            if next_stage and next_stage.health_status == StageHealthStatus.locked:
                next_stage.health_status = StageHealthStatus.green
                from datetime import date as date_cls
                next_stage.actual_start = date_cls.today()

    await db.commit()

    return {
        "message": f"Gate {data.gate_number} 评审已记录",
        "decision": data.decision,
        "new_stage": project.current_stage,
        "ai_summary_preview": ai_summary[:200] + "..." if len(ai_summary) > 200 else ai_summary,
    }


@router.get("/project/{project_id}")
async def list_gate_reviews(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(UserRole.manager, UserRole.admin)),
):
    """查看项目所有历史关卡评审记录"""
    result = await db.execute(
        select(GateReview, User.name)
        .join(User, GateReview.reviewer_id == User.id, isouter=True)
        .where(GateReview.project_id == project_id)
        .order_by(GateReview.reviewed_at.desc())
    )
    return [
        {
            "gate_number": r.GateReview.gate_number,
            "gate_name": r.GateReview.gate_name,
            "reviewer": r.name,
            "decision": r.GateReview.decision,
            "decision_notes": r.GateReview.decision_notes,
            "ai_summary": r.GateReview.ai_summary,
            "remediation_items": r.GateReview.remediation_items,
            "reviewed_at": r.GateReview.reviewed_at.isoformat(),
        }
        for r in result.all()
    ]
