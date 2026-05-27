# T-902 执行契约 — Pydantic Schemas + KPI 服务层

> **任务编号**: T-902
> **任务名**: 为 Phase 9 KPI 提供 Pydantic v2 Schemas + 服务层（list / upsert / achievement）
> **指挥官**: Claude (QA & Refactor Specialist)
> **执行人**: Codex (Worker)
> **前置**: T-901 + T-901-FIX 已落地（HEAD: `8ca30c5`），DB 在 alembic head `b4f6a8d2c9e1`，UNIQUE 已升级为 `NULLS NOT DISTINCT`。
> **依赖**: Phase 7 物化视图 `mv_daily_user_stats` / `mv_weekly_dept_stats` 已上线，可直接 SELECT。

---

## 1. 任务目标

为 Phase 9 KPI 模块搭建**纯无路由的数据访问层**，提供三类能力：

1. **读**：`list_kpi_targets(db)` —— 列出全部目标，租户隔离。
2. **写**：`upsert_kpi_target(db, payload, actor)` —— 走 PG `ON CONFLICT ... DO UPDATE`，依赖 T-901-FIX 的 `NULLS NOT DISTINCT` UNIQUE 保证 `(scope, NULL, metric, period)` 也能合并。
3. **算**：`calculate_kpi_achievement(db, period)` —— 复用 Phase 7 MV 拿 actual，按 scope 维度 join 目标，缺数据时 `actual=None / gap=None / achievement_rate=None`（**不要回退到 0**）。

T-902 **不输出**任何 router、不写测试、不动前端 —— 那是 T-903 / T-904 / T-905 的事。

---

## 2. 范围边界

### 范围内 (IN)

- 新建 `backend/app/schemas/kpi.py`：4 个 Pydantic v2 模型。
- 新建 `backend/app/services/kpi_service.py`：3 个异步函数 + 必要的内部 helper。
- 在 `backend/app/schemas/__init__.py` 暴露 4 个 schema 名（不强制，但若已是项目风格则跟随）。

### 范围外 (OUT)

- **绝对不要**新建 `backend/app/routers/kpi.py`。
- **绝对不要**改 `backend/app/models/kpi_target.py`（T-901 + T-901-FIX 已凝固）。
- **绝对不要**新增任何 Alembic migration。
- **绝对不要**新建测试文件 / 修改 `backend/tests/` 任何已有文件。
- **绝对不要**回填 / 删改 `kpi_targets` 之外的任何表数据。
- **绝对不要**碰 `backend/uv.lock`（继续保持未跟踪）。

---

## 3. Pydantic Schemas 契约（`backend/app/schemas/kpi.py`）

### 3.1 文件头

```python
"""
app/schemas/kpi.py — Phase 9 KPI 目标与达成率 Pydantic V2 Schemas

参考已落地的 ORM Model（app/models/kpi_target.py）字段约束：
  - scope ∈ {global, department, job_title}
  - scope_value 可空（global 模式必空，其他模式必填）
  - metric ∈ {submit_rate, avg_score, sprint_completion, blocker_resolve_days}
  - period ∈ {weekly, monthly, quarterly}
"""
```

### 3.2 输入模型 `KpiTargetIn`

字段：

| 字段 | 类型 | 校验 |
|---|---|---|
| `scope` | `KpiScope` 枚举 | `KpiScope` 从 `app.models.kpi_target` 复用 |
| `scope_value` | `str \| None` | `max_length=50`；`scope == global` 时**必须为 None**，否则**必填非空** |
| `metric` | `KpiMetric` 枚举 | 复用 ORM Enum |
| `target_value` | `float` | `gt=0` 严格大于 0 |
| `period` | `KpiPeriod` 枚举 | 默认 `KpiPeriod.monthly` |

校验落在 `@model_validator(mode="after")`，违反规则抛 `ValueError("scope=global 时 scope_value 必须为 None")` 等中文消息。

### 3.3 输出模型 `KpiTargetOut`

字段全集：`id / scope / scope_value / metric / target_value / period / created_at / updated_at / created_by / tenant_id`。

- 配 `model_config = ConfigDict(from_attributes=True)` 让 `KpiTargetOut.model_validate(orm_obj)` 直接工作。
- `created_by` 类型 `uuid.UUID | None`，`created_at` / `updated_at` 类型 `datetime | None`（`updated_at` 在创建后还没 onupdate，可为 None）。

### 3.4 达成率单行 `KpiAchievementRow`

字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `scope` | `KpiScope` | |
| `scope_value` | `str \| None` | |
| `metric` | `KpiMetric` | |
| `period` | `KpiPeriod` | |
| `target_value` | `float` | 来自 `kpi_targets` |
| `actual_value` | `float \| None` | 来自 MV，**缺数据时为 None，不要 0** |
| `gap` | `float \| None` | `actual - target`，actual 为 None 时为 None |
| `achievement_rate` | `float \| None` | `actual / target * 100`，actual 为 None 时为 None |
| `status` | `Literal["on_track", "below_target", "no_data"]` | actual=None → `no_data`；`achievement_rate >= 100` → `on_track`；否则 `below_target` |

### 3.5 达成率响应 `KpiAchievementResponse`

```python
class KpiAchievementResponse(BaseModel):
    period: KpiPeriod
    snapshot_at: datetime  # 服务层取 datetime.now(UTC)
    rows: list[KpiAchievementRow]
```

---

## 4. Service 层契约（`backend/app/services/kpi_service.py`）

### 4.1 文件头

```python
"""
app/services/kpi_service.py — Phase 9 KPI 服务层

职责：
  - 列出 / Upsert KPI 目标（依赖 T-901-FIX 的 NULLS NOT DISTINCT UNIQUE）。
  - 复用 Phase 7 物化视图 mv_daily_user_stats / mv_weekly_dept_stats 计算达成率。

注意：
  - 所有 DB 入参一律 AsyncSession（pattern: from sqlalchemy.ext.asyncio import AsyncSession）。
  - 不引入 router 依赖；不在本文件里 raise HTTPException。
"""
```

### 4.2 `list_kpi_targets(db: AsyncSession) -> list[KpiTargetOut]`

- `select(KpiTarget).where(KpiTarget.tenant_id == "default").order_by(KpiTarget.scope, KpiTarget.metric, KpiTarget.scope_value.nulls_first())`。
- 用 `KpiTargetOut.model_validate(row)` 转换。
- **不分页** —— 当前业务 KPI 数量 < 50，无需分页。

### 4.3 `upsert_kpi_target(db, payload, actor) -> KpiTargetOut`

签名：

```python
async def upsert_kpi_target(
    db: AsyncSession,
    payload: KpiTargetIn,
    actor: User,  # 来自 app.models.user
) -> KpiTargetOut:
```

实现要求：

1. 用 `sqlalchemy.dialects.postgresql.insert` 构造 INSERT。
2. `.on_conflict_do_update(constraint="uq_kpi_targets_scope_metric_period", set_={"target_value": stmt.excluded.target_value, "updated_at": func.now()})`。
3. 插入时显式带 `created_by=actor.id` / `tenant_id="default"`。
4. `RETURNING *`，再 `model_validate` 成 `KpiTargetOut`。
5. **不要 `await db.commit()`** —— 让 router 层（T-903）通过依赖注入的 session 决定事务边界（项目惯例：`get_db` 退出时自动 commit/rollback，参考 `app/services/deletion_cleanup.py`）。

### 4.4 `calculate_kpi_achievement(db, period) -> KpiAchievementResponse`

签名：

```python
async def calculate_kpi_achievement(
    db: AsyncSession,
    period: KpiPeriod = KpiPeriod.monthly,
) -> KpiAchievementResponse:
```

actual 取数策略（参考 `backend/app/routers/analytics.py:60-95` / `analytics.py:140-175`）：

| metric | scope=global | scope=department |
|---|---|---|
| `submit_rate` | `AVG(submitter_rate)` 在 `mv_weekly_dept_stats` 全表最近 4 周 | `AVG(submitter_rate)` 当部门最近 4 周 |
| `avg_score` | `AVG(avg_score)` 在 `mv_daily_user_stats` 最近 30 天 | `AVG(avg_score)` 在 `mv_weekly_dept_stats` 当部门最近 4 周 |
| `sprint_completion` | `actual = None`（Phase 7 MV 不含该字段，留给 T-906 二次补足） | 同左 |
| `blocker_resolve_days` | `actual = None`（同上） | 同左 |
| scope=`job_title` 的任何 metric | 一律 `actual = None`（暂无聚合视图） | — |

> **重要**：未覆盖的组合**返回 `actual_value=None`，不要回退到 0**。0 是「完全没达成」的有效业务值，None 是「无数据」，二者业务含义不同。

实现细节：

- 不要 join SQL，用 Python 字典聚合即可（KPI 量级小，避免复杂 JOIN）。
- 第一步：`SELECT * FROM kpi_targets WHERE tenant_id='default'`。
- 第二步：按需做两到三次 MV 查询（一次取全局指标聚合，一次按部门聚合）。
- 第三步：Python 侧逐行算 `gap / achievement_rate / status`。

返回的 `rows` 顺序：与 `list_kpi_targets` 同序（scope, metric, scope_value）。

### 4.5 内部 helper（可选）

允许（但非强制）定义私有 helper：

- `_status_of(target: float, actual: float | None) -> str`：返回 `"on_track" / "below_target" / "no_data"`。
- `_safe_divide(a, b) -> float | None`：b 为 0 / None 时返回 None。

不要把 helper 暴露为 `__all__`。

---

## 5. 验证标准

```bash
cd backend

# 1) 静态检查
.venv/bin/ruff check app/schemas/kpi.py app/services/kpi_service.py
.venv/bin/mypy app/schemas/kpi.py app/services/kpi_service.py

# 2) Import smoke 测试（必须无异常打印）
.venv/bin/python -c "
from app.schemas.kpi import KpiTargetIn, KpiTargetOut, KpiAchievementRow, KpiAchievementResponse
from app.services.kpi_service import list_kpi_targets, upsert_kpi_target, calculate_kpi_achievement
print('schemas + service import OK')
"

# 3) Pydantic 校验单测（inline，命令行跑，不写 test 文件）
.venv/bin/python -c "
from app.schemas.kpi import KpiTargetIn
from app.models.kpi_target import KpiScope, KpiMetric, KpiPeriod
# 全局 scope_value 必须 None
try:
    KpiTargetIn(scope=KpiScope.global_, scope_value='X', metric=KpiMetric.submit_rate, target_value=95.0, period=KpiPeriod.monthly)
    raise SystemExit('FAIL: 应拒绝 global+scope_value')
except ValueError:
    print('PASS: global scope 强制 scope_value=None')

# 部门 scope_value 必填
try:
    KpiTargetIn(scope=KpiScope.department, scope_value=None, metric=KpiMetric.avg_score, target_value=75.0, period=KpiPeriod.monthly)
    raise SystemExit('FAIL: 应拒绝 department+无 scope_value')
except ValueError:
    print('PASS: department scope 强制 scope_value 非空')

# target_value 必须 > 0
try:
    KpiTargetIn(scope=KpiScope.global_, scope_value=None, metric=KpiMetric.submit_rate, target_value=0.0, period=KpiPeriod.monthly)
    raise SystemExit('FAIL: 应拒绝 target_value=0')
except ValueError:
    print('PASS: target_value 必须 > 0')
"
```

三项必须全绿。

---

## 6. 提交规约

**两条原子 commit**：

1. `feat(kpi): add pydantic schemas and service layer for kpi targets`
   - 含 `backend/app/schemas/kpi.py` + `backend/app/services/kpi_service.py` 2 个新文件。
   - Body 简述：schemas v2 + upsert via ON CONFLICT + 达成率 actual=None on missing data。
2. 修改 `docs/dev_tasks.md` Task 2 方括号 `[/]` → `[x]`，然后：
   - `chore(progress): close T-902`

---

## 7. 不在本契约内的事项

- 不要新建 `backend/app/routers/kpi.py`。
- 不要修改 `app/main.py`（router 注册留给 T-903）。
- 不要新建 `backend/tests/test_kpi_phase9.py`（留给 T-904）。
- 不要改 `backend/uv.lock` / `requirements.txt`。
- 不要 touch `docs/recap.md`（留给 T-907 统一收尾）。

---

## 8. 风险与注意点

1. **`ON CONFLICT` 必须依赖 T-901-FIX 的 NULLS NOT DISTINCT** —— 否则 `(global, NULL, submit_rate, monthly)` 第二次 upsert 会走 INSERT 而非 UPDATE，产生重复行。指挥官已在 T-901-FIX 处理掉这个隐患，Codex 直接信任。
2. **MV 数据可能滞后 24h**（Phase 7 是 daily refresh）—— 达成率结果天然是 T-1 视角，业务可接受。
3. **`scope=job_title` 现阶段无聚合源** —— 一律返回 `actual=None`，注释里写明「待 Phase 9.1 或 Phase 10 引入岗位维度 MV 后再补」。
4. **`sprint_completion / blocker_resolve_days` 在 Phase 7 MV 缺字段** —— 同上，actual=None，注释标注 TODO。
5. **不要在 `upsert_kpi_target` 里 commit** —— 项目 `get_db` 依赖会在 router 返回后自动 commit/rollback，service 层 commit 会破坏事务原子性。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌，供 PM 探针自动提取**

- **当前持牌任务**: **T-902** —— Pydantic Schemas + KPI 服务层（看板已自动锁定为 `[/]`，不要重复 `chore(lock)`）。
- **执行入口**: 阅读本契约 §3 / §4，直接编码。无需先开 PR，无需先写注释，直接出代码。
- **核心交付**:
  1. `backend/app/schemas/kpi.py` —— 4 个 Pydantic v2 模型（`KpiTargetIn` / `KpiTargetOut` / `KpiAchievementRow` / `KpiAchievementResponse`）。
  2. `backend/app/services/kpi_service.py` —— 3 个 async 函数（`list_kpi_targets` / `upsert_kpi_target` / `calculate_kpi_achievement`），upsert 走 PG `ON CONFLICT DO UPDATE`（依赖 T-901-FIX 的 NULLS NOT DISTINCT UNIQUE）。
- **闸门**: `ruff check` + `mypy` + import smoke + 3 项 Pydantic 校验内联测试，全部见 §5。
- **完工提交序列**:
  1. `feat(kpi): add pydantic schemas and service layer for kpi targets`
  2. 改 `docs/dev_tasks.md` Task 2 → `[x]`，再提 `chore(progress): close T-902`
- **完工后**: 立即停手，等指挥官二次验收。**不要**自行进入 T-903（routers 那是下一份契约）。
- **验收通过的判定**: §5 三个 shell 块全绿；指挥官能复现 import smoke + Pydantic 三连 PASS。

**契约生效。Codex 收到后请确认 `alembic heads` = `b4f6a8d2c9e1`，然后开干。**
