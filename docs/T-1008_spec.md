# T-1008 实施契约:Phase 10 文档收尾

> **指挥官签字时间戳**:`[2026-05-28 09:10:00]`
> **持牌任务**:Phase 10 最终任务 — 文档收尾
> **范围**:**纯文档操作**,**零代码**改动(backend / frontend / alembic / tests / scripts 全冻结)
> **前置依赖**:T-1001 ~ T-1007 全部 `[x]` 已闭环;HEAD = `1ea45a4`;Phase 10 全功能代码就绪。

---

## §1 任务概述

Phase 10 七任务(T-1001 ~ T-1007 + T-1006-FIX 复议)代码 / 测试 / 前端全部闭环。本任务(T-1008)为 Phase 10 **最终收口**,只做两件事:

1. **`docs/implementation-plan.md` §10** 末尾(L817 「待补齐清单」末行之后 / L819 `---` 之前)追加一节「实际落地路径(Phase 10 实施)」,记录 T-1001 勘察发现的 6 维度从 `3 ❌ + 3 部分 ✅` → `6 ✅` 的实际变化、关键 commit 引用、实际对外 API/前端路径表 + Phase 11 候选方向。
2. **`docs/recap.md`** 更新三处:
   - **L4**:把原 T-1001 单行摘要替换为 Phase 10 八任务的结构化摘要(对齐 L15-22 Phase 9 Task 1~8 的写法)。
   - **L6**:`当前阶段:Phase 10(勘察先行轮)` → `当前阶段:Phase 11 候选(Phase 10 已闭环,T-1001 ~ T-1008 八任务全收口)`。
   - **L25 之前**:插入 Phase 10 完工 8 条「历史移交记录」(7 个 task entries + 1 个 Commander 闭环总结)。

完工后 Phase 10 **正式收口**,留待指挥官启动 Phase 11 候选规划。

---

## §2 文件范围锁定(严格 2 文件,白名单)

```
+ docs/implementation-plan.md   # 仅在 L817 之后 / L819 之前追加,严禁改 L1-817 已有内容
+ docs/recap.md                 # L4 替换 + L6 替换 + L25 之前插入,严禁改其他行
+ docs/dev_tasks.md             # 单点修改:Task 8 行首 `[ ]` → `[x]`(由 chore(progress) 触发)
```

**严禁清单**(改动一律驳回):

- ❌ 改任何 `backend/` 下文件(`app/` / `tests/` / `alembic/` / `scripts/` / `conftest.py` 全冻结)
- ❌ 改任何 `frontend/` 下文件
- ❌ 改 `docs/implementation-plan.md` L1-817 已有内容(只能在指定锚点之后追加)
- ❌ 改 `docs/recap.md` L7-23 / L26-end(只能动 L4 / L6 / 在 L25 之前插入)
- ❌ 改 `docs/T-1001_spec.md` ~ `docs/T-1007_spec.md` 任意一份(历史契约保留不动)
- ❌ 动 4 既定 untracked 文件(`.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` / `backend/uv.lock`)
- ❌ 自动 `git push`
- ❌ 自启 Phase 11 任何任务

---

## §3 详细文件改动(字面量锁定)

### §3.1 `docs/implementation-plan.md` 追加段(字面量,**复制粘贴**插入)

**插入位置**:L817(`- 前端总经理看板的全员 / 按部门 / 按项目 Tabs 切换器尚未落地。`)之后 + L819(`---`)之前。**不要**改 L786-817 已有的「实际落地路径(Phase 10 勘察)」段,**只追加**新段。

**字面量(逐字符锁定,空行也对齐)**:

```markdown
### 实际落地路径(Phase 10 实施)

T-1001 勘察结论(上文)指出 §10 原文 6 维度中 3 个 ❌ + 3 个部分 ✅。经 T-1002 ~ T-1007 七轮实施(七个 PR commit 链),全部 6 维度收敛为 ✅。落地映射如下:

| 维度 | T-1001 勘察 | Phase 10 实施 | 关键 commit | 落地状态 |
|------|------------|--------------|------------|----------|
| 部门表 | ❌ 无独立表 | T-1003 新建 `backend/app/models/department.py` `Department(BaseMixin, Base)` + Alembic migration 建表 + 7 seed(技术部/生产部/采购部/财务部/商务部/销售部/仓储部) | `ad6643a` | ✅ |
| 部门字段(`User.department`) | 部分 ✅(字符串字段,非 FK) | T-1003 增量并存:`User.department: VARCHAR(64)` 保留 + 新建 `Department` 独立表;FK 迁移延后 Phase 11+(本阶段双轨在线) | `ad6643a` | ✅(双轨) |
| 项目成员关联 | 部分 ✅(缺 UNIQUE) | T-1002 `ProjectMember.__table_args__` 添加 partial unique index `(project_id, user_id) WHERE left_at IS NULL`,软删除友好(允许员工离开后重新加入) | `6e2b94a` | ✅ |
| 项目路由(`group_by=project`) | 部分 ✅(无对外 group_by query) | T-1005 新建 `GET /api/v1/admin/reports?group_by=project&project_id=&start_date=&end_date=`,4 项聚合指标(`report_count` / `avg_score` / `pass_count` / `pass_rate`)+ inner join `Project` 剔除 NULL `project_id` | `02f3d58` | ✅ |
| 部门分组端点 | ❌ 无对外 group_by | T-1004 新建 `/api/v1/admin/departments/` 5 端点(GET list / POST 201 / GET `{id}/members` / PATCH `{id}` / DELETE `{id}` 204);T-1005 新建 `GET /api/v1/admin/reports?group_by=department` | `d8737d9` + `02f3d58` | ✅ |
| 前端 Tabs 切换器 | ❌ 无切换器 | T-1006 新建 `frontend/src/app/admin/departments/page.tsx`(表格 5 列 + Modal CRUD)+ 改造 `frontend/src/app/dashboard/page.tsx`(3 按钮 Tabs:`all` / `by_department` / `by_project` + `canSeeTabs` admin+manager 守卫)+ 改 `sidebar.tsx` 加 `Building2` 入口 | `72111e2` + `d169039` | ✅ |

**测试覆盖**(原 plan §10 未列入维度,但 V2.6 防回归基线要求):T-1007 新增 `backend/tests/test_phase10_dept_group.py` 18 case 三层(Model 3 + Service 5 + Router 10),后端 pytest 全量 `178 passed, 2 skipped`(从 Phase 9 收口 `160 passed` 准确 `+18 case` 零回归)。

实际对外 API 路径(Phase 10 新增,沿用 FastAPI router `prefix="/api/v1/admin/..."`):

| 方法 | 实际路径 | RBAC | 说明 |
|------|----------|------|------|
| GET | `/api/v1/admin/departments/` | admin+manager | 部门列表,按 `name asc` |
| POST | `/api/v1/admin/departments/` | admin+manager | 新建部门(201),名称冲突 409 `name_conflict` |
| GET | `/api/v1/admin/departments/{id}/members` | admin+manager | 部门成员反查(`User.department` 等值 + `is_active=True` 过滤) |
| PATCH | `/api/v1/admin/departments/{id}` | admin+manager | 部分更新,`manager_not_found` → 400 |
| DELETE | `/api/v1/admin/departments/{id}` | admin+manager | 硬删除(204) |
| GET | `/api/v1/admin/reports/?group_by=department\|project&project_id=&start_date=&end_date=` | admin+manager | 对外分组聚合,4 项指标,`start_date>end_date` → 400 |

前端落地路径(Phase 10 新增):

| 路径 / 入口 | 文件 | 说明 |
|------|------|------|
| `/admin/departments` | `frontend/src/app/admin/departments/page.tsx`(306 行) | 管理后台,表格 5 列 + Modal 新建/编辑 + 删除 confirm,RBAC `admin+manager` 守卫 |
| `/dashboard` Tabs 切换器 | `frontend/src/app/dashboard/page.tsx`(+92/-0 局部插入) | 3 按钮组 `all` / `by_department` / `by_project`,5 列分组表(部门 / 日报数 / 均分 / 通过数 / 通过率),admin+manager 可见;`viewMode === 'all'` 时现有 5 sections 行为 100% 不变 |
| Sidebar `/admin/departments` 入口 | `frontend/src/components/sidebar.tsx`(+2 行) | lucide-react `Building2` icon + `ADMIN_ITEMS` 入口插入 recycle-bin 之前 |

**Phase 10 闭环口径**:`implementation-plan.md` §10 原文 6 维度 100% 落地;`mv_daily_user_stats` / `mv_weekly_dept_stats` 物化视图未介入(本阶段直查 `daily_reports + users + projects`,精度优先,代价 = `group_by=department` 端点 P95 仍处单表聚合范围);Phase 11 候选方向 — ① `User.department` → `Department.id` FK 迁移(双轨融合);② 物化视图增量按部门聚合预热(将 `/api/v1/admin/reports?group_by=` P95 从 ms 级压到 sub-ms);③ 前端 Tabs `by_project` 视图加权重柱状图 + 趋势线;④ `Department.manager_id` 反查路径与 Phase 9 KPI `KpiScope=department` 打通(总经理在 KPI 面板直接钻取部门日报与达成率)。
```

**关键点**:此段是 §3.1 完整字面量,**插入即可,严禁改写**(包括表格列宽、空行数、emoji、commit 短哈希)。

### §3.2 `docs/recap.md` 三处修改(字面量锁定)

#### §3.2.1 L4 替换

**当前 L4**(单行,删除):
```
- [Phase 10] T-1001 §10 实物盘点 + plan 实际落地路径段落落盘(纯文档勘察,backend/frontend/tests 全冻结)
```

**替换为 8 行**(字面量,顺序锁定):
```
- **Phase 10 Task 1 (T-1001)**: 完成 §10 实物盘点(纯只读勘察)+ `docs/implementation-plan.md §10` 末尾「实际落地路径(Phase 10 勘察)」段落盘,6 维度对照(3 ❌ + 3 部分 ✅)。
- **Phase 10 Task 2 (T-1002)**: 完成 `ProjectMember.__table_args__` 补 partial UNIQUE index `(project_id, user_id) WHERE left_at IS NULL`,软删除友好(允许员工离开后重新加入)。
- **Phase 10 Task 3 (T-1003)**: 完成 `Department(BaseMixin, Base)` 独立表 + Alembic migration + 7 seed(技术部/生产部/采购部/财务部/商务部/销售部/仓储部),`User.department` VARCHAR 字段保留双轨在线。
- **Phase 10 Task 4 (T-1004)**: 完成 `/api/v1/admin/departments/` 5 端点(GET list / POST 201 / GET `{id}/members` / PATCH `{id}` / DELETE `{id}` 204),RBAC `admin+manager`,统一 `ValueError("not_found" / "name_conflict" / "manager_not_found")` 错误信号。
- **Phase 10 Task 5 (T-1005)**: 完成 `/api/v1/admin/reports?group_by=department|project` 对外分组聚合端点,4 项指标(`report_count` / `avg_score` / `pass_count` / `pass_rate`)+ inner join `Project` 剔除 NULL `project_id`,`start_date>end_date` → 400。
- **Phase 10 Task 6 (T-1006 + T-1006-FIX)**: 完成前端 `/admin/departments` 管理页(表格 5 列 + Modal CRUD)+ `/dashboard` 3 按钮 Tabs 切换器(`all` / `by_department` / `by_project`)+ sidebar `Building2` 入口;UUID_REGEX `8-4-4-4-12` 五段,单行复议闭环(三次验收通过)。
- **Phase 10 Task 7 (T-1007)**: 完成 `backend/tests/test_phase10_dept_group.py` 18 case 三层测试(Model 3 + Service 5 + Router 10),后端 pytest `178 passed, 2 skipped` 零回归。
- **Phase 10 Task 8 (T-1008)**: 完成文档收尾 — `docs/implementation-plan.md §10` 末尾追加「实际落地路径(Phase 10 实施)」段记录 6 维度从 ❌/部分 ✅ → ✅ 的变化 + `docs/recap.md` 当前阶段切换至 Phase 11 候选 + Phase 10 全 task 历史移交记录落盘。
```

#### §3.2.2 L6 替换

**当前 L6**(删除):
```
- 当前阶段:Phase 10(勘察先行轮)
```

**替换为**:
```
- 当前阶段:Phase 11 候选(Phase 10 已闭环,T-1001 ~ T-1008 八任务全收口)
```

#### §3.2.3 历史移交记录段(L25 之前插入 8 条)

**当前 L25**(保持不动,作为锚定):
```
- [2026-05-27 by Commander] Phase 10 启动 — Phase 9 KPI 已 push origin/main(`0b2a150`),Phase 10 不擅自臆造任务,改派 T-1001 勘察先行,落盘 plan §10 实际落地路径表后再起草后续 task。
```

**在 L25 之前(即「## 历史移交记录」标题行之后,L25 这一行之前)按倒序时间插入 8 行**(2026-05-28 在最上,2026-05-27 紧跟,日期内按 task 序号倒序):

```
- [2026-05-28 by Commander] Phase 10 闭环 — `implementation-plan.md` §10 原文 6 维度从 `3 ❌ + 3 部分 ✅` 全部落地为 `6 ✅`;T-1001~T-1008 八任务 33+ commit(含 T-1006-FIX 单行复议)零冗余、零回归;Phase 11 候选方向 — `User.department` → FK 迁移 / 物化视图增量按部门聚合 / Tabs `by_project` 加权重柱状图 / `Department.manager_id` 与 KPI scope 打通。
- [2026-05-28] Phase 10 Task 8 (T-1008) 完成:`implementation-plan.md §10` 末尾「实际落地路径(Phase 10 实施)」段 + `recap.md` 当前阶段切换至 Phase 11 候选 + Phase 10 全 task 历史移交记录落盘。
- [2026-05-28] Phase 10 Task 6 (T-1006 + T-1006-FIX) 完成:前端 `/admin/departments` 管理页 + `/dashboard` 3 按钮 Tabs 切换器 + sidebar `Building2` 入口;UUID_REGEX 8-4-4-4-12 五段单行复议闭环(三次验收通过)。
- [2026-05-27] Phase 10 Task 7 (T-1007) 完成:`backend/tests/test_phase10_dept_group.py` 18 case 三层测试,pytest `178 passed, 2 skipped` 零回归。
- [2026-05-27] Phase 10 Task 5 (T-1005) 完成:`/api/v1/admin/reports?group_by=department|project` 对外分组聚合端点,4 项指标 + inner join 剔除 NULL project_id。
- [2026-05-27] Phase 10 Task 4 (T-1004) 完成:`/api/v1/admin/departments/` 5 端点(CRUD + members 反查),RBAC admin+manager,统一 ValueError 错误信号。
- [2026-05-27] Phase 10 Task 3 (T-1003) 完成:`Department` 独立表 + ORM + Alembic migration + 7 seed(技术部/生产部/采购部/财务部/商务部/销售部/仓储部)。
- [2026-05-27] Phase 10 Task 2 (T-1002) 完成:`ProjectMember` partial UNIQUE index `(project_id, user_id) WHERE left_at IS NULL` 补丁,软删除友好。
- [2026-05-27] Phase 10 Task 1 (T-1001) 完成:§10 实物盘点 + `implementation-plan.md §10` 末尾「实际落地路径(Phase 10 勘察)」段落盘(纯文档勘察,backend/frontend/tests 全冻结)。
```

**注**:Task 2 完工日期严格沿用 `6e2b94a` commit author date(`git log -1 --format=%ai 6e2b94a` 可验证),其余日期参照各自 commit timestamps;插入后 L25 原 Phase 10 启动条不动,在视觉上 Phase 10 闭环条与启动条形成首尾呼应。

### §3.3 `docs/dev_tasks.md` 单点修改

**位置**:L167(`- [ ] **Task 8 (T-1008): 文档收尾**`)

**修改**:`[ ]` → `[x]`,保留缩进、emoji、子 bullet 等所有其他内容。

**配合**:与 `chore(progress): close T-1008` commit 一起 `git add`,**不**在 feat commit 中提交。

### §3.4 📣 锚点替换(`docs/dev_tasks.md` L194-end)

**当前**:L194-232 是 `T-1006-FIX` 持牌发牌段。

**T-1008 完工时**:整段替换为「Phase 10 已闭环,所有任务收口」终态文字,**不**留任何持牌任务,等待指挥官在 Phase 11 启动时重新发牌。

**字面量锁定**:

```markdown
## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌,供 PM 探针自动提取**
> **更新时间戳**: `[2026-05-28 待 Worker 填实际完工时间戳]`(指挥官 Phase 10 闭环 — T-1008 文档收尾完工,**当前无持牌任务**)

- **当前持牌任务**: **无** —— Phase 10(T-1001 ~ T-1008 共 8 任务)已**全数 `[x]` 闭环**,代码 / 测试 / 文档三轴全收口。HEAD 待 Worker T-1008 完工后 push origin/main 决策由指挥官单独决断。

- **下一步**: **停手待命,等待指挥官启动 Phase 11 规划**。Phase 11 候选方向:
  - ① `User.department` VARCHAR 字段 → `Department.id` FK 迁移(双轨融合,清理 Phase 10 增量并存)。
  - ② 物化视图增量按部门聚合预热(将 `/api/v1/admin/reports?group_by=` P95 从 ms 级压到 sub-ms,复用 Phase 7 `mv_daily_user_stats / mv_weekly_dept_stats` 模式)。
  - ③ 前端 Tabs `by_project` 视图加权重柱状图 + 趋势线(复用 Phase 7 Recharts `CompareBarChart / TrendLineChart` 组件)。
  - ④ `Department.manager_id` 反查路径与 Phase 9 KPI `KpiScope=department` 打通(总经理在 KPI 面板直接钻取部门日报与达成率)。

- **严禁项**(等待指挥官 Phase 11 发牌前):
  - **严禁** Worker 自启 Phase 11 任何任务(`/^T-11/` 任务前缀必须由指挥官在 `dev_tasks.md` + `T-11XX_spec.md` 物理落盘后才能动)。
  - **严禁**改 `implementation-plan.md` 任何非 §10 内容(其他 phase 已闭环,不重写历史)。
  - **严禁** `git push`(留给指挥官决策推送时机)。
  - **严禁**改 4 既定 untracked 文件。

- **时间戳纪律**(Phase 11 启动前最后一次落地):所有 commit message 末尾、终端汇报、`dev_tasks.md` 段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。

- **完工后**: 立即停手汇报「Phase 10 已闭环,T-1008 文档收尾完工,等待指挥官启动 Phase 11 规划」。**绝对不要**自启 Phase 11。
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
   必须确认:HEAD = `1ea45a4`,ahead origin/main 30 commits,工作树干净,4 既定 untracked 保留。

2. **加锁**(可选,因 T-1008 是纯文档短任务,允许跳过 chore(lock),直接进入 §4.3):
   ```bash
   # 若需加锁(>15 分钟预估):
   # dev_tasks.md Task 8 `[ ]` → `[/]` In Progress by Codex
   # git commit -m "chore(lock): T-1008 开工"
   ```

3. **执行文件改动**(单一原子 feat commit 范围):
   - 改 `docs/implementation-plan.md`:严格在 L817 之后 / L819 之前追加 §3.1 字面量段。
   - 改 `docs/recap.md`:L4 替换 + L6 替换 + L25 之前插入 8 条历史移交记录(§3.2.1 / §3.2.2 / §3.2.3)。

4. **闸门**(全绿才提交):
   ```bash
   # 1. 校验 implementation-plan.md 只动了追加段(diff 仅在 L817 之后)
   git diff docs/implementation-plan.md | head -20  # 应该只看到 +号行,无 - 号行(纯追加)

   # 2. 校验 recap.md 改动面 = L4 一行删除 + 8 行插入,L6 一行删除 + 1 行插入,L25 之前 8 行插入
   git diff docs/recap.md --stat   # 应该 1 file changed, ~17 insertions, ~2 deletions

   # 3. 校验所有目标段落都包含正确的 emoji / 表格列数(防止格式错乱)
   grep -c "✅" docs/implementation-plan.md  # 必须比之前多 6 次(6 个维度)
   grep -c "T-100" docs/recap.md             # 必须比之前多 8 次(8 个 task entries 引用)
   ```

5. **提交 feat commit**(单一原子,**改 2 文件**):
   ```bash
   git add docs/implementation-plan.md docs/recap.md
   git commit -m "feat(docs): T-1008 Phase 10 文档收尾 — §10 实施段 + recap 8 task entries + Phase 11 候选

   ① implementation-plan.md §10 末尾追加「实际落地路径(Phase 10 实施)」段:
      - 6 维度对照表 (3 ❌ + 3 部分 ✅) → (6 ✅)
      - 6 关键 commit 引用 (ad6643a / 6e2b94a / d8737d9 / 02f3d58 / 72111e2 / d169039)
      - 实际对外 API 路径表 (6 行) + 前端落地路径表 (3 行)
      - Phase 11 候选方向 4 项
   ② recap.md 三处更新:
      - 最新进度摘要 L4: T-1001 单行 → Phase 10 八 task 结构化摘要
      - L6 当前阶段: Phase 10 (勘察先行轮) → Phase 11 候选 (T-1001~T-1008 全收口)
      - 历史移交记录 L25 之前插入 8 条 (Phase 10 闭环总结 + 7 task entries 按倒序)

   零代码改动 (backend / frontend / alembic / tests 全冻结),纯文档收尾。

   Worker timestamp: [YYYY-MM-DD HH:MM:SS]"
   ```

6. **提交 chore(progress) commit**(改 `dev_tasks.md`,**§3.3 + §3.4 一起 add**):
   ```bash
   # §3.3: dev_tasks.md Task 8 `[ ]` → `[x]`
   # §3.4: dev_tasks.md L194-end 📣 锚点段整体替换为「Phase 10 已闭环,无持牌任务」终态文字

   git add docs/dev_tasks.md
   git commit -m "chore(progress): close T-1008 — Phase 10 文档收尾完工, Phase 10 八任务全闭环

   ① Task 8 行首 [ ] → [x]
   ② 📣 锚点段整体替换为「Phase 10 已闭环,当前无持牌任务」终态文字
      + Phase 11 候选方向 4 项 (等待指挥官启动 Phase 11 规划时重新发牌)

   Phase 10 收口状态:
   - 33+ commits 跨 T-1001 ~ T-1008 (含 T-1006-FIX 单行复议)
   - backend pytest 178 passed, 2 skipped (从 Phase 9 收口 +18 零回归)
   - frontend lint + typecheck 全绿
   - alembic head 仍 b58bb129c24b
   - 4 既定 untracked 保留未污染

   Worker timestamp: [YYYY-MM-DD HH:MM:SS]"
   ```

7. **完工汇报**(终端打印,**不要** `git push`):
   ```
   [YYYY-MM-DD HH:MM:SS] T-1008 完工,Phase 10 八任务全闭环,等待指挥官二次验收 + Phase 11 启动规划。
   ```

---

## §5 闸门(Worker 提交前必跑)

```bash
# 1. 改动范围闸门:严格 2 文件 (feat) + 1 文件 (chore) = 3 文件总修改
git status --short  # 验证只有 implementation-plan.md / recap.md / dev_tasks.md 改动 + 4 既定 untracked

# 2. 改动面闸门:implementation-plan.md 纯追加(无 - 行)
git diff docs/implementation-plan.md | grep "^-[^-]" | wc -l  # 必须 = 0

# 3. recap.md 改动总量闸门(防过度删除):
git diff docs/recap.md --stat   # 期望 ~17 insertions + ~2 deletions, NOT 重写

# 4. 关键 emoji / 表格闸门:
grep -c "实际落地路径(Phase 10 实施)" docs/implementation-plan.md  # 必须 = 1
grep -c "Phase 11 候选" docs/recap.md  # 必须 ≥ 1
grep -c "T-1008" docs/recap.md  # 必须 ≥ 2

# 5. 4 既定 untracked 闸门:
git status --short | grep "^??" | wc -l  # 必须 = 4
```

**不需要跑** backend pytest / frontend lint / alembic check —— 本任务零代码改动,跑闸门是浪费 token。

---

## §6 防越界红线(20 项,任何一项触发立即驳回)

1. ❌ 改 `backend/` 任何文件
2. ❌ 改 `frontend/` 任何文件
3. ❌ 改 `docs/implementation-plan.md` L1-817 任何内容(只能在 L817 之后追加)
4. ❌ 改 `docs/implementation-plan.md` L819(`---`)或之后的任何内容(只能在 L819 之前结束追加段)
5. ❌ 改 `docs/recap.md` L1-3(标题/章节头)
6. ❌ 改 `docs/recap.md` L7-23(非 L4/L6 的最新进度摘要其他行)
7. ❌ 改 `docs/recap.md` L26-end(非「L25 之前插入」的其他历史移交记录行)
8. ❌ 改任何 `docs/T-100X_spec.md` 历史契约
9. ❌ 改 `docs/dev_tasks.md` L1-148(Task 1~5 历史回执)
10. ❌ 改 `docs/dev_tasks.md` L149-165(Task 6/7 验收回执)
11. ❌ 改 `docs/dev_tasks.md` L166(Task 7 末尾结束行)
12. ❌ 改 `docs/dev_tasks.md` L168-169(Task 8 子 bullet)
13. ❌ 改 `docs/dev_tasks.md` L170-193(质量闸门 / 执行协议提醒)
14. ❌ 动 4 既定 untracked 文件
15. ❌ 自动 `git push`
16. ❌ 自启 Phase 11 任何任务
17. ❌ revert 任何已落地 commit
18. ❌ 在 feat / chore commit 之外打额外提交
19. ❌ 篡改 §3.1 / §3.2 字面量(包括 emoji / commit 短哈希 / 表格列宽 / 空行数)
20. ❌ 在 commit message 中省略 `Worker timestamp:` 行

---

## §7 commit message 序列(逐条字面量)

**Commit 1**(feat,改 `implementation-plan.md` + `recap.md`):

```
feat(docs): T-1008 Phase 10 文档收尾 — §10 实施段 + recap 8 task entries + Phase 11 候选

[body 见 §4 Step 5]

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

**Commit 2**(chore,改 `dev_tasks.md`):

```
chore(progress): close T-1008 — Phase 10 文档收尾完工, Phase 10 八任务全闭环

[body 见 §4 Step 6]

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

**严禁**:仅一行 commit message(对比 T-1005/T-1007 的 multi-line body 风格,**收紧审计可读性**)。**严禁**省略 `Worker timestamp:` 行。

---

## §8 验收清单(指挥官二次验收用,17 项)

| # | 项 | 通过条件 |
|---|---|---|
| 1 | commit 链路 | HEAD 在 `1ea45a4` 之后 = 2 个 commit(feat + chore) |
| 2 | feat commit 改动文件 | 严格 = `docs/implementation-plan.md` + `docs/recap.md`,**不含** `dev_tasks.md` |
| 3 | chore commit 改动文件 | 严格 = `docs/dev_tasks.md`,**不含**其他文件 |
| 4 | implementation-plan.md 纯追加 | `git diff <feat>^..<feat> -- docs/implementation-plan.md` 无 `-` 开头的删除行 |
| 5 | §10 实施段字面量 | grep `^### 实际落地路径(Phase 10 实施)` 输出 1 行 |
| 6 | 6 维度对照表 | 表格主体 6 行(部门表 / 部门字段 / 项目成员关联 / 项目路由 / 部门分组端点 / 前端 Tabs 切换器) |
| 7 | 6 commit 短哈希引用 | 段内含 `ad6643a` / `6e2b94a` / `d8737d9` / `02f3d58` / `72111e2` / `d169039` 全 6 个 |
| 8 | 实际对外 API 路径表 | 6 行(部门 5 端点 + reports 1 行) |
| 9 | 前端落地路径表 | 3 行(`/admin/departments` 页 + `/dashboard` Tabs + sidebar 入口) |
| 10 | Phase 11 候选 4 项 | 段尾列出 ① ~ ④ 候选方向(FK 迁移 / 物化视图 / 加权柱状图 / KPI 打通) |
| 11 | recap.md L4 替换 | 原 `[Phase 10] T-1001 ...` 单行删除;Phase 10 Task 1~8 共 8 行追加 |
| 12 | recap.md L6 替换 | `Phase 10(勘察先行轮)` → `Phase 11 候选(Phase 10 已闭环,T-1001 ~ T-1008 八任务全收口)` |
| 13 | recap.md 历史移交记录新插 | L25 之前 8 行(`[2026-05-28 by Commander] Phase 10 闭环` + 7 task entries 按倒序) |
| 14 | dev_tasks.md Task 8 状态 | L167 `[ ]` → `[x]`,其他子 bullet 不变 |
| 15 | dev_tasks.md 📣 锚点 | L194-end 替换为「Phase 10 已闭环,当前无持牌任务」终态文字 + Phase 11 候选 4 项 |
| 16 | Worker timestamp | feat + chore 两条 commit message 均含 `Worker timestamp: [...]` 行 |
| 17 | 4 既定 untracked 保留 | `git status --short \| grep "^??" \| wc -l` = 4 |

**全 17 项 PASS** → 验收通过 → 指挥官落 `docs(tasks): T-1008 验收通过` commit,Phase 10 正式收口。

---

## §9 风险与回滚

### 风险

1. **格式错乱**(中度):Markdown 表格列对齐错乱、emoji 显示异常、空行数错位。
   - 缓解:§3.1 / §3.2 字面量逐字符锁定;Worker 必须复制粘贴,**严禁手敲**。
2. **递归误改**(低度):Worker 误改 implementation-plan.md L1-817 已有内容。
   - 缓解:§5 闸门 #2 `grep "^-[^-]" | wc -l = 0` 强制校验纯追加。
3. **历史移交记录顺序错乱**(低度):Worker 按时间正序插入(错误),应该倒序(2026-05-28 在最上)。
   - 缓解:§3.2.3 字面量已按正确倒序排列,Worker 复制粘贴即可。
4. **`Worker timestamp:` 行遗漏**(低度):commit message 极简未带时间戳。
   - 缓解:§7 + §8 #16 双重把关。

### 回滚

- **feat commit 回滚**:`git revert <feat-sha>` —— 单文件回滚 implementation-plan.md + recap.md 改动。
- **chore commit 回滚**:`git revert <chore-sha>` —— 单文件回滚 dev_tasks.md 改动。
- **零代码改动**意味着回滚成本极低,不需要 alembic downgrade / npm 重装 / pytest 重跑。

---

## §10 📣 给 Worker (Codex) 的物理交接单

> **指挥官签字时间戳**:`[2026-05-28 09:10:00]`
> **持牌任务**:**T-1008**(Phase 10 最终任务 — 文档收尾,**零代码改动**)

- **执行入口**:**必须**读完整 `docs/T-1008_spec.md`(本文件)。**必须**在改动前跑 `git status --short --branch` / `git log -3 --oneline` / `git diff` / `git diff --cached` 四个前置探针,核验 HEAD = `1ea45a4`,工作树干净,4 既定 untracked 保留。

- **核心动作**(2 文件 feat + 1 文件 chore = 共 3 文件改动 / 2 commit):

  **Commit 1 (feat)**:
  1. **改** `docs/implementation-plan.md`:严格在 L817(`- 前端总经理看板的全员 / 按部门 / 按项目 Tabs 切换器尚未落地。`)之后 + L819(`---`)之前,追加 §3.1 字面量段(`### 实际落地路径(Phase 10 实施)` 整段)。**不要**改 L1-817 / L819 之后的任何内容。
  2. **改** `docs/recap.md`:
     - **L4 替换**(§3.2.1):删除 `[Phase 10] T-1001 §10 实物盘点 ...` 单行,替换为 Phase 10 Task 1~8 八行字面量。
     - **L6 替换**(§3.2.2):`Phase 10(勘察先行轮)` → `Phase 11 候选(Phase 10 已闭环,T-1001 ~ T-1008 八任务全收口)`。
     - **L25 之前插入**(§3.2.3):`## 历史移交记录` 标题行之后、L25 `[2026-05-27 by Commander] Phase 10 启动 ...` 之前,按字面量插入 8 行倒序条目(2026-05-28 在最上)。

  **Commit 2 (chore)**:
  3. **改** `docs/dev_tasks.md`:
     - **§3.3**:L167 `[ ] **Task 8 (T-1008): 文档收尾**` → `[x] **Task 8 (T-1008): 文档收尾**`(只改方括号)。
     - **§3.4**:L194-end(整个「## 📣 恢复执行指令」段)整体替换为「Phase 10 已闭环,当前无持牌任务」终态文字 + Phase 11 候选 4 项。字面量见 §3.4。

- **严禁项**(违反立即驳回,详见 §6 20 项):
  - **严禁**改 backend / frontend / alembic / tests / scripts 任何文件。
  - **严禁**改 `implementation-plan.md` L1-817 / L819+ 任何内容(只能在指定锚点之间追加)。
  - **严禁**改 `recap.md` L7-23 / L26-end 任何内容(只能动 L4 / L6 / 在 L25 之前插入)。
  - **严禁**改 `dev_tasks.md` L1-193 之间任何内容(只能动 L167 `[ ]` → `[x]` + L194-end 锚点段整体替换)。
  - **严禁**篡改 §3.1 / §3.2.1 / §3.2.3 / §3.4 字面量(包括 emoji / commit 短哈希 / 表格对齐 / 空行)。
  - **严禁**动 4 既定 untracked 文件(`.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` / `backend/uv.lock`)。
  - **严禁** `git push`(留给指挥官决策推送时机)。
  - **严禁**自启 Phase 11 任何任务。
  - **严禁** revert 历史 commit。
  - **严禁**在两条 commit message 中遗漏 `Worker timestamp:` 行。

- **闸门**(全绿才提交,详见 §5):
  ```bash
  # 严格 3 文件改动 + 4 既定 untracked
  git status --short
  # implementation-plan.md 纯追加(无删除行)
  git diff docs/implementation-plan.md | grep "^-[^-]" | wc -l  # 必须 = 0
  # 关键字面量在位
  grep -c "实际落地路径(Phase 10 实施)" docs/implementation-plan.md  # 必须 = 1
  grep -c "Phase 11 候选" docs/recap.md  # 必须 ≥ 1
  grep -c "T-1008" docs/recap.md  # 必须 ≥ 2
  ```

  **不需要跑** backend pytest / frontend lint / typecheck / alembic check —— 本任务零代码改动。

- **完工提交序列**(2 commit,顺序锁定):
  1. `feat(docs): T-1008 Phase 10 文档收尾 — §10 实施段 + recap 8 task entries + Phase 11 候选` —— **2 文件**(`implementation-plan.md` + `recap.md`)。
  2. `chore(progress): close T-1008 — Phase 10 文档收尾完工, Phase 10 八任务全闭环` —— **1 文件**(`dev_tasks.md`)。

  两条 commit message 都**必须**包含 multi-line body(对比 T-1005/T-1007 风格)+ 末尾 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 行。

- **时间戳纪律**:所有 commit message 末尾、终端汇报、`dev_tasks.md` 段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。

- **完工后**:立即停手汇报「T-1008 完工,Phase 10 八任务全闭环,等待指挥官二次验收 + Phase 11 启动规划」。**绝对不要**自启 Phase 11。**绝对不要** `git push`。
