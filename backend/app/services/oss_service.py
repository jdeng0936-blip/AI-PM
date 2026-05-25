"""
app/services/oss_service.py — 阿里云 OSS 对象存储封装

提供:
- upload_bytes(): 把字节流上传到 OSS,返回公网 URL
- generate_presigned_url(): 为 private bucket 生成限时访问 URL
- delete(): 删除对象
- is_configured(): 检查是否已配好凭证

降级模式:OSS 未配置时,自动落本地 LOCAL_UPLOAD_DIR 目录,
URL 形式为 /api/v1/attachments/local/{path},供前端通过后端代理访问。
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

import oss2

from app.config import settings

logger = logging.getLogger("aipm.oss")


def is_configured() -> bool:
    return bool(
        settings.oss_endpoint
        and settings.oss_bucket
        and settings.oss_access_key
        and settings.oss_secret_key
        and not settings.oss_access_key.startswith("your_")  # 占位值不算配好
    )


def _get_bucket() -> oss2.Bucket:
    """返回 OSS Bucket 客户端"""
    auth = oss2.Auth(settings.oss_access_key, settings.oss_secret_key)
    return oss2.Bucket(auth, settings.oss_endpoint, settings.oss_bucket)


def _build_public_url(key: str) -> str:
    """根据配置组装公网访问 URL"""
    if settings.oss_public_url_base:
        base = settings.oss_public_url_base.rstrip("/")
        return f"{base}/{key}"
    # 默认形式: https://<bucket>.<endpoint-host>/<key>
    endpoint = settings.oss_endpoint.replace("https://", "").replace("http://", "")
    return f"https://{settings.oss_bucket}.{endpoint}/{key}"


def make_storage_key(*, kind: str, user_id: str, file_name: str) -> str:
    """
    生成 OSS 对象 key,按日期 + 用户 + 类型分目录:
      attachments/{kind}/{YYYY}/{MM}/{DD}/{user_id}/{uuid}_{filename}
    """
    today = date.today()
    safe_name = Path(file_name).name.replace(" ", "_")  # 去掉路径分量
    unique = uuid.uuid4().hex[:12]
    return f"attachments/{kind}/{today.year}/{today.month:02d}/{today.day:02d}/{user_id}/{unique}_{safe_name}"


# ────────────────────────────────────────────────────────────────
# 上传
# ────────────────────────────────────────────────────────────────


async def upload_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """
    上传字节流到 OSS,返回公网 URL。
    未配置 OSS 时自动降级到本地 LOCAL_UPLOAD_DIR。
    """
    if is_configured():
        try:
            bucket = _get_bucket()
            # oss2 是同步 SDK,这里在线程池里跑避免阻塞 event loop
            import asyncio

            await asyncio.to_thread(
                bucket.put_object,
                key,
                data,
                headers={"Content-Type": content_type},
            )
            url = _build_public_url(key)
            logger.info("OSS upload ok: %s (%d bytes)", key, len(data))
            return url
        except Exception as exc:
            logger.exception("OSS upload failed, fallback to local: %s", exc)

    # ── 本地降级 ──
    local_dir = Path(settings.local_upload_dir).resolve()
    target = local_dir / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    logger.info("local upload ok: %s (%d bytes)", target, len(data))
    # 本地 URL 通过后端代理路由访问
    return f"/api/v1/attachments/local/{key}"


# ────────────────────────────────────────────────────────────────
# 临时签名 URL(private bucket)
# ────────────────────────────────────────────────────────────────


def generate_presigned_url(key: str, expires_seconds: int = 3600) -> Optional[str]:
    """为 private bucket 生成 expires_seconds 秒内有效的访问 URL"""
    if not is_configured():
        return None
    try:
        bucket = _get_bucket()
        return bucket.sign_url("GET", key, expires_seconds, slash_safe=True)
    except Exception:
        logger.exception("generate_presigned_url failed")
        return None


# ────────────────────────────────────────────────────────────────
# 删除
# ────────────────────────────────────────────────────────────────


async def delete(key: str) -> bool:
    """删除一个对象。本地降级模式下也会清理本地文件。"""
    success = True
    if is_configured():
        try:
            import asyncio

            bucket = _get_bucket()
            await asyncio.to_thread(bucket.delete_object, key)
        except Exception:
            logger.exception("oss delete failed")
            success = False

    # 同时尝试清理本地副本(降级模式产物)
    local_path = Path(settings.local_upload_dir).resolve() / key
    if local_path.exists():
        try:
            local_path.unlink()
        except OSError:
            pass

    return success


# ────────────────────────────────────────────────────────────────
# 本地文件读取(降级模式的反向通道)
# ────────────────────────────────────────────────────────────────


def read_local_file(key: str) -> Optional[bytes]:
    """读取本地降级文件。仅在降级模式下使用。"""
    base = Path(settings.local_upload_dir).resolve()
    # 先拼路径,再 resolve,这样 .. 会被规范化
    candidate = (base / key).resolve()
    # 路径穿越防护:解析后必须仍在 base 之内
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate.read_bytes()
