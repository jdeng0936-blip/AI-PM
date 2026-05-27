# T-1001 执行契约 — Phase 10 §10 实物盘点 + 实际落地路径段落落盘

> **任务编号**: T-1001
> **所属阶段**: Phase 10「部门与项目分组」/ 勘察先行轮(0/n)
> **任务性质**: **纯文档勘察 + 落盘**(只读 grep + 文档写入,**严禁触碰任何业务 src 代码 / 迁移 / 测试**)
> **接力人**: Codex(Worker)
> **指挥官**: Claude(Commander)
> **起草日期**: 2026-05-27
> **前置 commit**: `b29da90 chore(lock): Phase 10 Task 1 启动`
> **当前 alembic head**: `e8c4a1d9f2b0`(Phase 9 已闭环,Phase 10 第一轮不动 DB)

---

## 1. 任务背景

Phase 9(KPI 目标设定)全 54 commit 已 push 至 `origin/main`(`b87a417..0b2a150`)。开启 Phase 10 时,指挥官 V2.1 探针 + 三方文档对账发现**真实歧义**:

| 来源 | 关于 §10 部门与项目分组 |
|---|---|
| **`implementation-plan.md` §10 原文**(L737-784) | 描述 `departments` 独立表 + `/api/admin/reports?group_by=department\|project_id=` 端点 + 前端 Tabs 切换器(全员/按部门/按项目) |
| **`implementation-plan.md` 附录 A L1077** | "§10 部门与项目分组 ✅ — `models/{project,project_member,project_stage}.py`、`routers/projects.py`" |
| **`docs/dev_tasks.md`** | 通篇 Phase 9 看板,完全没有 Phase 10 任务清单 |
| **实物代码** | `Project` / `ProjectMember` / `ProjectStage` 三 ORM + 31KB `routers/projects.py` + 前端 `/projects` + `/project/[id]` 已实现;但 `departments` 独立表 / 对外 `group_by` 端点 / 前端 Tabs 切换器**尚未实现** |

指挥官选择**方向 C — 勘察先行**:不擅自臆造 Phase 10 实施任务,而是先派一轮 T-1001 把已实现 / 未实现的真实状态盘清,落盘到 `plan §10 末尾`,然后据此决定后续 task 的真实范围。

**T-1001 是 Phase 10 的"零号任务"**,与 Phase 9 的 T-901 起草前的 plan §9 阅读不同,T-1001 本身是一份正式任务,有锁、有契约、有 commit。

---

## 2. 范围决策

### 2.1 为什么先勘察

| 备选 | 优势 | 劣势 | 决策 |
|---|---|---|---|
| **A. 直接补 §10 三大空白** | 推进快 | 在不知道 V2.0 已实现到何程度的情况下补齐,可能与 `routers/projects.py` 31KB 已暴露的端点重复,触发"盲目覆盖"红线(CLAUDE.md §4) | ❌ 拒绝 |
| **B. 新立项 Phase 10 范围** | 不被 plan §10 历史包袱拖住 | 没有勘察基础,新范围立项缺乏事实依据,后续可能反复返工 | ❌ 拒绝 |
| **C. 勘察先行 + 落盘 plan** | 一次性把 V2.0 真实落地写入 plan,后续所有 Phase 10 task 共享同一份事实依据 | 推进慢一轮 | ✅ **采纳** |

### 2.2 勘察范围(6 个维度)

| 维度 | 勘察问题 | 勘察方法 |
|---|---|---|
| D1 | `departments` 独立表是否存在? | `grep -rn "class Department" backend/app/models/`、`grep "departments" backend/alembic/versions/*.py` |
| D2 | `User.department` 字段是什么类型? FK 还是 VARCHAR? | 读 `backend/app/models/user.py` 中 `department` 字段定义 |
| D3 | `ProjectMember` 表的实际语义是什么? | 读 `backend/app/models/project_member.py` 字段定义 + 主键 / FK |
| D4 | `routers/projects.py` 对外暴露了哪些端点? | `grep -nE "^@router\.|^router = APIRouter" backend/app/routers/projects.py` |
| D5 | `/api/admin/reports?group_by=` 这类对外分组端点存在吗? | `grep -rn "group_by" backend/app/routers/` 后甄别"SQL 内部 GROUP BY" vs "对外 query param" |
| D6 | 前端总经理看板的 Tabs 切换器(全员/按部门/按项目)是否实现? | 列出 `frontend/src/app/admin/` 子目录、读 `frontend/src/app/projects/page.tsx` 顶部 import + 顶层 JSX 是否含 `<Tabs>` |

### 2.3 严格不做的事

- ❌ **不写任何 backend/app/ 业务代码**(model / service / router / schema 全冻结)
- ❌ **不新建任何 alembic migration** —— Phase 10 第一轮 DB 零改动
- ❌ **不改 frontend/src/ 任何文件** —— 包括 api 客户端 / page / component
- ❌ **不动测试** —— `tests/` 全冻结,完工后 `pytest -v` 仍应 160+2(零变化)
- ❌ **不扩展到 §10 之外**(OKR / 资源负载 / 复盘留给后续 Phase)
- ❌ **不在落地路径表里写"我建议下一步做 X"** —— 表里只列事实(已实现 / 未实现 / API 路径),建议留给指挥官读完后起草 T-1002 时决策
- ❌ **不碰 `backend/uv.lock`**(继续 untracked)
- ❌ **不自动 `git push`** —— 完工后立即停手等指挥官

---

## 3. 原子步骤

### 3.1 勘察阶段(只读,不产生任何 commit)

按 §2.2 六维度依次 grep / read,把每个维度的事实结果记到工作内存(或临时记事)。**不要把勘察过程写成 markdown 提交**,只把最终结论写入 §3.2 的落地路径表。

具体命令模板:

```bash
cd /Users/hycdq2026/Downloads/AI-PM-main

# D1: departments 表
grep -rn "class Department" backend/app/models/ || echo "[D1] no Department class"
grep -l "departments" backend/alembic/versions/*.py || echo "[D1] no migration touches departments"

# D2: User.department 字段类型
sed -n '/class User/,/^class /p' backend/app/models/user.py | grep -n "department"

# D3: ProjectMember 字段
sed -n '/class ProjectMember/,/^class /p' backend/app/models/project_member.py

# D4: routers/projects.py 端点
grep -nE "^@router\.|^router = APIRouter" backend/app/routers/projects.py

# D5: group_by 端点
grep -rn "group_by" backend/app/routers/

# D6: 前端 Tabs 切换器
ls frontend/src/app/admin/
head -80 frontend/src/app/projects/page.tsx | grep -iE "tabs|tab " || echo "[D6] no Tabs in projects page"
```

### 3.2 落盘步骤 A — 改 `docs/implementation-plan.md §10` 末尾

在 §10 原文末尾(原文 L784 `---` **之前**,与 §9 末尾 `### 实际落地路径(Phase 9)` 章节位置严格对齐)追加以下结构:

```markdown
### 实际落地路径(Phase 10 勘察)

Phase 10「部门与项目分组」启动前由指挥官派 T-1001 做实物盘点,实际状态相对 plan §10 原文如下:

| 维度 | plan §10 原文 | V2.0 实际落地 | 状态 |
|------|--------------|--------------|------|
| 部门表 | `CREATE TABLE departments (...)` 独立表 + `manager_id FK` | <填写勘察结果 D1> | ✅/❌ |
| 部门字段 | (未明确) | <填写勘察结果 D2,例如 `User.department: VARCHAR(64), 非 FK`> | <定性> |
| 项目成员关联 | `project_members(project_id, user_id, role)` | <填写勘察结果 D3> | ✅/❌ |
| 项目路由 | `/api/admin/reports?group_by=project&project_id=` | <填写勘察结果 D4 关键端点清单> | <定性> |
| 部门分组端点 | `/api/admin/reports?group_by=department` | <填写勘察结果 D5,甄别 SQL 内部 vs 对外端点> | ✅/❌ |
| 前端切换器 | `<Tabs>` 全员/按部门/按项目 | <填写勘察结果 D6> | ✅/❌ |

实际对外 API 路径(沿用 FastAPI router `prefix="/api/v1/projects"` 等):

| 方法 | 实际路径 | 说明 |
|------|----------|------|
| <填写 D4 勘察出的真实端点> | | |

**待补齐清单**(Phase 10 后续 task 候选):

- <仅列事实空白项,如 "departments 独立表(plan 要求但 V2.0 未建)" / "对外 /api/v1/admin/reports?group_by= 端点" / "前端总经理 Tabs 切换器">
- <不写建议优先级 / 不写实施方案,留给指挥官>
```

**格式要求**:
- 章节标题必须为 `### 实际落地路径(Phase 10 勘察)`(三级标题,括号内 4 个字)
- 第一段引言一句话,说明谁派的、为什么
- 6 列对照表的"维度"列固定 6 行,**不许扩 7 行也不许缺**
- 实际 API 路径表的行数由 D4 实际勘察出的端点数决定
- 待补齐清单**只列空白项的事实陈述**,**严禁写"建议下一步做 X"**

### 3.3 落盘步骤 B — 改 `docs/recap.md`

打开 `docs/recap.md`,做两处改动(参考 T-907 / T-908 之前的同样模式):

1. **「当前阶段」段** —— 找到现有的 `当前阶段 Phase 9 ...` 行,改为:
   ```markdown
   当前阶段:Phase 10(勘察先行轮)
   ```

2. **「最新进度摘要」段** —— 在该段顶部插入新 bullet(若该段是无序列表,直接 prepend 一行):
   ```markdown
   - [Phase 10] T-1001 §10 实物盘点 + plan 实际落地路径段落落盘(纯文档勘察,backend/frontend/tests 全冻结)
   ```

3. **「历史移交记录」段** —— 在该段顶部插入一条:
   ```markdown
   - [2026-05-27 by Commander] Phase 10 启动 — Phase 9 KPI 已 push origin/main(`0b2a150`),Phase 10 不擅自臆造任务,改派 T-1001 勘察先行,落盘 plan §10 实际落地路径表后再起草后续 task。
   ```

**不动** recap.md 任何其他章节(架构决策 / Phase 9 历史 / 早期 V2.0 移交记录全部保留)。

### 3.4 落盘步骤 C — 改 `docs/dev_tasks.md`

仅一处:把 Phase 10 章节的 Task 1 从 `[/] In Progress by Commander` 改为 `[x]`(放到最后一个 commit 一起 add)。

**不动** dev_tasks.md 任何其他部分(Phase 9 看板 / 质量闸门 / 执行协议提醒 / 📣 锚点全部保留;📣 锚点中"当前持牌任务: T-1001"也不动 —— 留给指挥官在起草 T-1002 时整体替换)。

---

## 4. 防越界红线(CLAUDE.md §4 衍生)

| 红线 | 触发条件 | 后果 |
|---|---|---|
| 触动 `backend/app/` 任何 `.py` | `git diff --stat backend/app/` 非空 | 指挥官打回,Codex 回滚并重做 |
| 触动 `frontend/src/` 任何文件 | `git diff --stat frontend/src/` 非空 | 同上 |
| 新建 alembic migration | `ls backend/alembic/versions/ \| wc -l` 增长 | 同上 |
| 触动 `tests/` 任何文件 | `git diff --stat backend/tests/ frontend/` 非空 | 同上 |
| 在落地路径表里写"建议优先做 X" | grep 章节文本能找到"建议"/"推荐"/"应该先" | 同上,Codex 删掉重写 |
| 修改 `backend/uv.lock` | git status 显示 `uv.lock` 被跟踪 | 同上 |
| 自行 `git push` | origin/main 收到新 commit 而指挥官未 sign-off | 严重违纪,需立即 `git push --force-with-lease` 回滚 |

---

## 5. 测试基线

T-1001 是纯文档任务,**测试不应有任何变化**:

```bash
cd backend && .venv/bin/pytest tests/                          # 必须 160 passed + 2 skipped(与 0b2a150 完全一致)
cd backend && .venv/bin/ruff check .                            # 仍 All checks passed
cd frontend && npm run lint && npm run typecheck                # 仍零警告
```

**任何**测试数量变化(包括从 160 涨到 161 或跌到 159)、ruff 警告新增、typecheck error 新增,都说明 **Codex 越界动了代码**,必须立即排查并回滚到 `b29da90`。

无需跑 alembic 三件套(不动 DB),无需跑 `pytest tests/test_kpi_phase9.py -v`(不动 KPI)。

---

## 6. 完工提交序列(原子 2 commit,**顺序不可乱**)

### Commit 1 — `docs(phase10): T-1001 §10 实物盘点 + 实际落地路径段落落盘`

```bash
git add docs/implementation-plan.md docs/recap.md
git commit -m "$(cat <<'EOF'
docs(phase10): T-1001 §10 实物盘点 + 实际落地路径段落落盘

Phase 10 启动前由指挥官派 T-1001 做纯只读勘察,把 V2.0 已实现 /
未实现的真实状态盘清,落盘到 plan §10 末尾,与 §9 末尾「实际落地
路径(Phase 9)」格式对齐。

落盘内容:
- implementation-plan.md §10 末尾追加「### 实际落地路径
  (Phase 10 勘察)」章节,6 列对照表 + 已实现 API 路径表 + 待补
  齐清单
- recap.md「当前阶段」改为 Phase 10(勘察轮),新增 Task 1 bullet,
  历史移交记录顶部追加 [2026-05-27] 条目

不动 backend/ frontend/ tests/ alembic/ 任何代码,本 commit 是
纯文档落盘。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

### Commit 2 — `chore(progress): close T-1001 — Phase 10 勘察轮完工`

```bash
git add docs/dev_tasks.md
git commit -m "$(cat <<'EOF'
chore(progress): close T-1001 — Phase 10 勘察轮完工

dev_tasks.md Phase 10 章节 Task 1 状态从 [/] In Progress 改为 [x]。
📣 恢复执行指令锚点保留 T-1001 现状,留给指挥官在起草 T-1002 时
统一替换。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## 7. 风险与注意事项

1. **勘察是只读的,但落地路径表写错就要返工**。建议 Codex 把 6 个 grep 命令的原始输出贴到本地工作区(不要 commit),写表前对照核实。
2. **不要把勘察出的"已实现 API 路径"全部列完**。`routers/projects.py` 31KB 端点可能有 20+,实际落地路径表只列**与 plan §10 直接相关**的(即:增删改查项目 / 项目成员 / 部门分组类),不要把 dashboard / health / sprint 子端点扯进来。
3. **不要在 6 列对照表的"V2.0 实际落地"列写代码片段**,只写**结论性事实**(例如 `User.department: VARCHAR(64), 非 FK, default=""`),保持表格简洁可读。
4. **如果勘察发现某维度"部分实现"**(例如 projects 路由暴露了 group_by 但只针对 health_status,没有 department/project),状态列写 `部分 ✅`,在"V2.0 实际落地"列简短说明实现的子集和缺失的子集。
5. **如果勘察发现 plan §10 原文有 bug**(例如 `users.id` SERIAL 与实际 UUID 冲突,类似 §9 那种),**只如实记录差异**,不写"建议修改 plan"——这是指挥官的决策权。
6. **recap.md 改动要克制**。只动 3 个具体位置(当前阶段 / 进度摘要 / 历史移交记录),不要顺手优化排版 / 删旧条目 / 增加新章节。
7. **完工后必须停手**。Codex 不许自行启动 Task 2,不许把 T-1001 落地路径表当成 Task 2 的 spec 起草直接执行。等指挥官读完 plan §10 末尾新增章节,起草并发牌 T-1002。
8. **`backend/uv.lock` 继续保持 untracked**。git status 显示它在 `??` 区是正常的,不要 `git add`。

---

## 8. 验收标准(指挥官二次验收清单)

| 项 | 期望 | 校验命令 |
|---|---|---|
| 提交数量 | T-1001 区间内恰好 2 个 commit | `git log b29da90..HEAD --oneline \| wc -l` 应为 2 |
| 提交顺序 | docs(phase10) → chore(progress) | `git log b29da90..HEAD --oneline` |
| 文件隔离 | Commit 1 只含 plan + recap;Commit 2 只含 dev_tasks | `git show --stat <commit>` |
| 代码零变更 | backend/ frontend/ tests/ alembic/ 全部 0 字节改动 | `git diff b29da90..HEAD --stat -- backend/app backend/tests backend/alembic frontend/src` 应为空 |
| 测试零回归 | `pytest tests/` 仍 160+2 | 见 §5 |
| 落地路径表完整 | plan §10 末尾出现 `### 实际落地路径(Phase 10 勘察)` 章节,含 6 列对照表 + API 路径表 + 待补齐清单 | `grep -n "实际落地路径(Phase 10" docs/implementation-plan.md` 应有一行 |
| Task 1 状态 | dev_tasks.md Phase 10 章节 Task 1 = `[x]` | `grep "Task 1 (T-1001)" docs/dev_tasks.md` |
| 锚点保留 | 📣 锚点中 "当前持牌任务: T-1001" 保留(未自行替换为 T-1002) | `grep "当前持牌任务" docs/dev_tasks.md` |

任何一项不符,指挥官会要求 Codex 回滚到 `b29da90` 并重做。

---

## 9. 与历史契约的关系

| 契约 | 关系 |
|---|---|
| T-907 (Phase 9 文档收尾) | T-1001 的「实际落地路径(Phase 10 勘察)」格式直接抄 T-907 落盘的「实际落地路径(Phase 9)」段(plan §9 末尾) |
| T-908 (Phase 9 漂移修复) | T-1001 学到的教训:Phase 10 不再在不勘察的情况下闭眼起草,避免再次出现前后端枚举漂移 |
| plan §10 原文 (L737-784) | T-1001 不修改原文,只追加落地路径表 |
| plan 附录 A L1077 | T-1001 不修改附录,落地路径表会客观补充"哪些已实现 / 哪些未实现",附录维持 "§10 ✅" 标记不动(它在 V2.0 节点是真的) |

---

## 📣 恢复执行指令

> **给 Worker (Codex) 的直接发牌,供 PM 探针自动提取**

- **当前持牌任务**: **T-1001**(指挥官已通过 `b29da90` 加锁)—— Phase 10 **勘察先行轮**,纯文档勘察 + 落盘。
- **执行入口**: 阅读本契约 `docs/T-1001_spec.md`(已就是本文件),无需重打 `chore(lock)`,直接进入勘察。
- **核心动作**(严格按 §3 顺序):
  1. **只读勘察 6 维**(§2.2 + §3.1):D1 departments 表 / D2 User.department 字段 / D3 ProjectMember 表 / D4 routers/projects.py 端点 / D5 group_by 对外端点 / D6 前端 Tabs 切换器
  2. **写**:`docs/implementation-plan.md §10` 末尾(L784 `---` 前)追加 `### 实际落地路径(Phase 10 勘察)` 章节,3 段结构(6 列对照表 + API 路径表 + 待补齐清单)。详见 §3.2。
  3. **写**:`docs/recap.md` 三处微调(当前阶段 → Phase 10 / 进度摘要顶部新增 1 bullet / 历史移交记录顶部新增 1 条 [2026-05-27])。详见 §3.3。
  4. **写**:`docs/dev_tasks.md` 仅一处 —— Phase 10 章节 Task 1 由 `[/]` 改 `[x]`(放最后 commit)。详见 §3.4。
- **严禁项**(违反则立即回滚):
  - **严禁**触动 `backend/app/` 任何 `.py`(model / service / router / schema 全冻结)
  - **严禁**新建任何 alembic migration
  - **严禁**改 `frontend/src/` 任何文件
  - **严禁**改 `tests/` 任何文件
  - **严禁**在落地路径表里写「建议」/「推荐」/「应该先」类主观判断
  - **严禁**自行启动 Task 2 / 起草 T-1002
  - **严禁**自动 `git push`
- **闸门**(全文档任务,只跑形式校验,**不应有任何变化**):
  ```bash
  cd backend && .venv/bin/pytest tests/                          # 必须 160 passed + 2 skipped
  cd backend && .venv/bin/ruff check .                            # 仍 All checks passed
  cd frontend && npm run lint && npm run typecheck                # 仍零警告
  ```
- **完工提交序列**(原子 2 commit,顺序不可乱):
  1. `docs(phase10): T-1001 §10 实物盘点 + 实际落地路径段落落盘`(只含 `docs/implementation-plan.md` + `docs/recap.md`)
  2. `chore(progress): close T-1001 — Phase 10 勘察轮完工`(只含 `docs/dev_tasks.md`,Task 1 → `[x]`)
- **完工后**: 立即停手,汇报「T-1001 勘察落盘完成,落地路径段已写入 plan §10 末尾,等待指挥官审阅 + 起草 T-1002 实施契约」。**不要**自行启动 Task 2。
