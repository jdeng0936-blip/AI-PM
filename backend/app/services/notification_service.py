"""
app/services/notification_service.py — 统一通知分发服务

设计目标:
- 一个 notify() 调用,可以分发到多个渠道(企微/钉钉/邮件/站内)
- 模板化:渲染逻辑集中在 TEMPLATES,业务方只传 context
- 历史落库:每次发送写一条 notifications 记录,便于审计/重试
- 容错:任一渠道失败不影响其他渠道,失败状态记录到 DB
- 配置感知:未配置的渠道自动 skip,不报错

使用方式:
    await notify(
        db,
        template=NotificationTemplate.report_rejected,
        context={"name": "郭震", "reason": "缺少代码版本号"},
        user=user,
        channels=[NotificationChannel.wechat, NotificationChannel.dingtalk_bot],
        related_type="report", related_id=str(report.id),
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
)
from app.models.user import User
from app.services import dingtalk_api, email_api, wechat_api

logger = logging.getLogger("aipm.notification")


# ────────────────────────────────────────────────────────────────
# 模板:每个模板渲染成 (title, body_markdown) 二元组
# 占位符使用 Python str.format 语法
# ────────────────────────────────────────────────────────────────

TEMPLATES: dict[NotificationTemplate, dict[str, str]] = {
    NotificationTemplate.report_rejected: {
        "title": "日报需要补充",
        "body": (
            "### ⚠️ {name} 的日报未通过质检\n\n**问题**: {reason}\n\n**建议补充**:\n{guidance}\n\n请尽快修改后重新提交。"
        ),
    },
    NotificationTemplate.report_passed: {
        "title": "日报已收录",
        "body": ("### ✅ {name} 日报已收录\n\n**评分**: {score}/100\n**点评**: {comment}\n"),
    },
    NotificationTemplate.risk_alert: {
        "title": "风险预警",
        "body": (
            "### 🚨 风险预警\n\n"
            "**当事人**: {name} ({department})\n"
            "**类型**: {alert_type}\n"
            "**描述**: {description}\n"
            "**连续未解决**: {days_unresolved} 天\n"
        ),
    },
    NotificationTemplate.daily_briefing: {
        "title": "每日战情简报",
        "body": (
            "### 📊 {date} 战情简报\n\n"
            "**应交**: {expected} 人 | **已交**: {submitted} 人 | "
            "**未交**: {missing} 人\n\n"
            "**平均评分**: {avg_score}/100\n"
            "**风险预警**: {risk_count} 项\n\n"
            "{summary}\n"
        ),
    },
    NotificationTemplate.reminder_soft: {
        "title": "日报提醒",
        "body": "🌤️ {name},今天的日报还没交哦,记得在 22:00 前提交~",
    },
    NotificationTemplate.reminder_hard: {
        "title": "日报截止前催促",
        "body": "⏰ {name},距离 22:00 截止还有 2 小时,请尽快提交日报。",
    },
    NotificationTemplate.reminder_missed: {
        "title": "缺勤通知",
        "body": ("### 📋 {date} 未提交日报名单\n\n{missing_list}\n\n请相关同学补提交,管理层已收到本通知。"),
    },
    NotificationTemplate.sprint_review: {
        "title": "Sprint 回顾",
        "body": (
            "### 🔁 {sprint_name} 回顾\n\n"
            "**完成率**: {completion_rate}%\n"
            "**延期任务**: {delayed_count} 项\n\n"
            "{ai_summary}\n"
        ),
    },
    NotificationTemplate.weekly_report: {
        "title": "本周管理周报",
        "body": "### 📑 本周管理周报\n\n{weekly_summary}\n",
    },
    NotificationTemplate.erp_resolved: {
        "title": "ERP 联动卡点解除",
        "body": (
            "### ⚙️ ERP 联动卡点已自动解除\n\n"
            "**关联物料**: {material} ({material_code})\n"
            "**采购单号**: {po_number}\n"
            "**ERP 单号**: {erp_order_no}\n"
            "**当前状态**: {erp_status}\n\n"
            "**已自动解卡**: 已成功将该物料关联的 **{resolved_count}** 个风险卡点状态标记为 `已解决 (resolved)`，并已触发关联项目健康度实时重算。\n"
        ),
    },
}


def render_template(template: NotificationTemplate, context: dict[str, Any]) -> tuple[str, str]:
    """渲染模板,返回 (title, body)。占位符缺失会用空串兜底。"""
    spec = TEMPLATES.get(template)
    if not spec:
        return ("", str(context))

    class _SafeDict(dict):
        def __missing__(self, key: str) -> str:
            return ""

    safe_ctx = _SafeDict(**context)
    title = spec["title"].format_map(safe_ctx)
    body = spec["body"].format_map(safe_ctx)
    return title, body


# ────────────────────────────────────────────────────────────────
# 渠道分发
# ────────────────────────────────────────────────────────────────


async def _dispatch_one(
    channel: NotificationChannel,
    user: Optional[User],
    title: str,
    body: str,
) -> tuple[NotificationStatus, Optional[str]]:
    """
    向单个渠道发送。返回 (status, error_message)。
    遵循「未配置→skip,目标缺失→skip,接口失败→failed」原则。
    """
    try:
        if channel == NotificationChannel.wechat:
            if not wechat_api.is_app_configured():
                return NotificationStatus.skipped, "wechat app not configured"
            if not user or not user.wechat_userid:
                return NotificationStatus.skipped, "user has no wechat_userid"
            await wechat_api.send_markdown_message(user.wechat_userid, body)
            return NotificationStatus.sent, None

        if channel == NotificationChannel.wechat_bot:
            if not wechat_api.is_bot_configured():
                return NotificationStatus.skipped, "wechat bot not configured"
            res = await wechat_api.send_bot_markdown(body)
            if res.get("errcode", 0) != 0:
                return NotificationStatus.failed, str(res)
            return NotificationStatus.sent, None

        if channel == NotificationChannel.dingtalk:
            if not dingtalk_api.is_app_configured():
                return NotificationStatus.skipped, "dingtalk app not configured"
            if not user or not user.dingtalk_userid:
                return NotificationStatus.skipped, "user has no dingtalk_userid"
            res = await dingtalk_api.send_app_text(user.dingtalk_userid, body)
            if res.get("errcode", 0) != 0:
                return NotificationStatus.failed, str(res)
            return NotificationStatus.sent, None

        if channel == NotificationChannel.dingtalk_bot:
            if not dingtalk_api.is_bot_configured():
                return NotificationStatus.skipped, "dingtalk bot not configured"
            res = await dingtalk_api.send_bot_markdown(title=title, text=body)
            if res.get("errcode", 0) != 0:
                return NotificationStatus.failed, str(res)
            return NotificationStatus.sent, None

        if channel == NotificationChannel.in_app:
            # 站内信:仅落库,前端拉取(已有 notifications 表足够)
            return NotificationStatus.sent, None

        if channel == NotificationChannel.email:
            if not email_api.is_configured():
                return NotificationStatus.skipped, "email channel not configured"
            if not user or not user.email:
                return NotificationStatus.skipped, "user has no email"
            await email_api.send_markdown_email(user.email, title, body)
            return NotificationStatus.sent, None

    except Exception as exc:  # pragma: no cover
        logger.exception("notification dispatch failed: %s", channel)
        return NotificationStatus.failed, str(exc)[:500]

    return NotificationStatus.skipped, "unknown channel"


# ────────────────────────────────────────────────────────────────
# 对外主接口
# ────────────────────────────────────────────────────────────────


async def notify(
    db: AsyncSession,
    *,
    template: NotificationTemplate,
    context: dict[str, Any],
    channels: list[NotificationChannel],
    user: Optional[User] = None,
    related_type: Optional[str] = None,
    related_id: Optional[str] = None,
) -> list[Notification]:
    """
    分发一条通知到多个渠道,每个渠道一条 notifications 记录。

    返回所有落库的 Notification 列表。即使分发失败,记录也会存在(便于排查)。
    """
    title, body = render_template(template, context)
    results: list[Notification] = []

    for channel in channels:
        record = Notification(
            user_id=user.id if user else None,
            channel=channel,
            template=template,
            title=title or None,
            body=body,
            context=context,
            related_type=related_type,
            related_id=related_id,
            status=NotificationStatus.pending,
        )
        db.add(record)
        # flush 拿到 id,但不 commit(由上层事务控制)
        await db.flush()

        status, err = await _dispatch_one(channel, user, title, body)
        record.status = status
        record.error_message = err
        if status == NotificationStatus.sent:
            record.sent_at = datetime.now(timezone.utc)

        results.append(record)
        logger.info(
            "notify %s/%s -> %s%s",
            channel.value,
            template.value,
            status.value,
            f" ({err})" if err else "",
        )

    return results


async def notify_safe(*args, **kwargs) -> list[Notification]:
    """
    notify() 的兜底版本:任何异常都被吞掉,只返回空列表。
    用于「通知是副作用,不应让主流程崩」的场景(如日报提交触发)。
    """
    try:
        return await notify(*args, **kwargs)
    except Exception:  # pragma: no cover
        logger.exception("notify_safe swallowed exception")
        return []
