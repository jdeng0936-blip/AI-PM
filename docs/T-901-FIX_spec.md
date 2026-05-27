# T-901-FIX 执行契约 — UNIQUE NULL 语义补丁

> **任务编号**: T-901-FIX
> **任务名**: 把 `kpi_targets` 的 UNIQUE 约束升级为 `NULLS NOT DISTINCT`
> **指挥官**: Claude (QA & Refactor Specialist)
> **执行人**: Codex (Worker)
> **依据**: T-901 验收时发现的契约疏漏(指挥官承担)
> **前置**: T-901 已完成(commit `00779de` + `fc27571`),DB 已在 head `c7a9f1e2d4b6`
> **PG 版本**: 已验证 PostgreSQL 16.13,支持 `NULLS NOT DISTINCT`(PG 15+)

---

## 1. 缺陷根因

T-901 契约 §3.2 写的 `UniqueConstraint("scope", "scope_value", "metric", "period")` 在 PostgreSQL **默认 NULL DISTINCT 语义**下,对 `scope='global'` 这一类 `scope_value IS NULL` 的行**无法去重**。验收时实测:

```sql
INSERT INTO kpi_targets (scope, scope_value, metric, target_value, period, tenant_id)
VALUES ('global', NULL, 'submit_rate', 99.0, 'monthly', 'default');
-- 期望: IntegrityError (与 seed id=1 重复)
-- 实际: 成功插入(NULL ≠ NULL,SQL 标准语义)
```

业务后果:管理员重复点击「保存全局 submit_rate=80」会在 `kpi_targets` 里堆出多行 `(global, NULL, submit_rate, monthly)`,达成率计算时聚合错乱。

---

## 2. 范围边界

### 范围内 (IN)
- 新建 follow-up Alembic migration:`backend/alembic/versions/20260527_<HHMM>_phase9_fix_kpi_targets_unique_nulls.py`。
- 修改 `backend/app/models/kpi_target.py` 让 `UniqueConstraint` 也声明 `postgresql_nulls_not_distinct=True`,与 DB 保持一致。
- 跑双向迁移 + 重新执行 UNIQUE 负向测试,确认 IntegrityError 抛出。

### 范围外 (OUT)
- 任何 service / router / 测试 / 前端代码。
- 不删除 / 不修改 `20260527_1234_phase9_add_kpi_targets.py`(已 commit 的 migration 不可篡改)。
- 不要触碰 seed 数据。
- 不要改 `__init__.py`(已正确)。

---

## 3. Migration 实现要求

### 3.1 文件命名

`backend/alembic/versions/20260527_<HHMM>_phase9_fix_kpi_targets_unique_nulls.py`

`<HHMM>` 取本地北京时间执行点。

### 3.2 Revision 链

- `revision`: Codex 自定义 12 位 hex(沿用项目风格)。
- `down_revision`: 必须先跑 `alembic heads` 取实际 head,**期望值为 `c7a9f1e2d4b6`**;若不是,停下来 ping 指挥官。

### 3.3 upgrade() 步骤

```python
def upgrade() -> None:
    # PostgreSQL 15+ 支持 NULLS NOT DISTINCT。
    # 通过 drop + recreate 升级约束语义,避免对 ALTER CONSTRAINT 的方言兼容问题。
    op.drop_constraint("uq_kpi_targets_scope_metric_period", "kpi_targets", type_="unique")
    op.create_unique_constraint(
        "uq_kpi_targets_scope_metric_period",
        "kpi_targets",
        ["scope", "scope_value", "metric", "period"],
        postgresql_nulls_not_distinct=True,
    )
```

> **不要**用 `op.execute("ALTER TABLE ... ALTER CONSTRAINT ...")`,Alembic 的 `create_unique_constraint(postgresql_nulls_not_distinct=True)` 是 SQLAlchemy 2.x 官方支持的方言参数,可读性更好。

### 3.4 downgrade() 步骤

```python
def downgrade() -> None:
    op.drop_constraint("uq_kpi_targets_scope_metric_period", "kpi_targets", type_="unique")
    op.create_unique_constraint(
        "uq_kpi_targets_scope_metric_period",
        "kpi_targets",
        ["scope", "scope_value", "metric", "period"],
    )  # 回到默认 NULLS DISTINCT
```

### 3.5 Docstring

照搬 T-901 契约 §5.5 的六段格式(背景 / 变更 / 实现说明 / Revision ID / Revises / Create Date)。**Pre-commit 钩子会拒绝模板占位**。

---

## 4. Model 同步要求

修改 `backend/app/models/kpi_target.py` 第 47-50 行的 `__table_args__`:

```python
__table_args__ = (
    UniqueConstraint(
        "scope", "scope_value", "metric", "period",
        name="uq_kpi_targets_scope_metric_period",
        postgresql_nulls_not_distinct=True,  # ← 新增此行
    ),
    Index("ix_kpi_targets_scope_metric", "scope", "metric"),
)
```

这一步是为了让 `alembic check` 不报 schema drift —— 必须让 ORM 元数据与 DB 真实状态完全一致。

---

## 5. 验证标准

```bash
cd backend

# 1) 静态检查
.venv/bin/ruff check app/models/kpi_target.py alembic/versions/20260527_*_phase9_fix_kpi_targets_unique_nulls.py
.venv/bin/mypy app/models/kpi_target.py

# 2) Alembic 双向迁移
.venv/bin/alembic upgrade head     # 升到新 revision
.venv/bin/alembic downgrade -1     # 回退本次 fix(回到 c7a9f1e2d4b6 + 默认 UNIQUE)
.venv/bin/alembic upgrade head     # 再升回 fix
.venv/bin/alembic check            # 必须报 "No new upgrade operations detected"

# 3) 负向测试 — UNIQUE 必须拦截 NULL 重复
.venv/bin/python -c "
import asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.exc import IntegrityError
from app.config import settings

async def main():
    url = settings.database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
    eng = create_async_engine(url)
    async with eng.begin() as c:
        try:
            await c.execute(text(\"\"\"
                INSERT INTO kpi_targets (scope, scope_value, metric, target_value, period, tenant_id)
                VALUES ('global', NULL, 'submit_rate', 99.0, 'monthly', 'default')
            \"\"\"))
            raise SystemExit('FAIL: 重复 (global, NULL, submit_rate, monthly) 被允许插入')
        except IntegrityError:
            print('PASS: UNIQUE NULLS NOT DISTINCT 生效')
    await eng.dispose()

asyncio.run(main())
"
```

任一项失败禁止提交。

---

## 6. 提交规约

**两条原子 commit**:

1. `feat(kpi): tighten UNIQUE on kpi_targets to NULLS NOT DISTINCT`
   - 含 2 个文件:新 migration + `kpi_target.py` 改动。
   - Body 简述根因 + PG 15+ NULLS NOT DISTINCT + 双向可回滚。

2. 修改 `docs/dev_tasks.md` 把 Task 1.5 方括号从 `[/]` 改成 `[x]`,然后:
   - `chore(progress): close T-901-FIX`

---

## 7. 不在本契约内的事项

- 不要新建任何 service / router / 测试文件。
- 不要修改 `requirements.txt` / `backend/uv.lock`。
- 不要触碰 `docs/recap.md`(留给 Task 7 统一收尾)。
- 不要回填或加任何 seed 数据。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌,供 PM 探针自动提取**

- **当前持牌任务**: T-901-FIX
- **入口动作**: 阅读本契约 + `docs/dev_tasks.md` 的 Task 1.5 区。看板状态已是 `[/]`,**不要重复加 `chore(lock)` commit**。直接开始编码。
- **核心交付**:
  1. 新 Alembic migration(包含 drop + recreate UNIQUE constraint with `postgresql_nulls_not_distinct=True`)。
  2. 同步 `kpi_target.py` 的 `UniqueConstraint` 参数。
- **完工提交序列**:
  1. `feat(kpi): tighten UNIQUE on kpi_targets to NULLS NOT DISTINCT`
  2. 改 `dev_tasks.md` Task 1.5 → `[x]`,再提 `chore(progress): close T-901-FIX`
- **完工后**: 立即停手,等指挥官二次验收。**不要**擅自进入 T-902(Pydantic + Service 层),那是下一份契约的事。
- **验收通过的判定**: 验证标准 §5 三项全绿,且指挥官能复现负向测试 `PASS: UNIQUE NULLS NOT DISTINCT 生效`。

**契约生效。Codex 收到后请确认 `alembic heads` = `c7a9f1e2d4b6`,然后开干。**
