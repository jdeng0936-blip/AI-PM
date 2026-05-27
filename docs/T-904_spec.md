# T-904 执行契约 — Phase 9 KPI 后端测试

> **任务编号**: T-904
> **任务名**: 为 KPI Phase 9 全栈（model + service + router）补齐 pytest 覆盖
> **指挥官**: Claude (QA & Refactor Specialist)
> **执行人**: Codex (Worker)
> **前置**: T-901 / T-901-FIX / T-902 / T-903 全部已落地（HEAD: `288c454`），DB 在 alembic head `b4f6a8d2c9e1`。
> **依赖**:
>   - 测试 DB `aipm_db_test`（conftest `setup_test_db` 自动建表 / `TEST_DATABASE_URL`）
>   - JWT 工具 `app.middleware.rbac.create_access_token`
>   - 既有测试参考：`tests/test_deletion_cleanup.py`（本地 `db_session` fixture 模式）+ `tests/test_analytics.py`（真 token + httpx.AsyncClient 模式）

---

## 1. 任务目标

为 Phase 9 KPI 模块写一份系统化的 pytest 覆盖，分**三层**：

1. **Model 层** —— UNIQUE NULLS NOT DISTINCT 真生效 + Enum 非法值拦截。
2. **Service 层** —— upsert 走 UPDATE 不重复行 + 缺数据 `actual=None / status="no_data"` + list 排序稳定。
3. **Router 层** —— admin 200 / employee 403 / 参数 422 / 入参 422 四类响应路径。

写完跑 `pytest tests/test_kpi_phase9.py -v` 必须全绿；其余测试不能被引入回归。

---

## 2. 范围边界

### 范围内 (IN)

- 新建 `backend/tests/test_kpi_phase9.py`，单文件覆盖 Phase 9 全栈测试。
- 用 `pytest_asyncio.fixture` + **本地 `db_session`** 模式（避开 conftest 全局 fixture 的 pytest-asyncio 1.x loop-scope 错乱坑，参考 `test_deletion_cleanup.py:18-32`）。
- 路由层测试用 `httpx.AsyncClient(ASGITransport)` + `create_access_token` 真 token（参考 `test_analytics.py:53`），**不要**用 `app.dependency_overrides[get_current_user]` 绕过 RBAC（绕过等于没测）。

### 范围外 (OUT)

- **绝对不要**改任何已落地的源码（`app/models/kpi_target.py` / `app/services/kpi_service.py` / `app/routers/kpi.py` / `app/main.py`）—— 若测试发现 bug，**停下来 ping 指挥官**，不要擅自动源码。
- **绝对不要**改 `tests/conftest.py`（项目级 fixture 凝固）。
- **绝对不要**新增 Alembic migration。
- 不要碰前端、不要碰 `docs/recap.md`、不要碰 `backend/uv.lock`。

---

## 3. 测试文件结构（`backend/tests/test_kpi_phase9.py`）

### 3.1 文件头

```python
"""
tests/test_kpi_phase9.py — Phase 9 KPI 后端三层测试

覆盖:
  - Model 层: UNIQUE NULLS NOT DISTINCT + Enum 校验
  - Service 层: upsert UPDATE 路径 / achievement no_data / list 排序
  - Router 层: admin 200 / employee 403 / 参数 422 / 入参 422
"""

from __future__ import annotations

import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.middleware.rbac import create_access_token
from app.models.kpi_target import KpiMetric, KpiPeriod, KpiScope, KpiTarget
from app.models.user import User, UserRole
from app.schemas.kpi import KpiTargetIn
from app.services.kpi_service import (
    calculate_kpi_achievement,
    list_kpi_targets,
    upsert_kpi_target,
)
from tests.conftest import TEST_DATABASE_URL
```

### 3.2 本地 `db_session` fixture（强制）

照搬 `test_deletion_cleanup.py:18-32` 的本地模式：

```python
@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """本地 fixture - engine 在 test 自己的 event loop 内构造,
    规避 conftest 全局 db_session 与 pytest-asyncio 1.x loop_scope 不对齐的问题。"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()
```

### 3.3 User 工厂 helper

```python
async def _make_user(db: AsyncSession, role: UserRole, name: str = "KPI 测试用户") -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"kpi_{uuid.uuid4().hex[:12]}",
        name=name,
        department="技术部",
        job_title="工程师",
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}
```

### 3.4 client fixture（路由层用）

参考 `test_analytics.py:25-44` 模式（注入测试 session）：

```python
@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

---

## 4. 测试用例清单（最少 9 个）

### 4.1 Model 层（2 case）

#### `test_unique_null_scope_value_blocks_duplicate`

```python
@pytest.mark.asyncio
async def test_unique_null_scope_value_blocks_duplicate(db_session: AsyncSession):
    """UNIQUE NULLS NOT DISTINCT - 同 (global, NULL, submit_rate, monthly) 第二次插入必须 IntegrityError"""
    db_session.add(KpiTarget(
        scope=KpiScope.global_, scope_value=None,
        metric=KpiMetric.submit_rate, target_value=95.0,
        period=KpiPeriod.monthly, tenant_id="default",
    ))
    await db_session.commit()
    db_session.add(KpiTarget(
        scope=KpiScope.global_, scope_value=None,
        metric=KpiMetric.submit_rate, target_value=99.0,
        period=KpiPeriod.monthly, tenant_id="default",
    ))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
```

#### `test_invalid_enum_value_rejected`

```python
@pytest.mark.asyncio
async def test_invalid_enum_value_rejected(db_session: AsyncSession):
    """非法 Enum 值(如 scope='unknown')必须被 PG 拒绝"""
    from sqlalchemy import text
    with pytest.raises((DBAPIError, IntegrityError)):
        await db_session.execute(text(
            "INSERT INTO kpi_targets (scope, scope_value, metric, target_value, period, tenant_id) "
            "VALUES ('unknown', NULL, 'submit_rate', 50.0, 'monthly', 'default')"
        ))
        await db_session.commit()
    await db_session.rollback()
```

### 4.2 Service 层（3 case）

#### `test_upsert_updates_existing_row`

```python
@pytest.mark.asyncio
async def test_upsert_updates_existing_row(db_session: AsyncSession):
    """upsert 同 key 第二次写必须走 UPDATE, id 复用, 总行数不变"""
    actor = await _make_user(db_session, UserRole.admin, "KPI Admin")
    payload = KpiTargetIn(
        scope=KpiScope.global_, scope_value=None,
        metric=KpiMetric.submit_rate, target_value=80.0,
        period=KpiPeriod.monthly,
    )
    first = await upsert_kpi_target(db_session, payload, actor)
    payload2 = KpiTargetIn(
        scope=KpiScope.global_, scope_value=None,
        metric=KpiMetric.submit_rate, target_value=90.0,
        period=KpiPeriod.monthly,
    )
    second = await upsert_kpi_target(db_session, payload2, actor)
    assert first.id == second.id, "upsert 必须走 UPDATE 路径 (同 id)"
    assert second.target_value == 90.0
```

#### `test_calculate_achievement_no_data_returns_none`

```python
@pytest.mark.asyncio
async def test_calculate_achievement_no_data_returns_none(db_session: AsyncSession):
    """sprint_completion / blocker_resolve_days 在 Phase 7 MV 无聚合源, actual 必须 None / status='no_data'"""
    actor = await _make_user(db_session, UserRole.admin)
    await upsert_kpi_target(db_session, KpiTargetIn(
        scope=KpiScope.global_, scope_value=None,
        metric=KpiMetric.blocker_resolve_days, target_value=3.0,
        period=KpiPeriod.monthly,
    ), actor)
    resp = await calculate_kpi_achievement(db_session, KpiPeriod.monthly)
    row = next(r for r in resp.rows if r.metric == KpiMetric.blocker_resolve_days)
    assert row.actual_value is None
    assert row.gap is None
    assert row.achievement_rate is None
    assert row.status == "no_data"
```

#### `test_list_kpi_targets_stable_order`

```python
@pytest.mark.asyncio
async def test_list_kpi_targets_stable_order(db_session: AsyncSession):
    """list_kpi_targets 返回顺序按 (scope, metric, scope_value NULLS FIRST) 稳定"""
    actor = await _make_user(db_session, UserRole.admin)
    for payload in [
        KpiTargetIn(scope=KpiScope.department, scope_value="技术部", metric=KpiMetric.avg_score, target_value=80, period=KpiPeriod.monthly),
        KpiTargetIn(scope=KpiScope.global_, scope_value=None, metric=KpiMetric.submit_rate, target_value=95, period=KpiPeriod.monthly),
        KpiTargetIn(scope=KpiScope.global_, scope_value=None, metric=KpiMetric.avg_score, target_value=75, period=KpiPeriod.monthly),
    ]:
        await upsert_kpi_target(db_session, payload, actor)
    rows = await list_kpi_targets(db_session)
    # 至少前两行属于 global scope, 排在 department 前
    global_indexes = [i for i, r in enumerate(rows) if r.scope == KpiScope.global_]
    dept_indexes = [i for i, r in enumerate(rows) if r.scope == KpiScope.department]
    assert global_indexes and dept_indexes
    assert max(global_indexes) < min(dept_indexes), "global scope 必须排在 department 之前"
```

### 4.3 Router 层（4 case）

#### `test_router_admin_get_returns_200`

```python
@pytest.mark.asyncio
async def test_router_admin_get_returns_200(client: AsyncClient, db_session: AsyncSession):
    admin = await _make_user(db_session, UserRole.admin, "ADM")
    r = await client.get("/api/v1/admin/kpi/", headers=_headers(admin))
    assert r.status_code == 200
    assert isinstance(r.json(), list)
```

#### `test_router_employee_forbidden`

```python
@pytest.mark.asyncio
async def test_router_employee_forbidden(client: AsyncClient, db_session: AsyncSession):
    employee = await _make_user(db_session, UserRole.employee, "EMP")
    r = await client.get("/api/v1/admin/kpi/", headers=_headers(employee))
    assert r.status_code == 403
```

#### `test_router_invalid_period_returns_422`

```python
@pytest.mark.asyncio
async def test_router_invalid_period_returns_422(client: AsyncClient, db_session: AsyncSession):
    admin = await _make_user(db_session, UserRole.admin)
    r = await client.get("/api/v1/admin/kpi/achievement", params={"period": "daily"}, headers=_headers(admin))
    assert r.status_code == 422
```

#### `test_router_post_invalid_payload_returns_422`

```python
@pytest.mark.asyncio
async def test_router_post_invalid_payload_returns_422(client: AsyncClient, db_session: AsyncSession):
    admin = await _make_user(db_session, UserRole.admin)
    # global + scope_value="X" 违反 KpiTargetIn @model_validator
    r = await client.post("/api/v1/admin/kpi/", headers=_headers(admin), json={
        "scope": "global", "scope_value": "X", "metric": "submit_rate",
        "target_value": 95.0, "period": "monthly",
    })
    assert r.status_code == 422
```

---

## 5. 验证标准

```bash
cd backend

# 1) 静态
.venv/bin/ruff check tests/test_kpi_phase9.py
.venv/bin/mypy tests/test_kpi_phase9.py

# 2) 单文件全绿
.venv/bin/pytest tests/test_kpi_phase9.py -v

# 3) 关联回归(确认没踩到 deletion / analytics 测试)
.venv/bin/pytest tests/test_kpi_phase9.py tests/test_deletion_cleanup.py tests/test_analytics.py -v
```

预期：9+ 个 test PASS，0 fail，0 error。

> **本地 db_session 模式注意**：因为本地 fixture 在 test 自己的 event loop 内构造 engine，**不要**在 model/service 层 case 里依赖 `client` fixture（client 用的是 conftest 全局 `db_session`，可能 loop 错位）。Router 层 case 独立用 `client`+`db_session` 组合，参考 `test_analytics.py` 的 conftest 模式。

---

## 6. 提交规约

**两条原子 commit**：

1. `test(kpi): cover models, services, routers for phase 9 KPI module`
   - 含 `backend/tests/test_kpi_phase9.py` 单个新文件。
   - Body 简述：9+ test 覆盖三层 + 复用 create_access_token 真 token RBAC + 本地 db_session 规避 loop scope 坑。
2. 修改 `docs/dev_tasks.md` Task 4 方括号 `[/]` → `[x]`，然后：
   - `chore(progress): close T-904`

---

## 7. 不在本契约内的事项

- **绝对不要**改任何源码 —— 若测试暴露 bug，停下来 ping 指挥官。
- 不要新建 `tests/test_kpi_*.py` 之外的测试文件。
- 不要改 `conftest.py`。
- 不要写性能 / 压测 / Pyramid-下游 mock 测试。
- 不要 mock `mv_daily_user_stats / mv_weekly_dept_stats` —— `no_data` 测试通过让 `actual=None` 自然返回完成。

---

## 8. 风险与注意点

1. **本地 db_session 与路由层 client fixture 的 loop scope 冲突**：路由 case 必须用 `db_session` + `client` 组合（参考 §3.4），不要混用本地 db_session 和 client。或者：把 4 个 router case 单独拎到文件底部，依赖 conftest 风格 fixture。**实操建议**：本地 db_session 复用 `test_deletion_cleanup.py:23-32` 的写法；router fixture 参考 `test_analytics.py:25-44` 自己 yield 一对 (client, session)。
2. **测试库未建表**：`conftest.setup_test_db` 是 `autouse=True`，但若 PG 测试库未就绪整个 session 会被 `pytest.skip`。运行前确认 `aipm_db_test` 数据库存在并能连通。
3. **Enum 非法值在 PG 层会抛 `asyncpg.exceptions.InvalidTextRepresentationError`**，被 SQLAlchemy 包成 `DBAPIError`（不是 `IntegrityError`），所以 `test_invalid_enum_value_rejected` 用 `pytest.raises((DBAPIError, IntegrityError))` 双捕。
4. **`upsert_kpi_target` 不 commit**：service 层无 commit，测试里的 `await upsert_kpi_target(...)` 之后**必须**自己 `await db_session.commit()`（如果你想观察持久化）。但因为本地 db_session 结束 rollback，每个 case 隔离，无需担心污染。
5. **不要在测试里 update `created_by`**：upsert 默认带 `created_by=actor.id`，FK 必须能解析到 users 表的 UUID。`_make_user` 必须先于 upsert 调用，且 `db.commit()` 让 user 真持久化。
6. **`pytest-asyncio` 必须用 `@pytest.mark.asyncio`** 标记每个 async test —— 项目用的是 strict mode，遗漏即 collect error。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌，供 PM 探针自动提取**

- **当前持牌任务**: **T-904** —— `backend/tests/test_kpi_phase9.py` 三层 pytest 覆盖。看板已锁 `[/]`，不要重复 `chore(lock)`。
- **执行入口**: 阅读本契约 §3 / §4，直接编码。预计 200~300 行 9~12 个 test case。
- **核心交付**:
  1. `backend/tests/test_kpi_phase9.py` —— 单文件，含本地 `db_session` fixture + User 工厂 + `_headers` token helper + 9 个 `@pytest.mark.asyncio` test case。
  2. 三层全覆盖：Model UNIQUE+Enum（2）/ Service upsert+no_data+排序（3）/ Router 200+403+422+422（4）。
  3. RBAC 测试用 `create_access_token` 真 token，**不要**用 dependency_overrides 绕。
- **闸门**: `ruff check` + `mypy` + `pytest tests/test_kpi_phase9.py -v` 全绿；再跑一次连带 `test_deletion_cleanup.py + test_analytics.py` 确保无回归。
- **完工提交序列**:
  1. `test(kpi): cover models, services, routers for phase 9 KPI module`
  2. 改 `docs/dev_tasks.md` Task 4 → `[x]`，再提 `chore(progress): close T-904`
- **完工后**: 立即停手，等指挥官二次验收。**不要**自行进入 T-905（前端）—— 那是指挥官二次验收 T-904 通过后另发的契约。
- **验收通过的判定**: §5 三个 shell 块全绿；指挥官能复现 9+ test PASS 0 fail。

**契约生效。Codex 收到后请确认 `git log -1 --oneline` 包含 `chore(spec): T-904`，然后开干。如果测试过程中发现源码 bug，立即停手 ping 指挥官，不要擅自动 app/ 下代码。**
