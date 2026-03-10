"""
app/routers/erp.py — ERP 联动网关

POST /api/v1/erp/webhook/status_update
接收 ERP 系统物料状态推送，自动解除关联的 risk_alerts 卡点。

权限：仅 admin（高权限 API，防止外部伪造）
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.risk_alert import RiskAlert
from app.models.user import UserRole

router = APIRouter(prefix="/api/v1/erp", tags=["ERP Integration"])


class ERPStatusPayload(BaseModel):
    """ERP 推送的物料状态体"""
    material: str           # 物料名称（如 "MCU模块"、"206样机壳体"）
    status: str             # 新状态（如 "已入库"、"已到货"、"已签收"）
    erp_order_no: str = ""  # ERP 单据号（可选，用于追溯）
    remark: str = ""        # 备注信息


@router.post("/webhook/status_update")
async def erp_status_update(
    payload: ERPStatusPayload,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.admin)),
):
    """
    ERP 物料状态更新 → 自动解除相关 risk_alerts。

    匹配逻辑：
    在 risk_alerts.description 中模糊匹配物料名称关键词，
    将所有命中的 unresolved 卡点标记为 resolved。
    """
    keyword = payload.material.strip()

    stmt = (
        update(RiskAlert)
        .where(
            RiskAlert.status == "unresolved",
            RiskAlert.description.ilike(f"%{keyword}%"),
        )
        .values(
            status="resolved",
            resolved_at=datetime.utcnow(),
        )
        .returning(RiskAlert.id)
    )
    result = await db.execute(stmt)
    resolved_ids = [str(row[0]) for row in result.fetchall()]
    await db.commit()

    return {
        "success": True,
        "material": payload.material,
        "erp_status": payload.status,
        "resolved_alerts_count": len(resolved_ids),
        "resolved_alert_ids": resolved_ids,
    }
