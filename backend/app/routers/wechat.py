"""
app/routers/wechat.py — 企业微信消息网关（核心主流水线）

完整处理流程：
  GET  /api/v1/wechat/callback  → 企微服务器地址验证
  POST /api/v1/wechat/callback  → 接收加密消息 → 解密身份映射
                                → 异步 AI 质检 → 落库 / 推送结果
"""
import xml.etree.ElementTree as ET
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.daily_report import DailyReport
from app.models.risk_alert import RiskAlert
from app.models.user import User
from app.services.ai_engine import parse_report_with_ai
from app.services.token_guard import check_daily_quota, log_token_usage
from app.services.wechat_api import (
    decrypt_message,
    fetch_media_url,
    send_text_message,
    verify_signature,
)

router = APIRouter(prefix="/api/v1/wechat", tags=["WeChat Gateway"])


@router.get("/callback")
async def verify_wechat_server(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    """
    Step 1: 企微服务器地址验证（配置回调URL时调用一次）
    校验通过后原样返回 echostr，完成验证握手。
    """
    if verify_signature(msg_signature, timestamp, nonce):
        return int(echostr)
    return {"error": "signature mismatch"}


@router.post("/callback")
async def receive_wechat_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2+: 接收员工日报消息主入口
    注意：企微要求 5 秒内返回 "success"，因此 AI 处理走后台任务。
    """
    body = await request.body()

    # ── 解密消息体 ──────────────────────────────────────────────
    xml_tree = ET.fromstring(body.decode("utf-8"))
    encrypted_content = xml_tree.findtext("Encrypt", "")

    if not verify_signature(msg_signature, timestamp, nonce, encrypted_content):
        return "invalid signature"

    raw_xml = decrypt_message(encrypted_content)
    msg_tree = ET.fromstring(raw_xml)

    from_user: str = msg_tree.findtext("FromUserName", "")
    msg_type: str  = msg_tree.findtext("MsgType", "")

    # ── 身份映射（企微 userid → 数据库 User） ─────────────────────
    result = await db.execute(select(User).where(User.wechat_userid == from_user))
    user = result.scalar_one_or_none()

    if not user:
        await send_text_message(from_user, "❌ 您的账号尚未注册，请联系管理员添加。")
        return "success"

    # ── 提取消息内容（文字 + 图片） ───────────────────────────────
    raw_text = ""
    media_urls: list[str] = []

    if msg_type == "text":
        raw_text = msg_tree.findtext("Content", "").strip()
    elif msg_type == "image":
        media_id = msg_tree.findtext("MediaId", "")
        if media_id:
            url = await fetch_media_url(media_id)
            if url:
                media_urls.append(url)
        raw_text = "[员工附上了图片作为进度佐证]"
    elif msg_type == "voice":
        # 语音消息：企微提供文字识别结果（需开启语音识别）
        raw_text = msg_tree.findtext("Recognition", "[语音内容]").strip()
    else:
        # 其他消息类型暂不处理
        await send_text_message(
            from_user, "📌 目前仅支持文字和图片汇报，语音请直接发送文字。"
        )
        return "success"

    if not raw_text and not media_urls:
        await send_text_message(from_user, "⚠️ 收到空消息，请重新发送您的日报。")
        return "success"

    # ── 异步处理（5秒内必须返回 success） ────────────────────────
    background_tasks.add_task(
        _process_report_async,
        user=user,
        raw_text=raw_text,
        media_urls=media_urls,
    )

    return "success"


async def _process_report_async(
    user: User,
    raw_text: str,
    media_urls: list[str],
) -> None:
    """
    后台异步流水线：
    Token 熔断检查 → AI 解析 → 质检判断 → 落库 → 推送结果给员工
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        # ── Token 熔断检查 ──────────────────────────────────────
        allowed = await check_daily_quota(db)
        if not allowed:
            await send_text_message(
                user.wechat_userid,
                "⚠️ 今日 AI 处理配额已满，您的日报将在明日自动处理。\n"
                "如紧急，请直接联系管理员。",
            )
            return

        # ── AI 多模态解析 ───────────────────────────────────────
        try:
            ai_result, p_tokens, c_tokens = await parse_report_with_ai(
                raw_text, media_urls
            )
        except Exception as e:
            await send_text_message(
                user.wechat_userid,
                f"❌ AI 解析异常，请稍后重试或联系管理员。\n错误信息：{str(e)[:100]}",
            )
            return

        # 记录实际 Token 消耗
        await log_token_usage(db, str(user.id), p_tokens, c_tokens)

        # ── 落库（事务） ────────────────────────────────────────
        report = DailyReport(
            user_id=user.id,
            report_date=date.today(),
            raw_input_text=raw_text,
            media_urls=media_urls,
            parsed_content=ai_result.parsed_content.model_dump(mode="json"),
            pass_check=ai_result.pass_check,
            reject_reason=ai_result.reject_reason,
            suggested_guidance=ai_result.suggested_guidance,
            ai_score=ai_result.ai_score,
            ai_comment=ai_result.ai_comment,
            management_alert=ai_result.management_alert,
        )
        db.add(report)
        await db.flush()  # 获取 report.id

        # ── 若有预警，同步写入 risk_alerts ────────────────────────
        if ai_result.management_alert and ai_result.parsed_content.blocker:
            alert = RiskAlert(
                report_id=report.id,
                user_id=user.id,
                alert_type="blocker",
                description=ai_result.management_alert,
            )
            db.add(alert)

        await db.commit()

        # ── 推送结果给员工 ──────────────────────────────────────
        if ai_result.pass_check:
            msg = (
                f"✅ 日报已收录！\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"📊 AI 评分：{ai_result.ai_score}/100\n"
                f"📝 综合点评：{ai_result.ai_comment}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"感谢您的认真汇报！"
            )
        else:
            msg = (
                f"⚠️ 日报需要补充信息\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"❌ 问题：{ai_result.reject_reason}\n\n"
                f"📝 参考模板：\n"
                f"{ai_result.suggested_guidance}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"请按以上模板修改后重新发送。"
            )

        await send_text_message(user.wechat_userid, msg)
