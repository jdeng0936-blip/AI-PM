"""
app/routers/knowledge.py — 知识库 API

CRUD + 语义搜索 + V2.5 Stage 3 批量软删与回收站。

路由顺序注意:具体路径(/items/deleted, /items/batch, /items/batch-restore)
必须放在 /items/{item_id} 通配前,否则会被通配吞掉(FastAPI 按声明顺序匹配)。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import get_current_user, require_role
from app.models.knowledge import KnowledgeCategory, KnowledgeItem
from app.models.project import Project
from app.models.user import User, UserRole
from app.services.deletion_history import mark_soft_delete_restored, record_soft_delete

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


# V2.5 Stage 3:批量操作请求体
class KnowledgeBatchBody(BaseModel):
    ids: list[uuid.UUID] = Field(..., min_length=1, max_length=200, description="待操作的知识条目 ID 列表")


@router.get("/items")
async def list_knowledge(
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="关键词搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """知识库列表（支持分类筛选和关键词搜索）

    V2.5 Stage 3:默认过滤 deleted_at IS NULL,软删条目仅回收站可见。
    """
    stmt = select(KnowledgeItem).where(KnowledgeItem.deleted_at.is_(None), KnowledgeItem.tenant_id == _user.tenant_id)

    if category:
        stmt = stmt.where(KnowledgeItem.category == category)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                KnowledgeItem.title.ilike(pattern),
                KnowledgeItem.content.ilike(pattern),
                KnowledgeItem.tags.ilike(pattern),
            )
        )

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


# ────────────────────────────────────────────────────────────────
# V2.5 Stage 3:回收站 / 批量软删 / 批量恢复
# 必须放在 /items/{item_id} 通配之前(声明顺序匹配)
# ────────────────────────────────────────────────────────────────


@router.get("/items/deleted")
async def list_deleted_knowledge(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role(UserRole.admin)),
):
    """V2.5 Stage 3:回收站 — 已软删的知识条目(含 retrospective)。"""
    stmt = (
        select(KnowledgeItem)
        .where(KnowledgeItem.deleted_at.is_not(None), KnowledgeItem.tenant_id == _user.tenant_id)
        .order_by(KnowledgeItem.deleted_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    items = [
        {
            "id": str(i.id),
            "title": i.title,
            "category": i.category,
            "tags": i.tags,
            "source_type": i.source_type,
            "source_id": i.source_id,
            "project_id": str(i.project_id) if i.project_id else None,
            "view_count": i.view_count,
            "helpful_count": i.helpful_count,
            "created_at": i.created_at.isoformat() if i.created_at else None,
            "deleted_at": i.deleted_at.isoformat() if i.deleted_at else None,
        }
        for i in rows
    ]
    return {"items": items, "total": len(items)}


@router.delete("/items/batch")
async def batch_soft_delete_knowledge(
    body: KnowledgeBatchBody = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    """V2.5 Stage 3:批量软删知识条目(admin only)。

    - 同时覆盖 knowledge 库内容与 retrospective(retro 列表共用同一张表)
    - 历史 view_count / helpful_count / source_id 关联保留
    - knowledge 列表 / retro 列表 / 语义检索 / chat tools 下次刷新自动排除
    """
    deleted_at = datetime.now(timezone.utc)
    result = await db.execute(
        update(KnowledgeItem)
        .where(
            and_(
                KnowledgeItem.id.in_(body.ids),
                KnowledgeItem.deleted_at.is_(None),
                KnowledgeItem.tenant_id == user.tenant_id,
            )
        )
        .values(deleted_at=deleted_at)
        .returning(KnowledgeItem.id)
    )
    deleted_ids = [r[0] for r in result.all()]
    await record_soft_delete(
        db,
        actor_id=user.id,
        table_name="knowledge_items",
        record_ids=deleted_ids,
        deleted_at=deleted_at,
        tenant_id=user.tenant_id,
    )
    await db.commit()
    return {
        "requested": len(body.ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": [str(i) for i in deleted_ids],
    }


@router.patch("/items/batch-restore")
async def batch_restore_knowledge(
    body: KnowledgeBatchBody = Body(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    """V2.5 Stage 3:从回收站批量恢复知识条目(SET deleted_at = NULL)。"""
    result = await db.execute(
        update(KnowledgeItem)
        .where(
            and_(
                KnowledgeItem.id.in_(body.ids),
                KnowledgeItem.deleted_at.is_not(None),
                KnowledgeItem.tenant_id == user.tenant_id,
            )
        )
        .values(deleted_at=None)
        .returning(KnowledgeItem.id)
    )
    restored_ids = [r[0] for r in result.all()]
    await mark_soft_delete_restored(
        db,
        table_name="knowledge_items",
        record_ids=restored_ids,
        restored_by=user.id,
        tenant_id=user.tenant_id,
    )
    await db.commit()
    return {
        "requested": len(body.ids),
        "restored_count": len(restored_ids),
        "restored_ids": [str(i) for i in restored_ids],
    }


# ────────────────────────────────────────────────────────────────
# 单条操作(放在 batch 路由之后以避免 /items/batch 被吞)
# ────────────────────────────────────────────────────────────────


@router.get("/items/{item_id}")
async def get_knowledge_detail(
    item_id: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(get_current_user),
):
    """知识条目详情（自增浏览量）"""
    result = await db.execute(
        select(KnowledgeItem).where(
            KnowledgeItem.id == uuid.UUID(item_id),
            KnowledgeItem.tenant_id == _user.tenant_id,
            KnowledgeItem.deleted_at.is_(None),  # V2.5 Stage 3:软删条目对普通用户隐藏
        )
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
    project_uuid = uuid.UUID(req.project_id) if req.project_id else None
    if project_uuid:
        project = (
            await db.execute(
                select(Project.id).where(
                    Project.id == project_uuid,
                    Project.tenant_id == user.tenant_id,
                    Project.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if not project:
            raise HTTPException(404, "项目不存在")

    item = KnowledgeItem(
        title=req.title,
        content=req.content,
        category=req.category,
        tags=req.tags,
        source_type=req.source_type,
        project_id=project_uuid,
        created_by=user.id,
        tenant_id=user.tenant_id,
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
        select(KnowledgeItem).where(
            KnowledgeItem.id == uuid.UUID(item_id),
            KnowledgeItem.tenant_id == _user.tenant_id,
            KnowledgeItem.deleted_at.is_(None),  # V2.5 Stage 3:已软删条目不允许就地编辑
        )
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
        select(KnowledgeItem).where(
            KnowledgeItem.id == uuid.UUID(item_id),
            KnowledgeItem.tenant_id == _user.tenant_id,
            KnowledgeItem.deleted_at.is_(None),  # V2.5 Stage 3:软删条目不计有用数
        )
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
    user: User = Depends(require_role(UserRole.admin)),
):
    """V2.5 Stage 3:软删知识条目(原硬删改为 SET deleted_at = now())。

    历史 view_count / helpful_count / source_id(如复盘对应的 sprint)保留,
    可通过 /knowledge/items/deleted 回收站恢复。
    """
    result = await db.execute(
        select(KnowledgeItem).where(
            KnowledgeItem.id == uuid.UUID(item_id),
            KnowledgeItem.tenant_id == user.tenant_id,
            KnowledgeItem.deleted_at.is_(None),
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "知识条目不存在")

    deleted_at = datetime.now(timezone.utc)
    item.deleted_at = deleted_at
    await record_soft_delete(
        db,
        actor_id=user.id,
        table_name="knowledge_items",
        record_ids=[item.id],
        deleted_at=deleted_at,
        tenant_id=user.tenant_id,
    )
    await db.commit()
    return {"message": "知识已软删"}
