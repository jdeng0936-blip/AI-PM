# T-1003 执行契约 — `departments` 独立表 + ORM + 7 seed

> **任务编号**: T-1003
> **所属阶段**: Phase 10「部门与项目分组」/ 数据层主线轮(2/n,第一份新建表任务)
> **任务性质**: **新建 1 个 ORM 文件 + 1 条 Alembic migration(建表 + bulk_insert 7 seed)+ `models/__init__.py` 暴露**(共 3 个 src 文件改动,**严禁夹带任何 service / router / schema / 前端 / 测试 / `User.department` 字段改造**)
> **接力人**: Codex(Worker)
> **指挥官**: Claude(Commander)
> **起草日期**: 2026-05-27
> **起草时间戳**: `[2026-05-27 18:59:30]`
> **前置 commit 链**: `7d2ab02`(T-1002 spec) → `6e2b94a`(T-1002 fix:partial unique index)→ `b06db91`(T-1002 close)→ `<本 commit>`(T-1003 spec + lock 合并)
> **当前 alembic head**: `4f8e370435ea`(T-1002 落地后的最新 head,T-1003 新 migration 以此为 `down_revision`)

---

## 1. 任务背景

### 1.1 缺口出处

T-1001 勘察落盘的 `docs/implementation-plan.md §10「实际落地路径(Phase 10 勘察)」` 6 列对照表第 1 行(部门表)明确写明:

> 部门表 | `CREATE TABLE departments (...)` 独立表 + `manager_id FK` | 未发现 `Department` ORM;Alembic migrations 未命中 `departments` 表 | ❌

第 2 行(部门字段)补充:

> 部门字段 | (未明确)| `User.department: String(64), nullable=False, default=""`,普通字符串字段,非 FK | 部分 ✅

待补齐清单第 1 条:

> `departments` 独立表 / ORM / migration 尚未落地,当前仅有 `users.department` 字符串字段。

指挥官源码追查再次确认(2026-05-27 18:58):

```bash
$ grep -l "departments" backend/app/models/*.py        # 空
$ grep "departments" backend/alembic/versions/*.py     # 空
$ grep -n "department" backend/app/models/user.py
53:    department: Mapped[str] = mapped_column(String(64), nullable=False, default="")
```

`User.department` 仅为 `String(64)` 字段,无 FK,无对照表,与 plan §10 L755-759 原文设计有显著缺口。

### 1.2 缺口后果

- `/api/v1/admin/departments` 端点 (T-1004) 无表可查
- `/api/v1/admin/reports?group_by=department` (T-1005) 即使聚合也只能拿 `User.department` 字符串,无法获取 `manager_id` 完成组长画像
- 前端管理页 (T-1006) 无新建/管理部门的对外能力
- 历史数据迁移延后(Phase 11+)需要这张表作为底座

### 1.3 设计方案

**采纳 plan §10 L754-759 原文设计**(SQLAlchemy 等价表达):

```python
class Department(BaseMixin, Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="部门负责人,FK→users.id,删除用户时置 NULL",
    )
    # BaseMixin 自动注入 created_at / updated_at / created_by / tenant_id
```

**关键决策**:

| 决策点 | 选项 | 决策 | 理由 |
|---|---|---|---|
| `id` 类型 | INT vs UUID | **UUID** | 与全仓 V2.0 主键体例一致,T-1004 schema/router 直接 `uuid.UUID` 类型流转 |
| `name` 长度 | `VARCHAR(50)`(plan)vs `String(64)` | **`String(64)`** | 对齐 `User.department: String(64)`,方便 Phase 11+ 反向校验(`User.department` 串 ↔ `Department.name` 串) |
| `manager_id` 删除策略 | `RESTRICT` vs `SET NULL` vs `CASCADE` | **`SET NULL`** | 部门 outlive 个人;经理离职/降职不应连带整个部门消失;`RESTRICT` 会阻塞用户软删除,`CASCADE` 后果灾难 |
| `manager_id` nullable | `False` vs `True` | **`True`** | 7 seed 创建时 `manager_id=NULL`(由 Phase 11+ 通过管理页指派);非空约束会让 seed 不可行 |
| `manager_id` 索引 | 是 vs 否 | **是**(`index=True`) | T-1004 `get_with_members` 反查时按 `manager_id` 筛"我管的部门"是高频路径 |
| 7 seed 部门列表 | dev_tasks.md Task 3 已锁定 | **技术部/生产部/采购部/财务部/商务部/销售部/仓储部** | 与 `User.job_title` comment 中提到的"技术部长/采购经理/仓管"职能对齐;`scripts/seed_data.py` 现有 4 部门是子集,本 task 覆盖到 7 |
| 是否同步迁移 `User.department: String` → FK | 是 vs 否 | **否**(增量并存,FK 迁移延后到 Phase 11+) | 历史数据(若有)的 `User.department` 串可能不在 7 seed 内,FK 化会引发数据冲突;dev_tasks.md Task 3 已明确"**不**改 `User.department: VARCHAR(64)` 字段" |
| 是否补 BaseMixin | 是 vs 否 | **是** | 所有核心业务表必须含 `created_at/updated_at/created_by/tenant_id`(见 `backend/app/models/base_mixin.py` 文档字符串及 Rule 01-Stack-Database) |

### 1.4 与 plan §10 L754-759 原文差异(指挥官签字记录)

| plan 原文 | 本契约采纳 | 差异说明 |
|---|---|---|
| `id SERIAL PRIMARY KEY` | `id UUID PK default uuid.uuid4` | 全仓 V2.0 主键已统一为 UUID,SERIAL 不再使用 |
| `name VARCHAR(50)` | `name String(64)` | 与 `User.department: String(64)` 对齐,便于 Phase 11+ 串 ↔ FK 校验 |
| `manager_id INT REFERENCES users(id)` | `manager_id UUID FK→users.id ON DELETE SET NULL, nullable=True, index=True` | INT→UUID(跟 User 主键);新增 ON DELETE 策略 + nullable + 索引 |
| (无)| `BaseMixin`(created_at/updated_at/created_by/tenant_id)| 强制项(Rule 01-Stack-Database)|

---

## 2. 范围决策

### 2.1 为什么单独成 T-1003 而不与 T-1004(service+router)合并

| 备选 | 优势 | 劣势 | 决策 |
|---|---|---|---|
| **A. T-1003 数据层 + T-1004 服务层合并到一个 task** | commit 数量少 | 数据层与业务层耦合,验收混淆;新表 + 新服务 + 新路由放在同一 PR 体积爆炸,无法独立回滚 | ❌ 拒绝 |
| **B. 数据层 (T-1003) 独立成 task,服务层留给 T-1004** | 与 Phase 9 T-901(模型+迁移)→ T-902(服务)→ T-903(路由)的渐进体例严格对齐;新表落地后可独立 `alembic upgrade head` 验收;给后续 T-1004 service 留干净底座 | commit 数量略多 | ✅ **采纳** |

### 2.2 严格不做的事

- ❌ **不动 `User.department` 字段**(`String(64), nullable=False, default=""` 保留原样,FK 迁移延后到 Phase 11+)
- ❌ **不改任何其他 model**(`User / Project / ProjectMember / KpiTarget` 等全冻结)
- ❌ **不写任何 service**(`backend/app/services/department_service.py` 留给 T-1004)
- ❌ **不写任何 router**(`backend/app/routers/departments.py` 留给 T-1004)
- ❌ **不写任何 schema**(`backend/app/schemas/department.py` 留给 T-1004)
- ❌ **不改 `frontend/src/` 任何文件**(留给 T-1006)
- ❌ **不补任何测试**(留给 T-1007 集中补 Phase 10 测试套件)
- ❌ **不改 `scripts/seed_data.py`**(本 task 的 seed 走 alembic `bulk_insert`,与初始化脚本解耦;后者改造延后)
- ❌ **不在迁移里写 `UPDATE / DELETE` 涉及 `users` 表的 SQL** —— 不动 `User.department` 数据
- ❌ **不碰 `backend/uv.lock`**(继续 untracked)
- ❌ **不自动 `git push`**
- ❌ **不自行启动 T-1004**

---

## 3. 原子步骤

### 3.1 拿当前 alembic head

```bash
cd /Users/hycdq2026/Downloads/AI-PM-main/backend
.venv/bin/alembic heads
# 期望输出: 4f8e370435ea (head)
```

把 `4f8e370435ea` 抄到下一步新 migration 的 `down_revision` 字段。**不要硬编码**——以 `alembic heads` 实际输出为准(若指挥官在本契约 commit 后又夹带了其他 migration,head 会漂移)。

### 3.2 新建 ORM `backend/app/models/department.py`

完整文件(70-90 行,严格按下方模板,**不允许加注释/字段**):

```python
"""
app/models/department.py — 部门主表(Phase 10 落地)

对应 plan §10 L755-759 原文设计的独立 departments 表,作为部门分组、
对外 /api/v1/admin/departments 端点(T-1004)、按部门分组报表(T-1005)的底座。

V2.0 历史上仅有 User.department: String(64) 字符串字段,无独立部门表/无 manager 关联;
T-1003 仅落地表 + ORM + 7 seed,不动 User.department 字段(FK 化迁移延后到 Phase 11+)。

字段对齐 plan §10 L755-759 + Rule 01-Stack-Database 通用字段要求。
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class Department(BaseMixin, Base):
    """部门主表 —— 7 seed(技术部/生产部/采购部/财务部/商务部/销售部/仓储部)由 migration 写入。"""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    name: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        comment="部门名称,与 User.department 字符串字段对齐;UNIQUE 防重",
    )

    manager_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="部门负责人,FK→users.id;经理离职时置 NULL,部门不连带删除",
    )

    # NOTE: created_at / updated_at / created_by / tenant_id 由 BaseMixin 自动注入

    def __repr__(self) -> str:
        return f"<Department name={self.name} manager_id={self.manager_id}>"
```

**docstring 与字段要求**:
- 文件 docstring 必含"对应 plan §10 / V2.0 历史 / T-1003 范围 / Rule 01-Stack-Database"4 个关键信息(用于后续审计追溯)
- `comment=` 必须填写中文说明(与 `User.department / dingtalk_userid` 等现有体例一致)
- **严禁**加 `relationship` / `back_populates` / `members` 反向关系(留给 Phase 11+)
- **严禁**加 `__table_args__` / 任何 index(`name` 的 unique 自动建索引,`manager_id` 的 `index=True` 自动建索引,够用)
- **严禁**写任何 classmethod / property / 业务方法(纯数据类)

### 3.3 新建 Alembic migration

文件路径:`backend/alembic/versions/20260527_<HHMM>_phase10_create_departments_table.py`(HHMM 用执行时的实际时间填充)

新 `revision_id` 用 12 位 hex(随机生成,**不要复用历史 id**;例:用 `python -c "import secrets; print(secrets.token_hex(6))"` 拿)。

```python
"""Phase 10 / T-1003: 新建 departments 表 + 7 seed(技术部/生产部/采购部/财务部/商务部/销售部/仓储部)

实际背景
========
T-1001 §10 勘察确认 `departments` 独立表 / ORM / migration 在 V2.0 中尚未落地,
plan §10 L755-759 原文设计的"部门枚举"独立表与 manager_id FK 关联均缺失。当前
仅有 User.department: String(64) 字符串字段,无 manager 关联、无对外管理端点。

变更
====
- 新建 departments 表:id UUID PK / name VARCHAR(64) UNIQUE NOT NULL /
  manager_id UUID FK→users.id ON DELETE SET NULL nullable + index /
  BaseMixin 4 字段(created_at / updated_at / created_by FK→users.id / tenant_id index)。
- bulk_insert 7 seed:技术部 / 生产部 / 采购部 / 财务部 / 商务部 / 销售部 / 仓储部,
  manager_id 全 NULL(由 Phase 11+ 管理页指派),tenant_id="default"。
- 同步 ORM 文件 backend/app/models/department.py(本 commit 一起 add)
  以及 backend/app/models/__init__.py 的 Department 暴露与 __all__ 注册。

实现说明
========
- manager_id 选 ON DELETE SET NULL:经理离职/删除时部门 outlive,不连带删除整张部门;
  RESTRICT 会阻塞用户软删除,CASCADE 后果灾难。
- name 长度选 String(64) 对齐 User.department: String(64),便于 Phase 11+
  反向校验(目前两表并存,Phase 11+ 再做 FK 化迁移)。
- 7 seed 用 op.bulk_insert + sa.table()/sa.column() 体例,与 Phase 9
  T-901 add_kpi_targets migration L89-133 完全一致;每行 id 由 PostgreSQL
  服务端 default uuid.uuid4 生成(本 migration 不显式生成 UUID,避免与
  ORM default 不一致;若 server-side default 未生效,改为 Python 端预生成
  再 insert,但本 V2.0 backend 始终使用 PostgreSQL,server_default 可信)。
- 不动 users.department 字段、不动任何现有数据;upgrade 失败时停手报告,
  不在 migration 里写数据清洗 SQL。
- downgrade 仅 drop_table("departments");FK manager_id 的外键约束随表一并 drop,
  无需单独 drop_constraint。

Revision ID: <12 位 hex,执行时随机生成>
Revises: 4f8e370435ea
Create Date: 2026-05-27 <HH:MM:SS>
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "<12 位 hex>"
down_revision: Union[str, None] = "4f8e370435ea"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_DEPARTMENTS: list[str] = [
    "技术部",
    "生产部",
    "采购部",
    "财务部",
    "商务部",
    "销售部",
    "仓储部",
]


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column(
            "manager_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # BaseMixin 4 字段
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "tenant_id",
            sa.String(length=64),
            nullable=False,
            server_default="default",
        ),
        sa.UniqueConstraint("name", name="uq_departments_name"),
    )
    op.create_index("ix_departments_manager_id", "departments", ["manager_id"])
    op.create_index("ix_departments_tenant_id", "departments", ["tenant_id"])

    # 7 seed:manager_id 全 NULL,id 用 PostgreSQL gen_random_uuid()(extension pgcrypto 在
    # initial_schema 已启用;若担心可改 Python uuid.uuid4 预生成)
    import uuid as _uuid

    op.bulk_insert(
        sa.table(
            "departments",
            sa.column("id", sa.UUID),
            sa.column("name", sa.String),
            sa.column("manager_id", sa.UUID),
            sa.column("tenant_id", sa.String),
        ),
        [
            {
                "id": _uuid.uuid4(),
                "name": dept_name,
                "manager_id": None,
                "tenant_id": "default",
            }
            for dept_name in SEED_DEPARTMENTS
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_departments_tenant_id", table_name="departments")
    op.drop_index("ix_departments_manager_id", table_name="departments")
    op.drop_table("departments")
```

**docstring 要求**(与 T-1002 一致):
- 必须含**实际背景 / 变更 / 实现说明**三段
- **严禁保留**自动生成器留下的模板占位(例如 `"""<description>"""`),pre-commit hook 会拒绝

**SEED_DEPARTMENTS 列表顺序要求**:严格按 `技术部/生产部/采购部/财务部/商务部/销售部/仓储部` 排列,**不要重排**,Codex 完工后 T-1007 测试会按此顺序 assert。

**id 生成策略**:本契约采用 **Python 端 `uuid.uuid4()` 预生成**(见 `import uuid as _uuid` + `"id": _uuid.uuid4()`)。这样每次 `alembic upgrade head` 重跑都会生成新 UUID,但 7 seed 行的 `name` 是 UNIQUE 的,Codex 不需要担心 reentrant 问题(downgrade 时整表 drop;重 upgrade 会重 insert 7 行不同 UUID 但相同 name,UNIQUE 不冲突因为下一轮已 drop)。

### 3.4 改 `backend/app/models/__init__.py`

仅两处插入,**不许重排其他 import**,**不许动其他 `__all__` 元素顺序**:

**改动 1**:`from app.models.daily_report import DailyReport` 之后(按字母顺序),新增一行:

```python
from app.models.department import Department
```

或者放在 `from app.models.deletion_history import DeletionHistory` 之前(实际位置以字母顺序为准,d 开头 5 个 import 应排序为 `daily_report → deletion_history → department`?——**注意**:Python 字典按字母序排是 `daily_report → deletion_history → department`,其中 `deletion_history` 排在 `department` 之前(`del` < `dep`)。**最终建议**:放在 `from app.models.deletion_history import DeletionHistory` 之后、`from app.models.gate_review import GateReview` 之前)。

**改动 2**:`__all__` 列表中插入 `"Department"`。**建议位置**:放在 `"DeletionHistory"` 之后、`"RiskAlert"` 之前(保持字母序;现有 list 已经不是严格字母序,但 Phase 10 至少把 Department 放在合理位置 —— 优先级:**接近 `DeletionHistory` 一行,便于 grep**)。

可参考的最终片段:

```python
from app.models.daily_report import DailyReport
from app.models.deletion_history import DeletionHistory
from app.models.department import Department  # ← 新增
from app.models.gate_review import GateReview
# ...
__all__ = [
    "User",
    "DailyReport",
    "DeletionHistory",
    "Department",   # ← 新增
    "RiskAlert",
    # ...保持其他不变
]
```

**严禁**:
- 重排其他 import(只允许在两个 import 之间插入一行)
- 重排 `__all__` 其他元素(只允许插入一个字符串)
- 删除任何注释(`# --- Mixin ---` / `# --- 附件模型 ---` 等分块注释保留原样)

### 3.5 跑闸门(本地预验)

按 §6 全部跑一遍,任何一个红:停手排查,不要打 commit。

### 3.6 改 `docs/dev_tasks.md`

仅一处:Phase 10 章节 Task 3 从 `[/] In Progress by Codex` 改为 `[x]`(放最后一个 commit 一起 add)。

**说明**:指挥官已在本 `chore(spec)` commit 同时完成两件事 —— ① 将 Task 3 状态从 `[ ]` 改为 `[/] In Progress by Codex`(加锁);② 将 📣 锚点整体替换为 T-1003 发牌内容。Codex 接力时**不要再动 📣 锚点**,锚点中 "当前持牌任务: T-1003" 保留,留给指挥官在起草 T-1004 时再次替换。

**不动** dev_tasks.md 任何其他部分(Phase 9 看板 / Task 4-8 后续清单 / 质量闸门 / 执行协议提醒全部保留)。

---

## 4. 防越界红线

| 红线 | 触发条件 | 后果 |
|---|---|---|
| 触动 `User.department` 字段 | `git diff backend/app/models/user.py` 显示 `department` 字段相关行变化 | 立即回滚 |
| 触动**任何**其他 `backend/app/models/*.py` | `git diff --stat backend/app/models/` 显示 `department.py` 和 `__init__.py` 之外的文件 | 同上 |
| 触动 `backend/app/{routers,services,schemas}/` | `git diff --stat` 命中 | 同上 |
| 触动 `frontend/src/` 任何文件 | 同上 | 同上 |
| 触动 `backend/tests/` 任何文件 | 同上 | 同上 |
| 触动 `backend/scripts/seed_data.py` | git diff 命中 | 同上(本 task seed 只走 migration) |
| 新 migration 含 `UPDATE / DELETE` SQL(无论作用对象) | `grep -E "op\.execute.*UPDATE\|op\.execute.*DELETE" 新 migration` 命中 | 严重违纪,立即回滚 |
| 新 migration 触动 `users` 表 | `grep "users" 新 migration` 命中非 FK 引用 | 严重违纪 |
| `alembic upgrade head` 失败 | upgrade 命令非零退出 | **不要自行清洗数据**,立即停手报告指挥官 |
| docstring 含模板占位 | 例如 `"""<description>"""` 或 `"""Revises: """` 留空 | pre-commit hook 拒绝 |
| 修改 `backend/uv.lock` | git status 显示其被跟踪 | 立即 `git restore --staged backend/uv.lock` |
| 自行 `git push` | origin/main 收到新 commit 而指挥官未 sign-off | 严重违纪 |
| 给 `Department` 加 `relationship` / `back_populates` / `members` 反向关系 | `grep relationship backend/app/models/department.py` 命中 | 立即删除(留给 Phase 11+) |
| 7 seed 顺序与契约不一致 | `SEED_DEPARTMENTS` 列表内容/顺序 ≠ `技术部/生产部/采购部/财务部/商务部/销售部/仓储部` | 立即修正 |
| 同 commit 夹带 `__all__` 重排 | `git diff backend/app/models/__init__.py` 显示**非插入式**改动 | 立即回滚到只插入一行模式 |

---

## 5. 数据风险评估

T-1003 是**纯增量**改动(新表 + 7 seed),理论上无对老数据的破坏性影响,但仍有以下边角风险:

### 5.1 风险 A — `users.department` 现有字符串值与 7 seed 不匹配

例如 `User.department = "研发部"`(不在 7 seed 内),那么 Phase 11+ 做 FK 化迁移时需要补数据清洗,但**本 task 不涉及**(T-1003 增量并存,不动 `users.department`)。

**应对**:**T-1003 不处理**。仅在 §10 文档收尾(T-1008)时记录一行"`users.department` 当前实际取值与 7 seed 的差异清单,留给 Phase 11+ 处理"。

### 5.2 风险 B — `gen_random_uuid()` extension 不可用

PostgreSQL 默认不带 `pgcrypto`/`uuid-ossp` extension,但本仓库 `initial_schema` migration(`20260309_1449_7c681b8e950c_initial_schema.py`)已启用 UUID(否则 `Project.id` / `User.id` 等都无法默认生成)。

**应对**:本契约的 migration 采用 **Python 端 `uuid.uuid4()` 预生成**(`"id": _uuid.uuid4()`),完全绕过 PostgreSQL extension,即使是测试用 SQLite 也能跑通。

### 5.3 风险 C — UNIQUE name 冲突(重 upgrade)

`alembic downgrade -1 && alembic upgrade head` 反复跑时,downgrade 已 `drop_table`,upgrade 重建时 7 seed 用新 UUID 重新 insert,name 全新一轮,**不会冲突**。

**应对**:无需处理,反复跑安全。

### 5.4 期望路径(无风险)

V2.0 deployed 库**没有**任何叫 `departments` 的表(已勘察确认),T-1003 upgrade 直接成功落地 7 seed,downgrade 直接 drop 表,**绝大概率一次过**。本 §5 是 just-in-case 防御,Codex 不要因为 §5 的存在而过度防御性编程。

---

## 6. 测试基线

```bash
cd /Users/hycdq2026/Downloads/AI-PM-main/backend

# alembic 三件套
.venv/bin/alembic upgrade head                    # 必须成功;尾部应 INFO "Running upgrade 4f8e370435ea -> <new_rev>"
.venv/bin/alembic downgrade -1                    # 反向 drop_table,必须成功
.venv/bin/alembic upgrade head                    # 重新应用,必须成功(seed 重 insert,新 UUID)
.venv/bin/alembic check                           # 必须 "No new upgrade operations detected."

# 数据落盘自检(可选,Codex 自查用,不强制)
.venv/bin/python -c "
from sqlalchemy import create_engine, text
import os
e = create_engine(os.environ['DATABASE_URL'])
with e.connect() as c:
    rows = c.execute(text('SELECT name FROM departments ORDER BY name')).fetchall()
    names = [r[0] for r in rows]
    assert names == sorted(['技术部','生产部','采购部','财务部','商务部','销售部','仓储部'])
    print('OK 7 seeds:', names)
"

# 测试零回归
.venv/bin/pytest tests/                           # 必须 160 passed + 2 skipped(与 b06db91 完全一致)

# 静态检查
.venv/bin/ruff check .                            # All checks passed
.venv/bin/mypy app/models/department.py app/models/__init__.py   # Success: no issues

# 前端无破坏验证
cd ../frontend
npm run lint && npm run typecheck                 # 仍零警告
```

**任何一项失败,T-1003 不许打完工 commit**。

---

## 7. 完工提交序列(原子 2 commit,**顺序不可乱**)

### Commit 1 — `feat(department): add Department model + migration + 7 seed (技术部/生产部/采购部/财务部/商务部/销售部/仓储部)`

```bash
git add backend/app/models/department.py \
        backend/app/models/__init__.py \
        backend/alembic/versions/20260527_<HHMM>_phase10_create_departments_table.py

git commit -m "$(cat <<'EOF'
feat(department): add Department model + migration + 7 seed (技术部/生产部/采购部/财务部/商务部/销售部/仓储部)

Phase 10 / T-1003 — T-1001 §10 勘察确认 V2.0 没有独立 departments 表/ORM,
仅有 User.department: String(64) 字符串字段;plan §10 L755-759 原文设计的
"部门枚举"独立表与 manager_id FK 缺失。

新增:
- backend/app/models/department.py:Department(BaseMixin, Base) ORM
  - id UUID PK / name String(64) UNIQUE / manager_id UUID FK→users.id ON DELETE SET NULL nullable + index
  - BaseMixin 自动注入 created_at/updated_at/created_by/tenant_id
  - 不加 relationship,留给 Phase 11+
- alembic migration:create_table + 3 个 index + bulk_insert 7 seed
  (manager_id 全 NULL,tenant_id="default",由 Phase 11+ 管理页指派负责人)
- backend/app/models/__init__.py:暴露 Department + 加入 __all__

不动 User.department 字段(增量并存,FK 化迁移延后到 Phase 11+);
不写 service / router / schema / 前端 / 测试(留给 T-1004 ~ T-1007)。

Commander timestamp: [2026-05-27 18:59:30]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Commit 2 — `chore(progress): close T-1003 — departments 表 + 7 seed 落地`

```bash
git add docs/dev_tasks.md
git commit -m "$(cat <<'EOF'
chore(progress): close T-1003 — departments 表 + 7 seed 落地

dev_tasks.md Phase 10 章节 Task 3 状态从 [ ] 改为 [x]。
📣 恢复执行指令锚点保留 T-1003 现状,留给指挥官在起草 T-1004
(/api/v1/admin/departments 服务 + 路由)时统一替换。

Worker timestamp: [<execution HH:MM:SS>]

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 8. 验收标准(指挥官二次验收清单)

| 项 | 期望 | 校验命令 |
|---|---|---|
| 提交数量 | T-1003 区间恰好 2 个 commit(从指挥官的 chore(spec) 之后起算) | `git log <spec_commit>..HEAD --oneline \| wc -l` 应为 2 |
| 提交顺序 | feat(department) → chore(progress) | `git log <spec_commit>..HEAD --oneline` |
| 文件隔离 | Commit 1 只含 3 个文件(`department.py` + `__init__.py` + 新 migration);Commit 2 只含 `dev_tasks.md` | `git show --stat <commit>` |
| 业务代码隔离 | `backend/app/{routers,services,schemas}/` 全 0 字节改动;`frontend/src/` 全 0 字节;`backend/tests/` 全 0 字节;`scripts/seed_data.py` 全 0 字节 | `git diff <spec_commit>..HEAD --stat -- backend/app/routers backend/app/services backend/app/schemas frontend/src backend/tests backend/scripts/seed_data.py` 应为空 |
| `User.department` 不变 | `git diff <spec_commit>..HEAD -- backend/app/models/user.py` 应为空 | 同左 |
| `__init__.py` 只插入 | 只新增 1 行 import + 1 个 `"Department"` 字符串,其他不变 | `git diff <spec_commit>..HEAD -- backend/app/models/__init__.py` |
| ORM 字段对齐 | `Department` 必含 `id / name / manager_id` 3 字段,无 relationship,无 __table_args__ | `grep -E "Mapped\|relationship\|__table_args__" backend/app/models/department.py` |
| Migration 7 seed | bulk_insert 内容包含且仅包含 `技术部/生产部/采购部/财务部/商务部/销售部/仓储部` 7 个 name,顺序与契约一致 | `grep -oE "技术部\|生产部\|采购部\|财务部\|商务部\|销售部\|仓储部" 新 migration \| wc -l` 应为 7 |
| alembic 三件套绿 | upgrade/downgrade/upgrade/check 全成功 | 见 §6 |
| 测试零回归 | `pytest tests/` 仍 160+2 | 见 §6 |
| ORM ↔ DB 一致 | `alembic check` 通过 | 见 §6 |
| 锚点保留 | 📣 锚点中 "当前持牌任务: T-1003" 保留(未自行替换为 T-1004) | `grep "当前持牌任务" docs/dev_tasks.md` |
| Task 3 状态 | dev_tasks.md Task 3 = `[x]` | `grep "Task 3 (T-1003)" docs/dev_tasks.md` |

任何一项不符,指挥官要求 Codex 回滚到 `<spec_commit>` 并重做。

---

## 9. 与历史契约 / 后续 task 的关系

| 关系对象 | 关系 |
|---|---|
| **T-1001**(Phase 10 勘察)| T-1003 是 T-1001 落盘的 6 列对照表第 1 行(部门表 ❌)的直接落地。完工后该行可在 T-1008 文档收尾时升级到 "✅ T-1003 已建表 + 7 seed" |
| **T-1002**(ProjectMember partial unique)| 两个 task 完全解耦:T-1002 是漏洞修复,T-1003 是新表建设。`down_revision` 串行(T-1003 → 4f8e370435ea → e8c4a1d9f2b0),仅此一条 alembic 依赖,无 ORM/服务/路由耦合 |
| **T-1004**(`/api/v1/admin/departments` 服务 + 路由)| T-1003 完工后,T-1004 直接在 `Department` ORM 之上建 schema/service/router。**T-1003 不写 service,T-1004 不动 ORM** |
| **T-1005**(`/api/v1/admin/reports?group_by=`)| T-1005 可独立于 T-1003 走 `User.department` 字符串字段聚合,但若 T-1003 已落地,T-1005 的 `group_by=department` 可直接拿 `Department.id/name` 做 enrich(留给 T-1005 决定) |
| **T-1006**(前端 admin/departments 管理页)| T-1006 调 T-1004 端点,与 T-1003 间隔一层(不直连 ORM) |
| **T-1007**(Phase 10 测试)| T-1007 必须覆盖:`Department` UNIQUE name 冲突抛 IntegrityError;`alembic upgrade` 后 `SELECT COUNT(*) FROM departments` 必须 = 7;7 个 name 必须与契约一致 |
| **Phase 11+ FK 化迁移**(`User.department: String` → `Department.id: FK`)| **不在 Phase 10 范围**。T-1003 故意保留增量并存,Phase 11+ 单独起 task 处理数据迁移 + 字段类型变更 + 历史 `User.department` 字符串到 `Department.id` 的映射清洗 |

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌,供 PM 探针自动提取**

- **当前持牌任务**: **T-1003**(指挥官已通过本 `chore(spec)` commit 同时打 `[/]` 锁)—— Phase 10 **第二份代码任务,数据层主线轮**:新建 `departments` 独立表 + ORM `Department` 类 + Alembic migration 建表 + bulk_insert 7 seed。**3 个 src 文件改动 + 1 条 migration,严禁夹带任何 service / router / schema / 前端 / 测试 / `User.department` 字段改造**。
- **执行入口**: 阅读本契约 `docs/T-1003_spec.md`,无需重打 `chore(lock)`(已由指挥官打过),直接进入实施。先 `cd backend && .venv/bin/alembic heads` 拿当前 head id(应为 `4f8e370435ea`),抄到新 migration 的 `down_revision`,**不要硬编码**。
- **核心动作**(严格按 §3 顺序):
  1. **新建** `backend/app/models/department.py` —— `Department(BaseMixin, Base)`,3 字段(`id UUID PK / name String(64) unique nullable=False / manager_id UUID FK→users.id ondelete=SET NULL nullable=True index=True`),**不加 relationship / __table_args__ / 业务方法**。
  2. **新建** `backend/alembic/versions/20260527_<HHMM>_phase10_create_departments_table.py` —— `upgrade()`:`op.create_table("departments", ...)` 含 7 列(3 业务 + 4 BaseMixin)+ `op.create_index` × 2 + `op.bulk_insert` 7 seed(name=`技术部/生产部/采购部/财务部/商务部/销售部/仓储部`,顺序不能乱,manager_id 全 NULL,tenant_id="default",id 用 Python `uuid.uuid4()` 预生成);`downgrade()`:反向 `drop_index` × 2 + `drop_table`。docstring 写**实际背景/变更/实现说明**,**严禁保留模板占位**。
  3. **改** `backend/app/models/__init__.py` —— 仅**插入** 1 行 `from app.models.department import Department`(放在 `deletion_history` 之后,`gate_review` 之前)+ 1 行 `"Department",`(放在 `"DeletionHistory"` 之后,`"RiskAlert"` 之前)。**不重排其他 import / `__all__` 元素**。
  4. **改** `docs/dev_tasks.md` Task 3 由 `[ ]` 改 `[x]`(放最后 commit,**不动 📣 锚点**)。
- **严禁项**(违反则立即回滚):
  - **严禁**改 `User.department` 字段(`String(64), nullable=False, default=""` 保留原样)
  - **严禁**改任何其他 model(`User / Project / ProjectMember / KpiTarget` 等)
  - **严禁**写 service / router / schema(留给 T-1004)
  - **严禁**改 `frontend/src/` / `backend/tests/` / `backend/scripts/seed_data.py` 任何文件
  - **严禁**给 `Department` 加 `relationship` / `back_populates` / `members` 反向关系
  - **严禁**在 migration 里写 `UPDATE / DELETE` 任何数据 SQL,**严禁**触动 `users` 表的数据
  - **严禁**自行清洗数据 —— upgrade 失败立即停手报告指挥官
  - **严禁**自动 `git push`
  - **严禁**自行启动 T-1004
  - **严禁**改 📣 锚点("当前持牌任务: T-1003" 保留,留给指挥官在起草 T-1004 时统一替换)
- **闸门**(都必须绿):
  ```bash
  cd backend
  .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head && .venv/bin/alembic check
  .venv/bin/pytest tests/                                      # 必须 160 passed + 2 skipped
  .venv/bin/ruff check . && .venv/bin/mypy app/models/department.py app/models/__init__.py
  cd ../frontend && npm run lint && npm run typecheck         # 前端无破坏验证
  ```
- **完工提交序列**(原子 2 commit,顺序不可乱):
  1. `feat(department): add Department model + migration + 7 seed (技术部/生产部/采购部/财务部/商务部/销售部/仓储部)`(只含 `backend/app/models/department.py` + `backend/app/models/__init__.py` + 新 alembic migration 3 个文件)
  2. `chore(progress): close T-1003 — departments 表 + 7 seed 落地`(只含 `docs/dev_tasks.md`,Task 3 → `[x]`)
- **完工后**: 立即停手汇报「T-1003 完工,等待指挥官二次验收 + 起草 T-1004 (`/api/v1/admin/departments` 服务 + 路由) 实施契约」。**不要**自行启动 T-1004。
- **时间戳纪律**: 所有 commit message 末尾 / 终端汇报 / 任何写入 `dev_tasks.md` 的段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。

---

**契约起草完成时间戳**: `[2026-05-27 19:00:00]`
**指挥官签字**: Claude(Commander)
**等待发牌**: PM 探针中转 → Codex(Worker)
