# T-901 执行契约 — kpi_targets 数据库迁移

> **任务编号**: T-901
> **任务名**: kpi_targets 表与 SQLAlchemy Model + Alembic 迁移 + Seed 数据
> **指挥官**: Claude (QA & Refactor Specialist)
> **执行人**: Codex (Worker)
> **依据**: `docs/implementation-plan.md §9` + 项目现有惯例
> **生效**: Phase 9 起始锁定提交 `191426d` 之后

---

## 1. 目标 (Goal)

为 Phase 9「KPI 目标设定」搭建数据层基座:

1. 创建 `kpi_targets` 表,可持久化三种 scope × 四类 metric 的 KPI 目标。
2. 提供 SQLAlchemy Model + 三个 Enum(`KpiScope` / `KpiMetric` / `KpiPeriod`)供后续 service / router 复用。
3. 写一份双向可回滚的 Alembic migration,并在 `upgrade()` 里 seed 4 条全局基线 KPI。
4. 不引入任何 service / router / 测试代码 —— **本任务范围仅止于「数据层落地 + 跑通 migration」**。

---

## 2. 范围边界 (Scope Boundaries)

### 范围内 (IN)
- 新建 `backend/app/models/kpi_target.py`。
- 新建 `backend/alembic/versions/20260527_<HHMM>_phase9_add_kpi_targets.py`。
- 修改 `backend/app/models/__init__.py`(导出 + `__all__` 登记)。
- 跑通 `alembic upgrade head` / `alembic downgrade -1` / `alembic check`。

### 范围外 (OUT — 留给 T-902 及以后)
- Pydantic Schemas(`app/schemas/kpi.py`)。
- Service 层(`app/services/kpi_service.py`)。
- API 路由(`app/routers/kpi.py`、`app.main.py` 注册)。
- 后端测试 / 前端 UI / 文档同步。
- 修改 `User` 模型加 `kpi_targets` 反向 relationship —— **不需要**,KPI 目标不通过 user 反查。

---

## 3. 表结构定义 (Schema)

### 3.1 完整字段表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | `Integer` | `primary_key=True`, `autoincrement=True` | 主键。**坚持用 Integer**(对齐 plan §9 SERIAL 设计),不要换成 UUID。 |
| `scope` | `VARCHAR(20)` / `Enum(KpiScope)` | `nullable=False` | 取值 `global` / `department` / `job_title`。 |
| `scope_value` | `VARCHAR(50)` | `nullable=True` | `scope='global'` 时为 `NULL`;其他 scope 必填,业务层校验(本任务**不**加 DB CHECK)。 |
| `metric` | `VARCHAR(30)` / `Enum(KpiMetric)` | `nullable=False` | 取值 `submit_rate` / `avg_score` / `sprint_completion` / `blocker_resolve_days`。 |
| `target_value` | `Float` | `nullable=False` | 目标值,业务侧可以是百分数 / 分数 / 天数。 |
| `period` | `VARCHAR(10)` / `Enum(KpiPeriod)` | `nullable=False`, `default='monthly'` | 取值 `weekly` / `monthly` / `quarterly`。 |
| `created_at` | `TIMESTAMPTZ` | `server_default=func.now()`, `nullable=False` | **来自 `BaseMixin`,不要重复声明**。 |
| `updated_at` | `TIMESTAMPTZ` | `server_default=func.now()`, `onupdate=func.now()`, `nullable=True` | 来自 `BaseMixin`。 |
| `created_by` | `UUID` | `ForeignKey("users.id", ondelete="SET NULL")`, `nullable=True` | 来自 `BaseMixin`,**校正了 plan §9 的 INT 类型错误**。 |
| `tenant_id` | `VARCHAR(64)` | `nullable=False`, `default='default'`, `index=True` | 来自 `BaseMixin`,多租户隔离。 |

> **强制**:`KpiTarget` 必须继承 `BaseMixin`(MRO 顺序 `class KpiTarget(BaseMixin, Base)`),让 `created_at / updated_at / created_by / tenant_id` 四个字段自动注入。**不要手写这四个字段**。

### 3.2 索引与约束

- `UniqueConstraint("scope", "scope_value", "metric", "period", name="uq_kpi_targets_scope_metric_period")` —— 防止重复目标。
- `Index("ix_kpi_targets_scope_metric", "scope", "metric")` —— 支持按 (scope, metric) 查询达成率。
- `Index("ix_kpi_targets_tenant_id", "tenant_id")` —— BaseMixin 已声明,不要重复加。

### 3.3 Enum 定义(写在 `kpi_target.py` 文件顶部)

```python
class KpiScope(str, enum.Enum):
    global_ = "global"          # 注意:不能用 global 作变量名,加下划线后缀
    department = "department"
    job_title = "job_title"

class KpiMetric(str, enum.Enum):
    submit_rate = "submit_rate"
    avg_score = "avg_score"
    sprint_completion = "sprint_completion"
    blocker_resolve_days = "blocker_resolve_days"

class KpiPeriod(str, enum.Enum):
    weekly = "weekly"
    monthly = "monthly"
    quarterly = "quarterly"
```

SQLAlchemy 列声明示例(用 `Enum(KpiScope, name="kpi_scope")` 让 Alembic 自动生成 PostgreSQL ENUM 类型):

```python
scope: Mapped[KpiScope] = mapped_column(Enum(KpiScope, name="kpi_scope"), nullable=False)
metric: Mapped[KpiMetric] = mapped_column(Enum(KpiMetric, name="kpi_metric"), nullable=False)
period: Mapped[KpiPeriod] = mapped_column(
    Enum(KpiPeriod, name="kpi_period"), nullable=False, default=KpiPeriod.monthly
)
```

---

## 4. SQLAlchemy Model 实现要求

文件:`backend/app/models/kpi_target.py`

- 文件顶部 docstring 简述用途与设计偏差(SERIAL id / UUID created_by / BaseMixin 继承)。
- `__tablename__ = "kpi_targets"`。
- `__table_args__` 放 `UniqueConstraint` 与额外的 `Index`(BaseMixin 已有的 `tenant_id` 索引不要重复)。
- `__repr__` 写一句简短的:`f"<KpiTarget {self.scope.value}:{self.scope_value or '-'} / {self.metric.value} = {self.target_value}>"`。
- 文件结尾 `from __future__ import annotations` 放顶部一行(对齐 `user.py` 等现有模型)。

---

## 5. Alembic Migration 实现要求

### 5.1 文件命名

`backend/alembic/versions/20260527_<HHMM>_phase9_add_kpi_targets.py`

`<HHMM>` 用执行任务时的本地北京时间(`Asia/Shanghai`),例:任务在 2026-05-27 16:30 执行 → `20260527_1630_phase9_add_kpi_targets.py`。

### 5.2 Revision 链

- `revision`: Codex 自定义 12 位 hex 字符串(沿用项目现有风格,例 `a1b2c3d4e5f6`)。
- `down_revision`: **必须先跑 `cd backend && .venv/bin/alembic heads`,取实际输出的 head ID,不要硬编码**。如果跑出来不是 `9b7d3e1c4a20`(Phase 7 MV)就说明环境状态不一致,停下来 ping 指挥官。

### 5.3 upgrade() 步骤(顺序严格)

```python
def upgrade() -> None:
    # 1) 创建三个 PostgreSQL ENUM 类型
    kpi_scope = sa.Enum("global", "department", "job_title", name="kpi_scope")
    kpi_metric = sa.Enum(
        "submit_rate", "avg_score", "sprint_completion", "blocker_resolve_days",
        name="kpi_metric",
    )
    kpi_period = sa.Enum("weekly", "monthly", "quarterly", name="kpi_period")
    kpi_scope.create(op.get_bind(), checkfirst=True)
    kpi_metric.create(op.get_bind(), checkfirst=True)
    kpi_period.create(op.get_bind(), checkfirst=True)

    # 2) 建表(含 BaseMixin 四字段)
    op.create_table(
        "kpi_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", kpi_scope, nullable=False),
        sa.Column("scope_value", sa.String(50), nullable=True),
        sa.Column("metric", kpi_metric, nullable=False),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("period", kpi_period, nullable=False, server_default="monthly"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("created_by", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "scope", "scope_value", "metric", "period",
            name="uq_kpi_targets_scope_metric_period",
        ),
    )

    # 3) 索引
    op.create_index("ix_kpi_targets_scope_metric", "kpi_targets", ["scope", "metric"])
    op.create_index("ix_kpi_targets_tenant_id", "kpi_targets", ["tenant_id"])

    # 4) Seed 数据(见 §6)
    op.bulk_insert(
        sa.table(
            "kpi_targets",
            sa.column("scope", kpi_scope),
            sa.column("scope_value", sa.String),
            sa.column("metric", kpi_metric),
            sa.column("target_value", sa.Float),
            sa.column("period", kpi_period),
            sa.column("tenant_id", sa.String),
        ),
        [
            {"scope": "global",     "scope_value": None,     "metric": "submit_rate",          "target_value": 95.0, "period": "monthly", "tenant_id": "default"},
            {"scope": "global",     "scope_value": None,     "metric": "avg_score",            "target_value": 75.0, "period": "monthly", "tenant_id": "default"},
            {"scope": "global",     "scope_value": None,     "metric": "blocker_resolve_days", "target_value": 3.0,  "period": "monthly", "tenant_id": "default"},
            {"scope": "department", "scope_value": "技术部", "metric": "sprint_completion",    "target_value": 80.0, "period": "monthly", "tenant_id": "default"},
        ],
    )
```

### 5.4 downgrade() 步骤(顺序严格)

```python
def downgrade() -> None:
    op.drop_index("ix_kpi_targets_tenant_id", table_name="kpi_targets")
    op.drop_index("ix_kpi_targets_scope_metric", table_name="kpi_targets")
    op.drop_table("kpi_targets")
    sa.Enum(name="kpi_period").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="kpi_metric").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="kpi_scope").drop(op.get_bind(), checkfirst=True)
```

### 5.5 Docstring

文件头 docstring 必须包含「背景 / 变更 / 实现说明 / Revision ID / Revises / Create Date」六段(对齐 `20260527_0900_phase7_add_analytics_materialized_views.py` 风格)。**pre-commit 钩子会拒绝保留模板占位 docstring**(`Add new column...` 类自动生成内容必须改写)。

---

## 6. Seed 数据明细

| scope | scope_value | metric | target_value | period |
|-------|-------------|--------|--------------|--------|
| `global` | `NULL` | `submit_rate` | `95.0` | `monthly` |
| `global` | `NULL` | `avg_score` | `75.0` | `monthly` |
| `global` | `NULL` | `blocker_resolve_days` | `3.0` | `monthly` |
| `department` | `技术部` | `sprint_completion` | `80.0` | `monthly` |

> `created_by` 全部 `NULL`(系统种入,无 actor 关联);`tenant_id` 全部 `'default'`。

---

## 7. `app/models/__init__.py` 登记

在 `# --- IPD 项目管理模型 ---` 区块后追加一节:

```python
# --- KPI 目标设定模型 (Phase 9) ---
from app.models.kpi_target import KpiMetric, KpiPeriod, KpiScope, KpiTarget
```

并在 `__all__` 列表追加四个名字:`"KpiTarget", "KpiScope", "KpiMetric", "KpiPeriod"`。

---

## 8. 验证标准 (Acceptance Criteria)

Codex 提交 `feat(kpi):` 前必须**全部跑过**:

```bash
cd backend

# 1) 静态检查
.venv/bin/ruff check app/models/kpi_target.py alembic/versions/20260527_*_phase9_add_kpi_targets.py
.venv/bin/mypy app/models/kpi_target.py

# 2) Alembic 双向迁移
.venv/bin/alembic upgrade head     # 应 exit 0,无 ERROR
.venv/bin/alembic downgrade -1     # 回退本次 migration,应 exit 0
.venv/bin/alembic upgrade head     # 再升回来,应 exit 0
.venv/bin/alembic check            # 应 exit 0,确认 model 与 schema 一致

# 3) 数据校验(直接 psql)
psql $DATABASE_URL -c "SELECT scope, COALESCE(scope_value,'(global)'), metric, target_value, period FROM kpi_targets ORDER BY id;"
# 期望输出 4 行,完全对齐 §6 表格

# 4) 计数校验
psql $DATABASE_URL -c "SELECT COUNT(*) FROM kpi_targets;"
# 期望输出 4
```

**任一项失败禁止提交**。如果 `alembic check` 报 schema drift,说明 model 字段类型/约束与 migration 不一致,优先改 model 不要改 migration。

---

## 9. 提交规约

执行完毕后,**两条原子 commit**:

1. `feat(kpi): add kpi_targets model and alembic migration`
   - 含 3 个文件:`kpi_target.py` / `<migration>.py` / `__init__.py` 修改。
   - Body 简述:表结构 / 4 条 seed / 偏差(SERIAL id 保留、UUID created_by 校正、BaseMixin 继承)。

2. 修改 `docs/dev_tasks.md` 把 Task 1 方括号从 `[/]` 改成 `[x]`,然后:
   - `chore(progress): close T-901`

> **不要**把 dev_tasks.md 改动塞进 `feat(kpi):` 提交内 —— 保持 feat 提交只含代码 + migration。

---

## 10. 已知风险与回滚

- **PostgreSQL ENUM 类型一旦创建,downgrade 必须显式 drop**,否则后续重跑 `upgrade` 会因「type already exists」报错。§5.4 已覆盖。
- 如果本地 DB 已经有过实验性 `kpi_targets` 表(手工建过),`upgrade()` 会因 `relation already exists` 失败 —— 此时先 `DROP TABLE kpi_targets CASCADE; DROP TYPE kpi_scope, kpi_metric, kpi_period;` 再重跑。
- Seed 数据中文字符串「技术部」必须用 UTF-8 编码;`psql` 客户端确认 `\encoding` 为 `UTF8`。

---

## 11. 不在本契约内的事项

以下任何一项,Codex **不得在 T-901 提交中包含**:
- 修改 `app.main.py` 路由注册。
- 新增 `app/schemas/kpi.py` 或 `app/services/kpi_service.py`。
- 新增 `tests/test_kpi_*.py`。
- 修改 `docs/recap.md` 或 `docs/implementation-plan.md`。
- 触碰 `backend/uv.lock` 或 `requirements.txt`。

如发现需要,先 ping 指挥官增订契约,不要私自越界。

---

**契约生效。Codex 收到后请确认 down_revision 实际 head,然后开干。完工后等指挥官(我)接手 QA 闸门。**
