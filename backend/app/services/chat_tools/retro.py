"""
chat_tools/retro.py — 复盘相关 Tools

供总经理 AI 对话使用:
- search_retros   按关键字搜索已沉淀的复盘
- list_recent_retros  最近 N 条复盘(按 scope 过滤)
- get_retro       拿到某条复盘的完整 Markdown

注:生成新复盘走 routers/retro.py 的端点(LLM 不直接生成,避免 chat 端点超时)。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import KnowledgeCategory, KnowledgeItem, RetroScope
from app.services.chat_tools import tool


@tool(description="按关键字搜索已沉淀的复盘报告(标题 + 标签),返回 Top N 条标题摘要")
async def search_retros(
    db: AsyncSession,
    keyword: str,
    limit: int = 10,
) -> dict:
    """
    Args:
        keyword: 搜索关键字(匹配标题或标签)
        limit: 返回数量上限
    """
    if not keyword:
        return {"error": "keyword 不能为空"}

    pattern = f"%{keyword}%"
    stmt = (
        select(KnowledgeItem)
        .where(
            KnowledgeItem.category == KnowledgeCategory.RETROSPECTIVE,
            or_(
                KnowledgeItem.title.ilike(pattern),
                KnowledgeItem.tags.ilike(pattern),
                KnowledgeItem.content.ilike(pattern),
            ),
        )
        .order_by(desc(KnowledgeItem.created_at))
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "count": len(rows),
        "items": [
            {
                "id": str(r.id),
                "title": r.title,
                "tags": r.tags,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@tool(description="列出最近 N 条复盘,可按 scope 过滤(okr_cycle/project/monthly/incident)")
async def list_recent_retros(
    db: AsyncSession,
    scope: str = "",
    limit: int = 10,
) -> dict:
    """
    Args:
        scope: 过滤复盘类型,可选 okr_cycle / project / monthly / incident,空=不过滤
        limit: 返回前 N 条
    """
    stmt = select(KnowledgeItem).where(
        KnowledgeItem.category == KnowledgeCategory.RETROSPECTIVE
    )
    if scope:
        if scope not in (RetroScope.OKR_CYCLE, RetroScope.PROJECT, RetroScope.MONTHLY, RetroScope.INCIDENT):
            return {"error": f"scope 不合法:{scope}"}
        stmt = stmt.where(KnowledgeItem.tags.ilike(f"%{scope}%"))
    stmt = stmt.order_by(desc(KnowledgeItem.created_at)).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()
    return {
        "scope": scope or None,
        "count": len(rows),
        "items": [
            {
                "id": str(r.id),
                "title": r.title,
                "tags": r.tags,
                "source_id": r.source_id,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@tool(description="拿到某条复盘的完整 Markdown 正文(用 search_retros / list_recent_retros 得到 id)")
async def get_retro(
    db: AsyncSession,
    retro_id: str,
) -> dict:
    """
    Args:
        retro_id: 复盘的知识条目 UUID
    """
    import uuid as _uuid
    try:
        item = await db.get(KnowledgeItem, _uuid.UUID(retro_id))
    except (ValueError, TypeError):
        return {"error": "retro_id 不是有效 UUID"}
    if not item or item.category != KnowledgeCategory.RETROSPECTIVE:
        return {"error": f"复盘 {retro_id} 不存在"}
    return {
        "id": str(item.id),
        "title": item.title,
        "tags": item.tags,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "view_count": item.view_count,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "content": item.content,
    }
