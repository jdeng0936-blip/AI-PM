# T-903 执行契约 — `/api/v1/admin/kpi` 路由层 + RBAC

> **任务编号**: T-903
> **任务名**: 暴露 Phase 9 KPI 管理 + 达成率 API 三端点
> **指挥官**: Claude (QA & Refactor Specialist)
> **执行人**: Codex (Worker)
> **前置**: T-902 已落地（HEAD: `0ff60e3`），`app/schemas/kpi.py` + `app/services/kpi_service.py` 已就绪并通过端到端真跑。
> **依赖**: 现有 RBAC 中间件 `app.middleware.rbac.{get_current_user, require_role}`、`UserRole` 枚举、`app.database.get_db`。

---

## 1. 任务目标

把 T-902 service 层封装成 HTTP 端点：

1. `GET  /api/v1/admin/kpi/` —— 列出全部 KPI 目标。
2. `POST /api/v1/admin/kpi/` —— 创建/更新一条 KPI 目标（走 service 层 upsert，依赖 T-901-FIX UNIQUE）。
3. `GET  /api/v1/admin/kpi/achievement` —— 返回当期达成率快照。

三个端点统一 RBAC：`require_role(UserRole.admin, UserRole.manager)`，普通员工 403。

最后在 `app/main.py` 注册新 router。

---

## 2. 范围边界

### 范围内 (IN)

- 新建 `backend/app/routers/kpi.py`。
- 改 `backend/app/main.py`：增加 `from app.routers import kpi`（若已是 routers package 风格，跟随既有 import 习惯）+ 一行 `app.include_router(kpi.router)`。
- **位置**：紧贴 `app.include_router(analytics.router)` 之后（参考 `app/main.py:119`），保持文件结构稳定。

### 范围外 (OUT)

- **绝对不要**改 `app/schemas/kpi.py` / `app/services/kpi_service.py` / `app/models/kpi_target.py`（T-901/T-901-FIX/T-902 凝固）。
- **绝对不要**新增 Alembic migration。
- **绝对不要**新建测试文件 / 修改 `tests/`。
- **绝对不要**碰前端、不要碰 `docs/recap.md`、不要碰 `backend/uv.lock`。

---

## 3. Router 契约（`backend/app/routers/kpi.py`）

### 3.1 文件头

```python
"""
app/routers/kpi.py — Phase 9 KPI 目标管理与达成率 API

三端点:
  - GET  /api/v1/admin/kpi/             —— 列出 KPI 目标
  - POST /api/v1/admin/kpi/             —— 创建/更新 KPI 目标 (upsert)
  - GET  /api/v1/admin/kpi/achievement  —— 计算达成率快照

RBAC: admin + manager;普通员工 403。
"""
```

### 3.2 Router 初始化

```python
router = APIRouter(prefix="/api/v1/admin/kpi", tags=["KPI"])
_mgr_or_admin = require_role(UserRole.admin, UserRole.manager)
```

跟随 `app/routers/analytics.py:26-28` 的现成模式。

### 3.3 端点 1 — `GET /`

```python
@router.get("/", response_model=list[KpiTargetOut])
async def list_targets(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> list[KpiTargetOut]:
    return await list_kpi_targets(db)
```

要点：
- response_model 用 `list[KpiTargetOut]`，FastAPI 自动序列化。
- `_user` 参数前缀下划线表示「仅用于 RBAC，不消费」。

### 3.4 端点 2 — `POST /`

```python
@router.post("/", response_model=KpiTargetOut, status_code=status.HTTP_200_OK)
async def upsert_target(
    payload: KpiTargetIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(_mgr_or_admin),
) -> KpiTargetOut:
    return await upsert_kpi_target(db, payload, actor)
```

要点：
- 用 `status.HTTP_200_OK`（不是 201），因为 upsert 语义可能 update 也可能 insert，统一 200 更准确。
- `actor` 必须**真名**（不带下划线），因为要传给 service 层做 `created_by`。
- Pydantic 自动校验 `KpiTargetIn` 的 scope/scope_value/metric/period/target_value 全部约束。非法值（如 `target_value=0` / `scope_value='X' + scope='global'`）自动 422。

### 3.5 端点 3 — `GET /achievement`

```python
@router.get("/achievement", response_model=KpiAchievementResponse)
async def get_achievement(
    period: KpiPeriod = Query(default=KpiPeriod.monthly, description="weekly/monthly/quarterly"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(_mgr_or_admin),
) -> KpiAchievementResponse:
    return await calculate_kpi_achievement(db, period)
```

要点：
- `period` 用 `KpiPeriod` 枚举作 Query 类型，FastAPI 自动校验，非法值（如 `?period=daily`）直接 422 —— **不要在 router 里手写 if/else**。
- 默认值 `KpiPeriod.monthly` 匹配 plan §9 业务期望。

### 3.6 必要 import 一览

```python
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.kpi_target import KpiPeriod
from app.models.user import User, UserRole
from app.schemas.kpi import KpiAchievementResponse, KpiTargetIn, KpiTargetOut
from app.services.kpi_service import (
    calculate_kpi_achievement,
    list_kpi_targets,
    upsert_kpi_target,
)
```

`HTTPException` **不需要**（service 层不抛业务异常，RBAC 由 `require_role` 接管）。

---

## 4. `app/main.py` 注册改动

参考 `app/main.py:119` 既有 `app.include_router(analytics.router)`。

**最小改动**：在 `analytics.router` include 行下方插入：

```python
from app.routers import kpi  # 或跟随项目既有 import 风格
...
app.include_router(kpi.router)
```

> 注意：如果 `app/main.py` 既有 import 是按模块名块式罗列的，跟随同风格放在合理位置；不要改动其他 router 顺序。

---

## 5. 验证标准

```bash
cd backend

# 1) 静态检查
.venv/bin/ruff check app/routers/kpi.py app/main.py
.venv/bin/mypy app/routers/kpi.py

# 2) FastAPI 路由表 smoke（必须列出 3 条新路径）
.venv/bin/python -c "
from app.main import app
paths = sorted({(r.path, ','.join(sorted(r.methods or []))) for r in app.routes if '/admin/kpi' in str(getattr(r, 'path', ''))})
for p in paths:
    print(p)
assert len(paths) == 3, f'expected 3 routes, got {len(paths)}'
print('PASS: 3 endpoints registered')
"

# 3) Pydantic 入参校验 smoke（绕过 RBAC，直接构造 KpiTargetIn 触发 422 等价校验）
.venv/bin/python -c "
from pydantic import ValidationError
from app.schemas.kpi import KpiTargetIn
from app.models.kpi_target import KpiScope, KpiMetric, KpiPeriod
# 非法 target_value
try:
    KpiTargetIn(scope=KpiScope.global_, scope_value=None, metric=KpiMetric.submit_rate, target_value=-1.0, period=KpiPeriod.monthly)
    raise SystemExit('FAIL')
except (ValidationError, ValueError):
    print('PASS: 422 等价 — target_value<=0 被拦截')
"
```

三项必须全绿。

> **更深的 RBAC 403 / Query 422 端到端测试**留给 T-904 用 `httpx.AsyncClient` 系统化覆盖。本契约只验证「路由可加载、Pydantic 入参校验生效」。

---

## 6. 提交规约

**两条原子 commit**：

1. `feat(kpi): add /api/v1/admin/kpi router with RBAC`
   - 含 `backend/app/routers/kpi.py`（新建）+ `backend/app/main.py`（include_router 行）2 个文件。
   - Body 简述：3 端点（list / upsert / achievement）+ admin/manager RBAC + 复用 T-902 service 层。
2. 修改 `docs/dev_tasks.md` Task 3 方括号 `[/]` → `[x]`，然后：
   - `chore(progress): close T-903`

---

## 7. 不在本契约内的事项

- 不要在 router 文件里手写 try/except 业务异常 —— Pydantic 422 + RBAC 403 + service 层 IntegrityError 让 FastAPI 默认处理即可。
- 不要在 router 里手动 `db.commit()` —— `get_db` 依赖会自动管理事务。
- 不要写测试。
- 不要改前端 `apiFetch` 路径常量（前端 T-905 自己改）。
- 不要扩展 service 层（如果你觉得 service 缺接口，先停下来 ping 指挥官，不要擅自扩展）。

---

## 8. 风险与注意点

1. **POST 用 200 而不是 201**：upsert 语义双向，200 更准确，避免 frontend 区分逻辑。前端 T-905 调用方默认接 200。
2. **`actor` 命名很关键**：在 `POST /` 里必须命名为 `actor`（不带下划线），因为它要传给 `upsert_kpi_target(db, payload, actor)` 做 `created_by`；在 `GET` 里命名为 `_user` 表示纯 RBAC。这是项目里 `analytics.py` 已有的约定。
3. **`require_role` 顺序**：`require_role(UserRole.admin, UserRole.manager)` 与 plan §9 业务文档一致 —— **admin** 在前。
4. **不要在 router 里 import service 层之外的东西**：保持路由文件薄，所有 SQL / 业务逻辑都在 service 层。
5. **路径末尾斜杠**：`prefix="/api/v1/admin/kpi"` + `@router.get("/")` 最终路径是 `/api/v1/admin/kpi/`。FastAPI 默认会重定向无斜杠到带斜杠（307），前端 `apiFetch` 用哪种都行。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌，供 PM 探针自动提取**

- **当前持牌任务**: **T-903** —— `/api/v1/admin/kpi` 三端点 + RBAC + main 注册。看板已锁 `[/]`，不要重复 `chore(lock)`。
- **执行入口**: 阅读本契约 §3 / §4，直接编码。三端点全是「薄包装 service 层」，预计 < 80 行代码。
- **核心交付**:
  1. `backend/app/routers/kpi.py` —— 3 个 async 端点 + APIRouter + `require_role(UserRole.admin, UserRole.manager)`。
  2. `backend/app/main.py` —— 1 行 import + 1 行 `app.include_router(kpi.router)`（紧贴 analytics 后）。
- **闸门**: `ruff` + `mypy` + FastAPI 路由表 smoke（必须列出 3 条 `/admin/kpi` 路径）+ Pydantic 入参 422 等价 smoke，详见 §5。
- **完工提交序列**:
  1. `feat(kpi): add /api/v1/admin/kpi router with RBAC`
  2. 改 `docs/dev_tasks.md` Task 3 → `[x]`，再提 `chore(progress): close T-903`
- **完工后**: 立即停手，等指挥官二次验收（指挥官会跑 RBAC 403 / 参数 422 / 200 三类端到端真跑）。**不要**自行进入 T-904（后端测试是下一份契约）。
- **验收通过的判定**: §5 三个 shell 块全绿；指挥官能复现：
  - employee 身份调 `GET /` → 403；
  - admin 身份调 `GET /?period=daily` （拼写错误参数）→ 422；
  - admin 身份调 `GET /` → 200 + 4 行 seed。

**契约生效。Codex 收到后请确认 `git log -1 --oneline` 包含 `chore(spec): T-903`，然后开干。**
