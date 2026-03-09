"""
app/routers/simulate.py — 开发环境模拟端点

跳过企微加密、签名校验，直接注入文本到 AI 解析 → 落库流水线。
仅在 AIPM_ENV=dev 时注册此路由。
"""
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.daily_report import DailyReport
from app.models.risk_alert import RiskAlert
from app.models.user import User
from app.services.ai_engine_mock import mock_parse_report
from app.services.token_guard import log_token_usage
from app.middleware.rbac import get_current_user

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

    # ── Mock AI 解析 ──
    ai_result, p_tokens, c_tokens = await mock_parse_report(req.raw_text)

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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Web 端提交日报（通过 JWT 自动识别用户）：
    1. 从 JWT token 中获取当前用户
    2. Mock AI 解析
    3. 落库到 daily_reports + risk_alerts
    4. 返回 AI 结果
    """
    # ── Mock AI 解析 ──
    ai_result, p_tokens, c_tokens = await mock_parse_report(req.raw_text)

    # ── 记录 Token 用量 ──
    await log_token_usage(db, str(current_user.id), p_tokens, c_tokens)

    # ── 落库 ──
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

    # ── 若有预警，写入 risk_alerts ──
    if ai_result.management_alert and ai_result.parsed_content.blocker:
        alert = RiskAlert(
            report_id=report.id,
            user_id=current_user.id,
            alert_type="blocker",
            description=ai_result.management_alert,
        )
        db.add(alert)

    await db.commit()

    return {
        "status": "ok",
        "report_id": str(report.id),
        "user_name": current_user.name,
        "department": current_user.department,
        "ai_score": ai_result.ai_score,
        "pass_check": ai_result.pass_check,
        "ai_comment": ai_result.ai_comment,
        "parsed_content": ai_result.parsed_content.model_dump(mode="json"),
        "management_alert": ai_result.management_alert,
        "tokens_used": {"prompt": p_tokens, "completion": c_tokens},
    }
