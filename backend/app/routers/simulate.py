"""
app/routers/simulate.py — 开发环境模拟端点

跳过企微加密、签名校验，直接注入文本到 AI 解析 → 落库流水线。
仅在 AIPM_ENV=dev 时注册此路由。
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.daily_report import DailyReport
from app.models.risk_alert import RiskAlert
from app.models.user import User
from app.services.ai_engine import parse_report_with_ai
from app.services.token_guard import log_token_usage
from app.services.notification_service import notify_safe
from app.models.notification import NotificationTemplate, NotificationChannel

router = APIRouter(prefix="/api/v1/simulate", tags=["DEV Simulation"])


class SimulateReportRequest(BaseModel):
    """模拟日报请求体"""
    wechat_userid: str          # 用 wechat_userid 定位用户
    raw_text: str               # 日报原始文本
    report_date: Optional[date] = None  # 可指定日期，默认今天


@router.post("/daily-report")
async def simulate_daily_report(
    req: SimulateReportRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    模拟企微日报提交：
    1. 按 wechat_userid 查找用户
    2. Mock AI 解析（不调用真实 API）
    3. 落库到 daily_reports + risk_alerts
    4. 返回 AI 结果供核验
    """
    from sqlalchemy import select

    # ── 查找用户 ──
    result = await db.execute(
        select(User).where(User.wechat_userid == req.wechat_userid)
    )
    user = result.scalar_one_or_none()
    if not user:
        return {"error": f"用户 {req.wechat_userid} 不存在，请先注册"}

    # ── AI 解析（Gemini 或自动降级 Mock）──
    ai_result, p_tokens, c_tokens = await parse_report_with_ai(
        req.raw_text, [], job_title=user.job_title, department=user.department
    )

    # ── 记录 Token 用量 ──
    await log_token_usage(db, str(user.id), p_tokens, c_tokens)

    # ── 落库 ──
    report = DailyReport(
        user_id=user.id,
        report_date=req.report_date or date.today(),
        raw_input_text=req.raw_text,
        media_urls=[],
        parsed_content=ai_result.parsed_content.model_dump(mode="json"),
        pass_check=ai_result.pass_check,
        reject_reason=ai_result.reject_reason,
        suggested_guidance=ai_result.suggested_guidance,
        ai_score=ai_result.ai_score,
        ai_comment=ai_result.ai_comment,
        management_alert=ai_result.management_alert,
    )
    db.add(report)
    await db.flush()

    # ── 若有预警，写入 risk_alerts ──
    if ai_result.management_alert and ai_result.parsed_content.blocker:
        alert = RiskAlert(
            report_id=report.id,
            user_id=user.id,
            alert_type="blocker",
            description=ai_result.management_alert,
        )
        db.add(alert)

    await db.commit()

    return {
        "status": "ok",
        "report_id": str(report.id),
        "user_name": user.name,
        "department": user.department,
        "ai_score": ai_result.ai_score,
        "pass_check": ai_result.pass_check,
        "ai_comment": ai_result.ai_comment,
        "parsed_content": ai_result.parsed_content.model_dump(mode="json"),
        "management_alert": ai_result.management_alert,
        "tokens_used": {"prompt": p_tokens, "completion": c_tokens},
    }


# ═══════════════════════════════════════════════════════════════════
# Web 端提交日报（JWT 鉴权，不需要传 wechat_userid）
# ═══════════════════════════════════════════════════════════════════

class WebReportRequest(BaseModel):
    """Web 端日报请求体"""
    raw_text: str
    report_date: Optional[date] = None


@router.post("/web-submit")
async def web_submit_daily_report(
    req: WebReportRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Web 端提交日报（通过 JWT 自动识别用户）：
    1. 从 JWT token 中获取当前用户
    2. Mock AI 解析
    3. 落库到 daily_reports + risk_alerts
    4. 返回 AI 结果
    """
    # ── 获取当前用户（延迟导入以规避循环引用） ──
    from app.middleware.rbac import get_current_user
    from fastapi.security import HTTPBearer
    
    security = HTTPBearer()
    credentials = await security(request)
    current_user = await get_current_user(credentials=credentials, db=db)

    # ── 防重复提交：同一用户 + 同一天 + 相同原始文本 → 拒绝 ──
    report_date = req.report_date or date.today()
    from sqlalchemy import select, and_, func
    dup_check = await db.execute(
        select(DailyReport.id).where(
            and_(
                DailyReport.user_id == current_user.id,
                DailyReport.report_date == report_date,
                DailyReport.raw_input_text == req.raw_text,
            )
        ).limit(1)
    )
    if dup_check.scalar():
        from fastapi import HTTPException
        raise HTTPException(
            status_code=409,
            detail="该内容今天已经提交过，请勿重复提交。如需修改，请更新内容后再提交。",
        )

    # ── AI 解析（Gemini 或自动降级 Mock）──
    ai_result, p_tokens, c_tokens = await parse_report_with_ai(
        req.raw_text, [], job_title=current_user.job_title, department=current_user.department
    )

    # ── 记录 Token 用量（无论是否通过都记录）──
    await log_token_usage(db, str(current_user.id), p_tokens, c_tokens)

    # ── 质检未通过 → 不入库，返回修改建议 ──
    if not ai_result.pass_check:
        # 推送质检驳回通知到员工(企微/钉钉/站内)
        await notify_safe(
            db,
            template=NotificationTemplate.report_rejected,
            context={
                "name": current_user.name,
                "reason": ai_result.reject_reason or "",
                "guidance": ai_result.suggested_guidance or "",
            },
            channels=[
                NotificationChannel.in_app,
                NotificationChannel.wechat,
                NotificationChannel.dingtalk,
            ],
            user=current_user,
            related_type="report_rejected",
        )
        await db.commit()  # 提交 token 用量 + 通知历史
        return {
            "status": "rejected",
            "user_name": current_user.name,
            "department": current_user.department,
            "ai_score": ai_result.ai_score,
            "pass_check": False,
            "ai_comment": ai_result.ai_comment,
            "reject_reason": ai_result.reject_reason,
            "suggested_guidance": ai_result.suggested_guidance,
            "parsed_content": ai_result.parsed_content.model_dump(mode="json"),
            "management_alert": ai_result.management_alert,
            "tokens_used": {"prompt": p_tokens, "completion": c_tokens},
        }

    # ── 质检通过 → 落库 ──
    report = DailyReport(
        user_id=current_user.id,
        report_date=req.report_date or date.today(),
        raw_input_text=req.raw_text,
        media_urls=[],
        parsed_content=ai_result.parsed_content.model_dump(mode="json"),
        pass_check=ai_result.pass_check,
        reject_reason=ai_result.reject_reason,
        suggested_guidance=ai_result.suggested_guidance,
        ai_score=ai_result.ai_score,
        ai_comment=ai_result.ai_comment,
        management_alert=ai_result.management_alert,
    )
    db.add(report)
    await db.flush()

    # ── 若有预警，写入 risk_alerts + 群推预警 ──
    if ai_result.management_alert and ai_result.parsed_content.blocker:
        alert = RiskAlert(
            report_id=report.id,
            user_id=current_user.id,
            alert_type="blocker",
            description=ai_result.management_alert,
        )
        db.add(alert)

        # 风险预警 → 企微/钉钉群推给管理层
        await notify_safe(
            db,
            template=NotificationTemplate.risk_alert,
            context={
                "name": current_user.name,
                "department": current_user.department,
                "alert_type": "blocker",
                "description": ai_result.management_alert,
                "days_unresolved": 1,
            },
            channels=[
                NotificationChannel.wechat_bot,
                NotificationChannel.dingtalk_bot,
            ],
            user=current_user,
            related_type="risk_alert",
            related_id=str(report.id),
        )

    # 通过日报也推一条「评分结果」给员工(可选,默认仅站内)
    await notify_safe(
        db,
        template=NotificationTemplate.report_passed,
        context={
            "name": current_user.name,
            "score": ai_result.ai_score,
            "comment": ai_result.ai_comment or "",
        },
        channels=[NotificationChannel.in_app],
        user=current_user,
        related_type="report_passed",
        related_id=str(report.id),
    )

    await db.commit()

    return {
        "status": "ok",
        "report_id": str(report.id),
        "user_name": current_user.name,
        "department": current_user.department,
        "ai_score": ai_result.ai_score,
        "pass_check": True,
        "ai_comment": ai_result.ai_comment,
        "parsed_content": ai_result.parsed_content.model_dump(mode="json"),
        "management_alert": ai_result.management_alert,
        "tokens_used": {"prompt": p_tokens, "completion": c_tokens},
    }
