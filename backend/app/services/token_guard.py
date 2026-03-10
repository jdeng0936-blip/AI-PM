"""
app/services/token_guard.py — Token 熔断守卫

调用大模型前必须通过 check_daily_quota() 检查。
超出每日配额后，拒绝服务并通知员工。
超出后调用日志也会记录（prompt_tokens=0），保留熔断事件的可追溯性。
"""
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.usage_log import TenantUsageLog


async def get_daily_usage(db: AsyncSession) -> int:
    """查询今日全系统已消耗 Token 总量"""
    today = date.today()
    result = await db.execute(
        select(
            func.coalesce(
                func.sum(TenantUsageLog.prompt_tokens + TenantUsageLog.completion_tokens),
                0
            )
        ).where(TenantUsageLog.log_date == today)
    )
    return result.scalar() or 0


async def check_daily_quota(db: AsyncSession) -> bool:
    """
    返回 True：当日配额充足，允许继续调用 AI。
    返回 False：已超配额，触发熔断。
    """
    used = await get_daily_usage(db)
    return used < settings.daily_token_limit


async def log_token_usage(
    db: AsyncSession,
    user_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    source: str = "daily_report",
) -> None:
    """
    记录本次 AI 调用的 Token 用量。
    在 AI 响应成功后调用（传入实际用量，而非预估值）。
    """
    log = TenantUsageLog(
        log_date=date.today(),
        user_id=user_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        source=source,
    )
    db.add(log)
    await db.commit()
