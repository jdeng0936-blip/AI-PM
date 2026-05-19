"""
app/models/attachment.py — 附件元数据表

设计原则:
- 文件二进制走 OSS,本表只存元数据 + URL(架构红线 Rule 3)
- 与 daily_reports 弱绑定:既支持「未提交日报前先上传」,也支持「直接关联到已提交日报」
- 支持图片/语音/文档三类,语音附加 transcript 字段保存讯飞 ASR 结果
"""
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class AttachmentKind(str, enum.Enum):
    image = "image"
    voice = "voice"
    document = "document"
    other = "other"


class Attachment(BaseMixin, Base):
    __tablename__ = "attachments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # 上传者
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # 可选关联到具体日报(允许先传文件再提交日报)
    related_report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    # 文件元数据
    kind: Mapped[AttachmentKind] = mapped_column(
        Enum(AttachmentKind), nullable=False, default=AttachmentKind.other, index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    # OSS 对象 key + 公网 URL(若 bucket 为 private,通过 presigned URL 访问)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    file_url: Mapped[str] = mapped_column(String(1024), nullable=False)

    # 语音专用:讯飞 ASR 转写文本
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Attachment kind={self.kind} name={self.file_name}>"
