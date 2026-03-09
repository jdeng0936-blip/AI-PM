"""
app/models/knowledge.py — 知识库模型

实现白皮书「知识沉淀/复用」功能：
  - FAQ 库、最佳实践 Wiki
  - 每条知识带 pgvector embedding 用于语义检索
  - 遵循 Rule 01-Stack-Database: embedding Vector(1536) + HNSW 索引
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import (
    String, Text, Integer, ForeignKey, Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin

# pgvector 类型（需要 pgvector 扩展已安装）
try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    # Fallback: 无 pgvector 时用 Text 存 JSON 数组
    HAS_PGVECTOR = False


class KnowledgeCategory:
    """知识分类常量"""
    FAQ = "faq"               # 常见问题
    BEST_PRACTICE = "best_practice"  # 最佳实践
    LESSON_LEARNED = "lesson_learned" # 经验教训
    TEMPLATE = "template"     # 模板
    WIKI = "wiki"             # Wiki 文档


class KnowledgeItem(BaseMixin, Base):
    """知识条目 — 结构化知识记录 + 向量嵌入"""
    __tablename__ = "knowledge_items"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(
        String(300), nullable=False, index=True,
        comment="知识标题"
    )
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, default=KnowledgeCategory.FAQ,
        comment="分类: faq / best_practice / lesson_learned / template / wiki"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="知识正文（Markdown 格式）"
    )
    tags: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True,
        comment="标签，逗号分隔（如：采购,风险,质量）"
    )
    # ── 来源追溯 ──────────────────────────────────────────────────
    source_type: Mapped[str] = mapped_column(
        String(30), nullable=False, default="manual",
        comment="来源类型: manual / ai_generated / sprint_review"
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
        comment="来源 ID（如 Sprint ID、日报 ID）"
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
        comment="关联项目"
    )
    # ── pgvector 嵌入 ─────────────────────────────────────────────
    # embedding 字段: 1536 维向量（OpenAI text-embedding-3-small 兼容）
    # 如果 pgvector 不可用，回退到 Text 存 JSON
    if HAS_PGVECTOR:
        embedding: Mapped[Optional[list]] = mapped_column(
            Vector(1536), nullable=True,
            comment="1536维语义向量 (pgvector)"
        )
    else:
        embedding_json: Mapped[Optional[str]] = mapped_column(
            Text, nullable=True,
            comment="语义向量 JSON（pgvector 不可用时的回退）"
        )
    # ── 使用统计 ──────────────────────────────────────────────────
    view_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="浏览次数"
    )
    helpful_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="有用次数"
    )


# HNSW 索引（需要 pgvector 扩展）
if HAS_PGVECTOR:
    Index(
        "ix_knowledge_items_embedding_hnsw",
        KnowledgeItem.embedding,
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
