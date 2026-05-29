# T-1401 契约 — Phase 14 第一任:里程碑与积分贡献激励模块(立项定盘 + 3 层验收 + 动态加减分 + 多人 ratio + 积分流水)

> **指挥官**:Claude(架构师 / Commander) `[2026-05-29 17:08:53]`
> **Worker**:Codex(待接手)
> **基线 commit**:`6788bdf chore(lock): T-1401 spec 起草开工`(本任 spec 起草 lock signal;T-1401 工程 commit 将以本 spec 起草后的 `chore(spec)` commit 为正式基线)
> **隶属阶段**:Phase 14(本任为 Phase 14 启动任,**价值流主轴**,与 Phase 11/12/13 进度流主轴**解耦并行**,先于所有 T-1107/T-1108/T-1202/T-1302/T-1402+ candidates)
> **老板原话**:`docs/PHASE14_REQUIREMENTS.md`(22 行 4 段,`[2026-05-29 16:50:00]` 追加)
> **预计改动面**:**17 src/test/migration/frontend/文档 文件**(后端 model 4 + service 2 + router 1 + schema 2 + migration 1 + main.py 1 + 测试 1 + 前端 API 2 + 前端 page 4 + 前端 component 1 + 文档 1)
> **测试基线**:T-1301 完工 `251 passed + 2 skipped` → T-1401 完工预期 `273 passed + 2 skipped`(+22 case)
> **质量闸门基线**:`ruff` PASS / `mypy` PASS / `pytest -q` PASS / `alembic upgrade-downgrade-upgrade` 来回幂等 + stdout 命中 `[T-1401 backfill]` / frontend `npm run lint && npm run typecheck` PASS
> **Auto Mode 决策签字数**:**7 主决策 + 4 次级决策 = 11 决策**(详见 §6)

---

## 1. 任务背景与业务需求

### 1.1 老板原话(`[2026-05-29 16:50:00]`)+ 业务驱动

> **老板**(`docs/PHASE14_REQUIREMENTS.md`):
>
> 老板已拍板追加 Phase 14:基于真实公司制度及最新反馈,构建以"积分贡献"为核心的里程碑及动态任务激励模块。
>
> ### 核心业务逻辑
> 1. **纯新增实体**:`ProjectMilestone`(里程碑与任务激励表)和 `MilestoneAllocation`(多人协作积分分配表)。
> 2. **立项时定盘(支持主线与临时工单)**:
>    - **主线项目(软件/硬件)**:立项弹窗根据项目轨道自动带出标准里程碑节点。
>      - 软件节点:需求文档完成、MVP完成、功能验证通过、正式上线/客户验收。
>      - 硬件节点:方案评审通过、样机完成、产品定型/客户验收。
>    - **临时性任务/工单**:也支持设定单一或自定义的"完成节点"。
>    - **积分设定**:总经理(Admin)在此填入每个节点的具体**积分贡献**(注意不是"元",统一使用积分衡量价值)。
> 3. **里程碑打卡与动态加减(基于真实实现)**:
>    - 项目到达某节点后发起验收,系统支持校验标准及特定流转签字。
>    - **动态调整机制**:根据项目真实的实现情况(如延期、质量优劣、超出预期等),验收审批时允许对该节点的"初始积分"进行**加分或减分(Penalty/Bonus)**,得出最终核算积分。
> 4. **结项分发流转**:对于多人协作,由技术负责人分配个人贡献比例(`contribution_ratio`),算出最终落在每个员工头上的"积分贡献额度",流转报批后入账。

**业务驱动**:
- 进度流(T-1104~T-1301 完工)已闭环,**价值流主轴缺位** — 公司没有任何结构化机制把"项目阶段成就"转化为"员工个人激励账户"。
- 老板真实公司制度跑了 10 年,各项目节点积分一直靠 Excel + 群通知人工记账,统计员工年终积分需要翻 12 个月聊天记录。
- Phase 14 第一刀:**把激励机制锁进数据库** — 立项时定盘节点 + 终批时入账流水 + 个人时间线可追溯。

### 1.2 老板需求拆解 + 业务三件套对齐

| 编号 | 老板需求 | T-1401 实现路径 | 落点 |
|---|---|---|---|
| ① | **立项定盘**(软件 4 / 硬件 3 / 临时单节点 / 支持自定义) | 新建 `services/milestone_template_service.py` 提供 `get_standard_template(track, is_temporary)` 字面量常量;立项弹窗调 `GET /api/v1/admin/milestones/templates?track=...` 拉模板 → 用户可改名/增删/填积分 → `POST /api/v1/projects/{project_id}/milestones/seed` 单事务批入 | `ProjectMilestone` 表 + `MilestoneNodeType` enum + `STANDARD_MILESTONE_TEMPLATES` 常量 + `seed_milestones: bool = True` 钩子写入 `routers/projects.py` create_project 末尾 |
| ② | **里程碑打卡 + 动态加减分**(发起验收 + 流转签字 + Penalty/Bonus) | 3 层链:① node owner(任意 ProjectMember)调 `POST .../request-review` 触发 `pending → in_review`;② `tech_lead`(ProjectMember.member_role='tech_lead' **新 enum 列**)调 `POST .../allocations` 提交 ratio + initial_points(单层 Pydantic + DB CHECK 校验 ∑=100%);③ admin 调 `POST /admin/milestones/{id}/approve` 提交 `final_points + adjustment_reason`(若 delta != 0 强制 reason),同事务写 Ledger | `MilestoneStatus` 4 角(pending/in_review/approved/void)+ `final_points` 单字段覆盖式 + `adjustment_reason TEXT NOT NULL when delta`(轻量审计) |
| ③ | **结项分发流转 + 多人 ratio + 入账**(技术负责人分 ratio + 报批后入账) | `MilestoneAllocation` 表存每位成员的 ratio + initial_points + final_points;admin 终批同事务:UPDATE milestone status + final_points → UPDATE 所有 allocations status + final_points(= round(milestone.final * ratio)) → INSERT `UserPointsLedger` income 行(每位成员 1 行,direction='income', amount=allocation.final_points, reason 含 milestone 名 + ratio%) | `UserPointsLedger` append-only 流水表 + `LedgerDirection` 3 角(income/refund/adjustment)+ `revert_allocation` API 支持冲销(写 refund 行) |
| ④ | **积分**(注意不是"元",统一用积分衡量价值) | 全新独立命名空间 `contribution_points`,**与现有 7 套 points/score 完全切割**(故事点/AI 评分/健康分/容量分配点/Sprint 燃尽点) | `contribution_ratio` / `initial_points` / `final_points` / `total_points` 字段统一前缀 + 中文 UI 统一称"贡献积分" |

### 1.3 当前痛点(从 `models/project.py + project_member.py + project_stage.py + frontend/dashboard,projects/page.tsx` 现状读盘)

**痛点 1 — 现有 7 套 points/score 字段语义混乱**:
- `User.story_points_capacity`(故事点容量)/ `SprintTask.story_points / actual_story_points`(故事点)/ `Capacity.allocated_points / completed_points`(容量分配点)/ `DailyReport.ai_score`(AI 评分 0-100)/ `ProjectStage.health_score`(健康分 0-100)/ `Sprint.health_score / planned_story_points / completed_story_points` 共 7 套
- 老板"贡献积分"语义**完全独立**(激励价值,直接关联薪酬/年终)— 若复用 `points` 名,DAU 报表 GROUP BY 时极易把"故事点"与"贡献积分"错聚合 → 财务结算崩盘
- **决策 A**(签字):全新独立命名 `contribution_points / contribution_ratio / final_points`,严禁与 `story_points / ai_score` 字段名碰撞

**痛点 2 — 没有结构化的项目节点积分激励容器**:
- 现有 `ProjectStage` 表(IPD 五段)+ `milestones JSONB`(硬件交付物清单)**仅是状态/进度容器**,**无任何积分字段**,无审批流转,无多人分配
- 历史里程碑积分散落在群聊截图 / Excel / 老板脑中 → 员工申诉无凭证,审批无追溯
- 老板需求 #1 "里程碑与任务激励表" 必须新建独立表 — **不**复用 ProjectStage(避免污染 IPD 五段语义)

**痛点 3 — `ProjectMember.role_in_project` 是 String(64) 自由文本**:
- "技术负责人" 在当前库内**无结构化标识**,只有 `String(64)` 自由文本("硬件负责人" / "Sprint Lead" / "采购专员" 等任意填)
- `MemberTrack.both` 有"PM/技术负责人兼跨双轨"注释,但**不能用作 RBAC 闸门**(both 也可能是 PM,不一定是 tech_lead)
- 老板需求 #4 "由技术负责人分配 ratio" 需精确 RBAC → **必须**新增结构化 enum 列

**痛点 4 — 立项弹窗当前无积分配置入口**:
- `frontend/src/app/dashboard/page.tsx`(刚被 `42a61c1 fix(frontend): 补齐 dashboard 新建弹窗的人员选择器` 修复)+ `frontend/src/app/projects/page.tsx` 立项弹窗现仅支持 name/code/track/members/dates 字段
- 老板需求 #2 "立项时定盘 + 总经理填积分" 需在立项弹窗内嵌入节点编辑表,且必须**复用同一份模板真相**(后端 service 字面量 + 前端 API 拉取,**禁** 前端硬编码)

**痛点 5 — 没有员工个人积分账户**:
- 当前查"员工 X 在 Q3 总贡献积分"需 GROUP BY 全 milestone_allocations + 跨项目聚合
- 若直接靠 `MilestoneAllocation` 累加,**调整/冲销时无法追溯历史快照**(直接改字段会丢失原始入账记录)
- 老板需求 #4 "结项分发流转报批后入账"暗示**财务级时间线** → 必须 append-only 流水表

### 1.4 业务三件套(本任交付范围)

| 编号 | 需求 | 实现路径 | 覆盖范围 |
|---|---|---|---|
| ① | **立项定盘 + 节点模板**(5 轨 + 临时工单) | 新建 `services/milestone_template_service.py` 字面量模板(software 4 / hardware 3 / dual 7 / support+other 1 / temporary 1)+ `GET /admin/milestones/templates?track=...` 模板拉取端点 + `POST /projects/{id}/milestones/seed` 立项种节点端点 + `routers/projects.py` create_project 末尾追加 `seed_milestones` 钩子 + 前端 `MilestoneTemplateEditor` 复用组件 | `ProjectMilestone` 表 + `MilestoneNodeType` enum 9 角(含 custom) + `MilestoneStatus` enum 4 角 |
| ② | **3 层验收 + 动态加减分** | 3 步 API:`request-review`(node owner)/ `allocations` propose(tech_lead,∑=100%)/ `approve`(admin,final_points + adjustment_reason)+ 状态机 pending→in_review→approved + Penalty/Bonus 单字段覆盖式 + reason 强制(when delta)| `ProjectMember.member_role` 新 enum 列 + `MemberProjectRole` enum 3 角 + `AllocationStatus` enum 3 角 + Pydantic + DB CHECK 双层 ratio 校验 |
| ③ | **多人分配 + 积分流水** | `MilestoneAllocation` 表(每行 1 user + ratio + initial/final points)+ `UserPointsLedger` append-only 流水(每次入账/冲销/调整 1 行)+ admin 终批同事务:milestone.status='approved' → allocations.status='approved' + final_points 按 ratio round → ledger income 行 × N 成员 + `revert_allocation` API 写 refund 行 | `LedgerDirection` enum 3 角(income/refund/adjustment) + 个人贡献账户 `GET /me/contribution` + 分页流水 `GET /me/contribution/ledger` |

### 1.5 触碰段说明(防 T-1104/T-1105/T-1106/T-1201/T-1301 文件踩踏)

| 文件 | T-1104~T-1301 触碰史 | T-1401 触碰段 | 风险防御 |
|---|---|---|---|
| `backend/app/models/__init__.py` | T-1104 添 Department / T-1106 添 ProjectFollowUp / T-1201 添 ChatSession+ChatMessage+ChatRole / T-1301 添 DailyReport+ReportType+PlannedStatus+DailySupervisedTask+SupervisedStatus(5 项) | **严格末尾追加**式 +10 行:`ProjectMilestone + MilestoneStatus + MilestoneNodeType + MilestoneAllocation + AllocationStatus + UserPointsLedger + LedgerDirection + MemberProjectRole`(7 新 + 1 enum 复用)+ `__all__` 末尾追加 8 项 | 严禁 重排现有项;严禁 修改 T-1104/1105/1106/1201/1301 添加的行 |
| `backend/app/models/project.py` | 未触碰(自 Phase 9 起冻结) | **零改动**(BLOCKER 红线;Project 表 schema 完全冻结,milestone 是子表通过 project_id FK 关联) | BLOCKER 红线 |
| `backend/app/models/project_member.py` | T-1105 通过 create_project 创建链路注入,Member 表 schema 自 T-1105 后冻结 | **改 +8 行**:文件头新增 `MemberProjectRole` enum(tech_lead/owner/member)+ 末尾 ProjectMember 类追加 `member_role: Mapped[MemberProjectRole]` 字段(`default=member, nullable=False, server_default='member', index=True`) | **严禁** 改 `role_in_project / track / joined_at / left_at / id / project_id / user_id` 既有字段 |
| `backend/app/models/project_followup.py` | T-1106 新建,T-1301 仅 INSERT 不改 schema | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/app/models/daily_report.py` | T-1301 改(+4 字段 + 2 ENUM) | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/app/models/daily_supervised_task.py` | T-1301 新建 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/app/models/chat_session.py` + `chat_message.py` | T-1201 新建 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/app/models/sprint_task.py + sprint.py + capacity.py + okr.py + kpi_target.py` | 未触碰(各自 Phase 完工后冻结) | **零改动**(BLOCKER 红线;严禁与 contribution_points 字段产生任何交互) | BLOCKER 红线 |
| `backend/app/routers/projects.py` | T-1105 改(create_project 加 members)/ T-1106 改(update_project 临时工单守卫 + followups 2 端点) | **改 +~10 行 / -0 行**:仅 create_project 函数末尾追加可选 `seed_milestones` 钩子(条件:request body `seed_milestones=True` default;调 `milestone_service.seed_project_milestones`)。**严禁** 改 create_project 现有 members 创建逻辑 / update_project 临时工单守卫 / followups 端点 / list_projects / get_project / delete_project / 其他既有逻辑 | 触碰段精准锁定 |
| `backend/app/routers/reports.py` | T-1301 重构 today-plan + 新增 4 端点 + my-active 端点 + 1 helper | **零改动**(BLOCKER 红线;contribution_points 不与日报路径耦合) | BLOCKER 红线 |
| `backend/app/routers/wechat.py` | 未触碰(企微独立入口) | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/app/routers/chat.py` | T-1201 改(admin_ai_chat 历史注入)+ 4 端点 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/app/services/{ai_engine,kr_progress_extractor,notification_service,token_guard,health_engine}.py` | T-1106 部分触碰 token_guard | **零改动**(BLOCKER 红线;contribution_points 完全独立路径,**禁** 通过 ai_engine / kr_progress_extractor 解析积分) | BLOCKER 红线 |
| `backend/app/schemas/report.py` | 未触碰 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/app/schemas/morning_evening.py` | T-1301 新建 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/app/schemas/chat_session.py` | T-1201 新建 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/app/schemas/project.py` | T-1105 改 / T-1106 改 | **改 +~3 行**:`ProjectCreateRequest` 末尾追加 `seed_milestones: bool = Field(default=True, description="是否在立项时根据 track 自动种入标准节点模板")`;**严禁** 改其他字段(`name / code / track / description / members / planned_launch_date / budget_total / is_temporary` 全冻结) | 触碰段精准锁定 |
| `backend/app/main.py` | 仅在新 router 加入时 +1~2 行 | **改 +2 行**:imports 加 `from app.routers.milestones import router as milestones_router` + `app.include_router(milestones_router)`(严格不动既有 18+ 路由注册顺序) | 触碰段精准锁定 |
| `backend/alembic/versions/` | T-1104/T-1106/T-1201/T-1301 各 1 | **新建** `20260530_HHMM_phase14_milestone_contribution_points.py`,`down_revision = "a8b9c0d1e2f3"`(T-1301 head),`revision = "b9c0d1e2f3a4"`(Codex 接手时探针 `alembic heads` 二次核验单头) | 严格挂在 T-1301 head 之后 |
| `frontend/src/api/reports.ts + chat.ts + projects.ts` | T-1301 改 reports.ts(+5 函数)/ T-1201 改 chat.ts(+4 函数)/ T-1105 改 projects.ts | **仅改 projects.ts +12 行**(`ProjectCreateRequest` 加 `seed_milestones?: boolean`);**reports.ts + chat.ts + 其他 api/*.ts 零改动** | 触碰段精准锁定 |
| `frontend/src/api/milestones.ts` | 不存在 | **新建** ~140 行 11 函数 + 14 interface | 全新文件 |
| `frontend/src/app/dashboard/page.tsx + projects/page.tsx` | `42a61c1 fix(frontend): 补齐 dashboard 新建弹窗的人员选择器` 刚改了 dashboard;projects/page.tsx 自 T-1105 起冻结 | **改 各 +~30 行**:立项弹窗内嵌 `<MilestoneTemplateEditor>` 区段(默认 collapsed,可展开;`seed_milestones` toggle)。**严禁** 改既有 MemberPicker 子系统 / 既有项目列表 UI / 既有筛选/搜索逻辑 | 触碰段精准锁定 |
| `frontend/src/app/admin/milestones/page.tsx` | 不存在 | **新建** ~280 行 admin 全局里程碑看板 | 全新页面 |
| `frontend/src/app/me/contribution/page.tsx` | 不存在 | **新建** ~220 行 员工自助积分账户页 | 全新页面 |
| `frontend/src/components/milestone-template-editor.tsx` | 不存在 | **新建** ~150 行 复用组件 | 全新组件 |
| `frontend/src/components/member-picker.tsx` | `42a61c1` 刚改 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `frontend/src/app/{reports,submit-report,chat,login,change-password,users}/page.tsx + sidebar` | T-1201/T-1301/历史 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `frontend/src/app/project/[id]/page.tsx` | T-1105 改 | **可选改 +~40 行**(Phase 14.5 改造:项目详情页加"里程碑"tab,可看节点列表 + 审批进度)— **本任不做**,留 backlog;若 Codex 自启会触发 BLOCKER 红线 | 本任范围外 |
| `backend/tests/test_kpi_phase9.py + test_phase11_*.py + test_phase12_chat_sessions.py + test_phase13_daily_report_v2.py` | 历史 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |
| `backend/conftest.py + tests/_isolation.py + tests/_db_url.py + .env* + README + DEPLOY + pyproject + uv.lock + package.json + package-lock.json` | 全冻结 | **零改动**(BLOCKER 红线) | BLOCKER 红线 |

---

## 2. 严禁项(BLOCKER 红线 — 22 条)

> **任何一条违反 = 工程作废,Codex 必须中止并喊话指挥官**

1. **严禁** `git push`(本任完工后由用户决定推送时机;指挥官二次验收后再 push)
2. **严禁** `git stash`(跨 Agent 不可见;遗留 5 项工作区状态原样保留)
3. **严禁** `git commit --amend` / `git rebase` / `git reset --hard` / `--no-verify`(完整链路必须可审计)
4. **严禁** 改 `models/__init__.py` 现有任何 import 行的顺序;仅允许严格末尾追加 8 项(7 新 + 1 enum 复用)
5. **严禁** 改 `Project / ProjectFollowUp / DailyReport / DailySupervisedTask / ChatSession / ChatMessage / Sprint / SprintTask / Capacity / Objective / KeyResult / KpiTarget / Notification / User / Department / Attachment` 任何字段(零 ALTER,即使是注释或排序也禁)
6. **严禁** 改 `ProjectMember` 既有字段:`role_in_project / track / joined_at / left_at / id / project_id / user_id`(仅允许末尾追加 `member_role` 列)
7. **严禁** 改 `services/ai_engine.py / kr_progress_extractor.py / notification_service.py / token_guard.py / health_engine.py`(零行触碰;contribution_points 不与 AI/通知/健康度路径耦合)
8. **严禁** 改 `routers/wechat.py / reports.py / chat.py`(零行触碰;contribution_points 仅走 milestones router 独立路径)
9. **严禁** 改 `routers/projects.py` create_project 既有 members 创建逻辑 / update_project 临时工单守卫 / followups 端点 / list_projects / get_project / delete_project / archive_project / `_get_project_or_404` / 其他既有 helper(仅允许 create_project 函数末尾追加 `seed_milestones` 钩子 5~10 行)
10. **严禁** 改 `schemas/report.py / morning_evening.py / chat_session.py`(零行触碰;contribution_points schemas 全部进 `schemas/milestone.py` 独立文件)
11. **严禁** 改 `schemas/project.py` 既有字段(`name / code / track / description / members / planned_launch_date / budget_total / is_temporary`),仅允许 `ProjectCreateRequest` 末尾追加 `seed_milestones: bool` 字段
12. **严禁** 改 `main.py` 既有 18+ 路由注册顺序(仅末尾追加 milestones_router 1 行 + imports 1 行)
13. **严禁** 改 `frontend/src/api/reports.ts / chat.ts / 其他 api/*.ts`(零行触碰;仅 projects.ts 加 1 字段)
14. **严禁** 改 `frontend/src/components/member-picker.tsx`(刚被 `42a61c1` 修复,完全冻结)
15. **严禁** 改 `frontend/src/app/{reports,submit-report,chat,login,change-password,users,project/[id]}/page.tsx + sidebar`(零行触碰)
16. **严禁** 改 `frontend/src/app/dashboard/page.tsx + projects/page.tsx` 既有 MemberPicker 子系统 / 既有项目列表 UI / 既有筛选/搜索/排序逻辑(仅允许立项弹窗内嵌 `<MilestoneTemplateEditor>` 区段)
17. **严禁** 改 `conftest.py / tests/_isolation.py / tests/_db_url.py / .env* / README / DEPLOY / pyproject / uv.lock / package.json / package-lock.json`
18. **严禁** 改既有任何 alembic migration(T-1104/T-1106/T-1201/T-1301 + Phase 9~10 historical 全部冻结)
19. **严禁** 引入新 Python 依赖(complete 用 stdlib + 现有 SQLAlchemy/Pydantic V2/FastAPI)
20. **严禁** 引入新前端依赖(complete 用 React + lucide-react + Tailwind 既有栈)
21. **严禁** 改既有 Phase 11/12/13 测试文件;`test_phase14_milestone_contribution.py` 独立闭包,作用域严格 `wechat_userid like "phase14_%"` + `projects.code like "phase14_%"`
22. **严禁** 自启 T-1402 / T-1403 / T-1107 / T-1108 / T-1202 / T-1203 / T-1302 / T-1303(任何 Phase 11/12/13/14 backlog),完工后等指挥官明示放牌

---

## 3. 实施方案

### 3.1 数据层(4 新模型 + 1 既有模型加列 + 1 migration)

#### 3.1.1 `backend/app/models/project_milestone.py`(新建 ~95 行)

```python
"""
app/models/project_milestone.py — 项目里程碑与积分激励表(Phase 14 T-1401)

立项时定盘的节点容器:
  - 模板来源:services/milestone_template_service.py STANDARD_MILESTONE_TEMPLATES
  - 软件轨 4 节点 / 硬件轨 3 节点 / 双轨 7 节点 / 临时单节点 / 其他默认 1 节点
  - admin 在立项弹窗可改名/增删/填积分

3 层验收链:
  - pending: 初始态(立项时种入)
  - in_review: node owner 调 request-review 触发
  - approved: admin 终批(此刻同事务写 UserPointsLedger income)
  - void: 软作废(节点未达成 / 项目取消;严禁硬删已 approved milestone)

零踩踏既有 7 套 points/score 字段:contribution_points 完全独立命名空间
"""

import enum
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import CheckConstraint, Date, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class MilestoneNodeType(str, enum.Enum):
    # 软件轨 4 节点(老板蓝图标准模板)
    software_req = "software_req"           # 需求文档完成
    software_mvp = "software_mvp"           # MVP 完成
    software_validate = "software_validate" # 功能验证通过
    software_launch = "software_launch"     # 正式上线/客户验收
    # 硬件轨 3 节点(老板蓝图标准模板)
    hardware_review = "hardware_review"     # 方案评审通过
    hardware_proto = "hardware_proto"       # 样机完成
    hardware_finalize = "hardware_finalize" # 产品定型/客户验收
    # 临时工单/support/other 默认单节点
    temporary_done = "temporary_done"       # 完成(临时工单默认)
    # admin 立项时自定义节点(脱离标准模板)
    custom = "custom"


class MilestoneStatus(str, enum.Enum):
    pending = "pending"       # 立项种入态,可改名/积分/删
    in_review = "in_review"   # node owner 已发起验收,等 tech_lead 分 ratio + admin 终批
    approved = "approved"     # admin 终批,积分已入账;不可改不可删
    void = "void"             # 软作废(节点未达成 / 项目取消)


class ProjectMilestone(BaseMixin, Base):
    __tablename__ = "project_milestones"
    __table_args__ = (
        Index("ix_project_milestones_project_status_order", "project_id", "status", "node_order"),
        Index("ix_project_milestones_project_status_target", "project_id", "status", "target_date"),
        CheckConstraint("initial_points >= 0", name="ck_project_milestones_initial_points_non_negative"),
        CheckConstraint(
            "(status != 'approved') OR (final_points IS NOT NULL)",
            name="ck_project_milestones_approved_requires_final_points",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE", name="fk_milestones_project"),
        index=True,
        nullable=False,
    )

    node_type: Mapped[MilestoneNodeType] = mapped_column(
        Enum(MilestoneNodeType, name="milestone_node_type", native_enum=True),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(512))

    node_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    initial_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0",
                                                 comment="贡献积分初始值(立项时 admin 填;严禁负数)")
    final_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
                                                        comment="贡献积分最终核算(approved 时落)")
    adjustment_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True,
                                                              comment="动态加减分原因(approved 且 final!=initial 时强制填)")

    target_date: Mapped[Optional[date]] = mapped_column(Date)

    status: Mapped[MilestoneStatus] = mapped_column(
        Enum(MilestoneStatus, name="milestone_status", native_enum=True),
        nullable=False,
        default=MilestoneStatus.pending,
        server_default="pending",
        index=True,
    )

    requested_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_milestones_requested_by"),
        nullable=True,
    )
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    approved_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_milestones_approved_by"),
        nullable=True,
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<ProjectMilestone {self.title[:20]} status={self.status} init={self.initial_points} final={self.final_points}>"
```

**字段决策记录**:
- `node_type` PG native ENUM 9 角(8 标准 + custom);custom 用于 admin 立项时手填脱离模板
- `initial_points INT >= 0`(CHECK 约束);final_points 可空(approved 前为 NULL)
- `adjustment_reason TEXT`:approved 且 delta != 0 时 Pydantic + service 双层校验强制;DB 层不强制(允许 final = initial 时为空)
- `status` 4 角默认 pending;approved 后不可改
- `requested_by/at + approved_by/at` 双签字时间戳
- `deleted_at` 软删(沿用 BaseMixin 体例);**严禁** 硬删 approved milestone

#### 3.1.2 `backend/app/models/milestone_allocation.py`(新建 ~80 行)

```python
"""
app/models/milestone_allocation.py — 里程碑积分多人分配表(Phase 14 T-1401)

每行 = (1 milestone × 1 user × 1 ratio)三元组
  - tech_lead 在 milestone in_review 状态下调 propose_allocations 批量插入 pending 行
  - 同 milestone 下 status='pending' 的所有 allocation 必须 ∑contribution_ratio = 1.0 ± 0.0001
  - admin 终批 milestone 时同事务批量 UPDATE status='approved' + final_points = round(milestone.final * ratio)
  - 可被 admin 单独 revert(写 reverted 状态 + 触发 UserPointsLedger refund 行)

ratio 精度:NUMERIC(5,4) → 0.0000 ~ 1.0000(支持千分位精度;DB 层校验 ∑=100%)
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class AllocationStatus(str, enum.Enum):
    pending = "pending"     # tech_lead 已提,等 admin 终批
    approved = "approved"   # admin 终批,final_points 已落,Ledger income 已写
    reverted = "reverted"   # admin 冲销,Ledger refund 已写


class MilestoneAllocation(BaseMixin, Base):
    __tablename__ = "milestone_allocations"
    __table_args__ = (
        # partial unique:同 milestone 下同 user 在非 reverted 状态最多 1 行(防重复分配)
        Index(
            "ix_milestone_allocations_milestone_user_active",
            "milestone_id", "user_id",
            unique=True,
            postgresql_where="status != 'reverted'",
        ),
        Index("ix_milestone_allocations_user_status_created", "user_id", "status", "created_at"),
        CheckConstraint("contribution_ratio >= 0 AND contribution_ratio <= 1",
                        name="ck_milestone_allocations_ratio_between_0_and_1"),
        CheckConstraint("initial_points >= 0", name="ck_milestone_allocations_initial_points_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    milestone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="CASCADE", name="fk_allocations_milestone"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_allocations_user"),
        index=True,
        nullable=False,
    )

    contribution_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False,
        comment="贡献比例 0.0000~1.0000(同 milestone 下 ∑=1.0000 ± 0.0001)",
    )
    initial_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0",
                                                 comment="初始分配积分 = round(milestone.initial_points * ratio)")
    final_points: Mapped[Optional[int]] = mapped_column(Integer, nullable=True,
                                                        comment="最终核算积分 = round(milestone.final_points * ratio);approved 时落")

    status: Mapped[AllocationStatus] = mapped_column(
        Enum(AllocationStatus, name="allocation_status", native_enum=True),
        nullable=False,
        default=AllocationStatus.pending,
        server_default="pending",
        index=True,
    )

    proposed_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL", name="fk_allocations_proposed_by"),
        nullable=True,
    )
    proposed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    reverted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    revert_reason: Mapped[Optional[str]] = mapped_column(Text)

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<MilestoneAllocation user={self.user_id} ratio={self.contribution_ratio} status={self.status}>"
```

**字段决策记录**:
- `contribution_ratio NUMERIC(5,4)`:支持 0.0000~1.0000(千分位精度;避免 FLOAT 浮点误差导致 ∑≠1)
- `initial_points / final_points INT`:round 取整,严禁小数(财务积分整数化)
- partial unique 索引:`(milestone_id, user_id) WHERE status != 'reverted'` 防重复分配 + 允许 revert 后重新 propose
- `revert_reason` 仅 reverted 时填(service 层兜底)
- ondelete RESTRICT(`user_id` FK):严禁删用户时级联删 allocation 记录(财务追溯)

#### 3.1.3 `backend/app/models/user_points_ledger.py`(新建 ~70 行)

```python
"""
app/models/user_points_ledger.py — 员工贡献积分流水表(Phase 14 T-1401)

财务级 append-only 时间线:
  - admin 终批 milestone 时同事务为每位成员写 1 行 income(amount = allocation.final_points)
  - admin 冲销 allocation 时写 1 行 refund(amount = -allocation.final_points)
  - admin 手工调整(adjustment)写 1 行,amount 可正可负

严禁 update / delete 路径:
  - service 层无 update/delete 方法
  - 所有调整都通过新增 adjustment 行实现
  - 个人贡献账户余额 = SUM(amount) GROUP BY user_id

性能索引:
  - (user_id, occurred_at DESC):个人时间线查询
  - (milestone_id, direction):某 milestone 下入账/冲销审计
"""

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class LedgerDirection(str, enum.Enum):
    income = "income"           # 入账(amount > 0):milestone 终批
    refund = "refund"           # 冲销(amount < 0):allocation revert
    adjustment = "adjustment"   # 手工调整(amount 任意非 0):admin 后台校正


class UserPointsLedger(BaseMixin, Base):
    __tablename__ = "user_points_ledger"
    __table_args__ = (
        Index("ix_user_points_ledger_user_occurred", "user_id", "occurred_at"),
        Index("ix_user_points_ledger_milestone_direction", "milestone_id", "direction"),
        CheckConstraint("amount != 0", name="ck_user_points_ledger_amount_non_zero"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_ledger_user"),
        index=True,
        nullable=False,
    )
    milestone_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("project_milestones.id", ondelete="SET NULL", name="fk_ledger_milestone"),
        nullable=True,
    )
    allocation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("milestone_allocations.id", ondelete="SET NULL", name="fk_ledger_allocation"),
        nullable=True,
    )

    direction: Mapped[LedgerDirection] = mapped_column(
        Enum(LedgerDirection, name="ledger_direction", native_enum=True),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False,
                                         comment="积分增量(income>0 / refund<0 / adjustment 任意非 0)")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False,
                                         comment="入账原因(必填;格式如『里程碑 X 终批入账(比例 N%)』)")

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供
    # NOTE: 严禁 update / delete 路径;所有调整通过新增 adjustment 行实现

    def __repr__(self) -> str:
        return f"<UserPointsLedger user={self.user_id} {self.direction}={self.amount}>"
```

**字段决策记录**:
- 严格 append-only:service 层无 update/delete 方法
- `amount != 0` CHECK 约束:零金额条目无意义
- 双层溯源:`milestone_id + allocation_id` 都 SET NULL,源头删除不影响流水追溯
- `occurred_at` 与 `created_at` 分离:occurred_at 是业务发生时间(可回溯录入历史),created_at 是写入时间

#### 3.1.4 `backend/app/models/project_member.py` 改动(+8 行)

```python
# 文件头部 import 段下方追加(在 MemberTrack 类之后):

class MemberProjectRole(str, enum.Enum):
    tech_lead = "tech_lead"   # 技术负责人(可分 contribution_ratio;每项目至少 1 人)
    owner = "owner"           # 项目 owner(可发起里程碑验收;通常 = create_by)
    member = "member"         # 普通成员(默认)


# ProjectMember 类内,在 left_at 字段之后、__repr__ 方法之前追加:

    member_role: Mapped[MemberProjectRole] = mapped_column(
        Enum(MemberProjectRole, name="member_project_role", native_enum=True),
        nullable=False,
        default=MemberProjectRole.member,
        server_default="member",
        index=True,
        comment="项目角色(T-1401):tech_lead 可分 ratio,owner 可发起验收,member 默认",
    )
```

**严禁** 改 `role_in_project / track / joined_at / left_at / id / project_id / user_id` 既有字段。

#### 3.1.5 `backend/app/models/__init__.py` 改动(+10 行)

```python
# 文件末尾 import 段(在 ChatRole 之后)严格末尾追加:

# --- Phase 14 T-1401 里程碑与积分贡献激励模型 ---
from app.models.milestone_allocation import AllocationStatus, MilestoneAllocation
from app.models.project_milestone import MilestoneNodeType, MilestoneStatus, ProjectMilestone
from app.models.user_points_ledger import LedgerDirection, UserPointsLedger
# project_member 既有 import 不动,但 MemberProjectRole 需补充 import:
from app.models.project_member import MemberProjectRole  # noqa: E402 — 与既有 ProjectMember import 同模块

# __all__ 列表末尾追加(在 ChatRole 之后):
    "ProjectMilestone",
    "MilestoneStatus",
    "MilestoneNodeType",
    "MilestoneAllocation",
    "AllocationStatus",
    "UserPointsLedger",
    "LedgerDirection",
    "MemberProjectRole",
```

**注意**:`MemberProjectRole` 与既有 `ProjectMember` 同模块;import 时分两行写明(IDE 友好;PyCharm/VSCode 不会折叠成同行)。

#### 3.1.6 `backend/alembic/versions/20260530_HHMM_phase14_milestone_contribution_points.py`(新建 ~260 行)

```python
"""Phase 14 T-1401: milestone + contribution points incentive module.

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-05-30 HH:MM:SS.XXXXXX
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # === 1. 建 5 PG ENUM ===
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE milestone_node_type AS ENUM (
                'software_req', 'software_mvp', 'software_validate', 'software_launch',
                'hardware_review', 'hardware_proto', 'hardware_finalize',
                'temporary_done', 'custom'
            );
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE milestone_status AS ENUM ('pending', 'in_review', 'approved', 'void');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE allocation_status AS ENUM ('pending', 'approved', 'reverted');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ledger_direction AS ENUM ('income', 'refund', 'adjustment');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE member_project_role AS ENUM ('tech_lead', 'owner', 'member');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # === 2. project_members 加 member_role 列 + backfill ===
    op.add_column(
        "project_members",
        sa.Column(
            "member_role",
            postgresql.ENUM("tech_lead", "owner", "member", name="member_project_role", create_type=False),
            nullable=False,
            server_default="member",
        ),
    )
    op.create_index("ix_project_members_member_role", "project_members", ["member_role"])
    # backfill 全表 update(server_default 已覆盖,显式 update 仅为 audit 可见)
    result = op.get_bind().execute(sa.text(
        "UPDATE project_members SET member_role='member' WHERE member_role IS NULL"
    ))
    print(f"[T-1401 backfill] members_updated={result.rowcount}")

    # === 3. 建 project_milestones 表 ===
    op.create_table(
        "project_milestones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_type",
                  postgresql.ENUM(name="milestone_node_type", create_type=False),
                  nullable=False),
        sa.Column("title", sa.String(128), nullable=False),
        sa.Column("description", sa.String(512)),
        sa.Column("node_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("initial_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_points", sa.Integer()),
        sa.Column("adjustment_reason", sa.Text()),
        sa.Column("target_date", sa.Date()),
        sa.Column("status",
                  postgresql.ENUM(name="milestone_status", create_type=False),
                  nullable=False, server_default="pending"),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True)),
        sa.Column("requested_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        # BaseMixin 字段
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE", name="fk_milestones_project"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL", name="fk_milestones_requested_by"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="SET NULL", name="fk_milestones_approved_by"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL", name="fk_milestones_created_by"),
        sa.CheckConstraint("initial_points >= 0", name="ck_project_milestones_initial_points_non_negative"),
        sa.CheckConstraint("(status != 'approved') OR (final_points IS NOT NULL)",
                           name="ck_project_milestones_approved_requires_final_points"),
    )
    op.create_index("ix_project_milestones_project_id", "project_milestones", ["project_id"])
    op.create_index("ix_project_milestones_status", "project_milestones", ["status"])
    op.create_index("ix_project_milestones_deleted_at", "project_milestones", ["deleted_at"])
    op.create_index("ix_project_milestones_project_status_order", "project_milestones",
                    ["project_id", "status", "node_order"])
    op.create_index("ix_project_milestones_project_status_target", "project_milestones",
                    ["project_id", "status", "target_date"])

    # === 4. 建 milestone_allocations 表 ===
    op.create_table(
        "milestone_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contribution_ratio", sa.Numeric(5, 4), nullable=False),
        sa.Column("initial_points", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_points", sa.Integer()),
        sa.Column("status",
                  postgresql.ENUM(name="allocation_status", create_type=False),
                  nullable=False, server_default="pending"),
        sa.Column("proposed_by", postgresql.UUID(as_uuid=True)),
        sa.Column("proposed_at", sa.DateTime(timezone=True)),
        sa.Column("reverted_at", sa.DateTime(timezone=True)),
        sa.Column("revert_reason", sa.Text()),
        # BaseMixin
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(["milestone_id"], ["project_milestones.id"], ondelete="CASCADE",
                                name="fk_allocations_milestone"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT", name="fk_allocations_user"),
        sa.ForeignKeyConstraint(["proposed_by"], ["users.id"], ondelete="SET NULL", name="fk_allocations_proposed_by"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL", name="fk_allocations_created_by"),
        sa.CheckConstraint("contribution_ratio >= 0 AND contribution_ratio <= 1",
                           name="ck_milestone_allocations_ratio_between_0_and_1"),
        sa.CheckConstraint("initial_points >= 0", name="ck_milestone_allocations_initial_points_non_negative"),
    )
    op.create_index("ix_milestone_allocations_milestone_id", "milestone_allocations", ["milestone_id"])
    op.create_index("ix_milestone_allocations_user_id", "milestone_allocations", ["user_id"])
    op.create_index("ix_milestone_allocations_status", "milestone_allocations", ["status"])
    op.create_index(
        "ix_milestone_allocations_milestone_user_active",
        "milestone_allocations",
        ["milestone_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status != 'reverted'"),
    )
    op.create_index("ix_milestone_allocations_user_status_created", "milestone_allocations",
                    ["user_id", "status", "created_at"])

    # === 5. 建 user_points_ledger 表 ===
    op.create_table(
        "user_points_ledger",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("milestone_id", postgresql.UUID(as_uuid=True)),
        sa.Column("allocation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("direction",
                  postgresql.ENUM(name="ledger_direction", create_type=False),
                  nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        # BaseMixin
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True)),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE", name="fk_ledger_user"),
        sa.ForeignKeyConstraint(["milestone_id"], ["project_milestones.id"], ondelete="SET NULL",
                                name="fk_ledger_milestone"),
        sa.ForeignKeyConstraint(["allocation_id"], ["milestone_allocations.id"], ondelete="SET NULL",
                                name="fk_ledger_allocation"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL", name="fk_ledger_created_by"),
        sa.CheckConstraint("amount != 0", name="ck_user_points_ledger_amount_non_zero"),
    )
    op.create_index("ix_user_points_ledger_user_id", "user_points_ledger", ["user_id"])
    op.create_index("ix_user_points_ledger_direction", "user_points_ledger", ["direction"])
    op.create_index("ix_user_points_ledger_user_occurred", "user_points_ledger", ["user_id", "occurred_at"])
    op.create_index("ix_user_points_ledger_milestone_direction", "user_points_ledger",
                    ["milestone_id", "direction"])


def downgrade() -> None:
    # === 反向 5 步 ===
    # 5. drop user_points_ledger
    op.drop_index("ix_user_points_ledger_milestone_direction", table_name="user_points_ledger")
    op.drop_index("ix_user_points_ledger_user_occurred", table_name="user_points_ledger")
    op.drop_index("ix_user_points_ledger_direction", table_name="user_points_ledger")
    op.drop_index("ix_user_points_ledger_user_id", table_name="user_points_ledger")
    op.drop_table("user_points_ledger")

    # 4. drop milestone_allocations
    op.drop_index("ix_milestone_allocations_user_status_created", table_name="milestone_allocations")
    op.drop_index("ix_milestone_allocations_milestone_user_active", table_name="milestone_allocations")
    op.drop_index("ix_milestone_allocations_status", table_name="milestone_allocations")
    op.drop_index("ix_milestone_allocations_user_id", table_name="milestone_allocations")
    op.drop_index("ix_milestone_allocations_milestone_id", table_name="milestone_allocations")
    op.drop_table("milestone_allocations")

    # 3. drop project_milestones
    op.drop_index("ix_project_milestones_project_status_target", table_name="project_milestones")
    op.drop_index("ix_project_milestones_project_status_order", table_name="project_milestones")
    op.drop_index("ix_project_milestones_deleted_at", table_name="project_milestones")
    op.drop_index("ix_project_milestones_status", table_name="project_milestones")
    op.drop_index("ix_project_milestones_project_id", table_name="project_milestones")
    op.drop_table("project_milestones")

    # 2. drop project_members.member_role 列
    op.drop_index("ix_project_members_member_role", table_name="project_members")
    op.drop_column("project_members", "member_role")

    # 1. drop 5 ENUM
    op.execute("DROP TYPE IF EXISTS member_project_role")
    op.execute("DROP TYPE IF EXISTS ledger_direction")
    op.execute("DROP TYPE IF EXISTS allocation_status")
    op.execute("DROP TYPE IF EXISTS milestone_status")
    op.execute("DROP TYPE IF EXISTS milestone_node_type")
```

**Migration 决策记录**:
- 5 PG ENUM 全用 `DO $$ ... EXCEPTION WHEN duplicate_object THEN NULL; END $$;` 条件分支防重(对齐 T-1106/T-1301 体例)
- backfill stdout `[T-1401 backfill] members_updated=N`(production hot upgrade 可人工审计)
- 11 FK 命名严格按 `fk_<table_short>_<col>` 体例,与 ORM `__table_args__` 字面量 1:1
- partial unique 索引 `ix_milestone_allocations_milestone_user_active` 用 `postgresql_where=sa.text("status != 'reverted'")` 字面量
- downgrade 5 步反向严格(drop index → drop table → drop column → drop enum)
- `down_revision = "a8b9c0d1e2f3"`(T-1301 head)→ Codex 接手时探针 `alembic heads` 二次核验单头(若 T-1107/T-1202/T-1302 已被指挥官放牌并先落,Codex 必须修改 down_revision 并喊话指挥官)

### 3.2 Schemas(新建 `backend/app/schemas/milestone.py` ~210 行)

```python
"""
app/schemas/milestone.py — Phase 14 T-1401 里程碑与积分贡献 Pydantic V2 schemas

零踩踏 schemas/report.py + schemas/morning_evening.py + schemas/chat_session.py + schemas/project.py
"""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.milestone_allocation import AllocationStatus
from app.models.project_milestone import MilestoneNodeType, MilestoneStatus
from app.models.user_points_ledger import LedgerDirection


# === 模板 ===

class MilestoneTemplateNode(BaseModel):
    node_type: MilestoneNodeType
    title: str = Field(..., max_length=128)
    suggested_initial_points: int = Field(default=0, ge=0)
    node_order: int = Field(default=0, ge=0)


class MilestoneTemplateResponse(BaseModel):
    track: Literal["software", "hardware", "dual", "support", "other"]
    is_temporary: bool
    nodes: list[MilestoneTemplateNode]


# === 立项种入 ===

class MilestoneNodeIn(BaseModel):
    node_type: MilestoneNodeType
    title: str = Field(..., max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    node_order: int = Field(default=0, ge=0)
    initial_points: int = Field(default=0, ge=0)
    target_date: Optional[date] = None


class MilestoneSeedRequest(BaseModel):
    nodes: list[MilestoneNodeIn] = Field(..., min_length=1, max_length=20)


class MilestoneSeedResponse(BaseModel):
    project_id: uuid.UUID
    created: int
    milestones: list["MilestoneOut"]


# === 节点 CRUD ===

class MilestoneOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    node_type: MilestoneNodeType
    title: str
    description: Optional[str]
    node_order: int
    initial_points: int
    final_points: Optional[int]
    adjustment_reason: Optional[str]
    target_date: Optional[date]
    status: MilestoneStatus
    requested_by: Optional[uuid.UUID]
    requested_at: Optional[datetime]
    approved_by: Optional[uuid.UUID]
    approved_at: Optional[datetime]
    created_at: datetime


class MilestonePatchRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=128)
    description: Optional[str] = Field(default=None, max_length=512)
    node_order: Optional[int] = Field(default=None, ge=0)
    initial_points: Optional[int] = Field(default=None, ge=0)
    target_date: Optional[date] = None


class MilestoneListResponse(BaseModel):
    project_id: uuid.UUID
    items: list[MilestoneOut]


# === Allocation 分配 ===

class AllocationItem(BaseModel):
    user_id: uuid.UUID
    contribution_ratio: Decimal = Field(..., ge=Decimal("0"), le=Decimal("1"), max_digits=5, decimal_places=4)


class AllocationProposalRequest(BaseModel):
    allocations: list[AllocationItem] = Field(..., min_length=1, max_length=20)

    @model_validator(mode="after")
    def check_ratio_sum(self) -> "AllocationProposalRequest":
        total = sum(item.contribution_ratio for item in self.allocations)
        if abs(total - Decimal("1")) > Decimal("0.0001"):
            raise ValueError(f"contribution_ratio 总和必须等于 1.0(实际:{total})")
        # 同 user_id 不可重复
        user_ids = [item.user_id for item in self.allocations]
        if len(set(user_ids)) != len(user_ids):
            raise ValueError("同一 user_id 不可在 allocations 中重复出现")
        return self


class AllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    milestone_id: uuid.UUID
    user_id: uuid.UUID
    contribution_ratio: Decimal
    initial_points: int
    final_points: Optional[int]
    status: AllocationStatus
    proposed_by: Optional[uuid.UUID]
    proposed_at: Optional[datetime]
    reverted_at: Optional[datetime]
    revert_reason: Optional[str]
    created_at: datetime


class AllocationProposalResponse(BaseModel):
    milestone_id: uuid.UUID
    allocations: list[AllocationOut]


# === Approval 终批 ===

class MilestoneApprovalRequest(BaseModel):
    final_points: int = Field(..., ge=0)
    adjustment_reason: Optional[str] = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def check_reason_when_delta(self) -> "MilestoneApprovalRequest":
        # service 层会与 milestone.initial_points 对比;此处仅做空值兜底
        if self.adjustment_reason is not None and not self.adjustment_reason.strip():
            raise ValueError("adjustment_reason 若提供则不可为空白")
        return self


class MilestoneApprovalResponse(BaseModel):
    milestone: MilestoneOut
    allocations: list[AllocationOut]
    ledger_entries_created: int


# === Allocation 冲销 ===

class AllocationRevertRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2048)


class AllocationRevertResponse(BaseModel):
    allocation: AllocationOut
    ledger_entry: "LedgerEntryOut"


# === Ledger 流水 + 个人贡献账户 ===

class LedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    milestone_id: Optional[uuid.UUID]
    milestone_title: Optional[str]   # service 层 JOIN 填充
    project_id: Optional[uuid.UUID]   # service 层 JOIN 填充
    project_name: Optional[str]       # service 层 JOIN 填充
    allocation_id: Optional[uuid.UUID]
    direction: LedgerDirection
    amount: int
    occurred_at: datetime
    reason: str


class LedgerHistoryResponse(BaseModel):
    items: list[LedgerEntryOut]
    next_cursor: Optional[str]


PeriodLiteral = Literal["all", "year", "quarter", "month"]


class ContributionSummary(BaseModel):
    user_id: uuid.UUID
    period: PeriodLiteral
    total_points: int           # SUM(amount) WHERE period
    income_points: int          # SUM(amount) WHERE direction='income'
    refund_points: int          # SUM(amount) WHERE direction='refund'(负数)
    adjustment_points: int      # SUM(amount) WHERE direction='adjustment'
    milestone_count: int        # COUNT(DISTINCT milestone_id)


class UserContributionResponse(BaseModel):
    summary: ContributionSummary
    recent_ledger: list[LedgerEntryOut]   # 最近 10 条流水


# 解决 forward reference
MilestoneSeedResponse.model_rebuild()
AllocationRevertResponse.model_rebuild()
```

### 3.3 Service 层

#### 3.3.1 `backend/app/services/milestone_template_service.py`(新建 ~110 行)

```python
"""
app/services/milestone_template_service.py — 立项模板字面量常量

5 轨标准模板(老板蓝图字面量,严禁前端硬编码;前后端共享同一份真相):
  - software: 4 节点(需求文档/MVP/功能验证/正式上线)
  - hardware: 3 节点(方案评审/样机完成/产品定型)
  - dual: 7 节点(软件 4 + 硬件 3 全展开,admin 立项时可删)
  - support / other: 1 节点("完成", initial=0, custom 可改名)
  - is_temporary=True 优先于 track: 1 节点("完成")
"""
from app.models.project import ProjectTrack
from app.models.project_milestone import MilestoneNodeType
from app.schemas.milestone import MilestoneTemplateNode


STANDARD_MILESTONE_TEMPLATES: dict[str, list[MilestoneTemplateNode]] = {
    "software": [
        MilestoneTemplateNode(node_type=MilestoneNodeType.software_req, title="需求文档完成", suggested_initial_points=10, node_order=1),
        MilestoneTemplateNode(node_type=MilestoneNodeType.software_mvp, title="MVP 完成", suggested_initial_points=30, node_order=2),
        MilestoneTemplateNode(node_type=MilestoneNodeType.software_validate, title="功能验证通过", suggested_initial_points=30, node_order=3),
        MilestoneTemplateNode(node_type=MilestoneNodeType.software_launch, title="正式上线/客户验收", suggested_initial_points=30, node_order=4),
    ],
    "hardware": [
        MilestoneTemplateNode(node_type=MilestoneNodeType.hardware_review, title="方案评审通过", suggested_initial_points=20, node_order=1),
        MilestoneTemplateNode(node_type=MilestoneNodeType.hardware_proto, title="样机完成", suggested_initial_points=40, node_order=2),
        MilestoneTemplateNode(node_type=MilestoneNodeType.hardware_finalize, title="产品定型/客户验收", suggested_initial_points=40, node_order=3),
    ],
    # dual 轨在 get_standard_template 内动态拼装(software + hardware)
    "support": [
        MilestoneTemplateNode(node_type=MilestoneNodeType.temporary_done, title="完成", suggested_initial_points=0, node_order=1),
    ],
    "other": [
        MilestoneTemplateNode(node_type=MilestoneNodeType.temporary_done, title="完成", suggested_initial_points=0, node_order=1),
    ],
}


def get_standard_template(track: ProjectTrack, is_temporary: bool) -> list[MilestoneTemplateNode]:
    """根据 track + is_temporary 返回标准节点模板。

    优先级:
      is_temporary=True > track
    """
    if is_temporary:
        return [MilestoneTemplateNode(
            node_type=MilestoneNodeType.temporary_done,
            title="完成",
            suggested_initial_points=0,
            node_order=1,
        )]
    if track == ProjectTrack.dual:
        # dual 轨展开:software 4 + hardware 3,node_order 顺延
        software_nodes = STANDARD_MILESTONE_TEMPLATES["software"]
        hardware_nodes = [
            MilestoneTemplateNode(
                node_type=n.node_type,
                title=n.title,
                suggested_initial_points=n.suggested_initial_points,
                node_order=n.node_order + len(software_nodes),
            )
            for n in STANDARD_MILESTONE_TEMPLATES["hardware"]
        ]
        return software_nodes + hardware_nodes
    return STANDARD_MILESTONE_TEMPLATES.get(track.value, STANDARD_MILESTONE_TEMPLATES["other"])
```

#### 3.3.2 `backend/app/services/milestone_service.py`(新建 ~240 行)

```python
"""
app/services/milestone_service.py — Phase 14 T-1401 核心业务服务

7 服务函数:
  - seed_project_milestones: 立项弹窗批量种入
  - list_project_milestones: 项目下里程碑列表
  - propose_allocations: tech_lead 分 ratio
  - approve_milestone: admin 终批(同事务写 Ledger)← 业务核心
  - revert_allocation: admin 冲销(同事务写 refund)
  - get_user_contribution: 个人贡献账户(SUM + COUNT)
  - list_user_ledger: 分页流水
"""
import uuid
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.milestone_allocation import AllocationStatus, MilestoneAllocation
from app.models.project import Project
from app.models.project_member import MemberProjectRole, ProjectMember
from app.models.project_milestone import MilestoneStatus, ProjectMilestone
from app.models.user import User
from app.models.user_points_ledger import LedgerDirection, UserPointsLedger
from app.schemas.milestone import (
    AllocationOut,
    AllocationProposalRequest,
    ContributionSummary,
    LedgerEntryOut,
    MilestoneApprovalRequest,
    MilestoneNodeIn,
    MilestoneOut,
    PeriodLiteral,
)


# ─── seed ───

async def seed_project_milestones(
    db: AsyncSession,
    project_id: uuid.UUID,
    nodes: list[MilestoneNodeIn],
    actor: User,
) -> list[ProjectMilestone]:
    """立项种入节点;单事务批量 INSERT。"""
    # 防重:同 project 已存在 pending milestone 时返回 409(由 router 层处理)
    existing = await db.execute(
        select(func.count(ProjectMilestone.id)).where(ProjectMilestone.project_id == project_id)
    )
    if existing.scalar_one() > 0:
        raise ValueError("项目已存在里程碑,不可重复 seed(改用 POST /milestones 单节点新增)")

    created: list[ProjectMilestone] = []
    for node in nodes:
        m = ProjectMilestone(
            project_id=project_id,
            node_type=node.node_type,
            title=node.title,
            description=node.description,
            node_order=node.node_order,
            initial_points=node.initial_points,
            target_date=node.target_date,
            status=MilestoneStatus.pending,
            created_by=actor.id,
            tenant_id=actor.tenant_id,
        )
        db.add(m)
        created.append(m)
    await db.flush()
    return created


# ─── list ───

async def list_project_milestones(
    db: AsyncSession,
    project_id: uuid.UUID,
) -> list[ProjectMilestone]:
    result = await db.execute(
        select(ProjectMilestone)
        .where(ProjectMilestone.project_id == project_id)
        .where(ProjectMilestone.deleted_at.is_(None))
        .order_by(ProjectMilestone.node_order.asc(), ProjectMilestone.created_at.asc())
    )
    return list(result.scalars().all())


# ─── propose allocations ───

async def propose_allocations(
    db: AsyncSession,
    milestone_id: uuid.UUID,
    payload: AllocationProposalRequest,
    proposer: User,
) -> list[MilestoneAllocation]:
    """tech_lead 提交 ratio 分配;校验 ∑=100% + 所有 user 必须是 active member。"""
    # 1. 锁 milestone
    milestone = await db.get(ProjectMilestone, milestone_id, with_for_update=True)
    if milestone is None or milestone.deleted_at is not None:
        raise ValueError("milestone 不存在")
    if milestone.status != MilestoneStatus.in_review:
        raise ValueError(f"milestone status={milestone.status},不在 in_review 状态")

    # 2. 清除该 milestone 下既有 pending allocations(允许 tech_lead 反复 propose)
    await db.execute(
        select(MilestoneAllocation)
        .where(MilestoneAllocation.milestone_id == milestone_id)
        .where(MilestoneAllocation.status == AllocationStatus.pending)
    )
    # 软清:DELETE pending 记录(没 approved 没流水)
    from sqlalchemy import delete
    await db.execute(
        delete(MilestoneAllocation)
        .where(MilestoneAllocation.milestone_id == milestone_id)
        .where(MilestoneAllocation.status == AllocationStatus.pending)
    )

    # 3. 校验所有 user_id 是该项目 active member
    user_ids = [item.user_id for item in payload.allocations]
    members_result = await db.execute(
        select(ProjectMember)
        .where(ProjectMember.project_id == milestone.project_id)
        .where(ProjectMember.user_id.in_(user_ids))
        .where(ProjectMember.left_at.is_(None))
    )
    member_user_ids = {m.user_id for m in members_result.scalars().all()}
    missing = set(user_ids) - member_user_ids
    if missing:
        raise ValueError(f"以下 user_id 不是项目活跃成员:{missing}")

    # 4. 批量插入 pending
    created: list[MilestoneAllocation] = []
    now = datetime.now(timezone.utc)
    for item in payload.allocations:
        initial_for_user = int(
            (Decimal(milestone.initial_points) * item.contribution_ratio).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
        alloc = MilestoneAllocation(
            milestone_id=milestone_id,
            user_id=item.user_id,
            contribution_ratio=item.contribution_ratio,
            initial_points=initial_for_user,
            status=AllocationStatus.pending,
            proposed_by=proposer.id,
            proposed_at=now,
            created_by=proposer.id,
            tenant_id=proposer.tenant_id,
        )
        db.add(alloc)
        created.append(alloc)
    await db.flush()
    return created


# ─── approve (核心事务) ───

async def approve_milestone(
    db: AsyncSession,
    milestone_id: uuid.UUID,
    payload: MilestoneApprovalRequest,
    approver: User,
) -> tuple[ProjectMilestone, list[MilestoneAllocation], int]:
    """admin 终批 milestone;同事务:
       1. UPDATE milestone status='approved' + final_points + adjustment_reason
       2. UPDATE 所有 pending allocations status='approved' + final_points = round(milestone.final * ratio)
       3. INSERT UserPointsLedger income 行 × N 成员
    返回 (milestone, allocations, ledger_count)
    """
    milestone = await db.get(ProjectMilestone, milestone_id, with_for_update=True)
    if milestone is None or milestone.deleted_at is not None:
        raise ValueError("milestone 不存在")
    if milestone.status != MilestoneStatus.in_review:
        raise ValueError(f"milestone status={milestone.status},不在 in_review")

    # 校验:delta != 0 时必填 reason
    delta = payload.final_points - milestone.initial_points
    if delta != 0 and (not payload.adjustment_reason or not payload.adjustment_reason.strip()):
        raise ValueError("final_points 与 initial_points 不一致时必须填写 adjustment_reason")

    # 锁 pending allocations
    allocs_result = await db.execute(
        select(MilestoneAllocation)
        .where(MilestoneAllocation.milestone_id == milestone_id)
        .where(MilestoneAllocation.status == AllocationStatus.pending)
        .with_for_update()
    )
    allocations = list(allocs_result.scalars().all())
    if not allocations:
        raise ValueError("milestone 下无 pending allocations,无法终批")

    # 校验 ∑ ratio = 1.0
    total_ratio = sum(a.contribution_ratio for a in allocations)
    if abs(total_ratio - Decimal("1")) > Decimal("0.0001"):
        raise ValueError(f"allocations 的 ratio 总和 != 1.0(实际:{total_ratio})")

    now = datetime.now(timezone.utc)

    # 1. UPDATE milestone
    milestone.status = MilestoneStatus.approved
    milestone.final_points = payload.final_points
    milestone.adjustment_reason = payload.adjustment_reason if delta != 0 else None
    milestone.approved_by = approver.id
    milestone.approved_at = now

    # 2. UPDATE allocations + 3. INSERT Ledger
    ledger_count = 0
    for alloc in allocations:
        alloc_final = int(
            (Decimal(payload.final_points) * alloc.contribution_ratio).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        alloc.status = AllocationStatus.approved
        alloc.final_points = alloc_final

        if alloc_final != 0:  # amount=0 不写流水(CHECK 约束)
            ledger = UserPointsLedger(
                user_id=alloc.user_id,
                milestone_id=milestone.id,
                allocation_id=alloc.id,
                direction=LedgerDirection.income,
                amount=alloc_final,
                occurred_at=now,
                reason=f"里程碑[{milestone.title}]终批入账(比例 {alloc.contribution_ratio * 100:.2f}%)",
                created_by=approver.id,
                tenant_id=approver.tenant_id,
            )
            db.add(ledger)
            ledger_count += 1

    await db.flush()
    return milestone, allocations, ledger_count


# ─── revert ───

async def revert_allocation(
    db: AsyncSession,
    allocation_id: uuid.UUID,
    reason: str,
    actor: User,
) -> tuple[MilestoneAllocation, UserPointsLedger]:
    alloc = await db.get(MilestoneAllocation, allocation_id, with_for_update=True)
    if alloc is None:
        raise ValueError("allocation 不存在")
    if alloc.status != AllocationStatus.approved:
        raise ValueError(f"仅 approved 状态可冲销;当前 status={alloc.status}")
    if alloc.final_points is None or alloc.final_points == 0:
        raise ValueError("final_points 为空或 0,无可冲销金额")

    now = datetime.now(timezone.utc)
    alloc.status = AllocationStatus.reverted
    alloc.reverted_at = now
    alloc.revert_reason = reason

    ledger = UserPointsLedger(
        user_id=alloc.user_id,
        milestone_id=alloc.milestone_id,
        allocation_id=alloc.id,
        direction=LedgerDirection.refund,
        amount=-alloc.final_points,
        occurred_at=now,
        reason=f"分配冲销:{reason}",
        created_by=actor.id,
        tenant_id=actor.tenant_id,
    )
    db.add(ledger)
    await db.flush()
    return alloc, ledger


# ─── contribution summary ───

async def get_user_contribution(
    db: AsyncSession,
    user_id: uuid.UUID,
    period: PeriodLiteral,
) -> ContributionSummary:
    # 时间窗
    window_start = _compute_period_start(period)

    base_query = select(
        func.coalesce(func.sum(UserPointsLedger.amount), 0).label("total"),
    ).where(UserPointsLedger.user_id == user_id)
    if window_start is not None:
        base_query = base_query.where(UserPointsLedger.occurred_at >= window_start)

    total_result = await db.execute(base_query)
    total_points = int(total_result.scalar_one())

    # 各 direction 分项
    by_direction_query = select(
        UserPointsLedger.direction,
        func.coalesce(func.sum(UserPointsLedger.amount), 0).label("sum_amount"),
    ).where(UserPointsLedger.user_id == user_id).group_by(UserPointsLedger.direction)
    if window_start is not None:
        by_direction_query = by_direction_query.where(UserPointsLedger.occurred_at >= window_start)
    by_direction_result = await db.execute(by_direction_query)
    by_direction = {row.direction: int(row.sum_amount) for row in by_direction_result.all()}

    # 涉及里程碑数
    milestone_count_query = select(
        func.count(func.distinct(UserPointsLedger.milestone_id))
    ).where(UserPointsLedger.user_id == user_id).where(UserPointsLedger.milestone_id.isnot(None))
    if window_start is not None:
        milestone_count_query = milestone_count_query.where(UserPointsLedger.occurred_at >= window_start)
    milestone_count_result = await db.execute(milestone_count_query)
    milestone_count = int(milestone_count_result.scalar_one())

    return ContributionSummary(
        user_id=user_id,
        period=period,
        total_points=total_points,
        income_points=by_direction.get(LedgerDirection.income, 0),
        refund_points=by_direction.get(LedgerDirection.refund, 0),
        adjustment_points=by_direction.get(LedgerDirection.adjustment, 0),
        milestone_count=milestone_count,
    )


def _compute_period_start(period: PeriodLiteral) -> Optional[datetime]:
    now = datetime.now(timezone.utc)
    if period == "all":
        return None
    if period == "year":
        return now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "quarter":
        q_month = ((now.month - 1) // 3) * 3 + 1
        return now.replace(month=q_month, day=1, hour=0, minute=0, second=0, microsecond=0)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


# ─── list ledger ───

async def list_user_ledger(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 20,
    cursor: Optional[str] = None,  # 简化:用 occurred_at iso string
) -> tuple[list[LedgerEntryOut], Optional[str]]:
    query = (
        select(
            UserPointsLedger,
            ProjectMilestone.title.label("milestone_title"),
            ProjectMilestone.project_id.label("project_id"),
            Project.name.label("project_name"),
        )
        .outerjoin(ProjectMilestone, UserPointsLedger.milestone_id == ProjectMilestone.id)
        .outerjoin(Project, ProjectMilestone.project_id == Project.id)
        .where(UserPointsLedger.user_id == user_id)
        .order_by(UserPointsLedger.occurred_at.desc(), UserPointsLedger.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        try:
            cursor_dt = datetime.fromisoformat(cursor)
            query = query.where(UserPointsLedger.occurred_at < cursor_dt)
        except ValueError:
            pass

    result = await db.execute(query)
    rows = result.all()
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1][0].occurred_at.isoformat()
        rows = rows[:limit]

    items = [
        LedgerEntryOut(
            id=row[0].id,
            user_id=row[0].user_id,
            milestone_id=row[0].milestone_id,
            milestone_title=row[1],
            project_id=row[2],
            project_name=row[3],
            allocation_id=row[0].allocation_id,
            direction=row[0].direction,
            amount=row[0].amount,
            occurred_at=row[0].occurred_at,
            reason=row[0].reason,
        )
        for row in rows
    ]
    return items, next_cursor
```

### 3.4 Router 层(新建 `backend/app/routers/milestones.py` ~280 行)

**端点清单(11 个)**:

| 路径 | 方法 | RBAC | 业务 |
|---|---|---|---|
| `/api/v1/admin/milestones/templates` | GET | admin/manager | 模板预览(track + is_temporary) |
| `/api/v1/projects/{project_id}/milestones/seed` | POST | admin/manager | 立项弹窗批量种入(409 if exists) |
| `/api/v1/projects/{project_id}/milestones` | GET | project member 或以上 | 列表 |
| `/api/v1/projects/{project_id}/milestones` | POST | admin/manager | 单节点追加 |
| `/api/v1/projects/{project_id}/milestones/{milestone_id}` | PATCH | admin/manager | 改 title/initial_points/target_date/node_order(仅 status=pending) |
| `/api/v1/projects/{project_id}/milestones/{milestone_id}` | DELETE | admin | 软删(status=void,仅 pending/void) |
| `/api/v1/projects/{project_id}/milestones/{milestone_id}/request-review` | POST | 项目内任意 member | 发起验收 pending→in_review |
| `/api/v1/projects/{project_id}/milestones/{milestone_id}/allocations` | POST | tech_lead OR admin | 分 ratio(∑=100% 校验) |
| `/api/v1/admin/milestones/{milestone_id}/approve` | POST | admin only | 终批 + 写 Ledger |
| `/api/v1/admin/milestones/allocations/{allocation_id}/revert` | POST | admin only | 冲销 + 写 refund |
| `/api/v1/me/contribution` | GET | 任意已认证用户 | 个人贡献账户汇总 + 近 10 条流水 |
| `/api/v1/me/contribution/ledger` | GET | 任意已认证用户 | 个人流水分页 |

**关键 helper(独立放在本文件)**:
- `_load_owned_milestone(db, project_id, milestone_id, user) -> ProjectMilestone`:5 条件 RBAC + 404
- `_require_tech_lead(db, project_id, user) -> bool`:验证 user 在该项目 member_role='tech_lead' OR 是 admin
- `_require_project_member(db, project_id, user) -> ProjectMember`:验证 user 在该项目 left_at IS NULL

**RBAC 调用约定**:
- admin only:`require_role(UserRole.admin)`
- admin/manager:`require_role(UserRole.admin, UserRole.manager)`
- tech_lead OR admin:`_require_tech_lead`
- 项目 member:`_require_project_member`

**前缀挂载**(由于 1 个 router 包含 3 个前缀,采用分段 router 模式):
```python
admin_router = APIRouter(prefix="/api/v1/admin/milestones", tags=["Milestones"])
project_router = APIRouter(prefix="/api/v1/projects", tags=["Milestones"])
me_router = APIRouter(prefix="/api/v1/me", tags=["Milestones"])
# 三个 sub-router 在 main.py 一次性 include
```

### 3.5 `backend/app/routers/projects.py` 改动(+~8 行)

```python
# create_project 函数末尾(在 db.commit() 之前)追加:

    if payload.seed_milestones:
        from app.schemas.milestone import MilestoneNodeIn
        from app.services.milestone_service import seed_project_milestones
        from app.services.milestone_template_service import get_standard_template

        template_nodes = get_standard_template(payload.track, payload.is_temporary)
        nodes_in = [
            MilestoneNodeIn(
                node_type=n.node_type,
                title=n.title,
                node_order=n.node_order,
                initial_points=n.suggested_initial_points,
            )
            for n in template_nodes
        ]
        await seed_project_milestones(db, new_project.id, nodes_in, actor=current_user)
```

**严禁** 改 create_project 现有 members 创建逻辑 / update_project / followups / list_projects / get_project / archive / delete / 其他 helper。

### 3.6 `backend/app/main.py` 改动(+2 行)

```python
# imports 段末尾追加:
from app.routers.milestones import admin_router as milestones_admin_router
from app.routers.milestones import me_router as milestones_me_router
from app.routers.milestones import project_router as milestones_project_router

# include_router 段末尾追加(在最后一个既有路由之后):
app.include_router(milestones_admin_router)
app.include_router(milestones_project_router)
app.include_router(milestones_me_router)
```

### 3.7 `backend/app/schemas/project.py` 改动(+~3 行)

```python
# ProjectCreateRequest 类末尾追加(在最后一个 Field 之后):

    seed_milestones: bool = Field(
        default=True,
        description="是否在立项时根据 track 自动种入标准节点模板(T-1401);旧客户端默认 True 向后兼容",
    )
```

**严禁** 改其他字段。

### 3.8 前端 API 层

#### 3.8.1 `frontend/src/api/projects.ts` 改动(+~12 行)

```typescript
// ProjectCreateRequest interface 末尾追加:
export interface ProjectCreateRequest {
  // ... 既有字段全部不动
  seed_milestones?: boolean;  // T-1401:默认 true,立项时种入标准模板
}
```

#### 3.8.2 `frontend/src/api/milestones.ts`(新建 ~140 行)

11 函数 + 14 interface:

```typescript
// 类型
export type MilestoneNodeType = "software_req" | "software_mvp" | "software_validate" | "software_launch"
  | "hardware_review" | "hardware_proto" | "hardware_finalize" | "temporary_done" | "custom";
export type MilestoneStatus = "pending" | "in_review" | "approved" | "void";
export type AllocationStatus = "pending" | "approved" | "reverted";
export type LedgerDirection = "income" | "refund" | "adjustment";
export type ContributionPeriod = "all" | "year" | "quarter" | "month";

export interface MilestoneTemplateNode { ... }
export interface MilestoneTemplateResponse { ... }
export interface MilestoneOut { ... }
export interface MilestoneListResponse { ... }
export interface MilestoneSeedRequest { ... }
export interface MilestoneSeedResponse { ... }
export interface AllocationOut { ... }
export interface AllocationProposalRequest { ... }
export interface MilestoneApprovalRequest { ... }
export interface MilestoneApprovalResponse { ... }
export interface AllocationRevertRequest { ... }
export interface LedgerEntryOut { ... }
export interface LedgerHistoryResponse { ... }
export interface ContributionSummary { ... }
export interface UserContributionResponse { ... }

// 11 函数
export async function getMilestoneTemplates(track: string, isTemporary: boolean): Promise<MilestoneTemplateResponse>;
export async function seedProjectMilestones(projectId: string, payload: MilestoneSeedRequest): Promise<MilestoneSeedResponse>;
export async function listProjectMilestones(projectId: string): Promise<MilestoneListResponse>;
export async function createMilestone(projectId: string, payload: any): Promise<MilestoneOut>;
export async function patchMilestone(projectId: string, milestoneId: string, payload: any): Promise<MilestoneOut>;
export async function deleteMilestone(projectId: string, milestoneId: string): Promise<void>;
export async function requestReview(projectId: string, milestoneId: string): Promise<MilestoneOut>;
export async function proposeAllocations(projectId: string, milestoneId: string, payload: AllocationProposalRequest): Promise<{ allocations: AllocationOut[] }>;
export async function approveMilestone(milestoneId: string, payload: MilestoneApprovalRequest): Promise<MilestoneApprovalResponse>;
export async function revertAllocation(allocationId: string, payload: AllocationRevertRequest): Promise<{ allocation: AllocationOut }>;
export async function getMyContribution(period: ContributionPeriod): Promise<UserContributionResponse>;
export async function getMyLedger(limit: number, cursor?: string): Promise<LedgerHistoryResponse>;
```

### 3.9 前端 UI 层(4 文件)

#### 3.9.1 `frontend/src/app/dashboard/page.tsx` + `projects/page.tsx` 改动(立项弹窗内嵌)

立项弹窗内追加"标准节点预览 + 可编辑表"区段(默认 collapsed,展开后可改):
- 用户切换 track → useEffect 自动调 `getMilestoneTemplates(track, isTemporary)` 拉模板填充
- 用户可改名、改积分、增删行、调整顺序
- `seed_milestones` toggle(默认 true)
- 提交时连同 `seed_milestones: true` 走 createProject;后端自动种入

**严禁** 改 MemberPicker / 既有项目列表 / 既有筛选/搜索逻辑。

#### 3.9.2 `frontend/src/app/admin/milestones/page.tsx`(新建 ~280 行)

admin 全局里程碑看板:
- 顶部 tabs:`pending` / `in_review` / `approved` / `void`
- 中间表格:列出所有 milestone(分页),列含 项目名 / 节点名 / status / initial_points / final_points / 待审标识
- 点击行进入审批面板:展示节点信息 + 当前 pending allocations(user/ratio/initial)+ 输入 `final_points` + `adjustment_reason`(若 delta != 0 强制)+ 提交按钮
- 冲销面板:approved 状态时显示已分配,admin 可对单条 allocation 调 revert

#### 3.9.3 `frontend/src/app/me/contribution/page.tsx`(新建 ~220 行)

员工自助积分账户页:
- 顶部 Period 切换器:全年 / 本季 / 本月 / 累计
- 摘要卡:`total_points`(大字)+ `income / refund / adjustment` 三色 chip + `milestone_count`
- 流水时间线:list of LedgerEntryOut,每条显示 occurred_at + 项目名 + 节点名 + amount(income 绿 / refund 红 / adjustment 灰)+ reason
- 分页:cursor-based 加载更多

#### 3.9.4 `frontend/src/components/milestone-template-editor.tsx`(新建 ~150 行)

复用组件,立项弹窗 / admin 加节点 / admin 改节点共用:
- props: `{ track, isTemporary, value: MilestoneNodeIn[], onChange: (nodes) => void }`
- useEffect:track 或 isTemporary 变化 → 拉模板覆盖 value(若 value 为空)
- 表格:行编辑 title / initial_points / target_date / node_order + 行尾删除按钮
- 底部"+ 增加节点"按钮
- 实时校验:title 不可空 / initial_points >= 0

### 3.10 测试(`backend/tests/test_phase14_milestone_contribution.py` ~520 行 ~22 case)

| # | 测试 | 类别 |
|---|---|---|
| 1 | test_project_milestone_check_initial_points_non_negative | Model |
| 2 | test_milestone_allocation_ratio_check_between_0_and_1 | Model |
| 3 | test_user_points_ledger_amount_check_not_zero | Model |
| 4 | test_member_project_role_enum_values_serialize | Model |
| 5 | test_standard_template_software_returns_4_nodes | Template |
| 6 | test_standard_template_dual_returns_7_nodes_with_offset_order | Template |
| 7 | test_standard_template_temporary_overrides_track | Template |
| 8 | test_seed_project_milestones_single_transaction | Service |
| 9 | test_propose_allocations_rejects_sum_not_100 | Service |
| 10 | test_approve_milestone_writes_ledger_atomically | Service |
| 11 | test_revert_allocation_writes_refund | Service |
| 12 | test_cross_tenant_isolation_for_milestones | Service |
| 13 | test_GET_templates_RBAC_admin_only_returns_403_for_member | Router |
| 14 | test_POST_seed_409_if_already_seeded | Router |
| 15 | test_PATCH_milestone_rejects_when_status_not_pending | Router |
| 16 | test_request_review_only_project_member_can | Router |
| 17 | test_propose_allocations_only_tech_lead_can_403_member | Router |
| 18 | test_propose_allocations_422_if_sum_not_100 | Router |
| 19 | test_approve_milestone_requires_adjustment_reason_when_delta | Router |
| 20 | test_approve_milestone_writes_ledger_for_all_members | Router |
| 21 | test_GET_me_contribution_returns_period_total | Router |
| 22 | test_GET_me_contribution_ledger_pagination_with_cursor | Router |

**测试约束**:
- 零 mock / 零 monkeypatch / 零 print / 零 logger / 零 skip / 零 xfail
- 私有 helpers `_phase14_*` 前缀
- 作用域:`wechat_userid like "phase14_%"` + `projects.code like "phase14_%"`
- 入口必跑 `_cleanup_phase14_test_data`
- 复用现有 conftest fixture `db_session` + `client` + `admin_user / manager_user / member_user`

### 3.11 fail-safe self-check(Codex 接手前必跑 10 项 grep 闸门)

```bash
# 1. 基线 commit 必须命中
git log --oneline | grep -E "chore\(spec\): T-1401" | head -1  # 必须有结果

# 2. T-1106 ProjectFollowUp 模型零改动
git diff HEAD~5..HEAD -- backend/app/models/project_followup.py | wc -l  # 必须 0

# 3. T-1201 ChatSession + ChatMessage 模型零改动
git diff HEAD~5..HEAD -- backend/app/models/chat_session.py backend/app/models/chat_message.py | wc -l  # 必须 0

# 4. T-1301 DailyReport + DailySupervisedTask 模型零改动
git diff HEAD~5..HEAD -- backend/app/models/daily_report.py backend/app/models/daily_supervised_task.py | wc -l  # 必须 0

# 5. T-1401 spec 文件存在
test -f docs/T-1401_spec.md && echo "OK"

# 6. 共享 6 模型零 ALTER
git diff HEAD~5..HEAD -- backend/app/models/{project,sprint,sprint_task,capacity,okr,kpi_target}.py | wc -l  # 必须 0

# 7. health_engine + AI + wechat 零改动
git diff HEAD~5..HEAD -- backend/app/services/{ai_engine,kr_progress_extractor,notification_service,token_guard,health_engine}.py backend/app/routers/wechat.py | wc -l  # 必须 0

# 8. 工作区遗留 = 接手时基线既定项(spec 落盘时 7 项:2 modified login/change-password + 3 untracked check_project/check_users/reset_admin + 2 untracked test_api/test_api2;PHASE14_REQUIREMENTS.md 在 chore(spec) 时已带走)
git status --short | grep -E "(M frontend/src/app/(login|change-password)/page.tsx|^\?\? backend/(check_project|check_users|reset_admin|test_api|test_api2).py)" | wc -l  # 必须 7

# 9. alembic heads 单头
cd backend && alembic heads | wc -l  # 必须 1

# 10. T-1401 spec docstring 含 11 决策签字
grep -c "决策签字" docs/T-1401_spec.md  # 必须 >= 1
```

---

## 4. 测试基线 + 闸门

- **后端测试基线**:T-1301 完工 `251 passed + 2 skipped` → T-1401 完工预期 `273 passed + 2 skipped`(+22 case)
- **质量闸门**(Codex 完工前 7 项必跑):
  1. `cd backend && .venv/bin/ruff check`(必 PASS,零 error)
  2. `cd backend && .venv/bin/mypy app/`(必 PASS,零 error)
  3. `cd backend && .venv/bin/pytest tests/test_phase14_milestone_contribution.py -q`(必 22 passed)
  4. `cd backend && .venv/bin/pytest tests/ -q`(必 273 passed + 2 skipped)
  5. `cd backend && alembic upgrade head → alembic downgrade -1 → alembic upgrade head`(必来回幂等,stdout 命中 `[T-1401 backfill]`)
  6. `cd frontend && npm run lint`(零 error)
  7. `cd frontend && npm run typecheck`(零 error)
- **alembic check** 沿用 T-1101/T-1102/T-1103 Supervisor 特批跳过 local DB drift 误报

---

## 5. 改动面文件清单(17 文件 + 6 边界冻结)

### 5.1 17 文件改动面

| # | 文件 | 操作 | 行数 |
|---|---|---|---|
| 1 | `backend/app/models/project_milestone.py` | 新建 | ~95 |
| 2 | `backend/app/models/milestone_allocation.py` | 新建 | ~80 |
| 3 | `backend/app/models/user_points_ledger.py` | 新建 | ~70 |
| 4 | `backend/app/models/project_member.py` | 改 | +8 |
| 5 | `backend/app/models/__init__.py` | 改 | +10 |
| 6 | `backend/alembic/versions/20260530_HHMM_phase14_milestone_contribution_points.py` | 新建 | ~260 |
| 7 | `backend/app/schemas/milestone.py` | 新建 | ~210 |
| 8 | `backend/app/services/milestone_template_service.py` | 新建 | ~110 |
| 9 | `backend/app/services/milestone_service.py` | 新建 | ~240 |
| 10 | `backend/app/routers/milestones.py` | 新建 | ~280 |
| 11 | `backend/app/routers/projects.py` | 改 | +~10 |
| 12 | `backend/app/schemas/project.py` | 改 | +~3 |
| 13 | `backend/app/main.py` | 改 | +5 |
| 14 | `backend/tests/test_phase14_milestone_contribution.py` | 新建 | ~520 |
| 15 | `frontend/src/api/projects.ts` | 改 | +~3 |
| 16 | `frontend/src/api/milestones.ts` | 新建 | ~140 |
| 17 | `frontend/src/app/admin/milestones/page.tsx` | 新建 | ~280 |
| 18 | `frontend/src/app/me/contribution/page.tsx` | 新建 | ~220 |
| 19 | `frontend/src/components/milestone-template-editor.tsx` | 新建 | ~150 |
| 20 | `frontend/src/app/dashboard/page.tsx` | 改 | +~30 |
| 21 | `frontend/src/app/projects/page.tsx` | 改 | +~30 |

(实际 21 文件 — feat commit 闭包;若 dashboard / projects 立项弹窗结构差异巨大无法同时嵌入,可降级为单一文件,留 backlog T-1402 补齐)

### 5.2 6 块边界冻结面(grep 闸门必须返回 0)

**触碰段 grep**(`git diff <baseline>..HEAD -- <files>` 必须 0 行):

```bash
# 块 1:T-1106 / T-1201 / T-1301 锁定文件
backend/app/models/project_followup.py
backend/app/models/chat_session.py
backend/app/models/chat_message.py
backend/app/models/daily_report.py
backend/app/models/daily_supervised_task.py

# 块 2:共享模型冻结
backend/app/models/project.py
backend/app/models/sprint.py
backend/app/models/sprint_task.py
backend/app/models/capacity.py
backend/app/models/okr.py
backend/app/models/kpi_target.py
backend/app/models/department.py
backend/app/models/notification.py
backend/app/models/attachment.py
backend/app/models/user.py
backend/app/models/audit_log.py

# 块 3:AI / 通知 / 健康度 / 企微 服务冻结
backend/app/services/ai_engine.py
backend/app/services/kr_progress_extractor.py
backend/app/services/notification_service.py
backend/app/services/token_guard.py
backend/app/services/health_engine.py
backend/app/routers/wechat.py
backend/app/routers/reports.py
backend/app/routers/chat.py

# 块 4:既有 schemas 冻结
backend/app/schemas/report.py
backend/app/schemas/morning_evening.py
backend/app/schemas/chat_session.py

# 块 5:既有测试 + 测试基础设施冻结
backend/tests/test_kpi_phase9.py
backend/tests/test_phase11_*.py
backend/tests/test_phase12_chat_sessions.py
backend/tests/test_phase13_daily_report_v2.py
backend/conftest.py
backend/tests/_isolation.py
backend/tests/_db_url.py
backend/pyproject.toml
backend/uv.lock
.env
.env.example
.env.production.template
README.md
DEPLOY.md

# 块 6:前端既有页面 + 依赖冻结
frontend/src/app/reports/page.tsx
frontend/src/app/submit-report/page.tsx
frontend/src/app/chat/page.tsx
frontend/src/app/login/page.tsx           # 注意:工作区已 modified,但是历史遗留不属 T-1401 改动
frontend/src/app/change-password/page.tsx # 同上
frontend/src/app/users/page.tsx
frontend/src/app/project/[id]/page.tsx
frontend/src/components/sidebar.tsx       # 若新页路由需挂入 sidebar,允许 +1~2 行,否则 0
frontend/src/components/member-picker.tsx
frontend/src/api/reports.ts
frontend/src/api/chat.ts
frontend/package.json
frontend/package-lock.json
```

---

## 6. 决策签字(指挥官 Auto Mode `[2026-05-29 17:08:53]`)

### 6.1 7 主决策(第一+二轮 AskUserQuestion 老板拍板)

| # | 决策项 | 选定方案 | 备选 | 理由 |
|---|---|---|---|---|
| A | 「积分」字段命名空间 | **全新独立命名 `contribution_points`** | 复用 `points` 加前缀 / 用 `value_credits` | 7 套 points/score 已混乱;贡献积分是财务级激励语义,必须切割避免错聚合 |
| B | 里程碑节点来源策略 | **预置模板 + 立项时可编辑** | 全硬编码 9 节点 / 完全空白手填 | 老板"自动带出标准节点"需求 + 临时工单/自定义场景兼顾 |
| C | 动态加减分(Penalty/Bonus)落点 | **单字段 final_points + 强制 adjustment_reason TEXT NOT NULL when delta** | 独立调整日志表 / 纯字段覆盖无 reason | 审计可解释 + 不引入新表 + 符合老板"动态加减分"业务述说 |
| D | dual 轨节点策略 | **dual = 软件 4 + 硬件 3 全展开 7 节点 admin 可删** | 二选一 / 暂不支持 dual | IoT 智能硬件项目主模式,双轨同时跑;admin 可删余下不需要的节点 |
| E | 验收审批角色链 | **3 层链:project member 发起 → tech_lead 分 ratio → admin 终批** | 2 层 / 1 层 | 最贴合老板"技术负责人分配 → 报批后入账"4 动作原文;tech_lead 用 enum 列识别 |
| F | contribution_ratio 总和校验 | **强制 ∑=100%(Pydantic + DB CHECK 双层)** | 允许 ≤100% 留公积金 / 完全自由 | 老板"分配个人贡献比例"暗示完整切分;财务对账可保证 |
| G | UserPointsLedger 流水表 | **同步建 ledger 表(income/refund/adjustment 3 类)** | 仅 MilestoneAllocation 累加 / Phase 15 再补 | 财务级激励本质需要流水追溯;Phase 15"个人总榜/季度贡献"可一句 SQL 算出 |

### 6.2 4 次级决策(指挥官 spec 内自决,老板未单独 veto)

| # | 决策项 | 选定方案 | 理由 |
|---|---|---|---|
| H | 技术负责人识别 | **新增 `ProjectMember.member_role` enum 列**(tech_lead/owner/member)+ migration backfill 全表 'member' | 不复用 `role_in_project` String(64) 自由文本,避免 T-1105 字段语义污染;新列零踩踏 |
| I | 临时工单/support/other 模板 | **默认 1 节点("完成",initial=0,custom 类型),admin 可改名/加节点(最多 3 节点)** | 老板"临时性任务也支持单一或自定义完成节点"原文;最少干预 |
| J | KPI 联动 | **本任仅落 MilestoneAllocation + Ledger,KPI metric 不动**;Phase 15 评估是否把"季度贡献积分"做 KPI 指标 | 防止与 T-908 metric 'objective_completion' 耦合;先 ship 价值流主轴 |
| K | 已审批 milestone 软作废 | **沿用 BaseMixin 软删体例:`status='void' + deleted_at=now()`**;**严禁** 硬删 status='approved' 的 milestone(物理保留;Ledger 也保留) | 财务追溯刚性需求;若必须冲销,走 revert_allocation 路径写 refund 行 |

### 6.3 5 次次级假设(无 veto 全部沿用)

| # | 假设 | 默认 | 是否在 spec 内可调 |
|---|---|---|---|
| L | ratio 精度 | NUMERIC(5,4) 千分位 | spec 内可改为 NUMERIC(7,6) 若老板要求百万分位 |
| M | 模板默认积分 | software 10/30/30/30,hardware 20/40/40,其他 0 | spec 内字面量;admin 立项时可改 |
| N | 流水分页 cursor | occurred_at iso string(简化版) | 后续 T-1402 改成签名 cursor |
| O | round 方式 | ROUND_HALF_UP(标准四舍五入) | spec 内字面量,不允许变 |
| P | revert 后能否重新 propose | 是(partial unique 索引允许 reverted 后新 pending 行) | spec 内字面量 |

---

## 7. Commit 计划(3 commit 闭环)

### 7.1 chore(lock) — 已由指挥官在 spec 起草前完成

```text
commit 6788bdf
作者: Claude(指挥官)
时间: [2026-05-29 17:08:53]
文件: docs/dev_tasks.md(+58 行 Phase 14 + T-1401 占位)
作用: 长耗时 spec 起草任务的物理加锁信号
```

### 7.2 chore(spec) — 本 spec 落盘 commit(指挥官)

```text
files: docs/dev_tasks.md(+~20 行 T-1401 完整摘要)+ docs/T-1401_spec.md(新建 ~1800 行)
作用: T-1401 契约起草完成,Codex 接手基线
```

**Codex 接手时** 探针:
```bash
git log --oneline -3
# 必须看到:
#   <hash> chore(spec): T-1401 契约起草 — Phase 14 里程碑+贡献积分激励
#   6788bdf chore(lock): T-1401 spec 起草开工 — Phase 14 价值流主轴启动
#   2a7a5df chore(progress): close T-1301 — Phase 13 第一任 日报重构闭环
```

### 7.3 chore(lock) — Codex 接手时

```text
[YYYY-MM-DD HH:MM:SS] (Codex 自填)
files: docs/dev_tasks.md(将 T-1401 task 状态从 In Progress by Claude 改为 In Progress by Codex)
作用: 接手物理 lock
```

### 7.4 feat — Codex 工程闭环

```text
[YYYY-MM-DD HH:MM:SS] (Codex 自填)
title: feat(milestones): T-1401 Phase 14 — 里程碑与贡献积分激励模块
files: 严格 17~21 文件(对齐 §5.1 清单)
约束:
  - 不夹带任何 §5.2 6 块边界文件
  - 不夹带工作区 5 项遗留(2 modified + 3 untracked)
  - 不夹带任何 backlog 议题(T-1107/T-1108/T-1202/T-1302/T-1402+)
```

### 7.5 chore(progress) — Codex 闭环战报

```text
[YYYY-MM-DD HH:MM:SS] (Codex 自填)
files: docs/dev_tasks.md 1 文件
body: 含完工实绩 4 项 + 严禁项 22 项遵守证据 + 7 闸门 PASS 证据 + 测试基线达成证据
```

---

## 8. 验收清单(指挥官二次验收 28 项)

### 8.1 改动面闸门(8 项)

1. ① Codex 4 commit 链路干净(spec 起草外加 lock + feat + progress 三 commit)
2. ② feat 严格 17~21 文件对齐 §5.1 文件清单
3. ③ chore(lock) + chore(progress) 各严格 1 文件 `docs/dev_tasks.md`
4. ④ §5.2 6 块边界 grep **完全空**(`git diff <baseline>..HEAD` 对所有 30+ 锁定文件 + 服务 + 测试基础设施 + 前端既有页 + 依赖 grep 0 行)
5. ⑤ §3.11 self-check 10 项探针 PASS
6. ⑥ Worker timestamp 三 commit 均带
7. ⑦ chore(progress) commit body 含完工实绩 4 项 + 严禁项 22 项遵守证据
8. ⑧ 工作区遗留 7 项保留未污染(2 modified `login/change-password` + 3 untracked `check_project/check_users/reset_admin` + 2 untracked `test_api/test_api2` — 全部接手时基线既定,与 T-1401 工程正交)

### 8.2 Migration + 数据层闸门(7 项)

9. ⑨ 命名 `20260530_HHMM_phase14_milestone_contribution_points.py`(HHMM 为 Codex 自填实际时间)
10. ⑩ `revision = "b9c0d1e2f3a4"` + `down_revision = "a8b9c0d1e2f3"` 精准承接 T-1301 head
11. ⑪ upgrade() 字面量全对齐 §3.1.6:5 PG ENUM + project_members 加 member_role 列 + 3 新表 + 11 FK 命名 + 9+ 索引 + 4 CHECK 约束
12. ⑫ Backfill stdout `[T-1401 backfill] members_updated=N` 命中
13. ⑬ downgrade() 反向 5 段完整,条件分支防重
14. ⑭ ProjectMilestone 4 关键字段(initial/final/adjustment_reason/status)+ 2 复合索引字面量对齐 §3.1.1
15. ⑮ MilestoneAllocation partial unique 索引 + 2 CHECK + AllocationStatus 3 角字面量对齐 §3.1.2;UserPointsLedger 3 索引 + amount!=0 CHECK + LedgerDirection 3 角字面量对齐 §3.1.3

### 8.3 Schema + Service + Router 闸门(8 项)

16. ⑯ `schemas/milestone.py` 14+ schemas 字面量对齐 §3.2;`AllocationProposalRequest.check_ratio_sum` model_validator 强制 ∑=1.0±0.0001 + 同 user_id 不重复
17. ⑰ `services/milestone_template_service.py` 5 轨字面量常量;`get_standard_template` dual 轨拼装 + is_temporary 优先逻辑
18. ⑱ `services/milestone_service.py` 7 函数;**核心** `approve_milestone` 同事务三步:UPDATE milestone → UPDATE allocations → INSERT Ledger 行 × N
19. ⑲ `routers/milestones.py` 3 sub-router(admin / project / me)+ 11 端点全部 RBAC 正确
20. ⑳ `routers/projects.py` create_project 末尾追加 `seed_milestones` 钩子(条件 True 时调 seed_project_milestones);**零** 改既有 members 创建逻辑 / update_project / followups
21. ㉑ `schemas/project.py` `ProjectCreateRequest.seed_milestones: bool = Field(default=True)` 字面量
22. ㉒ `main.py` 3 sub-router include 行字面量;**零** 改既有 18+ 路由注册顺序
23. ㉓ `services/milestone_service.approve_milestone` ROUND_HALF_UP 整数化逻辑

### 8.4 前端 + 测试闸门(4 项)

24. ㉔ `api/milestones.ts` 11 函数 + 14 interface 全在新文件;`api/projects.ts` 仅追加 `seed_milestones?: boolean`,既有函数零改动;`api/reports.ts` + `api/chat.ts` 零改动
25. ㉕ `app/dashboard/page.tsx` + `app/projects/page.tsx` 立项弹窗内嵌 `<MilestoneTemplateEditor>` 区段;**零** 改 MemberPicker / 既有列表 / 既有筛选;`app/admin/milestones/page.tsx` + `app/me/contribution/page.tsx` + `components/milestone-template-editor.tsx` 3 新文件
26. ㉖ `test_phase14_milestone_contribution.py` 22 case 命名 100% 对齐 §3.10 字面量(`grep -c "^async def test_" = 22`)+ 4 类分布严格(Model 4 + Template 3 + Service 5 + Router 10 = 22)
27. ㉗ 测试零 mock / 零 monkeypatch / 零 print / 零 logger / 零 skip / 零 xfail + `_phase14_*` 前缀 helpers + `_cleanup_phase14_test_data` 入口必跑

### 8.5 综合质量闸门(1 项)

28. ㉘ 指挥官本机抽样实测:`.venv/bin/ruff check` PASS / `.venv/bin/mypy` PASS / `pytest tests/test_phase14_milestone_contribution.py -q` 22 passed / `pytest -q` 全量 273 passed + 2 skipped / `alembic upgrade head → downgrade -1 → upgrade head` PASS 且 stdout 命中 `[T-1401 backfill]` / `cd frontend && npm run lint && npm run typecheck` PASS

---

## 9. 风险与 follow-up

### 9.1 风险

1. **R1 — 多人 ratio 校验 + 同事务 N+1 写 Ledger 的性能**:approve_milestone 在 N=20 时 1 milestone + 20 allocation update + 20 ledger insert = 41 写,在标准 Postgres 单事务下 100~300ms;production 可接受
2. **R2 — partial unique 索引 `status != 'reverted'` 与 `revert + 重新 propose` 的交互**:理论上允许 revert 后新 pending 行;但若 admin 在 reverted 状态下又 propose 同 user,partial unique 不阻止(因 status != 'reverted' 的行只剩 pending);此处假设业务流允许
3. **R3 — frontend 立项弹窗在 dashboard / projects 两处都需嵌入**:若两处 UI 结构差异巨大,可降级为单一文件(优先 dashboard),projects/page.tsx 留 backlog T-1402
4. **R4 — Ledger occurred_at vs created_at**:occurred_at 可手填(支持回填历史),但 backfill 工具不在本任范围;Phase 14 仅落 service 层支持
5. **R5 — `MemberProjectRole.tech_lead` 唯一性**:本任不强制"每项目至少 1 tech_lead";若立项时无 tech_lead 指定,milestones propose_allocations 端点会 403(workaround:admin 自己也可调 propose 端点)。建议 backlog T-1402 加 create_project 立项时强制 tech_lead 至少 1 人

### 9.2 backlog(明确不归本任)

- **T-1402**:立项时强制 tech_lead 至少 1 人 + 项目详情页加"里程碑" tab + 中后台导出 CSV
- **T-1403**:KPI metric 加 `contribution_points_total` 维度(联动 Phase 9 KpiTarget)
- **T-1404**:个人贡献账户加图表(月份/季度柱状图 + 项目占比饼图)
- **T-1405**:Ledger 历史 backfill 工具(从 Excel 导入)
- **T-1406**:Sprint / Project / 部门维度的贡献积分聚合排行榜
- **T-1407**:企微推送整合("您的里程碑[X]已终批入账 N 积分")

### 9.3 与 T-1106 / T-1201 / T-1301 关系

- **与 T-1106 ProjectFollowUp**:零耦合(督导跟进 vs 价值贡献 各自独立路径)
- **与 T-1201 ChatSession**:零耦合(AI 对话 vs 业务流水 不交叉)
- **与 T-1301 DailyReport + DailySupervisedTask**:零耦合(日报零选择 vs 节点积分 不交叉)
- **与 T-1105 ProjectMember**:仅加 member_role 新列,既有 role_in_project / track / joined_at / left_at 零改动

---

## 10. 关键决策记录

### 10.1 为什么用独立 ProjectMilestone 表而非给 ProjectStage 加 points 字段

- `ProjectStage` 是 IPD 五段(stage_number 1-5),语义是"项目当前在哪个阶段",有 `health_status` / `progress_pct` / `milestones JSONB`(硬件交付物清单)
- ProjectMilestone 是"激励节点容器",语义完全独立(可在同一 stage 内有多个 milestone;一个 milestone 可跨多个 stage)
- 若复用 ProjectStage 加 points 字段,会污染 IPD 五段语义 + 与 milestones JSONB 字段重复 + 无法支持临时工单单节点场景
- 独立表清晰隔离 + 未来可演化(如增加 milestone-stage 关联 JOIN)

### 10.2 为什么 `member_role` 用 PG native ENUM 而非 String + Check Constraint

- PG ENUM 类型安全(无法 INSERT 非法值)+ 自带索引友好(枚举值固定 → B-tree 性能最佳)
- String + CHECK 容易在前端 / API / DB 层各填一个值导致漂移(T-908 metric 漂移历史教训)
- 对齐 T-1201 ChatRole + T-1301 ReportType + 现有 ProjectStatus 体例

### 10.3 为什么 `contribution_ratio` 用 NUMERIC(5,4) 而非 FLOAT

- FLOAT 浮点误差累计:0.3 + 0.3 + 0.4 在 FLOAT 下可能 != 1.0(IEEE 754)
- NUMERIC(5,4) 精确十进制小数,DB 层校验 ∑=1.0 ± 0.0001 可 100% 可靠
- 千分位精度足够业务表达(0.001 = 0.1% 颗粒度;够用)

### 10.4 为什么 `final_points` 单字段覆盖 + reason 强制 而非独立调整日志表

- 调整日志表会让 schema +1 表 + service 层 +N 复杂度,但业务上"加减分"是**一次性决定**(admin 终批时一次性下定决心),不需要多轮预调
- 若未来真需要多轮预调,backlog T-140N 可补 MilestoneAdjustmentLog 表(独立追加,不破坏现有 schema)
- 当前方案:`adjustment_reason TEXT NOT NULL when delta != 0` 已满足审计可解释性

### 10.5 为什么 UserPointsLedger 是 append-only 而非可改可删

- 财务级激励本质需要时间线不可改(否则员工无法信任系统)
- append-only 让"个人贡献账户 = SUM(amount) GROUP BY user_id" 一句 SQL 即可,无需复杂去重逻辑
- 错误调整通过 adjustment 行实现:正向 income N → 负向 adjustment -M → 正向 adjustment K(三行流水)
- service 层无 update/delete 方法 + DB 层 amount != 0 CHECK 双重防御

### 10.6 为什么 seed_milestones 钩子放在 routers/projects.py create_project 末尾而非 main.py 事件订阅

- create_project 已是 admin/manager RBAC 路径,seed 业务天然属于"立项后置动作"
- 事件订阅(observer 模式)会引入 main.py 外部依赖 + 不易测试 + 异常处理复杂
- 直接调 service 函数:同事务保证(若 seed 失败,create_project 整个回滚)
- `seed_milestones: bool = True` 旧客户端兼容(默认 True,可显式关闭走 backlog 路径)

### 10.7 为什么 Ledger 不直接关联 SprintTask / DailyReport / ProjectFollowUp 等进度流实体

- 价值流(贡献积分)与进度流(日报、督导、Sprint 任务)**老板明确解耦并行**,Ledger 只关联 milestone + allocation,不下钻到进度实体
- 这样 milestone 的"业务定义"可以独立演化(如加"是否客户验收"字段),Ledger schema 不动
- 若未来需要"哪个 sprint task 触发了 milestone approval",在 milestone 层加 source_sprint_task_id 字段即可,Ledger 不动

---

## 📣 附录:给 Worker(Codex)的物理交接单

> **指挥官**:Claude `[2026-05-29 17:08:53]`
> **Worker**:Codex(接手时间待填)
> **基线 commit**:`<spec commit hash>`(本 spec 落盘 commit;Codex 接手前必探针确认)

### 物理交接单 9 步执行指令

#### Step 1:接手前置守卫

```bash
cd /Users/hycdq2026/Downloads/AI-PM-main

# 1. 探针 — git 真相
git status --short --branch
git log -5 --oneline

# 2. 必须命中 chore(spec): T-1401 commit
git log --oneline | grep -E "chore\(spec\): T-1401" | head -1

# 3. 必须命中 chore(lock): T-1401 commit(6788bdf)
git log --oneline | grep -E "chore\(lock\): T-1401" | head -1

# 4. T-1401 spec 文件必须存在
test -f docs/T-1401_spec.md && wc -l docs/T-1401_spec.md

# 5. T-1301 head 必须是当前 head(`a8b9c0d1e2f3`)
cd backend && .venv/bin/alembic heads
# 必须输出:a8b9c0d1e2f3 (head)

# 6. 工作区 5 项遗留确认
git status --short | grep -E "^( M|^\?\?) " | wc -l
# 必须 = 5 + docs/T-1401_spec.md 新增 0 行(若指挥官已 commit)

# 7. 锁定文件零改动(spec 起草期间)
git diff 2a7a5df..HEAD -- backend/app/models/project_followup.py backend/app/models/daily_report.py backend/app/models/chat_session.py | wc -l
# 必须 = 0

# 8. self-check 10 项见 §3.11(全部 PASS 再进入 Step 2)
```

#### Step 2:加锁(chore(lock) — Codex 接手 lock)

```bash
# 修改 docs/dev_tasks.md:把 T-1401 Task 9 状态从 "In Progress by Claude(指挥官)" 改为 "In Progress by Codex"
# 仅改 1 文件:docs/dev_tasks.md

git add docs/dev_tasks.md
git commit -m "chore(lock): T-1401 — Codex 接手工程执行

[YYYY-MM-DD HH:MM:SS]

Codex 接手 T-1401(Phase 14 第一任 — 里程碑与贡献积分激励),
spec 由指挥官已落盘,本 commit 为 Codex 工程执行 lock signal。
"
```

#### Step 3:数据层(4 模型 + __init__)

按 §3.1 字面量实现:
1. 新建 `backend/app/models/project_milestone.py`(~95 行,严格字面量对齐 §3.1.1)
2. 新建 `backend/app/models/milestone_allocation.py`(~80 行,严格字面量对齐 §3.1.2)
3. 新建 `backend/app/models/user_points_ledger.py`(~70 行,严格字面量对齐 §3.1.3)
4. 改 `backend/app/models/project_member.py`(+8 行,严格字面量对齐 §3.1.4)
5. 改 `backend/app/models/__init__.py`(+10 行,严格字面量对齐 §3.1.5;**严禁** 重排既有项)

```bash
# 闸门:
.venv/bin/ruff check app/models/{project_milestone,milestone_allocation,user_points_ledger,project_member,__init__}.py
.venv/bin/mypy app/models/{project_milestone,milestone_allocation,user_points_ledger,project_member,__init__}.py
```

#### Step 4:Migration + backfill

按 §3.1.6 字面量实现:
- 新建 `backend/alembic/versions/<YYYYMMDD>_<HHMM>_phase14_milestone_contribution_points.py`(~260 行)
- `revision = "b9c0d1e2f3a4"` + `down_revision = "a8b9c0d1e2f3"`
- upgrade:5 ENUM + project_members 加列 + backfill stdout `[T-1401 backfill] members_updated=N` + 3 表 + 11 FK + 9+ 索引 + 4 CHECK
- downgrade:反向 5 段完整

```bash
# 闸门:
cd backend && .venv/bin/alembic upgrade head      # 必 PASS,stdout 命中 [T-1401 backfill]
.venv/bin/alembic downgrade -1                     # 必 PASS
.venv/bin/alembic upgrade head                     # 必 PASS,再次命中 backfill
```

#### Step 5:Schemas + Template Service + Service + Router + main.py

按 §3.2~3.6 字面量实现:
1. 新建 `backend/app/schemas/milestone.py`(~210 行,14+ schemas + AllocationProposalRequest.check_ratio_sum + MilestoneApprovalRequest)
2. 新建 `backend/app/services/milestone_template_service.py`(~110 行,5 轨字面量 + get_standard_template)
3. 新建 `backend/app/services/milestone_service.py`(~240 行,7 函数 + ROUND_HALF_UP)
4. 新建 `backend/app/routers/milestones.py`(~280 行,3 sub-router + 11 端点 + 3 helpers)
5. 改 `backend/app/main.py`(+5 行,3 router include)

```bash
# 闸门:
.venv/bin/ruff check app/{schemas/milestone,services/milestone_template_service,services/milestone_service,routers/milestones,main}.py
.venv/bin/mypy app/{schemas/milestone,services/milestone_template_service,services/milestone_service,routers/milestones,main}.py
```

#### Step 6:projects.py 钩子 + schemas/project.py

按 §3.5 / §3.7 字面量实现:
1. 改 `backend/app/routers/projects.py` create_project 末尾追加 seed_milestones 钩子(+~8 行)
2. 改 `backend/app/schemas/project.py` `ProjectCreateRequest.seed_milestones` 字段(+~3 行)

**严禁** 改 create_project 现有 members 创建逻辑 / update_project / followups / 其他端点。

#### Step 7:前端 API + UI(7 文件)

按 §3.8 / §3.9 字面量实现:
1. 改 `frontend/src/api/projects.ts`(+~3 行)
2. 新建 `frontend/src/api/milestones.ts`(~140 行)
3. 新建 `frontend/src/components/milestone-template-editor.tsx`(~150 行)
4. 改 `frontend/src/app/dashboard/page.tsx`(+~30 行)
5. 改 `frontend/src/app/projects/page.tsx`(+~30 行)
6. 新建 `frontend/src/app/admin/milestones/page.tsx`(~280 行)
7. 新建 `frontend/src/app/me/contribution/page.tsx`(~220 行)

```bash
# 闸门:
cd frontend && npm run lint        # 零 error
npm run typecheck                   # 零 error
```

#### Step 8:测试 + 7 闸门

按 §3.10 字面量实现:
- 新建 `backend/tests/test_phase14_milestone_contribution.py`(~520 行 22 case)
- 私有 helpers `_phase14_*` 前缀
- 作用域 `wechat_userid like "phase14_%"` + `projects.code like "phase14_%"`
- 入口必跑 `_cleanup_phase14_test_data`

```bash
# 7 闸门:
cd backend
.venv/bin/ruff check                                         # PASS
.venv/bin/mypy app/                                          # PASS
.venv/bin/pytest tests/test_phase14_milestone_contribution.py -q  # 22 passed
.venv/bin/pytest tests/ -q                                   # 273 passed + 2 skipped
.venv/bin/alembic upgrade head → downgrade -1 → upgrade head # 来回幂等 + [T-1401 backfill] 命中
cd ../frontend && npm run lint                               # 零 error
npm run typecheck                                            # 零 error
```

#### Step 9:feat + chore(progress) 闭环

```bash
# feat commit
git add backend/app/models/{project_milestone,milestone_allocation,user_points_ledger,project_member,__init__}.py
git add backend/alembic/versions/<YYYYMMDD>_<HHMM>_phase14_milestone_contribution_points.py
git add backend/app/schemas/{milestone,project}.py
git add backend/app/services/{milestone_template_service,milestone_service}.py
git add backend/app/routers/{milestones,projects}.py
git add backend/app/main.py
git add backend/tests/test_phase14_milestone_contribution.py
git add frontend/src/api/{projects,milestones}.ts
git add frontend/src/components/milestone-template-editor.tsx
git add frontend/src/app/{dashboard,projects,admin/milestones,me/contribution}/page.tsx

# 严禁夹带:
git status --short | grep -E "^( M|^\?\?) " | grep -v "^M docs/dev_tasks.md" | grep -E "(login|change-password|check_project|check_users|reset_admin)"
# 必须 = 5 行(原工作区遗留,不在 git add 范围内)

git commit -m "feat(milestones): T-1401 Phase 14 — 里程碑与贡献积分激励模块

[YYYY-MM-DD HH:MM:SS]

Phase 14 价值流主轴启动:
- 3 新模型:ProjectMilestone(节点)/ MilestoneAllocation(分配)/ UserPointsLedger(流水)
- 5 PG ENUM:milestone_node_type(9 角)+ milestone_status(4 角)+ allocation_status(3 角)+ ledger_direction(3 角)+ member_project_role(3 角)
- 11 端点:templates/seed/list/create/patch/delete/request-review/allocations/approve/revert/me-contribution
- 22 case 全 PASS;全量 273 passed + 2 skipped(零回归)
- alembic upgrade-downgrade-upgrade PASS + [T-1401 backfill] 命中
- frontend lint/typecheck PASS

零踩踏 T-1104~T-1301 锁定文件;零改动 AI 服务+企微+共享模型+既有 schemas;
零夹带工作区 5 项遗留;零自启 T-1402+/T-1107+/T-1202+/T-1302+.

详见 docs/T-1401_spec.md §1-10 + 物理交接单 §📣
"

# chore(progress) commit
# 改 docs/dev_tasks.md:把 T-1401 task 状态从 In Progress by Codex 改为 Done by Codex + 完工实绩段
git add docs/dev_tasks.md
git commit -m "chore(progress): close T-1401 — Phase 14 第一任 里程碑+贡献积分激励闭环

[YYYY-MM-DD HH:MM:SS]

完工实绩:
- T-1401 工程严格 17~21 文件闭环(对齐 spec §5.1)
- 测试基线:T-1301 完工 251 → T-1401 完工 273 passed + 2 skipped(+22 case)
- 5 PG ENUM + 3 新表 + 1 列追加 + 11 端点 + 11 函数 + 7 服务 + 4 helpers
- 严禁项 22 项全部遵守(0 push / 0 stash / 0 amend / 0 rebase / 0 --no-verify / 0 锁定文件 drift / 0 工作区遗留 drift / 0 backlog 自启)
"
```

### Codex 接手红线(严禁项再确认 22 条)

(与 §2 字面量一致 — Codex 必须每步操作前 grep 自查)

### Codex 完工战报模板

```text
[YYYY-MM-DD HH:MM:SS]

T-1401 工程闭环:

Step 1 self-check 10 项:全部 PASS
Step 2 chore(lock):commit <hash>
Step 3 数据层(5 文件):commit pending
Step 4 migration:upgrade-downgrade-upgrade 来回幂等 + [T-1401 backfill] members_updated=N 命中
Step 5 schemas + services + router + main(7 文件):ruff/mypy PASS
Step 6 projects.py + schemas/project.py 钩子(2 文件):零踩踏既有逻辑
Step 7 前端(7 文件):lint + typecheck PASS
Step 8 测试 + 7 闸门:
  - test_phase14_milestone_contribution.py 22 passed
  - pytest 全量 273 passed + 2 skipped(零回归)
  - alembic 来回幂等 + backfill 命中
  - frontend lint/typecheck PASS
Step 9 feat + chore(progress) commit 落地

严禁项 22 项遵守证据:
  - git diff 检查无 §5.2 6 块边界文件改动
  - 工作区 5 项遗留状态 = 接手时
  - 无 backlog 议题自启
  - alembic heads 单头(b9c0d1e2f3a4)

等待指挥官二次验收(28 项 §8)。
```

---

**T-1401 契约结束 — 总长 ~1800 行 10 章 + 📣 附录物理交接单 — 指挥官 Claude `[2026-05-29 17:08:53]` 落盘**
