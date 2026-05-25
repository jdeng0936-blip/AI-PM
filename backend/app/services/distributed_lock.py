"""
app/services/distributed_lock.py — 基于 Redis 的分布式互斥锁

Stage 1 引入。解决 APScheduler 在多实例部署时同一 cron 任务会被每个进程
独立触发的问题。所有 scheduler.add_job 的目标函数都包裹 with_distributed_lock,
任一实例拿到锁,其他实例自动跳过本轮触发。

设计要点:
  1. Redis SET key value NX EX → 原子拿锁 + TTL,即使进程崩也不永久卡死
  2. 单进程开发/CI 场景:Redis 不可用时 **graceful degradation**(只记 warning,
     继续执行),避免分布式锁拖垮单实例正常运行
  3. 装饰器 + 上下文管理器双形态,使用方场景灵活
"""

from __future__ import annotations

import functools
import logging
from contextlib import asynccontextmanager
from typing import Awaitable, Callable

import redis.asyncio as redis_async

from app.config import settings

logger = logging.getLogger("aipm.lock")


def _new_redis() -> redis_async.Redis:
    """创建一个 Redis client(不复用全局单例 — 避免跨 event loop 时 client 闭合)。

    Scheduler 任务触发频率极低(分钟/小时/天级),每次新建 client 开销可忽略,
    换取在 pytest 多 loop / 多 worker / FastAPI lifespan 重启等场景下的健壮性。
    """
    return redis_async.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_timeout=2,
        socket_connect_timeout=2,
    )


@asynccontextmanager
async def acquire_lock(name: str, ttl_seconds: int = 3600):
    """异步分布式锁上下文管理器。

    用法:
        async with acquire_lock("my_task", ttl_seconds=600) as acquired:
            if not acquired:
                return  # 另一实例正在执行
            ...  # 业务逻辑

    Redis 不可用时:logger.warning 一行,然后 yield True(单实例语义,
    本进程视为已拿到锁,继续执行)。
    """
    lock_key = f"aipm:scheduler:lock:{name}"
    r = _new_redis()
    acquired_real = False  # 是否真的从 Redis 拿到了锁(用于 finally 清理)
    try:
        try:
            # SET key value NX EX seconds — 原子操作
            acquired_real = bool(await r.set(lock_key, "locked", nx=True, ex=ttl_seconds))
            if not acquired_real:
                logger.info("[%s] 分布式锁未拿到 — 另一实例正在执行,本轮跳过", name)
            yield acquired_real
        except (redis_async.RedisError, OSError) as e:
            # Redis 连接/操作失败:graceful 降级,允许本进程继续(单实例语义)
            logger.warning("[%s] Redis 不可用(%s),降级为单实例语义执行", name, e)
            yield True
    finally:
        if acquired_real:
            try:
                await r.delete(lock_key)
            except (redis_async.RedisError, OSError) as e:
                # 清理失败不影响业务,TTL 会兜底
                logger.warning("[%s] 释放锁失败(%s),依赖 TTL 自动过期", name, e)
        try:
            await r.aclose()
        except Exception:
            pass


def with_distributed_lock(
    name: str, ttl_seconds: int = 3600
) -> Callable[[Callable[..., Awaitable]], Callable[..., Awaitable]]:
    """装饰器形态:把 async 函数包成"拿到锁才执行"。

    用法:
        @with_distributed_lock("daily_briefing", ttl_seconds=600)
        async def run_morning_briefing(): ...

    或在 scheduler.add_job 时即时 wrap:
        scheduler.add_job(
            with_distributed_lock("remind_17_30", ttl_seconds=600)(remind_unreported_friendly),
            ...
        )
    """

    def deco(fn: Callable[..., Awaitable]) -> Callable[..., Awaitable]:
        @functools.wraps(fn)
        async def wrapped(*args, **kwargs):
            async with acquire_lock(name, ttl_seconds=ttl_seconds) as acquired:
                if not acquired:
                    return None
                return await fn(*args, **kwargs)

        return wrapped

    return deco
