"""
app/routers/knowledge.py — 知识库 API

CRUD + 语义搜索。
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role, get_current_user
from app.models.knowledge import KnowledgeItem, KnowledgeCategory
from app.models.user import User, UserRole

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Base"])


class KnowledgeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    content: str = Field(..., min_length=1)
    category: str = KnowledgeCategory.FAQ
    tags: Optional[str] = None
    project_id: Optional[str] = None
    source_type: str = "manual"


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None


@router.get("/items")
async def list_knowledge(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """知识库列表（支持分类筛选和关键词搜索）"""
    stmt = select(KnowledgeItem)

    if category:
        stmt = stmt.where(KnowledgeItem.category == category)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(
            KnowledgeItem.title.ilike(pattern),
            KnowledgeItem.content.ilike(pattern),
            KnowledgeItem.tags.ilike(pattern),
        ))

    stmt = stmt.order_by(KnowledgeItem.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    items = result.scalars().all()

    return {
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": str(i.id),
                "title": i.title,
                "category": i.category,
                "tags": i.tags,
                "source_type": i.source_type,
                "view_count": i.view_count,
                "helpful_count": i.helpful_count,
                "created_at": str(i.created_at) if i.created_at else None,
            }
            for i in items
        ],
    }


@router.get("/items/{item_id}")
async def get_knowledge_detail(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """知识条目详情（自增浏览量）"""
    result = await db.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == uuid.UUID(item_id))
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "知识条目不存在")

    item.view_count += 1
    await db.commit()

    return {
        "id": str(item.id),
        "title": item.title,
        "content": item.content,
        "category": item.category,
        "tags": item.tags,
        "source_type": item.source_type,
        "source_id": item.source_id,
        "project_id": str(item.project_id) if item.project_id else None,
        "view_count": item.view_count,
        "helpful_count": item.helpful_count,
        "created_at": str(item.created_at) if item.created_at else None,
    }


@router.post("/items")
async def create_knowledge(
    req: KnowledgeCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """创建知识条目"""
    item = KnowledgeItem(
        title=req.title,
        content=req.content,
        category=req.category,
        tags=req.tags,
        source_type=req.source_type,
        project_id=uuid.UUID(req.project_id) if req.project_id else None,
        created_by=user.id,
    )
    db.add(item)
    await db.commit()
    return {"id": str(item.id), "message": f"知识「{req.title}」已创建"}


@router.patch("/items/{item_id}")
async def update_knowledge(
    item_id: str,
    req: KnowledgeUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """更新知识条目"""
    result = await db.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == uuid.UUID(item_id))
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "知识条目不存在")

    for field in ["title", "content", "category", "tags"]:
        val = getattr(req, field, None)
        if val is not None:
            setattr(item, field, val)

    await db.commit()
    return {"message": "知识已更新"}


@router.post("/items/{item_id}/helpful")
async def mark_helpful(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """标记知识条目为「有用」"""
    result = await db.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == uuid.UUID(item_id))
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "知识条目不存在")

    item.helpful_count += 1
    await db.commit()
    return {"helpful_count": item.helpful_count}


@router.delete("/items/{item_id}")
async def delete_knowledge(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_role(UserRole.admin)),
):
    """删除知识条目"""
    result = await db.execute(
        select(KnowledgeItem).where(KnowledgeItem.id == uuid.UUID(item_id))
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "知识条目不存在")

    await db.delete(item)
    await db.commit()
    return {"message": "知识已删除"}
