# T-908 执行契约 —— Phase 9 metric 枚举漂移修复

> 类型: **Worker (Codex) 任务卡** · 唯一持牌任务
> 上游: T-907(Phase 9 文档收尾 + 后端测试补全)已交付并通过指挥官最终验收(commit `9529295` / `169dcec` / `83550a9`)
> 目的: 修复 Phase 9 验收时发现的**前后端 metric 枚举命名漂移**,让同一份 Phase 9 PR 在 push 前完全自洽 —— 后端 ORM/migration `sprint_completion` → `objective_completion`,与前端 T-905/T-906 已 ship 的命名对齐
> 性质: **Bug 修复**,出处由指挥官在 T-905_spec 中起草前端契约时引入(指挥官承担),Codex 在 T-905/T-906 严格按契约执行,无责

---

## §1 任务定义

T-908 是 Phase 9 的**修补任务**,**不引入新功能**,只做一件事:**统一前后端 KPI metric 枚举命名**。

漂移现状:

| 层 | 当前 metric 集合 |
|---|---|
| 后端 ORM `KpiMetric` (`app/models/kpi_target.py:35`) | `submit_rate / avg_score / sprint_completion / blocker_resolve_days` |
| 后端 Pydantic schema docstring (`app/schemas/kpi.py:7`) | 同上 |
| 后端 PostgreSQL `kpi_metric` ENUM 类型(由首条 migration 建立) | 同上 |
| 后端 seed 数据(`alembic/versions/..._1234_phase9_add_kpi_targets.py:127`) | 含 1 行 `sprint_completion` |
| **前端** type `KpiMetric` (`frontend/src/api/kpi.ts:14`) | `submit_rate / avg_score / blocker_resolve_days / objective_completion` |
| 前端 admin/kpi 表单选项 (`frontend/src/app/admin/kpi/page.tsx:38`) | 含 `objective_completion`(OKR 完成率) |
| 前端 dashboard 指标标签 (`frontend/src/components/dashboard/kpi-achievement-panel.tsx:40`) | 同上 |

可观察的用户面 bug:

1. 在 `/admin/kpi` 选「OKR 完成率」并 POST 提交 → 后端 Pydantic 校验失败 → **HTTP 422**(因为 `objective_completion` 不在后端 enum)。
2. 后端 seed 的 `sprint_completion` 行在 dashboard 渲染时,前端 `METRIC_LABELS[row.metric]` 查表落空 → 指标名渲染为**空字符串**(不会崩,但用户体验残缺)。

修复策略:**改后端**(单点)而非改前端(三处)—— 前端已经 ship,且 `objective_completion` 对齐 OKR 模块语义更优。

---

## §2 修复策略 —— 后端 `sprint_completion` → `objective_completion`

### §2.1 为什么改后端而非前端

| 选项 | 改动面 | 评估 |
|---|---|---|
| **A. 改后端**(本契约选定) | 1 个 ORM 文件 + 1 个 schema docstring + 1 条新 alembic migration | **✓** 单点,DDL 原子,seed 自动同步 |
| B. 改前端回 sprint_completion | 3 个前端文件 + 修 T-905/T-906 历史契约文档 + 失去 OKR 语义对齐 | 改动面更大,且要回退 contract 历史 |

### §2.2 PostgreSQL ENUM 重命名机制

后端 `kpi_metric` 是 PG **native ENUM type**,可用单条 DDL 原子重命名:

```sql
ALTER TYPE kpi_metric RENAME VALUE 'sprint_completion' TO 'objective_completion';
```

- PG 9.1+ 支持 RENAME VALUE,本项目 PG 16.13 ✓
- **自动同步现有数据**:enum value 是 OID 引用,RENAME 是元数据级修改,所有 `kpi_targets.metric = 'sprint_completion'` 的行**自动**变成 `objective_completion`,**无需 UPDATE 数据**
- RENAME 是 transactional,可以在 alembic migration 默认事务里运行
- downgrade 反向 RENAME,可重复

---

## §3 改动清单

### §3.1 新建 Alembic migration

文件路径(自行用当前时间生成 HHMM): `backend/alembic/versions/20260527_<HHMM>_phase9_rename_metric_objective_completion.py`

**关键**:
- `Revises = "b4f6a8d2c9e1"`(当前 alembic head,即 T-901-FIX),**不要硬编码上一个 revision id 之外的值**,先 `cd backend && .venv/bin/alembic heads` 复核
- `upgrade()`:
  ```python
  op.execute("ALTER TYPE kpi_metric RENAME VALUE 'sprint_completion' TO 'objective_completion'")
  ```
- `downgrade()`:
  ```python
  op.execute("ALTER TYPE kpi_metric RENAME VALUE 'objective_completion' TO 'sprint_completion'")
  ```
- docstring 顶部按本仓库模板(参见 `20260527_1317_phase9_fix_kpi_targets_unique_nulls.py` 的格式)写背景 / 变更 / 实现说明 / Revision ID / Revises / Create Date。**不要保留模板 docstring 占位**,否则 pre-commit hook 拒绝。

### §3.2 修改 ORM

`backend/app/models/kpi_target.py:35`:

```diff
 class KpiMetric(str, enum.Enum):
     submit_rate = "submit_rate"
     avg_score = "avg_score"
-    sprint_completion = "sprint_completion"
+    objective_completion = "objective_completion"
     blocker_resolve_days = "blocker_resolve_days"
```

### §3.3 修改 Pydantic schema docstring

`backend/app/schemas/kpi.py:7`:

```diff
-  - metric ∈ {submit_rate, avg_score, sprint_completion, blocker_resolve_days}
+  - metric ∈ {submit_rate, avg_score, blocker_resolve_days, objective_completion}
```

### §3.4 修改 plan §9「实际落地路径(Phase 9)」段

`docs/implementation-plan.md` 第 `### 实际落地路径(Phase 9)` 子节里 `metric 枚举` 那一行:

```diff
-| metric 枚举 | `submit_rate / avg_score / sprint_completion / blocker_resolve_days` | 后端 DB/ORM 当前仍为 `submit_rate / avg_score / sprint_completion / blocker_resolve_days`;T-905/T-906 前端契约已使用 `objective_completion` 展示 | T-907 勘察发现前后端命名漂移;本任务按契约只补文档与测试,不改 src |
+| metric 枚举 | `submit_rate / avg_score / sprint_completion / blocker_resolve_days` | `submit_rate / avg_score / blocker_resolve_days / objective_completion`(T-908 已统一) | T-907 勘察出前后端漂移,T-908 通过 `ALTER TYPE kpi_metric RENAME VALUE` 单条 DDL 修正,枚举名对齐 OKR 模块语义 |
```

同时把 §「actual_value 数据源」段:

```diff
-- `sprint_completion` / `blocker_resolve_days` → 暂无聚合源,固定返回 `no_data`(后续 KPI/OKR 聚合阶段实现)
-- 前端 T-905/T-906 当前以 `objective_completion` 文案展示 OKR 完成率;后端仍使用 `sprint_completion`,需要后续专项统一命名
+- `objective_completion` / `blocker_resolve_days` → 暂无聚合源,固定返回 `no_data`(后续 KPI/OKR 聚合阶段实现)
```

### §3.5 修改 `docs/recap.md`

在「最新进度摘要」段尾追加 1 条 Task 8 bullet:

```markdown
- **Phase 9 Task 8 (T-908)**: 修 metric 枚举漂移,后端 ORM/PG ENUM `sprint_completion` → `objective_completion`(单条 `ALTER TYPE RENAME VALUE` DDL 原子重命名 + seed 自动同步),前后端命名统一。Phase 9 PR 已自洽。
```

在「历史移交记录」段顶部插入 1 条:

```markdown
- [2026-05-27] Phase 9 Task 8 (T-908) 完成:后端 KpiMetric `sprint_completion` → `objective_completion`,前后端枚举对齐,Phase 9 PR 闭环可推送。
```

### §3.6 修改 `docs/dev_tasks.md`

在「文档与收尾」之后**新增**「### 漂移修复 (Drift Fixes)」段(或追加在 Task 7 之后,题型自洽即可),内容:

```markdown
### 漂移修复 (Drift Fixes)
- [/] **Task 8 (T-908): 修 metric 枚举漂移 (In Progress by Codex)**
  - 出处:T-907 验收时勘察发现 —— 后端 ORM/migration `sprint_completion` 与前端 T-905/T-906 已 ship 的 `objective_completion` 命名不一致,导致前端 POST OKR 完成率会被后端 422,后端 seed `sprint_completion` 行在 dashboard 显示时指标名空白。
  - 修复:新增 alembic migration `ALTER TYPE kpi_metric RENAME VALUE 'sprint_completion' TO 'objective_completion'`(PG native enum 原子重命名,seed 自动同步),同步 ORM `KpiMetric` enum 与 Pydantic schema docstring。
  - **完整执行契约见 `docs/T-908_spec.md`**(必读)。
```

完工时改为 `[x]`。

---

## §4 不要做的事(红线)

1. **不要改任何前端文件** —— 前端 `api/kpi.ts` / `admin/kpi/page.tsx` / `kpi-achievement-panel.tsx` 已经是目标命名,T-908 是后端单边修复。
2. **不要改历史 alembic migration**(`20260527_1234_phase9_add_kpi_targets.py` / `..._1317_phase9_fix_kpi_targets_unique_nulls.py`)—— 即使 docstring 注释里有 `sprint_completion` 也**保留**作为历史记录;Alembic 历史 migration 是 schema 真相源,改了会破哈希追踪与 `alembic check` 一致性。
3. **不要 UPDATE seed 数据** —— `ALTER TYPE RENAME VALUE` 自动同步,如果你自己写 UPDATE 会因为 enum 不再有 `sprint_completion` 值而失败。
4. **不要碰 `backend/uv.lock`** —— 继续保持 untracked。
5. **不要改 service 逻辑** —— `kpi_service.py` 的 `if target.metric not in (KpiMetric.submit_rate, KpiMetric.avg_score)` 走 no_data 分支,T-908 后 `objective_completion` 也继续走 no_data,不需要补 actual_value 计算。这是 Phase 11+ 才做的。
6. **不要改测试代码** —— 现有 12 个测试**不引用** `sprint_completion`,T-908 不需要补新测试。`pytest tests/test_kpi_phase9.py -v` 应自动仍 12 passed。
7. **不要自动 `git push`** —— 完工后由指挥官最终 sign-off 后统一推送 Phase 9 全部 commit。
8. **不要硬编码 down_revision** —— 必须 `cd backend && .venv/bin/alembic heads` 输出后,把 head id 抄到新 migration 的 `down_revision`。

---

## §5 闸门(提交前 must 全绿)

### §5.1 Alembic 三件套

```bash
cd backend
.venv/bin/alembic upgrade head           # 应执行新 migration,无 error
.venv/bin/alembic downgrade -1           # 反向 RENAME,无 error
.venv/bin/alembic upgrade head           # 再正向,无 error
.venv/bin/alembic check                  # 应 "No new upgrade operations detected." 之类的全绿信息
```

### §5.2 测试

```bash
cd backend
.venv/bin/pytest tests/test_kpi_phase9.py -v     # 必须 12 passed(测试不引用 sprint_completion,应零变化)
.venv/bin/pytest tests/                          # 防回归全套,应 160 passed + 2 skipped
```

### §5.3 静态检查

```bash
cd backend
.venv/bin/ruff check .
.venv/bin/mypy app/models/kpi_target.py app/services/kpi_service.py app/routers/kpi.py
```

### §5.4 前端无破坏验证(只跑 lint+typecheck,不需要 build)

```bash
cd frontend
npm run lint
npm run typecheck
```

(前端没动文件,但跑一遍确认无破。)

### §5.5 真机最小验证(可选,但强烈建议)

启动 backend + frontend production server,用 admin 账号:

1. `curl -X POST .../api/v1/admin/kpi/ -d '{"scope":"department","scope_value":"研发部","metric":"objective_completion","target_value":85,"period":"monthly"}'` → **应 200** 不再 422
2. `curl .../api/v1/admin/kpi/achievement?period=monthly` → seed `sprint_completion` 行应该不再出现,改为 `objective_completion`(因为 enum RENAME 自动同步)
3. 浏览器看 `/dashboard` KPI 面板 → 「OKR 完成率」指标名应正确显示

---

## §6 完工提交序列(原子 3 commit)

```bash
# 第 1 个: 修复(model + schema + 新 migration)
git add backend/app/models/kpi_target.py backend/app/schemas/kpi.py backend/alembic/versions/20260527_<HHMM>_phase9_rename_metric_objective_completion.py
git commit -m "fix(kpi): rename metric sprint_completion to objective_completion"

# 第 2 个: 文档同步(plan §9 + recap.md)
git add docs/implementation-plan.md docs/recap.md
git commit -m "docs(kpi): mark Phase 9 metric drift resolved by T-908"

# 第 3 个: 收口(dev_tasks Task 8 → [x])
git add docs/dev_tasks.md
git commit -m "chore(progress): close T-908 + Phase 9 PR ready"
```

---

## §7 风险与坑(实战经验)

1. **`ALTER TYPE ... RENAME VALUE` 兼容性**: PG 9.1+ 支持,本项目 PG 16.13 ✓。如果跑在 PG < 9.1 环境会失败,但本项目 README 已锁 PG 16,无虞。
2. **事务包裹**: PG RENAME VALUE 是 transactional,可以在 alembic 默认事务里运行,**不需要** `op.execute_isolation_level` 或 AUTOCOMMIT 处理。这与 `ALTER TYPE ... ADD VALUE`(PG 12+ 才能在事务内运行)不同。
3. **seed 数据自动同步**: enum value 是 OID 引用,RENAME 是元数据级操作,**不要**写 `UPDATE kpi_targets SET metric = 'objective_completion' WHERE metric = 'sprint_completion'`,RENAME 之后 `'sprint_completion'` 字面量在 enum 里已经不存在,UPDATE 会因为 enum cast 失败。
4. **`alembic check`**: 因 ORM 与 PG schema 同步重命名,check 应通过;如果出现 "value '...' of enum '...' is not in schema" 错误,检查 ORM 文件改对了没。
5. **Python Enum vs PG ENUM 顺序**: PG enum 内部有顺序(由声明顺序决定),`ALTER TYPE RENAME VALUE` **保持原位置**,不会重排;ORM 这边 Python Enum 顺序也最好同步保持(改名但位置不动)。
6. **测试 fixture 缓存**: pytest 每次 collection fresh import,session-scope fixture 在测试运行间会重建,无需特殊处理。
7. **新 migration revision id**: 不要复用 `c7a9f1e2d4b6` 或 `b4f6a8d2c9e1`,自己生成新的(8 字符随机十六进制,如 `e3a5b1c9f4d2`),格式参考已有两条 migration。
8. **历史 migration docstring 里 `sprint_completion` 字面量保留**: `20260527_1234_phase9_add_kpi_targets.py:5/42/127` 的字面量是**历史事实**,Phase 9 第一版确实建表为 sprint_completion;不要修改,保留作为审计轨迹。`alembic upgrade` 是顺序执行,会先建 enum `sprint_completion`,再 T-908 migration RENAME 为 `objective_completion`,最终态正确。
9. **pre-commit hook**: 本仓库有 hook 拒绝 "Alembic 迁移保留模板 docstring 占位",新 migration 一定写实际背景/变更/实现说明,不要留默认 placeholder。
10. **前端不需要任何改动验证**: 前端只跑 `npm run lint && npm run typecheck`,**不需要**重新 build —— 前端代码字面量没变。

---

## §8 完工后停手位

T-908 完工后:

1. 3 个原子 commit 落盘(见 §6)。
2. 修改 `docs/dev_tasks.md` Task 8 → `[x]`。
3. **立即停手**,等指挥官最终验收 + Phase 9 PR 整体 sign-off + 推送 51+ 个 commit 到 origin/main。
4. **不要**自动 `git push`。
5. **不要**开新 Phase。

T-908 是 Phase 9 PR push 前的**最后一份**契约,通过后 Phase 9 全部代码 + 文档 + 测试自洽,可统一推送。

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌,供 PM 探针自动提取**

- **当前持牌任务**: **T-908**(已自动锁定为 `[/]`)—— Phase 9 **修补任务**:统一前后端 KPI metric 枚举命名,改后端单边(ORM + Pydantic schema docstring + 新增 alembic migration `ALTER TYPE kpi_metric RENAME VALUE`),**不动前端、不动历史 migration、不动测试**。
- **执行入口**: 阅读 `docs/T-908_spec.md`,不要重复 `chore(lock)`,直接动手。先 `cd backend && .venv/bin/alembic heads` 拿当前 head id(应为 `b4f6a8d2c9e1`),抄到新 migration 的 `down_revision`。
- **核心动作**:
  1. **新建** `backend/alembic/versions/20260527_<HHMM>_phase9_rename_metric_objective_completion.py`:`upgrade()` 执行 `ALTER TYPE kpi_metric RENAME VALUE 'sprint_completion' TO 'objective_completion'`,`downgrade()` 反向 RENAME。Revises 指向当前 alembic head,**不要硬编码**。docstring 写实际背景,不留模板占位。
  2. **改** `backend/app/models/kpi_target.py:35` —— `sprint_completion = "sprint_completion"` → `objective_completion = "objective_completion"`。
  3. **改** `backend/app/schemas/kpi.py:7` docstring —— metric 集合改为 `{submit_rate, avg_score, blocker_resolve_days, objective_completion}`。
  4. **改** `docs/implementation-plan.md §9` 「实际落地路径(Phase 9)」段 —— metric 枚举行改成「已修(T-908)」,actual_value 数据源段把 `sprint_completion` 改成 `objective_completion`。详见 §3.4。
  5. **改** `docs/recap.md` —— 在「最新进度摘要」段尾追加 1 条 Task 8 bullet,在「历史移交记录」顶部插入 1 条 [2026-05-27] 时间戳。详见 §3.5。
  6. **改** `docs/dev_tasks.md` —— Task 8 从 `[/] In Progress` 改为 `[x]`(在最后一个 commit 一起 add)。
- **重要不要做**:
  - **不要**改 `frontend/` 任何文件(前端已经是目标命名)。
  - **不要**改历史 alembic migration `20260527_1234_phase9_add_kpi_targets.py` 与 `_1317_phase9_fix_kpi_targets_unique_nulls.py`,即使其中 docstring/字面量含 `sprint_completion`(历史事实保留)。
  - **不要**写 `UPDATE kpi_targets SET metric = ...`,enum RENAME 自动同步,UPDATE 会失败。
  - **不要**改 `backend/app/services/kpi_service.py` —— `objective_completion` 继续走 no_data 分支,这是预期行为。
  - **不要**改测试 —— 现有 12 个测试不引用 `sprint_completion`,T-908 不补新测试。
  - **不要**碰 `backend/uv.lock`。
  - **不要**自动 `git push`。
- **闸门**(都必须绿):
  ```bash
  cd backend
  .venv/bin/alembic upgrade head && .venv/bin/alembic downgrade -1 && .venv/bin/alembic upgrade head && .venv/bin/alembic check
  .venv/bin/pytest tests/test_kpi_phase9.py -v                 # 必须 12 passed
  .venv/bin/pytest tests/                                       # 必须 160 passed + 2 skipped
  .venv/bin/ruff check .
  .venv/bin/mypy app/models/kpi_target.py app/services/kpi_service.py app/routers/kpi.py
  cd ../frontend
  npm run lint && npm run typecheck                             # 前端无破坏验证
  ```
- **完工提交序列**(原子 3 commit,**顺序不可乱**):
  1. `fix(kpi): rename metric sprint_completion to objective_completion`(只含 `backend/app/models/kpi_target.py` + `backend/app/schemas/kpi.py` + 新 alembic migration 文件)
  2. `docs(kpi): mark Phase 9 metric drift resolved by T-908`(只含 `docs/implementation-plan.md` + `docs/recap.md`)
  3. `chore(progress): close T-908 + Phase 9 PR ready`(只含 `docs/dev_tasks.md`,Task 8 → `[x]`)
- **完工后**: 立即停手,等指挥官最终验收 + Phase 9 PR 整体 sign-off + 统一推送 51+ commit。T-908 是 Phase 9 PR push 前**最后一份**契约。
