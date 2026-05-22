"""
app/routers/erp.py — ERP 联动网关 v2

POST /api/v1/erp/webhook/status_update
接收 ERP 系统物料状态推送，自动解除关联的 risk_alerts 卡点。
权限：HMAC-SHA256 签名校验
"""
from datetime import datetime
import hmac
import hashlib
import logging

from fastapi import APIRouter, Depends, Header, Request, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import update, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.risk_alert import RiskAlert

logger = logging.getLogger("aipm.erp")

router = APIRouter(prefix="/api/v1/erp", tags=["ERP Integration"])


class ERPStatusPayload(BaseModel):
    """ERP 推送的物料状态体"""
    material: str           # 物料名称（如 "MCU模块"、"206样机壳体"）
    status: str             # 新状态（如 "已入库"、"已到货"、"已签收"）
    erp_order_no: str = ""  # ERP 单据号（可选，用于追溯）
    remark: str = ""        # 备注信息
    
    # v2 扩展精确字段
    material_code: str = "" # 物料编码（可选，优先精确匹配）
    po_number: str = ""     # 采购订单号（可选，优先精确匹配）


async def verify_erp_hmac(request: Request, x_erp_signature: str = Header(None)):
    """
    验证 ERP 系统 Webhook 推送的 HMAC-SHA256 签名。
    
    1. 若未配置 settings.erp_webhook_secret (即为 None 或空字符串)，
       则为友好支持 dev 开发测试，直接 skip 鉴权，但记录一条 warning。
    2. 若已配置，要求请求头中必须提供 X-ERP-Signature Header，
       使用 secret 对原始 body 字节流计算 HMAC-SHA256 签名。
    3. 若签名不匹配，返回 401 Unauthorized。
    """
    secret = settings.erp_webhook_secret
    if not secret:
        logger.warning("ERP webhook secret is not configured. Signature validation is skipped.")
        return
    
    if not x_erp_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-ERP-Signature header"
        )
        
    body_bytes = await request.body()
    computed_signature = hmac.new(
        secret.encode("utf-8"),
        body_bytes,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(computed_signature, x_erp_signature):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-ERP-Signature"
        )


@router.post("/webhook/status_update")
async def erp_status_update(
    payload: ERPStatusPayload,
    db: AsyncSession = Depends(get_db),
    _auth=Depends(verify_erp_hmac),
):
    """
    ERP 物料状态更新 → 自动解除相关 risk_alerts。

    匹配与解卡逻辑：
    1. 优先使用 po_number 或 material_code 精准检索 unresolved 卡点。
    2. 若未提供精确匹配字段，或精准匹配无结果，退避到在 description 中模糊匹配 material 关键字。
    3. 被解卡的 risk_alerts status 标记为 resolved，并更新 resolved_at。
    4. 联动更新：找到这些被解卡 alerts 对应用户的 active 项目，触发项目健康度实时重算。
    5. 消息推送：触发企微群机器人发送 Markdown 状态更新通知。
    """
    # 1. 精确匹配
    exact_filters = []
    if payload.po_number:
        exact_filters.append(RiskAlert.po_number == payload.po_number.strip())
    if payload.material_code:
        exact_filters.append(RiskAlert.material_code == payload.material_code.strip())
    
    resolved_ids = []
    user_ids = set()

    if exact_filters:
        stmt = (
            update(RiskAlert)
            .where(
                RiskAlert.status == "unresolved",
                or_(*exact_filters)
            )
            .values(
                status="resolved",
                resolved_at=datetime.utcnow(),
            )
            .returning(RiskAlert.id, RiskAlert.user_id)
        )
        result = await db.execute(stmt)
        rows = result.fetchall()
        resolved_ids = [str(row[0]) for row in rows]
        user_ids = {row[1] for row in rows}

    # 2. 精确匹配无结果时，退避到 description 模糊匹配
    if not resolved_ids:
        keyword = payload.material.strip()
        if keyword:
            stmt = (
                update(RiskAlert)
                .where(
                    RiskAlert.status == "unresolved",
                    RiskAlert.description.ilike(f"%{keyword}%")
                )
                .values(
                    status="resolved",
                    resolved_at=datetime.utcnow(),
                )
                .returning(RiskAlert.id, RiskAlert.user_id)
            )
            result = await db.execute(stmt)
            rows = result.fetchall()
            resolved_ids = [str(row[0]) for row in rows]
            user_ids = {row[1] for row in rows}

    # 提交解卡状态
    await db.commit()

    # 3. 联动重算项目健康度
    if resolved_ids and user_ids:
        from app.models.project import Project, ProjectStatus
        from app.models.project_member import ProjectMember
        from app.services.health_engine import refresh_project_health

        project_stmt = (
            select(Project.id)
            .join(ProjectMember, Project.id == ProjectMember.project_id)
            .where(
                ProjectMember.user_id.in_(user_ids),
                ProjectMember.left_at.is_(None),
                Project.status == ProjectStatus.active
            )
        )
        project_result = await db.execute(project_stmt)
        active_project_ids = [row[0] for row in project_result.fetchall()]

        # 刷新所有受影响活跃项目的健康度
        for p_id in active_project_ids:
            await refresh_project_health(db, p_id)

    # 4. 触发微信机器人 Markdown 通知
    if resolved_ids:
        from app.services.notification_service import notify_safe, NotificationChannel, NotificationTemplate
        await notify_safe(
            db,
            template=NotificationTemplate.erp_resolved,
            context={
                "material": payload.material,
                "material_code": payload.material_code or "N/A",
                "po_number": payload.po_number or "N/A",
                "erp_order_no": payload.erp_order_no or "N/A",
                "erp_status": payload.status,
                "resolved_count": len(resolved_ids),
            },
            channels=[NotificationChannel.wechat_bot],
            related_type="risk_alert",
            related_id=",".join(resolved_ids[:5]),
        )
        await db.commit()

    return {
        "success": True,
        "material": payload.material,
        "material_code": payload.material_code,
        "po_number": payload.po_number,
        "erp_status": payload.status,
        "resolved_alerts_count": len(resolved_ids),
        "resolved_alert_ids": resolved_ids,
    }
