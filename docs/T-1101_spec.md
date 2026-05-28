# T-1101 实施契约:修复 26 个测试 failure(`tenant_id` 签名 + `must_change_password` RBAC)

> **指挥官签字时间戳**:`[2026-05-28 15:27:00]`
> **持牌任务**:Phase 11 **首任 Task** — 测试基线回归修复
> **触发来源**:`8459a5b fix: tighten tenant scope and report idempotency` + `b5e77c3 fix: harden security and deployment readiness`(您在 12:54 + 13:34 push 的两条远程 fix commits)改了 service 签名 + RBAC middleware,但测试**没同步**导致 26 个 failure
> **范围**:**纯测试改动**,**零 src/migration/frontend 改动**

---

## §1 任务概述

`b5e77c3` + `8459a5b` 两条远程 fix commits 引入 2 类破坏性变更,影响 Phase 9 / 10 测试基线:

### Type A:Service 层签名变更(影响 12 个测试)

`backend/app/services/department_service.py` 和 `backend/app/services/admin_reports_service.py` 删除了 `TENANT_ID = "default"` 全局常量,改为由 router 从 `actor.tenant_id` 注入。结果**所有 service 公开函数的签名加了 `tenant_id`**(部分 keyword-only):

| 函数 | 改前 | 改后 |
|------|------|------|
| `list_departments` | `(db)` | `(db, *, tenant_id: str)` |
| `delete_department` | `(db, dept_id)` | `(db, dept_id, *, tenant_id: str)` |
| `get_department_with_members` | `(db, dept_id)` | `(db, dept_id, *, tenant_id: str)` |
| `create_department` | `(db, payload, actor)` | 签名不变,但内部读 `actor.tenant_id`(测试无影响) |
| `update_department` | `(db, dept_id, payload, actor)` | 签名不变,内部读 `actor.tenant_id`(测试无影响) |
| `group_reports_by_department` | `(db, start_date, end_date, project_id)` | `(db, start_date, end_date, project_id, tenant_id: str)`(**位置参数,不带 `*`**) |
| `group_reports_by_project` | `(db, start_date, end_date, project_id)` | 同上 |

### Type B:RBAC `must_change_password` 检查(影响 14 个测试)

`backend/app/middleware/rbac.py` `get_current_user` 加了:

```python
if user.must_change_password and request.url.path not in PASSWORD_CHANGE_ALLOWED_PATHS:
    raise HTTPException(403, "首次登录或密码已重置,请先修改密码")
```

`User.must_change_password` 默认值 = `True`(见 `backend/app/models/user.py:64-66`)。测试创建 user 时**没显式设 `must_change_password=False`**,所以所有经过 HTTP client(httpx)的 router test 都被 403 拒绝。

---

## §2 文件范围锁定(严格 3 文件,白名单)

```
+ backend/tests/test_phase10_dept_group.py    # Type A 12 处 service call + Type B helper 1 处
+ backend/tests/test_kpi_phase9.py             # Type B helper 1 处
+ backend/tests/test_me_deletions.py           # Type B inline User(...)  1 处
+ docs/dev_tasks.md                            # Task X (T-1101) `[ ]` → `[x]` + chore(progress) 触发
```

**严禁清单**(改动一律驳回):

- ❌ 改 `backend/app/` 任何文件(service 签名是远程 fix 的有意改动,不要回滚)
- ❌ 改 `backend/alembic/` 任何 migration
- ❌ 改 `frontend/` 任何文件
- ❌ 改 `backend/conftest.py` / `backend/pyproject.toml` / `backend/requirements.txt`
- ❌ 改 `backend/tests/` 上述 3 个 file 之外的任何 test
- ❌ 动 4 既定 untracked 文件(`.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` / `backend/uv.lock`)
- ❌ 动 `.gitignore` / `.claude/` 项目级 ECC symlinks
- ❌ 改 `docs/T-1XXX_spec.md` 历史契约
- ❌ 自动 `git push`
- ❌ 改远程 fix 引入的 `must_change_password` 检查逻辑或 service 签名(本任务只修测试基线)

---

## §3 详细文件改动

### §3.1 `backend/tests/test_phase10_dept_group.py` 改动

#### §3.1.1 `_make_user` helper 加 `must_change_password=False`(Type B)

**当前**(L76-99):
```python
async def _make_user(
    db: AsyncSession,
    role: UserRole,
    name: str = "Phase10 用户",
    department: str = "Phase10 技术部",
    is_active: bool = True,
) -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"phase10_{uuid.uuid4().hex[:12]}",
        name=name,
        department=department,
        job_title="工程师",
        role=role,
        is_active=is_active,
        tenant_id=TENANT_ID,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user
```

**改后**:在 `tenant_id=TENANT_ID,` 之后插入一行 `must_change_password=False,`:

```python
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"phase10_{uuid.uuid4().hex[:12]}",
        name=name,
        department=department,
        job_title="工程师",
        role=role,
        is_active=is_active,
        tenant_id=TENANT_ID,
        must_change_password=False,  # 测试 user 默认不要求改密(避免 rbac 403)
    )
```

#### §3.1.2 12 处 service call 加 `tenant_id="default"`(Type A)

用 `TENANT_ID = "default"` 常量(test file 顶部已定义)。逐处 grep + 加参数:

**位置 1**:`get_department_with_members(db_session, dept.id)` 调用处(grep 应找到 ~5 处)
→ `get_department_with_members(db_session, dept.id, tenant_id=TENANT_ID)`

**位置 2**:`list_departments(db_session)` 调用处
→ `list_departments(db_session, tenant_id=TENANT_ID)`

**位置 3**:`delete_department(db_session, dept.id)` 调用处
→ `delete_department(db_session, dept.id, tenant_id=TENANT_ID)`

**位置 4**:`group_reports_by_department(db_session, ...)` 调用处
→ 在末尾参数后追加 `tenant_id=TENANT_ID`(位置参数也可,但 keyword 更清晰)

**位置 5**:`group_reports_by_project(db_session, ...)` 调用处
→ 同上

**执行原则**:Codex 应 `grep -n "list_departments\|delete_department\|get_department_with_members\|group_reports_by_department\|group_reports_by_project" backend/tests/test_phase10_dept_group.py` 列全所有调用点,逐个加 `tenant_id=TENANT_ID` 关键字参数。`create_department / update_department` 签名不变(actor 已带 tenant_id),**无需改动**。

### §3.2 `backend/tests/test_kpi_phase9.py` 改动

#### §3.2.1 `_make_user` helper 加 `must_change_password=False`(Type B)

**当前**(L147-起):
```python
async def _make_user(db: AsyncSession, role: UserRole, name: str = "KPI 测试用户") -> User:
    user = User(
        ...
    )
```

**改后**:同 §3.1.1 模式,在 `User(...)` 构造内最后一个字段后插入 `must_change_password=False,`。

**注**:Codex 应**读完 helper 的完整 User(...) 字段块**,在末尾插入,**保留**所有现有字段(`tenant_id` / `wechat_userid` / `name` / `role` / `is_active` / 等)。

### §3.3 `backend/tests/test_me_deletions.py` 改动

#### §3.3.1 inline `User(...)` 加 `must_change_password=False`(Type B)

**当前**(L25 附近):
```python
return User(
    id=uuid.uuid4(),
    ...
)
```

**改后**:Codex 应 `grep -n "User(" backend/tests/test_me_deletions.py` 列出所有 `User(...)` 构造点(可能有多处),每处都在末尾字段后插入 `must_change_password=False,`。

**注**:若 test file 用 fixture 创建 user(非 `_make_user` helper),Codex 应在 fixture 内修。**不**新增 helper(保持文件结构最小改动)。

### §3.4 `docs/dev_tasks.md` 改动

#### §3.4.1 加 Phase 11 section + Task 1 (T-1101)

在文件末尾(L194 `## 📣 恢复执行指令` 之前)**插入 Phase 11 章节**:

```markdown
---

# Phase 11: 测试基线回归修复(远程 fix 后)

## 当前状态与上下文

- Phase 10 已 100% 闭环并 push origin/main(全 34 commit 已合并)。
- 后续 push 引入 2 条破坏性 fix(由 ericdv111 在 12:54 + 13:34):
  - `b5e77c3 fix: harden security and deployment readiness` — RBAC middleware 加 `must_change_password` 强制改密检查。
  - `8459a5b fix: tighten tenant scope and report idempotency` — `department_service` + `admin_reports_service` 删除 `TENANT_ID = "default"` 常量,改由 router 从 `actor.tenant_id` 注入(service 公开函数签名增加 `tenant_id`)。
- 后端 pytest 出现 **26 failures**(从 Phase 10 收口 `178 passed` 退化到 `152 passed`)。
- 工作树干净,有 ECC 项目级 symlinks(`.claude/skills/` 16 个,已 `.gitignore` 排除)。

## 任务看板

### 测试回归修复 (Test Baseline Restoration)
- [ ] **Task 1 (T-1101): 修复 26 个 test failure(`tenant_id` 签名 + `must_change_password` RBAC)**
  - **改** `backend/tests/test_phase10_dept_group.py`:`_make_user` helper 加 `must_change_password=False` + 12 处 service call 加 `tenant_id=TENANT_ID` 关键字参数(`list_departments / delete_department / get_department_with_members / group_reports_by_department / group_reports_by_project`)。
  - **改** `backend/tests/test_kpi_phase9.py`:`_make_user` helper 加 `must_change_password=False`(8 个 router test 因此 RBAC 403 → 200)。
  - **改** `backend/tests/test_me_deletions.py`:inline `User(...)` 加 `must_change_password=False`(1 个 router test)。
  - **不**改 `backend/app/` 任何 src 代码(远程 fix 是有意改动)。
  - **不**改 `backend/alembic/`、`backend/conftest.py`、`backend/pyproject.toml`、`backend/requirements.txt`。
  - **不**改其他 tests/test_*.py 文件。
  - **完整执行契约见 `docs/T-1101_spec.md`**(必读)。
```

#### §3.4.2 chore(progress) commit 触发 `[ ]` → `[x]`

#### §3.4.3 📣 锚点替换为 T-1101 持牌

**当前**(L194-end)是「Phase 10 已闭环,无持牌任务」终态文字。

**T-1101 完工时**:整段保留 + 上面追加新 📣 锚点:

```markdown
> **更新时间戳(T-1101 完工)**: `[YYYY-MM-DD HH:MM:SS]`
> **当前持牌任务**: 无(T-1101 已 `[x]`,等待指挥官二次验收)。Phase 11 后续候选:① `User.department` FK 迁移 / ② 物化视图增量 / ③ 加权柱状图 / ④ KPI scope 打通。
```

---

## §4 执行步骤(逐步可审计)

1. **前置探针**(强制):
   ```bash
   git status --short --branch
   git log -3 --oneline
   git diff
   git diff --cached
   ```
   必须确认:HEAD = `c9693a9`,ahead origin/main 1 commit,工作树干净,4 既定 untracked + `.claude/` 保留。

2. **加锁**(可选,短任务):
   ```bash
   # dev_tasks.md Phase 11 Task 1 [ ] → [/] In Progress by Codex
   # git commit -m "chore(lock): T-1101 开工"
   ```

3. **执行 3 个 test file 改动**:
   ```bash
   # Codex grep 列全 service call 位置:
   grep -n "list_departments\|delete_department\|get_department_with_members\|group_reports_by_department\|group_reports_by_project" backend/tests/test_phase10_dept_group.py
   
   # Codex grep _make_user / User( 位置:
   grep -n "User(" backend/tests/test_kpi_phase9.py backend/tests/test_me_deletions.py backend/tests/test_phase10_dept_group.py
   ```
   按 §3.1 / §3.2 / §3.3 逐处加 `must_change_password=False` + `tenant_id=TENANT_ID` 关键字参数。

4. **闸门**(全绿才提交):
   ```bash
   cd backend
   .venv/bin/ruff check .
   .venv/bin/mypy tests/test_phase10_dept_group.py tests/test_kpi_phase9.py tests/test_me_deletions.py
   .venv/bin/pytest -q   # 必须 178 passed + 2 skipped (零 fail),即恢复 Phase 10 收口基线 + b5e77c3/8459a5b 加的新测试也通过
   ```

5. **提交 feat commit**(单一原子,3 文件):
   ```bash
   git add backend/tests/test_phase10_dept_group.py backend/tests/test_kpi_phase9.py backend/tests/test_me_deletions.py
   git commit -m "fix(tests): T-1101 restore baseline — pass tenant_id and must_change_password=False

   Two upstream commits (b5e77c3 + 8459a5b) hardened RBAC and tenant scope:
   - rbac.get_current_user now rejects users with must_change_password=True
     unless they hit /auth/me or /auth/change-password
   - department_service & admin_reports_service drop TENANT_ID constant and
     require tenant_id explicitly (kwarg) from router actors

   Test fixtures were not updated, causing 26 failures (8 kpi + 1 me_deletions
   + 12 phase10_dept + others returning 403 or TypeError).

   This commit aligns three test files with the new contract:
   - tests/test_phase10_dept_group.py: _make_user gets must_change_password=False;
     12 service call sites add tenant_id=TENANT_ID kwarg.
   - tests/test_kpi_phase9.py: _make_user gets must_change_password=False.
   - tests/test_me_deletions.py: inline User(...) get must_change_password=False.

   No application code, migrations, or frontend changes.

   Worker timestamp: [YYYY-MM-DD HH:MM:SS]"
   ```

6. **提交 chore(progress) commit**(改 `dev_tasks.md`):
   ```bash
   # Phase 11 Task 1 [ ] → [x]
   # 📣 锚点 append T-1101 完工标记
   git add docs/dev_tasks.md
   git commit -m "chore(progress): close T-1101 — Phase 11 测试基线回归修复完工

   - 26 failed → 0 failed
   - pytest 178 passed + 2 skipped (恢复 Phase 10 收口基线)
   - 改动严格 3 test files + dev_tasks.md, 零 src 改动

   Worker timestamp: [YYYY-MM-DD HH:MM:SS]"
   ```

7. **完工汇报**(终端打印,**不要** `git push`):
   ```
   [YYYY-MM-DD HH:MM:SS] T-1101 完工,pytest 26 failed → 0 failed, 178 passed + 2 skipped 恢复基线。等待指挥官二次验收。
   ```

---

## §5 闸门(Worker 提交前必跑)

```bash
cd backend
.venv/bin/ruff check .                          # All passed
.venv/bin/mypy tests/test_phase10_dept_group.py tests/test_kpi_phase9.py tests/test_me_deletions.py   # 0 error
.venv/bin/pytest -q                             # 0 failed, 178 passed (或 >= 178), 2 skipped
.venv/bin/alembic check                         # No new upgrade operations
```

**改动面校验**:

```bash
cd ..
git status --short                              # 只 tests/ 3 文件 + docs/dev_tasks.md 改动(feat + chore 分提)
git diff <feat-sha>^..<feat-sha> -- backend/app/  # 必须 = 空(零 src 改动)
git diff <feat-sha>^..<feat-sha> -- backend/alembic/  # 必须 = 空
git diff <feat-sha>^..<feat-sha> -- frontend/   # 必须 = 空
git status --short | grep "^??" | wc -l         # 必须 = 4(既定 untracked 保留)
```

---

## §6 防越界红线(20 项)

1. ❌ 改 `backend/app/` 任何文件
2. ❌ 改 `backend/alembic/` 任何 migration
3. ❌ 改 `backend/conftest.py` / `backend/pyproject.toml` / `backend/requirements.txt`
4. ❌ 改 `backend/tests/` 上述 3 个 file 之外的任何 test
5. ❌ 改 `frontend/` 任何文件
6. ❌ 改 `docs/T-1XXX_spec.md` 历史契约
7. ❌ 删除或修改远程 fix 引入的 `must_change_password` RBAC 检查逻辑
8. ❌ 删除或修改 `department_service` / `admin_reports_service` 的新 `tenant_id` 参数(签名是远程有意改动)
9. ❌ 给 service `tenant_id` 参数加默认值绕过新签名(必须显式传递)
10. ❌ 写新 helper / fixture(本任务最小改动:helper 内插 1 行 + 调用处加 kwarg)
11. ❌ 把 `must_change_password=False` 设为 model 默认值(模型层是 src 改动)
12. ❌ 修改 `User.__init__` 或加 `__post_init__`
13. ❌ 篡改 §3.1 / §3.2 / §3.3 字面量插入位置(必须在现有 `User(...)` 字段块末尾追加)
14. ❌ 动 4 既定 untracked 文件 + `.claude/` 项目级 ECC symlinks
15. ❌ 自动 `git push`(留给指挥官决策)
16. ❌ 自启 T-1102 / T-11XX 任何后续任务
17. ❌ revert `8459a5b` / `b5e77c3` / `c9693a9` 任何 commit
18. ❌ 在 feat / chore commit 之外打额外提交
19. ❌ 用 `sed` / 一刀切批量 replace(必须 Read + 精确 Edit 每处)
20. ❌ 在 commit message 中省略 `Worker timestamp:` 行

---

## §7 commit message 序列(逐条字面量)

**Commit 1**(fix,改 3 个 test files):

```
fix(tests): T-1101 restore baseline — pass tenant_id and must_change_password=False

[完整 body 见 §4 Step 5]

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

**Commit 2**(chore,改 `dev_tasks.md`):

```
chore(progress): close T-1101 — Phase 11 测试基线回归修复完工

[完整 body 见 §4 Step 6]

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

---

## §8 验收清单(指挥官二次验收用,17 项)

| # | 项 | 通过条件 |
|---|---|---|
| 1 | commit 链路 | HEAD 在 `c9693a9` 之后 = 2 个 commit(fix + chore) |
| 2 | fix commit 改动文件 | 严格 = `backend/tests/test_phase10_dept_group.py` + `backend/tests/test_kpi_phase9.py` + `backend/tests/test_me_deletions.py`,**不含**其他 |
| 3 | chore commit 改动文件 | 严格 = `docs/dev_tasks.md`,**不含**其他 |
| 4 | 零 src 改动 | `git diff <fix>^..<fix> -- backend/app/ backend/alembic/ frontend/` 完全空 |
| 5 | `_make_user` helper(test_phase10_dept_group.py) | grep `must_change_password=False` 在 `_make_user` 函数体内 |
| 6 | `_make_user` helper(test_kpi_phase9.py) | 同上 |
| 7 | `User(...)` inline(test_me_deletions.py) | grep `must_change_password=False` 在所有 `User(...)` 构造点 |
| 8 | service call 加 `tenant_id`(test_phase10_dept_group.py) | grep `list_departments(.*tenant_id` / `delete_department(.*tenant_id` / `get_department_with_members(.*tenant_id` / `group_reports_by_department(.*tenant_id` / `group_reports_by_project(.*tenant_id` 全部命中 |
| 9 | `ruff check .` | All passed |
| 10 | `mypy` 3 个 test file | 0 error |
| 11 | **`pytest -q` 通过** | `26 failed → 0 failed`,`152 passed → ≥178 passed`,`2 skipped` 保留 |
| 12 | `alembic check` | No new upgrade operations |
| 13 | dev_tasks.md 加 Phase 11 章节 | grep `# Phase 11: 测试基线回归修复` 命中 1 处 |
| 14 | Task 1 (T-1101) 状态 | `[ ] → [x]`(chore commit 后) |
| 15 | 📣 锚点保留 + 追加 T-1101 完工标记 | grep `T-1101 完工` 在 📣 段命中 |
| 16 | Worker timestamp 双 commit | 两条 commit message 均含 `Worker timestamp:` 行 |
| 17 | 4 既定 untracked + `.claude/` 保留 | `git status --short \| grep "^??" \| wc -l` = 4 |

**全 17 项 PASS** → 验收通过 → Phase 11 首任 Task 收口。

---

## §9 风险与回滚

### 风险

1. **测试 helper 与 fixture 命名差异**(中度):若 `test_me_deletions.py` 不是 inline 而是 fixture/helper,Codex 需精确定位实际 user 构造点。
   - 缓解:Codex 在 §4 Step 3 用 grep 探针先确认 user 构造点全集。
2. **service call 调用点遗漏**(中度):若 grep 不全(例如 typo `list_departments(`),可能漏处导致 pytest 仍失败。
   - 缓解:Codex 跑 pytest 后逐失败 case 看 traceback,补漏。
3. **`must_change_password=False` 影响业务逻辑**(低度):本任务仅在测试 user 构造时加,不影响生产 user 默认值(模型层 `default=True`)。
   - 缓解:严禁改 model(§6 #11)。
4. **`tenant_id=TENANT_ID` 与 actor.tenant_id 不一致**(低度):测试 user 用 `TENANT_ID = "default"`,刚好对齐 service 期望。
   - 缓解:不要乱改 `TENANT_ID` 常量值。

### 回滚

- **fix commit 回滚**:`git revert <fix-sha>` —— 单文件回滚 3 个 test 改动。
- **chore commit 回滚**:`git revert <chore-sha>` —— 回滚 dev_tasks.md。
- 零 src 改动,回滚不影响 backend src 代码。

---

## §10 📣 给 Worker (Codex) 的物理交接单

> **指挥官签字时间戳**:`[2026-05-28 15:27:00]`
> **持牌任务**:**T-1101**(Phase 11 **首任** — 测试基线回归修复,**零 src 改动**)

- **执行入口**:**必须读完整** `docs/T-1101_spec.md`(本文件 ~450 行,10 章 + 📣 附录)。**必须**在改动前跑 4 个前置探针,核验 HEAD = `c9693a9`,工作树干净,4 既定 untracked + `.claude/` 保留。

- **核心动作**(2 commit / 4 文件 = 3 tests + 1 dev_tasks):

  **Commit 1 (fix)** — `fix(tests): T-1101 restore baseline — pass tenant_id and must_change_password=False`:
  1. **改** `backend/tests/test_phase10_dept_group.py`:
     - **L76-99 `_make_user` helper** 在 `User(...)` 字段末尾插入 `must_change_password=False,`(§3.1.1 字面量)。
     - **12 处 service call**(grep `list_departments\|delete_department\|get_department_with_members\|group_reports_by_department\|group_reports_by_project`)逐处加 `tenant_id=TENANT_ID` 关键字参数(§3.1.2)。
  2. **改** `backend/tests/test_kpi_phase9.py`:
     - **L147+ `_make_user` helper** 在 `User(...)` 字段末尾插入 `must_change_password=False,`(§3.2.1)。
  3. **改** `backend/tests/test_me_deletions.py`:
     - **L25+ inline `User(...)`**(可能多处,grep `User(` 全找出来)每处末尾插入 `must_change_password=False,`(§3.3.1)。

  **Commit 2 (chore)** — `chore(progress): close T-1101 — Phase 11 测试基线回归修复完工`:
  4. **改** `docs/dev_tasks.md`:
     - **§3.4.1 / 3.4.2**:在 L194 `## 📣 恢复执行指令` **之前**插入 Phase 11 章节字面量(§3.4.1),Task 1 `[ ]` → `[x]`。
     - **§3.4.3**:保留现有「Phase 10 已闭环」终态文字,在 📣 锚点**末尾追加** T-1101 完工时间戳标记(§3.4.3)。

- **严禁项**(违反立即驳回,详见 §6 完整 20 项):
  - **严禁**改 `backend/app/` / `backend/alembic/` / `frontend/` 任何文件(远程 fix 是有意改动,不要回滚)。
  - **严禁**改 `must_change_password` RBAC 检查 / `tenant_id` service 签名(本任务仅修测试基线)。
  - **严禁**给 service `tenant_id` 加默认值绕过新签名。
  - **严禁**在 model 层把 `must_change_password` 改为 `default=False`(model 是 src)。
  - **严禁** sed 一刀切批量 replace(必须 Read + 精确 Edit 每处)。
  - **严禁**改其他 `tests/test_*.py` 文件(§2 白名单严格 3 文件)。
  - **严禁**动 4 既定 untracked + `.claude/` 项目级 ECC symlinks。
  - **严禁** `git push`(留给指挥官决策)。
  - **严禁**自启 T-1102 / T-11XX 任何后续任务。
  - **严禁** revert `8459a5b` / `b5e77c3` / `c9693a9` 任何 commit。
  - **严禁**在两条 commit message 中遗漏 `Worker timestamp:` 行。

- **闸门**(全绿才提交,详见 §5):
  ```bash
  cd backend
  .venv/bin/ruff check .
  .venv/bin/mypy tests/test_phase10_dept_group.py tests/test_kpi_phase9.py tests/test_me_deletions.py
  .venv/bin/pytest -q   # 0 failed, ≥178 passed, 2 skipped
  .venv/bin/alembic check
  ```

  改动面校验:
  ```bash
  git diff <fix-sha>^..<fix-sha> -- backend/app/ backend/alembic/ frontend/  # 必须空
  ```

- **完工提交序列**(2 commit,顺序锁定):
  1. `fix(tests): T-1101 restore baseline — pass tenant_id and must_change_password=False` —— **3 文件**(`test_phase10_dept_group.py` + `test_kpi_phase9.py` + `test_me_deletions.py`)。
  2. `chore(progress): close T-1101 — Phase 11 测试基线回归修复完工` —— **1 文件**(`dev_tasks.md`)。

  两条 commit message 都**必须**包含 multi-line body(对比 T-1005/T-1007 风格)+ 末尾 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 行。

- **时间戳纪律**:所有 commit message 末尾、终端汇报、`dev_tasks.md` 段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。

- **完工后**:立即停手汇报「T-1101 完工,pytest 26 failed → 0 failed,等待指挥官二次验收 + Phase 11 后续 task 起草」。**绝对不要**自启 T-1102。**绝对不要** `git push`。
