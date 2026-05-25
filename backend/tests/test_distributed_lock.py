"""
tests/test_distributed_lock.py — Redis 分布式锁基础验证

测试目标(用真实 Redis):
  1. 单次 acquire_lock 能拿到锁 + 释放
  2. 同一 name 并发抢锁,只有一个能拿到
  3. with_distributed_lock 装饰器正确传递返回值
  4. Redis 不可用时 graceful 降级
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.services.distributed_lock import acquire_lock, with_distributed_lock


@pytest.mark.asyncio
async def test_acquire_lock_single_runner_gets_it():
    """单次取锁应当拿到。"""
    async with acquire_lock("ut_single_runner", ttl_seconds=10) as acquired:
        assert acquired is True


@pytest.mark.asyncio
async def test_acquire_lock_concurrent_only_one_winner():
    """两个并发 acquire 同一 name → 只有一个拿到。"""
    results = []

    async def worker(idx: int):
        async with acquire_lock("ut_concurrent", ttl_seconds=10) as acquired:
            results.append((idx, acquired))
            # 给另一个 worker 一点时间也来抢
            await asyncio.sleep(0.1)

    await asyncio.gather(worker(1), worker(2))

    winners = [r for r in results if r[1]]
    losers = [r for r in results if not r[1]]
    assert len(winners) == 1, f"应当只有一个 winner,实际 {len(winners)}"
    assert len(losers) == 1, f"应当只有一个 loser,实际 {len(losers)}"


@pytest.mark.asyncio
async def test_with_distributed_lock_decorator_returns_value():
    """装饰器形态:拿到锁时正确传递函数返回值。"""

    @with_distributed_lock("ut_deco_return", ttl_seconds=10)
    async def my_task() -> str:
        return "executed"

    result = await my_task()
    assert result == "executed"


@pytest.mark.asyncio
async def test_with_distributed_lock_decorator_returns_none_when_locked():
    """装饰器形态:同一 name 第二个并发调用,返回 None(被跳过)。"""

    @with_distributed_lock("ut_deco_locked", ttl_seconds=10)
    async def my_task(idx: int):
        await asyncio.sleep(0.1)
        return f"executed-{idx}"

    results = await asyncio.gather(my_task(1), my_task(2))
    executed = [r for r in results if r is not None]
    skipped = [r for r in results if r is None]
    assert len(executed) == 1
    assert len(skipped) == 1


@pytest.mark.asyncio
async def test_acquire_lock_graceful_degradation_on_redis_failure():
    """Redis 不可用时降级:仍 yield True(单实例语义),不阻塞业务。"""
    import redis.asyncio as redis_async

    class FakeBrokenRedis:
        async def set(self, *args, **kwargs):
            raise redis_async.RedisError("simulated outage")

        async def delete(self, *args, **kwargs):
            raise redis_async.RedisError("simulated outage")

    with patch("app.services.distributed_lock._new_redis", return_value=FakeBrokenRedis()):
        async with acquire_lock("ut_degraded", ttl_seconds=10) as acquired:
            # Redis 挂了 → graceful 降级 → yield True
            assert acquired is True
