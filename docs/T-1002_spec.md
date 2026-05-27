# T-1002 执行契约 — `ProjectMember` 联合 UNIQUE 补丁

> **任务编号**: T-1002
> **所属阶段**: Phase 10「部门与项目分组」/ 漏洞修复轮(1/n,第一份代码任务)
> **任务性质**: **schema 补丁 + ORM 同步**(1 个 src 文件改动 + 1 条 Alembic migration,**严禁夹带任何业务代码 / 测试 / 前端**)
> **接力人**: Codex(Worker)
> **指挥官**: Claude(Commander)
> **起草日期**: 2026-05-27
> **前置 commit 链**: `b29da90`(lock) → `7cd0f9d`(T-1001 spec) → `7a7822a`(T-1001 落盘) → `c2941e0`(T-1001 完工) → `<本 commit>`(T-1002 spec + lock 合并)
> **当前 alembic head**: `e8c4a1d9f2b0`(Phase 9 已闭环,T-1002 新 migration 以此为 `down_revision`)

---

## 1. 任务背景

### 1.1 漏洞出处

T-1001 勘察落盘的 plan §10「实际落地路径(Phase 10 勘察)」表第 3 行(项目成员关联)写明:

> `ProjectMember` 已存在:`id UUID PK`,`project_id/user_id UUID FK CASCADE`,`track` enum(`hardware/software/both`),`role_in_project` 文本,`joined_at/left_at`,继承 BaseMixin;**模型层未声明 `UNIQUE(project_id,user_id)`** | 部分 ✅

指挥官追查源代码确认:

```python
# backend/app/models/project_member.py L32-40
class ProjectMember(BaseMixin, Base):
    __tablename__ = "project_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
```

- 只有 `index=True` 的单字段 index,**无 `__table_args__`,无联合 UNIQUE 约束**。
- plan §10 L751 原文写明 `UNIQUE(project_id, user_id)`,但 V2.0 实际落地遗漏。

### 1.2 漏洞后果

允许重复插入同一员工到同一项目:

```sql
INSERT INTO project_members (project_id, user_id, track, ...) VALUES ('p1', 'u1', 'hardware', ...);
INSERT INTO project_members (project_id, user_id, track, ...) VALUES ('p1', 'u1', 'software', ...);  -- 当前不会被拒
```

后续 `health_engine` 按 `project_members` 聚合时会重复计数,污染部门健康度 / 项目健康度;`/api/v1/projects/{id}/members` 也会返回同一员工多行。

### 1.3 修复方案设计

**不使用** 简单 `UNIQUE(project_id, user_id)`,原因:破坏「员工离开项目后再加入」工作流(`left_at` 不为空的历史行 + `left_at IS NULL` 的现行行,需要共存)。

**使用** PostgreSQL **partial unique index** `WHERE left_at IS NULL`:

```sql
CREATE UNIQUE INDEX ix_project_members_project_user_active
ON project_members (project_id, user_id)
WHERE left_at IS NULL;
```

- 同一员工 + 同一项目 + `left_at IS NULL`(在场)→ 最多 1 行,符合"一人在同一项目内只能挂一次"的真实业务
- 历史离场记录 `left_at = '2026-04-15'` → 不受约束,可以保留多条历史
- 同一员工**离场后再加入**(新行 `left_at IS NULL`)→ 因前一行已 `left_at NOT NULL`,新行不冲突

SQLAlchemy ORM 等价表达:

```python
__table_args__ = (
    Index(
        "ix_project_members_project_user_active",
        "project_id", "user_id",
        unique=True,
        postgresql_where=text("left_at IS NULL"),
    ),
)
```

---

## 2. 范围决策

### 2.1 为什么单独成 T-1002 而不合并到 T-1003 (departments 表)

| 备选 | 优势 | 劣势 | 决策 |
|---|---|---|---|
| **A. 合并到 T-1003 数据层 task** | commit 数量少 | 两个独立漏洞耦合,验收混淆;Phase 9 T-901-FIX 已开过 UNIQUE 补丁独立成 task 的先例 | ❌ 拒绝 |
| **B. 单独成 T-1002** | 与 T-901-FIX 模式严格对齐;第一个 Phase 10 代码任务最小风险,易验收易回滚;给 Codex 一个"开门红" | commit 数量略多 | ✅ **采纳** |

### 2.2 严格不做的事

- ❌ **不动 `ProjectMember` 任何现有字段**(`id` / `project_id` / `user_id` / `track` / `role_in_project` / `joined_at` / `left_at` 全部保留原样)
- ❌ **不改任何其他 model**(`User` / `Project` / `KpiTarget` 等全冻结)
- ❌ **不写任何 service / router / schema**
- ❌ **不改 `frontend/src/` 任何文件**
- ❌ **不补任何测试**(留给 T-1007 集中补 Phase 10 测试套件)
- ❌ **不在迁移里写 `UPDATE / DELETE / 数据清洗`** —— 若 upgrade 因现有数据冲突失败,**立即停手报告指挥官**,由指挥官决定方案
- ❌ **不碰 `backend/uv.lock`**(继续 untracked)
- ❌ **不自动 `git push`**

---

## 3. 原子步骤

### 3.1 拿当前 alembic head

```bash
cd /Users/hycdq2026/Downloads/AI-PM-main/backend
.venv/bin/alembic heads
# 期望输出: e8c4a1d9f2b0 (head)
```

把 `e8c4a1d9f2b0` 抄到下一步新 migration 的 `down_revision` 字段。**不要硬编码**——以 `alembic heads` 实际输出为准(以防 Codex 拿到本契约时已有其他 head 漂移)。

### 3.2 新建 Alembic migration

文件路径:`backend/alembic/versions/20260527_<HHMM>_phase10_project_members_partial_unique.py`(HHMM 用执行时的实际时间填充)

新 `revision_id` 用 12 位 hex,例如 `a3b7c2e1d9f4`(随机生成,**不要复用历史 id**)。

```python
"""Phase 10 / T-1002: project_members 加 partial unique index (project_id, user_id) WHERE left_at IS NULL

实际背景
========
T-1001 §10 勘察发现 ProjectMember 模型层未声明联合 UNIQUE,允许同一员工在同一项目内
重复挂多次,污染 health_engine 按成员聚合的统计结果。plan §10 L751 原文已写明
UNIQUE(project_id, user_id),但 V2.0 实际落地遗漏。

变更
====
- 新建 partial unique index `ix_project_members_project_user_active` on
  project_members(project_id, user_id) WHERE left_at IS NULL。
- 同步 ORM `ProjectMember.__table_args__`(在同 commit 的 project_member.py 中)。

实现说明
========
- 使用 partial unique index 而非简单 UNIQUE,保留「员工离场后再加入」的工作流:
  一旦员工 left_at NOT NULL,即视为"历史行"不再受约束;新加入会生成新行 left_at IS NULL,
  与历史行不冲突。
- 该 index 同时承担 "查询某项目当前在场成员" 的加速作用,无需额外建独立 index。
- upgrade 前若现有数据存在重复 (project_id, user_id) WHERE left_at IS NULL,
  upgrade 会因 UNIQUE 冲突失败 —— 此时由指挥官决定是先清洗数据还是改约束方案,
  本 migration 不做自动清洗。

Revision ID: <12 位 hex,执行时随机生成>
Revises: e8c4a1d9f2b0
Create Date: 2026-05-27 <HH:MM:SS>
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "<12 位 hex>"
down_revision: Union[str, None] = "e8c4a1d9f2b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_project_members_project_user_active",
        "project_members",
        ["project_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_members_project_user_active",
        table_name="project_members",
    )
```

**docstring 要求**:
- 必须含**实际背景 / 变更 / 实现说明**三段(参考 Phase 9 T-908 migration 体例)
- **严禁保留**自动生成器留下的模板占位(例如 `"""<description>"""`),pre-commit hook 会拒绝

### 3.3 同步 ORM `project_member.py`

读 `backend/app/models/project_member.py`,做两处改动:

**改动 1**:顶部 import 区扩充 `Index, text`:

```python
# 原 L19:
from sqlalchemy import Date, Enum, ForeignKey, String

# 改为:
from sqlalchemy import Date, Enum, ForeignKey, Index, String, text
```

**改动 2**:在类 `ProjectMember` 的 `__tablename__` 之后、`id` 字段之前,插入 `__table_args__`:

```python
class ProjectMember(BaseMixin, Base):
    __tablename__ = "project_members"
    __table_args__ = (
        Index(
            "ix_project_members_project_user_active",
            "project_id",
            "user_id",
            unique=True,
            postgresql_where=text("left_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # ...(以下字段全部保持原样)
```

**注意**:
- 不要把 `__table_args__` 写成 dict 形式(`{}`)—— 必须是 tuple,即使只有一个 Index 也要写成 `(Index(...),)` 注意末尾逗号
- 不要重排其他字段,不要改字段类型,不要加 `Optional` 标注
- 保留所有现有的注释(包括类文档字符串和「NOTE: created_at, updated_at, ...」)

### 3.4 跑闸门(本地预验)

按 §6 全部跑一遍,任何一个红:停手排查,不要打 commit。

### 3.5 修改 `docs/dev_tasks.md`

仅一处:Phase 10 章节 Task 2 从 `[/] In Progress by Commander` 改为 `[x]`(放最后一个 commit 一起 add)。

**不动** dev_tasks.md 任何其他部分(Phase 9 看板 / Task 3-8 后续清单 / 质量闸门 / 执行协议提醒全部保留;📣 锚点中"当前持牌任务: T-1002"也不动 —— 留给指挥官在起草 T-1003 时整体替换)。

---

## 4. 防越界红线

| 红线 | 触发条件 | 后果 |
|---|---|---|
| 触动 `ProjectMember` 任何**字段定义** | `git diff backend/app/models/project_member.py` 显示字段名/类型/FK 变化 | 立即回滚,只允许加 `__table_args__` 和 import |
| 触动 **其他** `backend/app/models/*.py` | `git diff --stat backend/app/models/` 显示 `project_member.py` 之外的文件 | 同上 |
| 触动 `backend/app/{routers,services,schemas}/` | `git diff --stat` 命中 | 同上 |
| 触动 `frontend/src/` 任何文件 | 同上 | 同上 |
| 触动 `backend/tests/` 任何文件 | 同上 | 同上 |
| 新 migration 含 `UPDATE / DELETE / INSERT` SQL | `grep -E "op\.execute.*UPDATE\|op\.execute.*DELETE" 新 migration` 命中 | 严重违纪,立即回滚并报告指挥官 |
| `alembic upgrade head` 失败 | upgrade 命令非零退出 | **不要自行清洗数据**,立即停手报告指挥官 |
| docstring 含模板占位 | 例如 `"""<description>"""` 或 `"""Revises: """` 留空 | pre-commit hook 拒绝,Codex 重写 |
| 修改 `backend/uv.lock` | git status 显示其被跟踪 | 立即 `git restore --staged backend/uv.lock` |
| 自行 `git push` | origin/main 收到新 commit 而指挥官未 sign-off | 严重违纪,需立即 `git push --force-with-lease` 回滚 |

---

## 5. 数据风险评估

T-1002 是 schema-only 改动,但 partial unique index 创建会**扫描全表并校验唯一性**,有以下风险:

### 5.1 风险 A — 现有数据存在重复 `(project_id, user_id) WHERE left_at IS NULL`

`alembic upgrade head` 会因 IntegrityError 失败。

**应对**(**严禁 Codex 自行处理**):
1. Codex 立即停手,把失败堆栈完整贴给指挥官
2. 指挥官在主分支检查是否真有重复数据:
   ```sql
   SELECT project_id, user_id, COUNT(*) FROM project_members
   WHERE left_at IS NULL
   GROUP BY project_id, user_id HAVING COUNT(*) > 1;
   ```
3. 若有重复:指挥官决定清洗方案(保留最新 `joined_at` / 合并 `track` 等),起草 T-1002-FIX 单独清洗 task
4. 若清洗后无重复:继续 T-1002 upgrade

**T-1002 本身**:upgrade 失败时停手,**不写 `op.execute("DELETE FROM ...")`**

### 5.2 风险 B — 同一员工先离场再加入,旧行 `left_at` 为空

历史数据若存在 `joined_at=2026-03-01, left_at=NULL`(在场)+ `joined_at=2026-04-01, left_at=NULL`(再加入)的两行(都视为"在场"),partial index 会拒绝。

**应对**:同 5.1,停手报告。

### 5.3 期望路径(无风险)

V2.0 deployed 数据**应当**没有重复(否则 health_engine 早就异常),所以**绝大概率 upgrade 直接成功**。本 §5 是 just-in-case 防御,Codex 不要因为 §5 的存在而过度防御性编程。

---

## 6. 测试基线

```bash
cd /Users/hycdq2026/Downloads/AI-PM-main/backend

# alembic 三件套
.venv/bin/alembic upgrade head                    # 必须成功
.venv/bin/alembic downgrade -1                    # 反向 drop index,必须成功
.venv/bin/alembic upgrade head                    # 重新应用,必须成功
.venv/bin/alembic check                           # 必须 "No new upgrade operations detected."

# 测试零回归
.venv/bin/pytest tests/                           # 必须 160 passed + 2 skipped(与 c2941e0 完全一致)

# 静态检查
.venv/bin/ruff check .                            # All checks passed
.venv/bin/mypy app/models/project_member.py       # Success: no issues

# 前端无破坏验证
cd ../frontend
npm run lint && npm run typecheck                 # 仍零警告
```

**任何一项失败,T-1002 不许打完工 commit**。

---

## 7. 完工提交序列(原子 2 commit,**顺序不可乱**)

### Commit 1 — `fix(project): add partial unique index on project_members(project_id, user_id) WHERE left_at IS NULL`

```bash
git add backend/app/models/project_member.py backend/alembic/versions/20260527_<HHMM>_phase10_project_members_partial_unique.py
git commit -m "$(cat <<'EOF'
fix(project): add partial unique index on project_members(project_id, user_id) WHERE left_at IS NULL

Phase 10 / T-1002 — T-1001 §10 勘察发现 ProjectMember 模型层未声明
联合 UNIQUE,允许同一员工在同一项目内重复挂多次,污染 health_engine
按成员聚合的统计结果。plan §10 L751 原文已写明该约束,V2.0 落地遗漏。

修复:partial unique index
  ix_project_members_project_user_active(project_id, user_id) WHERE left_at IS NULL
- 软删除友好(员工离场后再加入,新行与历史行不冲突)
- 同时承担 "查项目当前在场成员" 的加速作用
- ORM `ProjectMember.__table_args__` 同步注入,保持 ORM ↔ DB schema 一致

不动任何字段定义 / 服务层 / 路由 / 前端 / 测试;T-1007 集中补 Phase 10 测试套件。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Commit 2 — `chore(progress): close T-1002 — ProjectMember partial unique index 落地`

```bash
git add docs/dev_tasks.md
git commit -m "$(cat <<'EOF'
chore(progress): close T-1002 — ProjectMember partial unique index 落地

dev_tasks.md Phase 10 章节 Task 2 状态从 [/] In Progress 改为 [x]。
📣 恢复执行指令锚点保留 T-1002 现状,留给指挥官在起草 T-1003
(departments 表)时统一替换。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 8. 验收标准(指挥官二次验收清单)

| 项 | 期望 | 校验命令 |
|---|---|---|
| 提交数量 | T-1002 区间恰好 2 个 commit(从指挥官的 chore(spec) 之后起算) | `git log <spec_commit>..HEAD --oneline \| wc -l` 应为 2 |
| 提交顺序 | fix(project) → chore(progress) | `git log <spec_commit>..HEAD --oneline` |
| 文件隔离 | Commit 1 只含 `project_member.py` + 1 个新 migration;Commit 2 只含 `dev_tasks.md` | `git show --stat <commit>` |
| 业务代码隔离 | `backend/app/{routers,services,schemas}/` 全 0 字节改动;`frontend/src/` 全 0 字节;`backend/tests/` 全 0 字节 | `git diff <spec_commit>..HEAD --stat -- backend/app/routers backend/app/services backend/app/schemas frontend/src backend/tests` 应为空 |
| 字段定义不变 | `ProjectMember` 类字段名/类型/FK/default 全部与 `c2941e0` 一致 | `git diff <spec_commit>..HEAD -- backend/app/models/project_member.py` 只显示 import 和 `__table_args__` 新增 |
| alembic 三件套绿 | upgrade/downgrade/upgrade/check 全成功 | 见 §6 |
| 测试零回归 | `pytest tests/` 仍 160+2 | 见 §6 |
| ORM ↔ DB 一致 | `alembic check` 通过("No new upgrade operations detected.") | 见 §6 |
| 锚点保留 | 📣 锚点中 "当前持牌任务: T-1002" 保留(未自行替换为 T-1003) | `grep "当前持牌任务" docs/dev_tasks.md` |
| Task 2 状态 | dev_tasks.md Task 2 = `[x]` | `grep "Task 2 (T-1002)" docs/dev_tasks.md` |

任何一项不符,指挥官要求 Codex 回滚到 `<spec_commit>` 并重做。

---

## 9. 与历史契约 / 后续 task 的关系

| 关系对象 | 关系 |
|---|---|
| **T-901-FIX** (Phase 9 UNIQUE NULLS NOT DISTINCT) | T-1002 模式与之严格对齐:UNIQUE 漏洞独立成 task,与主线数据层 task(T-1003)解耦 |
| **T-1001** (Phase 10 勘察) | T-1002 是 T-1001 落盘的 6 列对照表第 3 行(项目成员关联)中标记 "部分 ✅" 的那个缺失约束的补丁。完工后该行可在 T-1008 文档收尾时升级到 "✅ T-1002 已补 UNIQUE" |
| **T-1003** (departments 表) | T-1002 与 T-1003 严格解耦,不共享 migration,不互为依赖。T-1002 完工后指挥官独立起草 T-1003 |
| **T-1007** (Phase 10 测试) | T-1002 不补测试,但 T-1007 必须覆盖:重复 `(project_id, user_id) WHERE left_at IS NULL` 抛 IntegrityError + `left_at` 不为空时允许重复 |

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌,供 PM 探针自动提取**

- **当前持牌任务**: **T-1002**(指挥官已通过 `chore(spec)` commit 同时打 `[/]` 锁)—— Phase 10 **第一份代码任务,纯漏洞修复轮**。给 `ProjectMember` 补 partial unique index `(project_id, user_id) WHERE left_at IS NULL`。
- **执行入口**: 阅读本契约 `docs/T-1002_spec.md`,无需重打 `chore(lock)`,直接进入实施。先 `cd backend && .venv/bin/alembic heads` 拿当前 head id(应为 `e8c4a1d9f2b0`),抄到新 migration 的 `down_revision`,**不要硬编码**。
- **核心动作**(严格按 §3 顺序):
  1. **新建** `backend/alembic/versions/20260527_<HHMM>_phase10_project_members_partial_unique.py` —— `upgrade()` 调 `op.create_index(..., unique=True, postgresql_where=sa.text("left_at IS NULL"))`,`downgrade()` 反向 drop。docstring 写实际背景/变更/实现说明,**严禁保留模板占位**。
  2. **改** `backend/app/models/project_member.py` —— import 区补 `Index, text`,类 `ProjectMember` 上加 `__table_args__ = (Index(..., unique=True, postgresql_where=text("left_at IS NULL")),)`,**不动任何字段定义**。
  3. **改** `docs/dev_tasks.md` Task 2 由 `[/]` 改 `[x]`(放最后 commit)。
- **严禁项**(违反则立即回滚):
  - **严禁**改 `ProjectMember` 任何**字段定义**(id / project_id / user_id / track / role_in_project / joined_at / left_at)
  - **严禁**改 `backend/app/` 任何其他 `.py` 文件
  - **严禁**改 `frontend/src/` 任何文件
  - **严禁**补任何测试
  - **严禁**在 migration 里写 `UPDATE / DELETE / INSERT` 任何数据 SQL
  - **严禁**自行清洗"现有数据冲突" —— upgrade 失败立即停手报告指挥官
  - **严禁**自动 `git push`
  - **严禁**自行启动 T-1003
- **闸门**(都必须绿):
  ```bash
  cd backend
  .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head && .venv/bin/alembic check
  .venv/bin/pytest tests/                                      # 必须 160 passed + 2 skipped
  .venv/bin/ruff check . && .venv/bin/mypy app/models/project_member.py
  cd ../frontend && npm run lint && npm run typecheck         # 前端无破坏验证
  ```
- **完工提交序列**(原子 2 commit,顺序不可乱):
  1. `fix(project): add partial unique index on project_members(project_id, user_id) WHERE left_at IS NULL`(只含 `backend/app/models/project_member.py` + 新 alembic migration)
  2. `chore(progress): close T-1002 — ProjectMember partial unique index 落地`(只含 `docs/dev_tasks.md`)
- **完工后**: 立即停手汇报「T-1002 完工,等待指挥官二次验收 + 起草 T-1003 (departments 表) 实施契约」。**不要**自行启动 T-1003。
