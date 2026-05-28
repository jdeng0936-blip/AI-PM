"""
tests/test_attachments.py — 附件上传/查询/删除测试

覆盖:
- oss_service 本地降级模式
- Attachment 模型落库
- mime_type 自动分类
- 路径穿越防护

注:不依赖真实 OSS / 讯飞凭证,所有外部调用走本地降级。
"""

from __future__ import annotations

import asyncio
import tempfile
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.models.attachment import Attachment, AttachmentKind
from app.models.user import User, UserRole
from app.routers.attachments import _classify
from app.services import oss_service
from tests._db_url import derive_test_database_url

TEST_DATABASE_URL = derive_test_database_url(settings.database_url)


@pytest_asyncio.fixture
async def isolated_db():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session

    await engine.dispose()


# ────────────────────────────────────────────────────────────────
# 纯函数:mime 分类
# ────────────────────────────────────────────────────────────────


def test_classify_image():
    assert _classify("image/png", "x.png") == AttachmentKind.image
    assert _classify("image/jpeg", "x.jpg") == AttachmentKind.image
    assert _classify("", "photo.webp") == AttachmentKind.image


def test_classify_voice():
    assert _classify("audio/wav", "v.wav") == AttachmentKind.voice
    assert _classify("audio/mpeg", "v.mp3") == AttachmentKind.voice
    assert _classify("", "rec.m4a") == AttachmentKind.voice


def test_classify_document():
    assert _classify("application/pdf", "c.pdf") == AttachmentKind.document
    assert _classify("", "doc.docx") == AttachmentKind.document
    assert _classify("text/plain", "note.txt") == AttachmentKind.document


def test_classify_other_fallback():
    assert _classify("application/octet-stream", "unknown.bin") == AttachmentKind.other


# ────────────────────────────────────────────────────────────────
# 存储 key 生成
# ────────────────────────────────────────────────────────────────


def test_make_storage_key_format():
    key = oss_service.make_storage_key(
        kind="image",
        user_id="u123",
        file_name="photo.png",
    )
    assert key.startswith("attachments/image/")
    assert "u123" in key
    assert key.endswith("_photo.png")


def test_make_storage_key_strips_path():
    """文件名中的目录分量应被剥离,防止路径穿越"""
    key = oss_service.make_storage_key(
        kind="image",
        user_id="u1",
        file_name="../../etc/passwd",
    )
    assert "../" not in key
    assert key.endswith("_passwd")


def test_make_storage_key_unique():
    """同名文件每次生成不同 key"""
    k1 = oss_service.make_storage_key(kind="image", user_id="u1", file_name="a.png")
    k2 = oss_service.make_storage_key(kind="image", user_id="u1", file_name="a.png")
    assert k1 != k2


# ────────────────────────────────────────────────────────────────
# 本地降级:上传 + 读取
# ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_local_upload_when_oss_unavailable(monkeypatch, tmp_path):
    """OSS 未配置时,upload_bytes 应落到本地目录并返回代理 URL"""
    monkeypatch.setattr(oss_service, "is_configured", lambda: False)
    monkeypatch.setattr(settings, "local_upload_dir", str(tmp_path))

    key = "attachments/test/2026/05/19/abc/xxx_hello.txt"
    url = await oss_service.upload_bytes(key, b"hello world", "text/plain")

    assert url.startswith("/api/v1/attachments/local/")
    saved = tmp_path / key
    assert saved.exists()
    assert saved.read_bytes() == b"hello world"


@pytest.mark.asyncio
async def test_local_read_back(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "local_upload_dir", str(tmp_path))
    target = tmp_path / "attachments/test/1.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"abc")

    data = oss_service.read_local_file("attachments/test/1.txt")
    assert data == b"abc"


def test_local_read_path_traversal_blocked(monkeypatch, tmp_path):
    """读取本地文件时禁止 ../ 跳出 upload_dir"""
    monkeypatch.setattr(settings, "local_upload_dir", str(tmp_path))
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("PWNED")

    data = oss_service.read_local_file("../secret.txt")
    assert data is None


# ────────────────────────────────────────────────────────────────
# Attachment 模型落库
# ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_attachment_persists(isolated_db):
    user = User(
        wechat_userid=f"test_att_{uuid.uuid4().hex[:8]}",
        name="附件测试员",
        department="测试部",
        role=UserRole.employee,
    )
    isolated_db.add(user)
    await isolated_db.commit()
    await isolated_db.refresh(user)

    att = Attachment(
        uploaded_by=user.id,
        kind=AttachmentKind.image,
        file_name="photo.png",
        mime_type="image/png",
        size_bytes=1234,
        storage_key=f"attachments/image/test/{uuid.uuid4().hex}.png",
        file_url="https://example.com/photo.png",
    )
    isolated_db.add(att)
    await isolated_db.commit()
    await isolated_db.refresh(att)

    rows = (await isolated_db.execute(select(Attachment).where(Attachment.uploaded_by == user.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].kind == AttachmentKind.image
    assert rows[0].file_name == "photo.png"
    assert rows[0].size_bytes == 1234
