# T-1301 契约 — Phase 13 第一任:日报重构 — 零选择智能铺盘 + 晨晚闭环 + 督导追踪

> **指挥官**:Claude(架构师 / Commander) `[2026-05-29 12:05:18]`
> **Worker**:Codex(待接手)
> **基线 commit**:`ade1163 chore(spec): T-1201 契约起草`(T-1201 spec 已落盘,工程未执行;本任独立编排,与 T-1201 双线并行)
> **隶属阶段**:Phase 13(本任为 Phase 13 启动任,先于所有 Phase 11/12 candidates T-1107/T-1108/T-1202)
> **老板原话**:`docs/T-1301_spec.md` §1.1 + 老板蓝图 `gemini/antigravity-ide/brain/.../implementation_plan.md`(57 行 4 段)
> **预计改动面**:**10 src/test/migration 文件**(后端 5 + 前端 2 + 测试 1 + migration 1 + 文档 1)
> **测试基线**:T-1106 完工 220 → T-1301 完工预期 `236 passed + 2 skipped`(+16 case)
> **质量闸门基线**:`ruff` PASS / `mypy` PASS / `pytest -q` PASS / `alembic upgrade-downgrade-upgrade` 来回幂等 / frontend `npm run lint && npm run typecheck` PASS
> **Auto Mode 决策签字数**:6(详见 §6)

---

## 1. 任务背景与业务需求

### 1.1 老板原话(`[2026-05-29 12:02:00]`)+ 蓝图蓝本

> 老板追加新需求(请开启 **Phase 13**):重构日报模块,实现"**零选择智能铺盘**"、"**多任务标签化批量填报**"与"**晨晚闭环**"。
>
> 要求:
> 1. **晨规划(零选择)**:彻底废弃项目下拉选择框。页面加载时,直接列出该员工名下所有执行中的项目和 Sprint 任务。员工只需勾选今天要做的事并点选固化标签(工作类型等),即可一键批量提交。
> 2. **晚复核(自动对账)**:自动列出晨规划的对应任务,员工直接点选结果状态。新增的自主内容允许自己手工增加。
> 3. **督导追踪闭环**:晚复核标记为已完成的任务自动归类;未实现/延期的任务必须自动推送到项目的"督导追踪(follow-ups)"列表中,并在次日晨规划强制督导持续跟进,直至完成。
>
> 请起草详细的 T-1301_spec.md,规划"我的活跃项目"拉取接口、表结构(区分早晚/关联字段)和业务接口逻辑,并在看板中留下发给 Codex 的接手指令。

**老板蓝图四段(原始 `implementation_plan.md` 简化)**:
- ① 零选择智能拉取:废弃下拉 → 自动铺盘 → 一键勾选
- ② 晨晚闭环对账:自动拉晨规划 → 点选完成情况 → 自主追加
- ③ 督导跟进机制:未完任务 → ProjectFollowUp + 次日强制顶置 → 直至闭环
- ④ 后端支持:`/projects/my-active` + `/reports/today-plan` + `/reports/evening-batch` 三接口 + DailyReport `report_type / parent_plan_id / status` 字段

### 1.2 当前痛点(从 `routers/reports.py` + `models/daily_report.py` + `app/submit-report/page.tsx` 现状读盘)

**痛点 1 — 文本前缀粗暴区分早晚**:
- `routers/reports.py:523` `DailyReport.raw_input_text.like("[晨规划]%")` 用文本前缀做硬编码区分,**脆弱且无法被结构化查询利用**
- 历史日报有部分无前缀(走 `/web-submit` AI 解析路径)→ 默认归类困难,统计漏洞
- 当文本前缀拼错(如 `[晨规划:]` 或 `【晨规划】`)→ 直接漏统计

**痛点 2 — 单条下拉选择繁琐**:
- `app/submit-report/page.tsx:L64-100` 当前为典型「项目下拉 → Sprint 任务下拉」结构
- 员工每天必须经过:选项目 → 等加载任务 → 选任务 → 填表单 → 提交,**5 步交互,体感笨重**
- 蓝图明确"让系统找人,而不是让人找系统",**应反向**

**痛点 3 — 晨晚无强关联**:
- 当前 `DailyReport` 表**无 `parent_plan_id` 字段**,晚复核与晨规划只能通过 `report_date + user_id` 软关联
- 一旦员工早上发了两份晨规划(如再补充一条),晚复核无法精确锁定要对账哪一份
- 老板需求 #2 "自动列出晨规划的对应任务" 需精确指引,文本对照不可靠

**痛点 4 — 督导追踪机制缺位**:
- T-1106 完成的 `ProjectFollowUp` 表是**通用项目跟进**(主干 + 临时共享),**无类型区分**
- 若直接把"未完成日报"灌进 ProjectFollowUp,与人工跟进笔记混杂,**无法独立查询/督导闭环统计**
- 老板需求 #3 "次日晨规划强制顶置,直至彻底闭环" 需独立的"督导任务"状态机

### 1.3 业务三件套(本任交付范围)

| 编号 | 需求 | 实现路径 | 覆盖范围 |
|---|---|---|---|
| ① | **零选择智能铺盘 + 多任务标签批量** | 新增 `GET /api/v1/projects/my-active`(聚合 ProjectMember + Project + SprintTask)+ 前端废下拉改卡片打勾 + 工作类型标签固化 8 个 + 新增 `POST /api/v1/reports/morning-batch`(批量 INSERT,单事务) | DailyReport 扩 `report_type ENUM + work_tags ARRAY` |
| ② | **晚复核自动对账** | 重构 `GET /api/v1/reports/today-plan` 改用 `report_type='morning_plan'` ENUM 字段 + 新增 `POST /api/v1/reports/evening-batch`(参考 morning_plan id 自动建 evening_review 行)+ `DailyReport.parent_plan_id` self-FK | DailyReport 扩 `parent_plan_id + planned_status ENUM` |
| ③ | **督导追踪闭环 + 次日顶置** | 新建独立 `DailySupervisedTask` 关联表(承接督导溯源 + 状态机 open/closed + 自动闭合)+ evening-batch 内嵌督导推送逻辑 + 新增 `GET /api/v1/reports/pending-follow-ups`(次日晨规划查 open 督导)+ 同步 INSERT `ProjectFollowUp`(复用 T-1106 表,但**仅 INSERT 不 SELECT**) | 新表 + 关联 ProjectFollowUp **零模型踩踏** |

### 1.4 触碰段说明(防 T-1104/T-1105/T-1106/T-1201 文件踩踏)

| 文件 | T-1104/1105/1106/1201 触碰史 | T-1301 触碰段 | 风险防御 |
|---|---|---|---|
| `backend/app/models/__init__.py` | T-1104 添 `Department` / T-1106 添 `ProjectFollowUp` / T-1201 添 `ChatSession+ChatMessage+ChatRole`(待 Codex 落 T-1201) | **仅插入式追加** `DailySupervisedTask` + `ReportType` + `PlannedStatus` 3 项 import + 3 项 `__all__` | 严禁 重排现有项;严禁 修改 T-1104/1105/1106/1201 添加的行 |
| `backend/app/models/daily_report.py` | 未触碰 | **改 +4 字段**(`report_type / parent_plan_id / planned_status / work_tags`)+ ENUM 2 个新建在文件头部 | 不动现有 `parsed_content / pass_check / project_id / sprint_task_id / mentioned_task_ids / deleted_at` 字段 |
| `backend/app/models/project_followup.py` | T-1106 新建 | **零改动**(本任仅 INSERT,严禁 ALTER 字段) | BLOCKER 红线 |
| `backend/app/routers/reports.py` | 未触碰 | **改 today-plan 端点重构 + 新增 4 端点 + 2 私有 helper**(本任 owner,**严禁** 改 web-submit AI 路径 / list_reports / batch_soft_delete / batch_restore / get_report_detail) | 触碰段精准锁定 |
| `backend/app/routers/projects.py` | T-1105 改(create_project 加 members)/ T-1106 改(update_project 临时工单守卫 + followups 2 端点) | **零改动**(my-active 端点放在 reports.py 内,**不**新增到 projects.py;蓝图 #4 mentioned 但本任决策选 reports.py) | 严守 |
| `backend/app/schemas/report.py` | 未触碰 | **新建 `backend/app/schemas/morning_evening.py`** 独立 module(8 schemas Pydantic V2),**不**改 `report.py`(避免与 ParsedContent / AIParseResult AI 路径耦合) | 完全独立 |
| `backend/alembic/versions/` | T-1104 / T-1106 各 1 / T-1201 待 Codex 落 | **新建** `20260530_HHMM_phase13_daily_report_morning_evening.py` | `down_revision` Codex 接手时探针 `alembic heads` 二次核验 |
| `frontend/src/api/reports.ts` | 未触碰 | **改**(+5 函数 + 5 interface)| 不动现有 5 个函数 |
| `frontend/src/app/submit-report/page.tsx` | 未触碰 | **完全重构**(本任 owner)| 废现有项目/Sprint 下拉;但需保留**自由文本备用模式**(`inputStyle='free'` legacy fallback)以防回滚需求 |
| `frontend/src/app/reports/page.tsx` | 未触碰 | **零改动**(后台报告管理页,与员工填报无关) | BLOCKER 红线 |
| `backend/app/routers/wechat.py` | 未触碰 | **零改动**(企微入口路径独立,本任仅面向 Web 端) | BLOCKER 红线 |
| `backend/app/services/ai_engine.py` | 未触碰 | **零改动**(AI 解析仅 web-submit 路径使用,本任零依赖) | BLOCKER 红线 |

---

## 2. 严禁项(BLOCKER 红线 — 16 条)

1. ❌ **严禁** 基线 commit 错误。本任基线 = `ade1163 chore(spec): T-1201 契约起草`(T-1201 spec 已落盘 commit)。Codex 接手前必跑探针 `git log --oneline | grep "chore(spec): T-1201"`,**必须命中**才能开工。
2. ❌ **严禁** 修改 T-1104 / T-1105 / T-1106 / T-1201 任何锁定文件(详见 §1.4 表):特别是 `backend/app/models/project_followup.py`(T-1106) / T-1201 待 Codex 落的所有文件。
3. ❌ **严禁** 改 `backend/conftest.py` / `backend/tests/_isolation.py` / `backend/tests/_db_url.py`(T-1102/T-1103 已闭环)。
4. ❌ **严禁** 改 `backend/.env*` / `README.md` / `DEPLOY.md`(T-1102 已闭环)。
5. ❌ **严禁** 改 `backend/app/services/ai_engine.py` / `backend/app/services/kr_progress_extractor.py` / `backend/app/services/notification_service.py` / `backend/app/services/token_guard.py`(AI 解析路径完全不动)。
6. ❌ **严禁** 改 `backend/app/routers/wechat.py`(企微入口完全不动)。
7. ❌ **严禁** 改 `backend/app/routers/reports.py:web_submit_daily_report` 函数体(AI 解析路径走老路;本任不改它的实现,**仅在文件内追加新端点**)。
8. ❌ **严禁** 改 `backend/app/routers/reports.py:list_reports / batch_soft_delete_reports / batch_restore_reports / get_report_detail` 4 函数(回收站 / 详情面不动)。
9. ❌ **严禁** 改 `backend/app/schemas/report.py`(ParsedContent / AIParseResult 完全不动,新 schemas 独立 module)。
10. ❌ **严禁** 改 `frontend/src/app/reports/page.tsx`(后台管理页与员工填报无关)。
11. ❌ **严禁** 改 `backend/app/models/project_followup.py` / `project.py` / `project_member.py` / `sprint_task.py` 等共享模型字段(仅消费现有字段,**绝对零** ALTER)。
12. ❌ **严禁** 改 `backend/pyproject.toml` / `backend/requirements.txt` / `backend/uv.lock` / `frontend/package.json` / `frontend/package-lock.json`(本任零依赖新增)。
13. ❌ **严禁** 改 `backend/app/routers/projects.py`(蓝图 #4 mentioned 的 my-active 端点决策放 reports.py,详见 §6 第 5 条)。
14. ❌ **严禁** `git push` / `git stash` / `git rebase` / `git commit --amend` / `--no-verify`。
15. ❌ **严禁** 自启 T-1107 / T-1108 / T-1202 / T-1203 / T-1302 / 其他 Phase 11/12/13 backlog 议题。本任**单点闭环**。
16. ❌ **严禁** 改工作区**遗留** 5 项(`frontend/src/app/{change-password,login}/page.tsx` 2 modified + `backend/{check_project,check_users,reset_admin}.py` 3 untracked)。**与 T-1301 无关**,留待用户决策。

---

## 3. 实施方案

### 3.1 数据层

#### 3.1.1 改 `backend/app/models/daily_report.py`(+4 字段 + 2 ENUM)

**改动锚点**:在文件头部加 2 个 `enum.Enum` 类;在 `DailyReport` 类内 `mentioned_task_ids` 之后(L57-61)、`project_id` 之前(L66)插入 4 个新字段。

**字面量(严格追加在现有 imports 之后,L27 之后)**:

```python
import enum

# ... existing imports above ...

class ReportType(str, enum.Enum):
    """T-1301: 日报类型严格三角(优雅化原文本前缀 [晨规划]/[晚复盘])"""
    morning_plan = "morning_plan"      # 晨规划:零选择批量提交
    evening_review = "evening_review"  # 晚复核:对账 + 新增自主内容
    ad_hoc = "ad_hoc"                  # 其他:历史数据 / web-submit AI 解析 / 企微 / 临时补录


class PlannedStatus(str, enum.Enum):
    """T-1301: 晚复核对每个晨规划任务的状态四角"""
    done = "done"          # 已完成 — 自动归类
    partial = "partial"    # 部分完成 — 推送 ProjectFollowUp 督导
    delayed = "delayed"    # 延期 — 推送 ProjectFollowUp 督导
    cancelled = "cancelled"  # 取消 — 不推送,记录在案
```

**`DailyReport` 类内新增字段(严格插入位置:`mentioned_task_ids` L57-61 之后,`project_id` L66 之前)**:

```python
    # ── T-1301: 晨晚闭环 + 督导追踪字段 ──────────────────────────────
    # report_type 优雅化原 raw_input_text 文本前缀 [晨规划] / [晚复盘]
    # 历史数据 backfill:LIKE "[晨规划]%" → morning_plan / LIKE "[晚复盘]%" → evening_review / 其余 → ad_hoc
    report_type: Mapped[ReportType] = mapped_column(
        Enum(ReportType, name="daily_report_type", native_enum=True),
        default=ReportType.ad_hoc,
        server_default="ad_hoc",
        nullable=False,
        index=True,
        comment="日报类型(T-1301):晨规划/晚复核/其他",
    )

    # parent_plan_id 仅 evening_review 行使用,精确对账对应 morning_plan 行
    parent_plan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="晚复核引用的晨规划日报 ID(T-1301):仅 report_type=evening_review 填充",
    )

    # planned_status 仅 evening_review 行使用,标识该条复核的完成状态
    planned_status: Mapped[Optional[PlannedStatus]] = mapped_column(
        Enum(PlannedStatus, name="daily_report_planned_status", native_enum=True),
        nullable=True,
        index=True,
        comment="复核结果状态(T-1301):仅 report_type=evening_review 填充;partial/delayed 触发督导追踪",
    )

    # work_tags 仅 morning_plan / evening_review / ad_hoc 共享:固化标签
    # 初版 8 个候选:研发 / 测试 / 评审 / 部署 / 沟通 / 调研 / 文档 / 学习
    work_tags: Mapped[Optional[list[str]]] = mapped_column(
        ARRAY(String),
        nullable=True,
        default=list,
        server_default="{}",
        comment="工作类型固化标签数组(T-1301):前端固化 8 候选,后端零业务校验",
    )
```

**`Enum` 与 `ARRAY` import** 已存在(L22 + L23),**严禁** 重复 import。

**`__repr__` 不动**(L89-90)。

**字面量约束**:
- ENUM 名 `daily_report_type` + `daily_report_planned_status`(PG native ENUM,对齐 `OKRStatus / TaskStatus / SprintStatus` 体例)
- `parent_plan_id` self-FK + `ON DELETE SET NULL`(避免循环 cascade;若晨规划被删,晚复核行保留但失去关联)
- `work_tags ARRAY(String) + default=list`(前端固化候选,后端零校验,允许未来扩展)
- 默认值 `report_type=ad_hoc + server_default="ad_hoc"` 保证 Migration upgrade 时既有行不 NOT NULL 违反
- 索引 `report_type / parent_plan_id / planned_status` 各 1 个(B-tree),覆盖 today-plan / morning-batch / evening-batch / pending-follow-ups 端点的主查询 pattern

#### 3.1.2 新建 `backend/app/models/daily_supervised_task.py`(~95 行)

**职责**:独立关联表承接督导追踪溯源 — 关联到具体 `daily_reports.id`(被督导的复核记录)+ 关联到 `project_follow_ups.id`(T-1106 自动写入的跟进文本)+ 状态机 `open/closed` + 自动闭合 `closed_by_report_id`。

**字面量(对齐 T-1106 `ProjectFollowUp` 体例)**:

```python
"""
app/models/daily_supervised_task.py — 督导追踪溯源关联(T-1301)

桥接「晚复核未完成任务」与「项目跟进 ProjectFollowUp(T-1106)」+ 「次日晨规划顶置」:
  - 晚复核标记 partial/delayed 时,evening-batch 内自动 INSERT 一条 DailySupervisedTask
    + 同步 INSERT 一条 ProjectFollowUp(content 含 [督导] 前缀以兼容人工阅读)
  - 次日晨规划查 status='open' 的 DailySupervisedTask 顶置显示
  - 后续某天晨规划/晚复核同一员工在同一 source_report_id 下打勾完成 → 自动 closed

设计:
  - 不修改 T-1106 ProjectFollowUp 模型字段(BLOCKER 红线)
  - DailySupervisedTask 是独立 module,通过 FK 软关联 ProjectFollowUp
  - state 机:open(默认) ↔ closed(closed_at + closed_by_report_id 填充)
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base_mixin import BaseMixin


class SupervisedStatus(str, enum.Enum):
    open = "open"      # 督导追踪进行中 — 次日晨规划顶置
    closed = "closed"  # 已闭环 — 不再次日顶置


class DailySupervisedTask(BaseMixin, Base):
    __tablename__ = "daily_supervised_tasks"
    __table_args__ = (
        Index(
            "ix_daily_supervised_tasks_user_status_active",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_daily_supervised_tasks_project_status",
            "project_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="被督导用户(从晚复核行的 user_id 继承)",
    )

    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
        comment="督导所属项目(若晚复核行带 project_id 则继承;否则 NULL)",
    )

    sprint_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sprint_tasks.id", ondelete="SET NULL"),
        nullable=True,
        comment="督导关联的 Sprint 任务(若晚复核行带 sprint_task_id 则继承)",
    )

    source_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="触发督导的晚复核日报 ID(evening_review 行)",
    )

    project_followup_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("project_follow_ups.id", ondelete="SET NULL"),
        nullable=True,
        comment="同步写入的 ProjectFollowUp 跟进记录 ID(T-1106 表;允许 NULL 兼容补录场景)",
    )

    status: Mapped[SupervisedStatus] = mapped_column(
        Enum(SupervisedStatus, name="supervised_status", native_enum=True),
        default=SupervisedStatus.open,
        server_default="open",
        nullable=False,
        index=True,
    )

    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="闭环时间;非 NULL ↔ status=closed",
    )

    closed_by_report_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("daily_reports.id", ondelete="SET NULL"),
        nullable=True,
        comment="闭环触发的日报 ID(后续某次晚复核或晨规划完成同一 source_report_id 任务)",
    )

    # NOTE: created_at, updated_at, created_by, tenant_id 由 BaseMixin 提供

    def __repr__(self) -> str:
        return f"<DailySupervisedTask user={self.user_id} status={self.status.value} source={self.source_report_id}>"
```

**关键设计点**:
- **零 ProjectFollowUp 模型踩踏**:T-1106 表保持原样,本任仅通过 `project_followup_id` FK 软关联 + `INSERT` 同步写入
- **状态机简单**:`open ↔ closed` 二态,避免 over-engineering(老板未要求"暂缓 / 转交"等额外态)
- **复合索引 `(user_id, status, created_at)`**:次日晨规划查询 `WHERE user_id=? AND status='open' ORDER BY created_at` 的覆盖索引
- **复合索引 `(project_id, status)`**:项目级督导列表(可选 T-1302 backlog)
- **`source_report_id ON DELETE CASCADE`**:若晚复核行被软删 → 督导记录自动清除(语义合理:被删的复核没有督导意义);**注意** DailyReport 用软删 `deleted_at` 而非硬 DELETE,CASCADE 仅在物理 DELETE 时触发,日常软删不会动督导
- **`project_followup_id ON DELETE SET NULL`**:T-1106 followup 被(将来)硬删时,本表保留 + 失联但不级联消失
- **`closed_by_report_id`**:闭环溯源,审计回溯"哪一份新日报关闭了这条督导"

#### 3.1.3 改 `backend/app/models/__init__.py`(+5 行,严格插入式)

**改动锚点**(从 T-1106 后状态 L40-44):

```python
# --- IPD 项目管理模型 ---
from app.models.project import Project
from app.models.project_followup import ProjectFollowUp
from app.models.project_member import ProjectMember
from app.models.project_stage import ProjectStage
```

**在 `from app.models.project_stage import ProjectStage` 之后追加**(防止与 T-1106 / T-1201 行冲突;**注意** T-1201 添加 ChatSession + ChatMessage + ChatRole 时也在该位置之后插入,Codex 接手 T-1301 时若 T-1201 已先落,本任插入位置自动后移到 T-1201 行之后,**无需手工调整顺序**):

```python
# --- 日报模型 ---
from app.models.daily_report import DailyReport, PlannedStatus, ReportType
from app.models.daily_supervised_task import DailySupervisedTask, SupervisedStatus
```

**字面量约束**:
- 若 `daily_report` 已有现有 import 行(grep 校验)→ 在原行替换为 `from app.models.daily_report import DailyReport, PlannedStatus, ReportType`(同一行扩 import)
- `__all__` 列表追加在最末尾:`"DailyReport"`(若已存在则跳过)+ `"DailySupervisedTask"` + `"ReportType"` + `"PlannedStatus"` + `"SupervisedStatus"`,**不动** 现有项顺序

#### 3.1.4 新建 Migration `backend/alembic/versions/20260530_HHMM_phase13_daily_report_morning_evening.py`(~190 行)

**`HHMM`** Codex 接手时按系统时间填(例如 `20260530_1500_phase13_daily_report_morning_evening.py`)。

**revision 链定锚**:
- `revision = "a8b9c0d1e2f3"`(本任 head — 12 字符 hex,沿用 T-1104/T-1106/T-1201 风格)
- `down_revision = "e6f7a8b9c0d1"`(T-1106 head;Codex 接手时探针 `alembic heads` 二次核验;**若 T-1201 已先落 head=`f7a8b9c0d1e2`,Codex 应改 down_revision 为 `f7a8b9c0d1e2`**)

**upgrade 字面量**:

```python
"""Phase 13 T-1301: 日报晨晚闭环 + 督导追踪(report_type/parent_plan_id/planned_status/work_tags + DailySupervisedTask)

Revision ID: a8b9c0d1e2f3
Revises: e6f7a8b9c0d1   # 若 T-1201 已先落则改为 f7a8b9c0d1e2
Create Date: 2026-05-30 HH:MM:00

T-1301 零选择 + 晨晚闭环 + 督导追踪:
  - 新建 daily_report_type ENUM(morning_plan/evening_review/ad_hoc)
  - 新建 daily_report_planned_status ENUM(done/partial/delayed/cancelled)
  - 新建 supervised_status ENUM(open/closed)
  - 扩 daily_reports 表 4 列(report_type/parent_plan_id/planned_status/work_tags)
  - 回填历史 raw_input_text 文本前缀 → report_type ENUM
  - 新建 daily_supervised_tasks 表 + 4 索引(user_id + project_id + source_report_id + 复合 user_status_active + project_status)
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "e6f7a8b9c0d1"  # T-1106 head;若 T-1201 已先落则 Codex 改为 f7a8b9c0d1e2
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ── 1. 3 个 PG ENUM(条件分支防重) ────────────────────────
    existing_enums = {row[0] for row in bind.execute(sa.text(
        "SELECT typname FROM pg_type WHERE typtype='e'"
    )).fetchall()}

    report_type_enum = postgresql.ENUM(
        "morning_plan", "evening_review", "ad_hoc",
        name="daily_report_type",
        create_type=False,
    )
    if "daily_report_type" not in existing_enums:
        report_type_enum.create(bind, checkfirst=False)

    planned_status_enum = postgresql.ENUM(
        "done", "partial", "delayed", "cancelled",
        name="daily_report_planned_status",
        create_type=False,
    )
    if "daily_report_planned_status" not in existing_enums:
        planned_status_enum.create(bind, checkfirst=False)

    supervised_status_enum = postgresql.ENUM(
        "open", "closed",
        name="supervised_status",
        create_type=False,
    )
    if "supervised_status" not in existing_enums:
        supervised_status_enum.create(bind, checkfirst=False)

    # ── 2. daily_reports 扩 4 列(条件分支防重) ───────────────
    daily_reports_columns = {column["name"] for column in inspector.get_columns("daily_reports")}

    if "report_type" not in daily_reports_columns:
        op.add_column(
            "daily_reports",
            sa.Column(
                "report_type",
                postgresql.ENUM(name="daily_report_type", create_type=False),
                nullable=False,
                server_default="ad_hoc",
                comment="日报类型(T-1301):晨规划/晚复核/其他",
            ),
        )
        op.create_index("ix_daily_reports_report_type", "daily_reports", ["report_type"])

    if "parent_plan_id" not in daily_reports_columns:
        op.add_column(
            "daily_reports",
            sa.Column(
                "parent_plan_id",
                postgresql.UUID(as_uuid=True),
                nullable=True,
                comment="晚复核引用的晨规划日报 ID(T-1301)",
            ),
        )
        op.create_foreign_key(
            "fk_daily_reports_parent_plan_id",
            "daily_reports", "daily_reports",
            ["parent_plan_id"], ["id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_daily_reports_parent_plan_id", "daily_reports", ["parent_plan_id"])

    if "planned_status" not in daily_reports_columns:
        op.add_column(
            "daily_reports",
            sa.Column(
                "planned_status",
                postgresql.ENUM(name="daily_report_planned_status", create_type=False),
                nullable=True,
                comment="复核结果状态(T-1301)",
            ),
        )
        op.create_index("ix_daily_reports_planned_status", "daily_reports", ["planned_status"])

    if "work_tags" not in daily_reports_columns:
        op.add_column(
            "daily_reports",
            sa.Column(
                "work_tags",
                postgresql.ARRAY(sa.String()),
                nullable=True,
                server_default="{}",
                comment="工作类型固化标签数组(T-1301)",
            ),
        )

    # ── 3. 历史 raw_input_text 前缀回填 report_type ──────────
    op.execute(sa.text("""
        UPDATE daily_reports
           SET report_type = 'morning_plan'
         WHERE raw_input_text LIKE '[晨规划]%%'
           AND report_type = 'ad_hoc'
    """))
    op.execute(sa.text("""
        UPDATE daily_reports
           SET report_type = 'evening_review'
         WHERE raw_input_text LIKE '[晚复盘]%%'
           AND report_type = 'ad_hoc'
    """))
    # stdout dry-run 报告(参考 T-1104 backfill 体例)
    morning_count = bind.execute(sa.text(
        "SELECT COUNT(*) FROM daily_reports WHERE report_type='morning_plan'"
    )).scalar() or 0
    evening_count = bind.execute(sa.text(
        "SELECT COUNT(*) FROM daily_reports WHERE report_type='evening_review'"
    )).scalar() or 0
    ad_hoc_count = bind.execute(sa.text(
        "SELECT COUNT(*) FROM daily_reports WHERE report_type='ad_hoc'"
    )).scalar() or 0
    print(f"[T-1301 backfill] morning_plan={morning_count} / evening_review={evening_count} / ad_hoc={ad_hoc_count}")

    # ── 4. daily_supervised_tasks 表 ────────────────────────
    if "daily_supervised_tasks" not in inspector.get_table_names():
        op.create_table(
            "daily_supervised_tasks",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("sprint_task_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_report_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_followup_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "status",
                postgresql.ENUM(name="supervised_status", create_type=False),
                nullable=False,
                server_default="open",
            ),
            sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("closed_by_report_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("tenant_id", sa.String(length=64), server_default=sa.text("'default'"), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_supervised_tasks_user_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name="fk_supervised_tasks_project_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["sprint_task_id"], ["sprint_tasks.id"], name="fk_supervised_tasks_sprint_task_id", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["source_report_id"], ["daily_reports.id"], name="fk_supervised_tasks_source_report_id", ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_followup_id"], ["project_follow_ups.id"], name="fk_supervised_tasks_project_followup_id", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["closed_by_report_id"], ["daily_reports.id"], name="fk_supervised_tasks_closed_by_report_id", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_supervised_tasks_created_by", ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    supervised_indexes = set()
    if "daily_supervised_tasks" in inspector.get_table_names():
        supervised_indexes = {idx["name"] for idx in inspector.get_indexes("daily_supervised_tasks")}
    for index_name, cols in (
        ("ix_daily_supervised_tasks_user_id", ["user_id"]),
        ("ix_daily_supervised_tasks_project_id", ["project_id"]),
        ("ix_daily_supervised_tasks_source_report_id", ["source_report_id"]),
        ("ix_daily_supervised_tasks_status", ["status"]),
        ("ix_daily_supervised_tasks_tenant_id", ["tenant_id"]),
        ("ix_daily_supervised_tasks_user_status_active", ["user_id", "status", "created_at"]),
        ("ix_daily_supervised_tasks_project_status", ["project_id", "status"]),
    ):
        if index_name not in supervised_indexes:
            op.create_index(index_name, "daily_supervised_tasks", cols)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 反向 4 步:索引 → 表 → daily_reports 列 → ENUM
    if "daily_supervised_tasks" in inspector.get_table_names():
        existing = {idx["name"] for idx in inspector.get_indexes("daily_supervised_tasks")}
        for name in (
            "ix_daily_supervised_tasks_project_status",
            "ix_daily_supervised_tasks_user_status_active",
            "ix_daily_supervised_tasks_tenant_id",
            "ix_daily_supervised_tasks_status",
            "ix_daily_supervised_tasks_source_report_id",
            "ix_daily_supervised_tasks_project_id",
            "ix_daily_supervised_tasks_user_id",
        ):
            if name in existing:
                op.drop_index(name, table_name="daily_supervised_tasks")
        op.drop_table("daily_supervised_tasks")

    daily_reports_columns = {column["name"] for column in inspector.get_columns("daily_reports")}
    daily_reports_indexes = {idx["name"] for idx in inspector.get_indexes("daily_reports")}

    if "work_tags" in daily_reports_columns:
        op.drop_column("daily_reports", "work_tags")
    if "planned_status" in daily_reports_columns:
        if "ix_daily_reports_planned_status" in daily_reports_indexes:
            op.drop_index("ix_daily_reports_planned_status", table_name="daily_reports")
        op.drop_column("daily_reports", "planned_status")
    if "parent_plan_id" in daily_reports_columns:
        if "ix_daily_reports_parent_plan_id" in daily_reports_indexes:
            op.drop_index("ix_daily_reports_parent_plan_id", table_name="daily_reports")
        op.drop_constraint("fk_daily_reports_parent_plan_id", "daily_reports", type_="foreignkey")
        op.drop_column("daily_reports", "parent_plan_id")
    if "report_type" in daily_reports_columns:
        if "ix_daily_reports_report_type" in daily_reports_indexes:
            op.drop_index("ix_daily_reports_report_type", table_name="daily_reports")
        op.drop_column("daily_reports", "report_type")

    existing_enums = {row[0] for row in bind.execute(sa.text(
        "SELECT typname FROM pg_type WHERE typtype='e'"
    )).fetchall()}
    for enum_name in ("supervised_status", "daily_report_planned_status", "daily_report_type"):
        if enum_name in existing_enums:
            sa.Enum(name=enum_name).drop(bind, checkfirst=False)
```

**字面量约束**:
- `revision = "a8b9c0d1e2f3"` / `down_revision = "e6f7a8b9c0d1"` 字面量精准对齐
- 3 ENUM 名:`daily_report_type` / `daily_report_planned_status` / `supervised_status` 与 ORM 1:1
- 7 FK 命名 `fk_daily_reports_parent_plan_id / fk_supervised_tasks_*`(对齐 T-1104 体例)
- 7 索引 `ix_daily_supervised_tasks_*` + 3 索引 `ix_daily_reports_*`
- backfill stdout `[T-1301 backfill] morning_plan=N / evening_review=N / ad_hoc=N`(对齐 T-1104 backfill stdout 体例)
- 全表 condition-branch 防重复(对齐 T-1106 migration 体例),`alembic upgrade-downgrade-upgrade` 来回幂等

### 3.2 Schemas

#### 3.2.1 新建 `backend/app/schemas/morning_evening.py`(~165 行)

**职责**:T-1301 独立 module,与 `schemas/report.py`(AI 解析路径)完全隔离。

```python
"""Pydantic V2 schemas for T-1301 morning-evening close loop + supervised tracking"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.daily_report import PlannedStatus, ReportType


# ────────────────────────────────────────────────
# GET /projects/my-active
# ────────────────────────────────────────────────

class MyActiveTaskItem(BaseModel):
    """活跃任务卡片(嵌套在 MyActiveProjectItem 下)"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str  # TaskStatus.value
    priority: str
    story_points: int
    planned_end: Optional[date]
    is_on_critical_path: bool


class MyActiveProjectItem(BaseModel):
    """活跃项目卡片"""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    health_status: str
    is_temporary: bool
    member_track: str  # ProjectMember.track.value
    role_in_project: Optional[str]
    tasks: list[MyActiveTaskItem] = []


class MyActiveProjectsResponse(BaseModel):
    projects: list[MyActiveProjectItem]
    total_projects: int
    total_tasks: int


# ────────────────────────────────────────────────
# POST /reports/morning-batch
# ────────────────────────────────────────────────

WORK_TAG_CHOICES = (
    "研发", "测试", "评审", "部署", "沟通", "调研", "文档", "学习",
)


class MorningPlanCardIn(BaseModel):
    """晨规划单卡输入"""
    project_id: Optional[uuid.UUID] = None
    sprint_task_id: Optional[uuid.UUID] = None
    work_tags: list[str] = Field(default_factory=list, max_length=8)
    note: Optional[str] = Field(None, max_length=500, description="员工对该任务的当日备注")

    @model_validator(mode="after")
    def _at_least_one_anchor(self) -> "MorningPlanCardIn":
        if self.project_id is None and self.sprint_task_id is None:
            # 允许 ad-hoc 计划外卡(两者均 NULL)但要求至少 note 不空
            if not (self.note and self.note.strip()):
                raise ValueError("计划外任务卡必须填写 note")
        return self


class MorningBatchRequest(BaseModel):
    """晨规划批量提交"""
    items: list[MorningPlanCardIn] = Field(..., min_length=1, max_length=30)
    report_date: Optional[date] = None  # 缺省 = today;允许补录历史日

    @model_validator(mode="after")
    def _normalize_date(self) -> "MorningBatchRequest":
        if self.report_date is None:
            self.report_date = date.today()
        return self


class MorningBatchResponse(BaseModel):
    inserted: int
    report_ids: list[uuid.UUID]


# ────────────────────────────────────────────────
# POST /reports/evening-batch
# ────────────────────────────────────────────────

class EveningReviewCardIn(BaseModel):
    """晚复核单卡:对一条晨规划行的复核"""
    parent_report_id: uuid.UUID
    planned_status: PlannedStatus
    actual_note: Optional[str] = Field(None, max_length=500)


class EveningAdHocCardIn(BaseModel):
    """晚复核中自主新增的计划外任务"""
    project_id: Optional[uuid.UUID] = None
    sprint_task_id: Optional[uuid.UUID] = None
    work_tags: list[str] = Field(default_factory=list, max_length=8)
    note: str = Field(..., min_length=1, max_length=500)


class EveningBatchRequest(BaseModel):
    """晚复核批量提交 — 主体是 reviews(对账),extras 是自主追加"""
    reviews: list[EveningReviewCardIn] = Field(default_factory=list, max_length=30)
    extras: list[EveningAdHocCardIn] = Field(default_factory=list, max_length=10)
    report_date: Optional[date] = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "EveningBatchRequest":
        if not self.reviews and not self.extras:
            raise ValueError("晚复核至少需要一条 review 或 extra")
        if self.report_date is None:
            self.report_date = date.today()
        return self


class EveningBatchResponse(BaseModel):
    review_count: int
    extra_count: int
    supervised_created: int  # 因 partial/delayed 新建的督导追踪数
    supervised_closed: int    # 因 done 自动闭环旧督导的数量
    evening_report_ids: list[uuid.UUID]


# ────────────────────────────────────────────────
# GET /reports/pending-follow-ups
# ────────────────────────────────────────────────

class PendingFollowUpItem(BaseModel):
    """次日晨规划顶置督导卡"""
    model_config = ConfigDict(from_attributes=True)

    supervised_id: uuid.UUID
    project_id: Optional[uuid.UUID]
    project_name: Optional[str]
    sprint_task_id: Optional[uuid.UUID]
    sprint_task_title: Optional[str]
    source_report_id: uuid.UUID
    source_planned_status: PlannedStatus
    source_note: Optional[str]
    created_at: datetime


class PendingFollowUpsResponse(BaseModel):
    items: list[PendingFollowUpItem]
    total: int
```

**字面量约束**:
- 全 Pydantic V2(`ConfigDict(from_attributes=True)` + `model_validator(mode="after")`)
- `WORK_TAG_CHOICES` 8 候选**仅作前端引用约定**,后端**零校验**(允许员工误传新 tag 而不报错,审计跟踪)
- `MorningPlanCardIn._at_least_one_anchor`:计划外卡至少要 note(防止纯空卡污染)
- `EveningBatchRequest._at_least_one`:reviews 或 extras 至少一个(防止空提交)
- `EveningBatchResponse` 统计 4 项指标 + ID 列表,便于前端 toast 反馈

### 3.3 Router 改造

#### 3.3.1 改 `backend/app/routers/reports.py`(+~280 行,**严禁** 改既有函数体)

**改动锚点 5 类**:① imports 块追加;② 重构 `/today-plan` 端点(L505-549);③ 新增 4 端点 + 2 helper;④ **零改动** `web_submit_daily_report / list_reports / batch_soft_delete_reports / batch_restore_reports / get_report_detail`。

**imports 块追加(L29 之后)**:

```python
from app.models.daily_report import DailyReport, PlannedStatus, ReportType
from app.models.daily_supervised_task import DailySupervisedTask, SupervisedStatus
from app.models.project_followup import ProjectFollowUp
from app.schemas.morning_evening import (
    EveningAdHocCardIn,
    EveningBatchRequest,
    EveningBatchResponse,
    EveningReviewCardIn,
    MorningBatchRequest,
    MorningBatchResponse,
    MorningPlanCardIn,
    MyActiveProjectItem,
    MyActiveProjectsResponse,
    MyActiveTaskItem,
    PendingFollowUpItem,
    PendingFollowUpsResponse,
    WORK_TAG_CHOICES,
)
from sqlalchemy import func, or_
from sqlalchemy.orm import aliased
```

**`/today-plan` 重构(L505-549 整段替换)**:

```python
@router.get("/today-plan")
async def get_today_plan(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    T-1301 重构:当前用户今日的晨规划列表(report_type='morning_plan',按 created_at ASC)。
    晚复核 UI 调用此端点拉取应对账的卡片清单。
    向后兼容:返回 dict 结构 {"plan": ..., "items": [...]},既保留 V2 plan 字段(最近一条),
    又新增 items 数组供晚复核对账。
    """
    today = date.today()
    rows = (await db.execute(
        select(DailyReport, Project.name.label("project_name"), SprintTask.title.label("sprint_task_title"))
        .outerjoin(Project, and_(DailyReport.project_id == Project.id, Project.tenant_id == current_user.tenant_id))
        .outerjoin(SprintTask, and_(DailyReport.sprint_task_id == SprintTask.id, SprintTask.tenant_id == current_user.tenant_id))
        .where(
            DailyReport.user_id == current_user.id,
            DailyReport.tenant_id == current_user.tenant_id,
            DailyReport.report_date == today,
            DailyReport.report_type == ReportType.morning_plan,
            DailyReport.deleted_at.is_(None),
        )
        .order_by(DailyReport.created_at.asc())
    )).all()
    items = [
        {
            "id": str(r.DailyReport.id),
            "report_date": r.DailyReport.report_date,
            "project_id": str(r.DailyReport.project_id) if r.DailyReport.project_id else None,
            "project_name": r.project_name,
            "sprint_task_id": str(r.DailyReport.sprint_task_id) if r.DailyReport.sprint_task_id else None,
            "sprint_task_title": r.sprint_task_title,
            "work_tags": r.DailyReport.work_tags or [],
            "raw_input_text": r.DailyReport.raw_input_text,
            "created_at": r.DailyReport.created_at.isoformat() if r.DailyReport.created_at else None,
        }
        for r in rows
    ]
    # 向后兼容:plan 仍返回最近一条(老前端 V2.2 字段)
    plan = items[-1] if items else None
    return {"plan": plan, "items": items}
```

**新增 4 端点 + 2 helper(在 `get_report_detail` 之后追加)**:

```python
# ────────────────────────────────────────────────────────────────
# T-1301: 零选择智能铺盘 + 晨晚闭环 + 督导追踪
# ────────────────────────────────────────────────────────────────


@router.get("/projects/my-active", response_model=MyActiveProjectsResponse)
async def get_my_active_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    T-1301 #1:零选择铺盘数据源 — 当前员工名下所有 active 项目 + 进行中 Sprint 任务聚合。

    查询 pattern:
      ProjectMember (left_at IS NULL) JOIN Project (status='active', deleted_at IS NULL)
        LEFT JOIN SprintTask (assignee_id=me, status IN [todo, in_progress, blocked], deleted_at IS NULL)
    """
    project_rows = (await db.execute(
        select(Project, ProjectMember.track, ProjectMember.role_in_project)
        .join(ProjectMember, and_(
            ProjectMember.project_id == Project.id,
            ProjectMember.user_id == current_user.id,
            ProjectMember.left_at.is_(None),
            ProjectMember.tenant_id == current_user.tenant_id,
        ))
        .where(
            Project.status == "active",
            Project.deleted_at.is_(None),
            Project.tenant_id == current_user.tenant_id,
        )
        .order_by(Project.is_temporary.desc(), Project.code.asc())
    )).all()
    if not project_rows:
        return MyActiveProjectsResponse(projects=[], total_projects=0, total_tasks=0)

    project_ids = [p.Project.id for p in project_rows]
    task_rows = (await db.execute(
        select(SprintTask, Sprint.project_id)
        .join(Sprint, SprintTask.sprint_id == Sprint.id)
        .where(
            Sprint.project_id.in_(project_ids),
            SprintTask.assignee_id == current_user.id,
            SprintTask.status.in_(["todo", "in_progress", "blocked"]),
            SprintTask.deleted_at.is_(None),
            SprintTask.tenant_id == current_user.tenant_id,
            Sprint.tenant_id == current_user.tenant_id,
        )
        .order_by(SprintTask.priority.asc(), SprintTask.planned_end.asc().nulls_last())
    )).all()

    tasks_by_project: dict[uuid.UUID, list[MyActiveTaskItem]] = {}
    for t in task_rows:
        tasks_by_project.setdefault(t.project_id, []).append(MyActiveTaskItem(
            id=t.SprintTask.id,
            title=t.SprintTask.title,
            status=t.SprintTask.status.value if hasattr(t.SprintTask.status, "value") else str(t.SprintTask.status),
            priority=t.SprintTask.priority.value if hasattr(t.SprintTask.priority, "value") else str(t.SprintTask.priority),
            story_points=t.SprintTask.story_points,
            planned_end=t.SprintTask.planned_end,
            is_on_critical_path=t.SprintTask.is_on_critical_path,
        ))

    projects_out = [
        MyActiveProjectItem(
            id=p.Project.id,
            code=p.Project.code,
            name=p.Project.name,
            health_status=p.Project.health_status.value if hasattr(p.Project.health_status, "value") else str(p.Project.health_status),
            is_temporary=p.Project.is_temporary,
            member_track=p.track.value if hasattr(p.track, "value") else str(p.track),
            role_in_project=p.role_in_project,
            tasks=tasks_by_project.get(p.Project.id, []),
        )
        for p in project_rows
    ]

    total_tasks = sum(len(p.tasks) for p in projects_out)
    return MyActiveProjectsResponse(
        projects=projects_out,
        total_projects=len(projects_out),
        total_tasks=total_tasks,
    )


@router.post("/morning-batch", response_model=MorningBatchResponse)
async def submit_morning_batch(
    body: MorningBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    T-1301 #2:零选择晨规划批量提交。
    单事务批量 INSERT,每条 item → 1 行 DailyReport(report_type=morning_plan)。
    严禁走 AI 解析(/web-submit 路径独立)。
    """
    inserted_ids: list[uuid.UUID] = []
    for item in body.items:
        # 校验 project + task 归属(复用既有 helper)
        normalized_project_id = await _validate_project_task_consistency(
            db, current_user, item.project_id, item.sprint_task_id
        )
        # 构造 raw_input_text:维护既有列表查询的可读性
        if item.project_id or item.sprint_task_id:
            raw = f"[晨规划] {item.note or ''}".strip()
        else:
            raw = f"[晨规划/计划外] {item.note}"
        report = DailyReport(
            user_id=current_user.id,
            report_date=body.report_date,
            raw_input_text=raw,
            media_urls=[],
            parsed_content={"tasks": item.note or "", "progress": 0, "report_type": "晨规划"},
            pass_check=True,  # 零选择不走 AI 质检
            ai_score=None,
            ai_comment=None,
            report_type=ReportType.morning_plan,
            work_tags=item.work_tags or [],
            project_id=normalized_project_id,
            sprint_task_id=item.sprint_task_id,
            tenant_id=current_user.tenant_id,
            created_by=current_user.id,
        )
        db.add(report)
        await db.flush()
        inserted_ids.append(report.id)
    await db.commit()
    return MorningBatchResponse(inserted=len(inserted_ids), report_ids=inserted_ids)


@router.post("/evening-batch", response_model=EveningBatchResponse)
async def submit_evening_batch(
    body: EveningBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    T-1301 #3:晚复核批量对账 + 督导追踪推送 + 已完成自动闭环。

    流程:
      1. 对 body.reviews:逐条 INSERT evening_review 行(parent_plan_id + planned_status)
      2. partial/delayed → 同步 INSERT ProjectFollowUp(T-1106 表)+ DailySupervisedTask(open)
      3. done → 查同一 user_id + same source_report_id 的旧 DailySupervisedTask(open),自动 closed
      4. 对 body.extras:逐条 INSERT ad_hoc 行(零督导逻辑)
    """
    review_ids: list[uuid.UUID] = []
    supervised_created = 0
    supervised_closed = 0

    for rv in body.reviews:
        parent_plan = await _load_owned_morning_plan(db, rv.parent_report_id, current_user)
        eve = DailyReport(
            user_id=current_user.id,
            report_date=body.report_date,
            raw_input_text=f"[晚复盘] {rv.actual_note or ''}".strip(),
            media_urls=[],
            parsed_content={"tasks": rv.actual_note or "", "progress": 100 if rv.planned_status == PlannedStatus.done else 50, "report_type": "晚复盘"},
            pass_check=True,
            report_type=ReportType.evening_review,
            parent_plan_id=parent_plan.id,
            planned_status=rv.planned_status,
            project_id=parent_plan.project_id,
            sprint_task_id=parent_plan.sprint_task_id,
            work_tags=parent_plan.work_tags or [],
            tenant_id=current_user.tenant_id,
            created_by=current_user.id,
        )
        db.add(eve)
        await db.flush()
        review_ids.append(eve.id)

        if rv.planned_status in (PlannedStatus.partial, PlannedStatus.delayed):
            # 写 ProjectFollowUp(T-1106 表)— 仅当 parent 有 project_id
            followup_id = None
            if parent_plan.project_id is not None:
                followup = ProjectFollowUp(
                    project_id=parent_plan.project_id,
                    content=f"[督导] {current_user.name}:{rv.actual_note or '(无备注)'} — 来自 {body.report_date} 晚复核",
                    tenant_id=current_user.tenant_id,
                    created_by=current_user.id,
                )
                db.add(followup)
                await db.flush()
                followup_id = followup.id
            # 写 DailySupervisedTask
            supervised = DailySupervisedTask(
                user_id=current_user.id,
                project_id=parent_plan.project_id,
                sprint_task_id=parent_plan.sprint_task_id,
                source_report_id=eve.id,
                project_followup_id=followup_id,
                status=SupervisedStatus.open,
                tenant_id=current_user.tenant_id,
                created_by=current_user.id,
            )
            db.add(supervised)
            supervised_created += 1
        elif rv.planned_status == PlannedStatus.done:
            # 自动闭环:查同一 user_id 下与 parent_plan 关联的 open 督导
            stale_rows = (await db.execute(
                select(DailySupervisedTask).where(
                    DailySupervisedTask.user_id == current_user.id,
                    DailySupervisedTask.tenant_id == current_user.tenant_id,
                    DailySupervisedTask.status == SupervisedStatus.open,
                    or_(
                        DailySupervisedTask.sprint_task_id == parent_plan.sprint_task_id if parent_plan.sprint_task_id else False,
                        DailySupervisedTask.project_id == parent_plan.project_id if parent_plan.project_id else False,
                    ),
                )
            )).scalars().all()
            for st in stale_rows:
                st.status = SupervisedStatus.closed
                st.closed_at = datetime.now(timezone.utc)
                st.closed_by_report_id = eve.id
                supervised_closed += 1

    extra_ids: list[uuid.UUID] = []
    for ex in body.extras:
        normalized_project_id = await _validate_project_task_consistency(
            db, current_user, ex.project_id, ex.sprint_task_id
        )
        rep = DailyReport(
            user_id=current_user.id,
            report_date=body.report_date,
            raw_input_text=f"[晚复盘/自主新增] {ex.note}",
            media_urls=[],
            parsed_content={"tasks": ex.note, "progress": 100, "report_type": "晚复盘"},
            pass_check=True,
            report_type=ReportType.ad_hoc,  # 晚复核自主新增标 ad_hoc(无晨规划对照)
            project_id=normalized_project_id,
            sprint_task_id=ex.sprint_task_id,
            work_tags=ex.work_tags or [],
            tenant_id=current_user.tenant_id,
            created_by=current_user.id,
        )
        db.add(rep)
        await db.flush()
        extra_ids.append(rep.id)

    await db.commit()
    return EveningBatchResponse(
        review_count=len(review_ids),
        extra_count=len(extra_ids),
        supervised_created=supervised_created,
        supervised_closed=supervised_closed,
        evening_report_ids=review_ids + extra_ids,
    )


@router.get("/pending-follow-ups", response_model=PendingFollowUpsResponse)
async def list_pending_follow_ups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    T-1301 #4:次日晨规划顶置督导列表 — 当前用户 open 状态的 DailySupervisedTask。
    """
    rows = (await db.execute(
        select(DailySupervisedTask, DailyReport, Project.name.label("project_name"), SprintTask.title.label("sprint_task_title"))
        .join(DailyReport, DailySupervisedTask.source_report_id == DailyReport.id)
        .outerjoin(Project, and_(DailySupervisedTask.project_id == Project.id, Project.tenant_id == current_user.tenant_id))
        .outerjoin(SprintTask, and_(DailySupervisedTask.sprint_task_id == SprintTask.id, SprintTask.tenant_id == current_user.tenant_id))
        .where(
            DailySupervisedTask.user_id == current_user.id,
            DailySupervisedTask.tenant_id == current_user.tenant_id,
            DailySupervisedTask.status == SupervisedStatus.open,
        )
        .order_by(DailySupervisedTask.created_at.asc())
    )).all()
    items = [
        PendingFollowUpItem(
            supervised_id=r.DailySupervisedTask.id,
            project_id=r.DailySupervisedTask.project_id,
            project_name=r.project_name,
            sprint_task_id=r.DailySupervisedTask.sprint_task_id,
            sprint_task_title=r.sprint_task_title,
            source_report_id=r.DailySupervisedTask.source_report_id,
            source_planned_status=r.DailyReport.planned_status or PlannedStatus.partial,
            source_note=r.DailyReport.raw_input_text,
            created_at=r.DailySupervisedTask.created_at,
        )
        for r in rows
    ]
    return PendingFollowUpsResponse(items=items, total=len(items))


# ────────────────────────────────────────────────────────────────
# T-1301 内部 helper
# ────────────────────────────────────────────────────────────────


async def _load_owned_morning_plan(
    db: AsyncSession,
    plan_id: uuid.UUID,
    user: User,
) -> DailyReport:
    """加载本人当日晨规划行;校验 user_id + tenant + report_type=morning_plan + 未软删;失败 404"""
    plan = (await db.execute(
        select(DailyReport).where(
            DailyReport.id == plan_id,
            DailyReport.user_id == user.id,
            DailyReport.tenant_id == user.tenant_id,
            DailyReport.report_type == ReportType.morning_plan,
            DailyReport.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if plan is None:
        raise HTTPException(404, detail="晨规划记录不存在或无权访问")
    return plan
```

**字面量约束**:
- `/morning-batch` 单事务循环 INSERT;每行 `pass_check=True`(零选择路径不走 AI 质检,信任员工选择)
- `/evening-batch` 三类处理顺序:reviews 逐条 → 对每条按 planned_status 三分支(partial/delayed → 双 INSERT;done → 闭环旧督导;cancelled → 仅 INSERT review 不动督导)→ 然后 extras
- `_load_owned_morning_plan` helper 校验严格 5 条件,严禁 cross-user 提交
- `ProjectFollowUp.content` 前缀 `[督导]` + 含当前 user.name + actual_note + report_date → 便于人工阅读
- 督导自动闭环用 `OR(sprint_task_id 匹配, project_id 匹配)` 模糊匹配 — 容忍员工对账时关联到上一层项目而非具体任务
- 全 5 端点 RBAC 由 `get_current_user` 兜底(任何已登录用户都能填自己的报);跨用户访问 helper 内 404 拦截

#### 3.3.2 严禁项再确认

- ❌ 严禁 改 `web_submit_daily_report` 函数(L122-290)— AI 解析路径独立
- ❌ 严禁 改 `list_reports / batch_soft_delete_reports / batch_restore_reports / get_report_detail`(L293-612)
- ❌ 严禁 改 `_validate_project_task_consistency` helper(L56-119)— 复用现有
- ❌ 严禁 在 `routers/projects.py` 新增 my-active 端点(§6 决策第 5 条:统一放 reports.py)

### 3.4 前端 API 层

#### 3.4.1 改 `frontend/src/api/reports.ts`(+~95 行,在末尾追加)

```typescript
import request from '@/api/request'

export const getReports = (params?: any) => request.get('/reports', { params })
export const getReportDetail = (id: string) => request.get(`/reports/${id}`)
export const getTodayPlan = () => request.get('/reports/today-plan')

export const batchSoftDeleteReports = (ids: string[]) =>
  request.delete('/reports/batch', { data: { ids } })

export const batchRestoreReports = (ids: string[]) =>
  request.patch('/reports/batch-restore', { ids })

// ──────────────────────────────────────
// T-1301: 零选择智能铺盘 + 晨晚闭环 + 督导追踪
// ──────────────────────────────────────

export interface MyActiveTaskItem {
  id: string
  title: string
  status: string
  priority: string
  story_points: number
  planned_end: string | null
  is_on_critical_path: boolean
}

export interface MyActiveProjectItem {
  id: string
  code: string
  name: string
  health_status: string
  is_temporary: boolean
  member_track: string
  role_in_project: string | null
  tasks: MyActiveTaskItem[]
}

export interface MyActiveProjectsResponse {
  projects: MyActiveProjectItem[]
  total_projects: number
  total_tasks: number
}

export interface MorningPlanCardIn {
  project_id?: string
  sprint_task_id?: string
  work_tags?: string[]
  note?: string
}

export interface MorningBatchRequest {
  items: MorningPlanCardIn[]
  report_date?: string
}

export interface MorningBatchResponse {
  inserted: number
  report_ids: string[]
}

export type PlannedStatus = 'done' | 'partial' | 'delayed' | 'cancelled'

export interface EveningReviewCardIn {
  parent_report_id: string
  planned_status: PlannedStatus
  actual_note?: string
}

export interface EveningAdHocCardIn {
  project_id?: string
  sprint_task_id?: string
  work_tags?: string[]
  note: string
}

export interface EveningBatchRequest {
  reviews?: EveningReviewCardIn[]
  extras?: EveningAdHocCardIn[]
  report_date?: string
}

export interface EveningBatchResponse {
  review_count: number
  extra_count: number
  supervised_created: number
  supervised_closed: number
  evening_report_ids: string[]
}

export interface PendingFollowUpItem {
  supervised_id: string
  project_id: string | null
  project_name: string | null
  sprint_task_id: string | null
  sprint_task_title: string | null
  source_report_id: string
  source_planned_status: PlannedStatus
  source_note: string | null
  created_at: string
}

export interface PendingFollowUpsResponse {
  items: PendingFollowUpItem[]
  total: number
}

export const WORK_TAG_CHOICES = [
  '研发', '测试', '评审', '部署', '沟通', '调研', '文档', '学习',
] as const
export type WorkTag = (typeof WORK_TAG_CHOICES)[number]

export async function getMyActiveProjects(): Promise<MyActiveProjectsResponse> {
  return request.get<unknown, MyActiveProjectsResponse>('/reports/projects/my-active')
}

export async function submitMorningBatch(body: MorningBatchRequest): Promise<MorningBatchResponse> {
  return request.post<unknown, MorningBatchResponse>('/reports/morning-batch', body)
}

export async function submitEveningBatch(body: EveningBatchRequest): Promise<EveningBatchResponse> {
  return request.post<unknown, EveningBatchResponse>('/reports/evening-batch', body)
}

export async function getPendingFollowUps(): Promise<PendingFollowUpsResponse> {
  return request.get<unknown, PendingFollowUpsResponse>('/reports/pending-follow-ups')
}
```

**字面量约束**:
- 全 5 新增函数 + 11 interface + `WORK_TAG_CHOICES` 常量 + `WorkTag` 类型,**全在文件末尾**
- **严禁** 改既有 5 个函数(getReports / getReportDetail / getTodayPlan / batchSoftDeleteReports / batchRestoreReports)
- **严禁** 引入新依赖

### 3.5 前端 UI 层

#### 3.5.1 改 `frontend/src/app/submit-report/page.tsx`(完全重构,~+450 行)

**改造策略**:**保留** 现有自由文本 `inputStyle='free'` 备用模式(legacy fallback,以防回滚需求)+ **新增** 默认零选择模式 `inputStyle='zero-select'` + 切换开关。**完全替换** 现有 V2.2 项目/Sprint 下拉(L60-100)。

**核心改造点 8 类**:

1. **顶部 imports 扩展**:
   ```typescript
   import {
     getTodayPlan,
     getMyActiveProjects,
     submitMorningBatch,
     submitEveningBatch,
     getPendingFollowUps,
     WORK_TAG_CHOICES,
     type MyActiveProjectItem,
     type MyActiveTaskItem,
     type PendingFollowUpItem,
     type PlannedStatus,
     type MorningPlanCardIn,
     type EveningReviewCardIn,
     type EveningAdHocCardIn,
     type WorkTag,
   } from '@/api/reports'
   ```

2. **type 扩展**(L12 之后):
   ```typescript
   type ReportMode = 'plan' | 'review'
   type InputStyle = 'zero-select' | 'form' | 'free'  // 默认 zero-select
   ```

3. **零选择 state 扩展**:
   ```typescript
   const [activeProjects, setActiveProjects] = useState<MyActiveProjectItem[]>([])
   const [pendingFollowUps, setPendingFollowUps] = useState<PendingFollowUpItem[]>([])
   const [zeroSelectLoading, setZeroSelectLoading] = useState(false)

   // 晨规划:选中的卡片 key 集合(key = `task:${task_id}` or `project:${project_id}`)+ 每卡的标签 / 备注
   const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
   const [cardTags, setCardTags] = useState<Record<string, WorkTag[]>>({})
   const [cardNotes, setCardNotes] = useState<Record<string, string>>({})

   // 晨规划自主新增 ad-hoc 卡片
   const [adHocCards, setAdHocCards] = useState<MorningPlanCardIn[]>([])

   // 晚复核:从 /today-plan 拉取的晨规划行 + 每行选择的 PlannedStatus + 备注
   const [todayPlanItems, setTodayPlanItems] = useState<any[]>([])
   const [reviewStatuses, setReviewStatuses] = useState<Record<string, PlannedStatus>>({})
   const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({})
   const [eveningExtras, setEveningExtras] = useState<EveningAdHocCardIn[]>([])
   ```

4. **进入页面加载 4 件数据**(useEffect):
   ```typescript
   useEffect(() => {
     if (inputStyle !== 'zero-select') return
     setZeroSelectLoading(true)
     Promise.all([
       getMyActiveProjects(),
       getPendingFollowUps(),
       getTodayPlan(),
     ])
       .then(([active, pending, today]) => {
         setActiveProjects(active.projects)
         setPendingFollowUps(pending.items)
         const items = (today as any)?.items ?? []
         setTodayPlanItems(items)
         // 自动判定模式:已有晨规划 → 进入 review;否则 plan
         if (items.length > 0 && mode === 'plan' && new Date().getHours() >= 12) {
           setMode('review')
         }
       })
       .catch((e) => setError(e?.message || '加载活跃项目失败'))
       .finally(() => setZeroSelectLoading(false))
   }, [inputStyle, mode])
   ```

5. **晨规划 UI 区块**(渲染 4 段):
   - **段 1 — 督导追踪顶置**(`pendingFollowUps.length > 0`):红色高亮卡片列表,显示项目名 + 任务标题 + 上次延期原因;**每张卡片默认 checkbox 已勾选 + 锁定**(不可取消,直至闭环)
   - **段 2 — 我的活跃项目+任务**(`activeProjects.map`):每个项目作为分组,卡片为该项目下的 SprintTask(若该项目无 task → 显示一张项目级卡片代表"参与该项目的工作");卡片右侧 checkbox + 工作类型标签 chip(多选)+ 备注 textarea
   - **段 3 — 自主追加计划外**(`adHocCards.map` + 「+ 新增计划外任务」按钮)
   - **段 4 — 一键批量提交**(底部按钮 + 提交后 toast `已提交 N 条晨规划`)

6. **晚复核 UI 区块**(渲染 3 段):
   - **段 1 — 晨规划对账卡片**(`todayPlanItems.map`):每张卡片显示项目+任务+原始备注 + 工作类型标签(只读)+ 4 状态单选 radio + 完成备注 textarea
   - **段 2 — 自主新增完成任务**(`eveningExtras.map` + 「+ 追加完成任务」按钮)
   - **段 3 — 一键提交晚复核**(底部按钮 + toast `已对账 N 条 / 新增 M 条 / 督导 X 条`)

7. **`handleSubmit` 改造**(根据 inputStyle 分支):
   ```typescript
   async function handleSubmit() {
     if (inputStyle === 'zero-select') {
       if (mode === 'plan') return submitZeroSelectPlan()
       return submitZeroSelectReview()
     }
     // legacy 走原 form/free 路径(保留旧 web-submit 调用)
     return submitLegacy()
   }

   async function submitZeroSelectPlan() {
     const items: MorningPlanCardIn[] = []
     // 督导顶置(自动 included)
     for (const f of pendingFollowUps) {
       items.push({
         project_id: f.project_id ?? undefined,
         sprint_task_id: f.sprint_task_id ?? undefined,
         work_tags: cardTags[`supervised:${f.supervised_id}`] || [],
         note: `[督导持续跟进] ${f.source_note?.slice(0, 100) || ''}`,
       })
     }
     // 活跃项目/任务勾选
     for (const p of activeProjects) {
       if (p.tasks.length === 0 && selectedKeys.has(`project:${p.id}`)) {
         const k = `project:${p.id}`
         items.push({ project_id: p.id, work_tags: cardTags[k] || [], note: cardNotes[k] || '' })
       }
       for (const t of p.tasks) {
         const k = `task:${t.id}`
         if (selectedKeys.has(k)) {
           items.push({ project_id: p.id, sprint_task_id: t.id, work_tags: cardTags[k] || [], note: cardNotes[k] || '' })
         }
       }
     }
     items.push(...adHocCards.filter((c) => (c.note || '').trim()))
     if (items.length === 0) { toast.error('请至少勾选一项任务或新增计划外任务'); return }
     setSubmitting(true)
     try {
       const r = await submitMorningBatch({ items })
       toast.success(`已提交 ${r.inserted} 条晨规划`)
       // 提交后清空 + 刷新 today-plan
       setSelectedKeys(new Set()); setCardTags({}); setCardNotes({}); setAdHocCards([])
       const today = await getTodayPlan()
       setTodayPlanItems((today as any)?.items ?? [])
       setMode('review')
     } catch (e: any) { toast.error(e?.message || '提交失败') } finally { setSubmitting(false) }
   }

   async function submitZeroSelectReview() {
     const reviews: EveningReviewCardIn[] = todayPlanItems
       .filter((p) => reviewStatuses[p.id])
       .map((p) => ({
         parent_report_id: p.id,
         planned_status: reviewStatuses[p.id]!,
         actual_note: reviewNotes[p.id] || undefined,
       }))
     const extras = eveningExtras.filter((c) => (c.note || '').trim())
     if (reviews.length === 0 && extras.length === 0) { toast.error('请至少对账一条或追加一条完成任务'); return }
     setSubmitting(true)
     try {
       const r = await submitEveningBatch({ reviews, extras })
       toast.success(`已对账 ${r.review_count} 条 / 新增 ${r.extra_count} 条 / 督导 ${r.supervised_created} 条 / 自动闭环 ${r.supervised_closed} 条`)
       setReviewStatuses({}); setReviewNotes({}); setEveningExtras([])
     } catch (e: any) { toast.error(e?.message || '提交失败') } finally { setSubmitting(false) }
   }
   ```

8. **顶部模式切换条**:
   - 主切:`mode` plan ↔ review(早晚)
   - 副切:`inputStyle` zero-select(默认)↔ form ↔ free(legacy 备用)
   - 字幕:"零选择智能铺盘 — T-1301 启用" / "传统表单 — Legacy"

**改造严禁项**:
- ❌ 严禁 删 `FORM_FIELDS` 常量(legacy form 模式仍使用)
- ❌ 严禁 删 `submitLegacy` / `getProjectsOverview / getProjectSprints / getSprintTasks` 调用(用于 legacy 备用 + 兼容性)
- ❌ 严禁 修改 `attachments` / `recognitionRef` 相关 attachment + voice 子系统
- ❌ 严禁 引入新 UI 库
- ❌ 严禁 删 `result` / `error` state(legacy 路径仍展示)

### 3.6 测试

#### 3.6.1 新建 `backend/tests/test_phase13_daily_report_v2.py`(~480 行,~16 case)

**测试 case 命名清单(严格 16 个,4 类)**:

| # | 函数名 | 类别 | 验证点 |
|---|---|---|---|
| 1 | `test_daily_report_report_type_enum_persisted` | Model | 3 种 ENUM 值落盘读出 + 默认 ad_hoc + index 命中 |
| 2 | `test_daily_report_parent_plan_id_self_fk_set_null_on_delete` | Model | parent 软删时 evening 行 parent_plan_id 不动(软删非硬 DELETE);物理 DELETE 时 SET NULL |
| 3 | `test_daily_supervised_task_cascade_on_source_report_delete` | Model | source_report 物理 DELETE → DailySupervisedTask CASCADE 清光 |
| 4 | `test_my_active_returns_active_projects_with_open_tasks` | my-active | admin 建项目 active + 加 member + sprint task assignee_id=me → 接口返回 1 project + N task |
| 5 | `test_my_active_excludes_completed_projects` | my-active | 项目 status='completed' → 接口跳过该项目 |
| 6 | `test_my_active_excludes_done_tasks` | my-active | SprintTask status='done' → 不进 tasks 列表;status='todo/in_progress/blocked' → 进 |
| 7 | `test_my_active_tenant_isolation` | my-active | tenant=t1 项目;tenant=t2 用户调 → 0 项目 |
| 8 | `test_morning_batch_inserts_morning_plan_rows` | morning-batch | items=3 → DB 新建 3 行 report_type=morning_plan;work_tags 落盘 |
| 9 | `test_morning_batch_ad_hoc_card_requires_note` | morning-batch | item 无 project/task 且 note 空 → 422 |
| 10 | `test_morning_batch_rejects_unauthorized_project` | morning-batch | 给非本人 project 的 sprint_task_id → 403 / 404(复用 _validate helper) |
| 11 | `test_evening_batch_done_does_not_create_supervised` | evening-batch | reviews 1 条 status=done → supervised_created=0 + DailySupervisedTask 表 0 行 |
| 12 | `test_evening_batch_partial_creates_supervised_and_followup` | evening-batch | reviews 1 条 status=partial(parent.project_id 非 NULL)→ supervised_created=1 + ProjectFollowUp 1 行 content 含 `[督导]` |
| 13 | `test_evening_batch_done_auto_closes_existing_supervised` | evening-batch | 先插一条 open supervised → reviews status=done 关联同 sprint_task_id → 该 supervised closed + supervised_closed=1 |
| 14 | `test_evening_batch_extras_create_ad_hoc_rows` | evening-batch | extras 2 条 → 2 行 ad_hoc + 零督导写入 + parent_plan_id=NULL |
| 15 | `test_pending_follow_ups_returns_open_only` | pending | 建 3 supervised(2 open + 1 closed)→ 接口返回 2 |
| 16 | `test_pending_follow_ups_tenant_isolation` | pending | tenant=t1 supervised;tenant=t2 用户调 → 0 |

**测试基础设施**:
- consume `db_session + client` fixture
- consume `_isolation_external_settings` autouse fixture(T-1102/T-1103)
- 每 case 入口 `_cleanup_phase13_test_data` helper:**精准** DELETE 顺序 `daily_supervised_tasks → project_follow_ups (LIKE "[督导]%" 且 created_by=phase13 user) → daily_reports (LIKE "phase13_%") → project_members → sprint_tasks → sprints → projects (code LIKE "phase13_%") → users (wechat_userid LIKE "phase13_%")`
- 私有 helpers `_phase13_*` 前缀
- 作用域闸门:**全部** test data 命名以 `phase13_` 起手
- 零 mock / 零 monkeypatch / 零 print / 零 logger / 零 skip / 零 xfail

#### 3.6.2 测试基线对齐

| 阶段 | 全套 pytest 期望 |
|---|---|
| T-1106 完工(基线) | `220 passed + 2 skipped` |
| T-1301 完工(预期) | `236 passed + 2 skipped`(+16 case) |
| 若 T-1201 先落,T-1201+T-1301 完工 | `251 passed + 2 skipped`(+15+16) |

**回归承诺**:**零** existing test 减分。

### 3.7 main.py / router 挂载

**零改动**:`backend/app/main.py` 已 include reports.py 路由;本任新增 4 端点全在该 router 内,无需新挂。

### 3.8 fail-safe self-check(Codex 接手前必跑 9 项 grep 闸门)

```bash
# 1. 基线锁定
git log --oneline -5 | head -1 | grep -F "chore(spec): T-1201"

# 2. T-1106 migration 已存在
test -f backend/alembic/versions/20260530_1203_phase11_project_followups.py

# 3. T-1106 ProjectFollowUp 模型零改动
git diff ade1163..HEAD -- backend/app/models/project_followup.py | wc -l   # 期望 0

# 4. T-1201 spec 已落盘 + 待 Codex 接手(不阻塞 T-1301 起工程,因为 T-1301 改的文件与 T-1201 锁定文件不重叠)
test -f docs/T-1201_spec.md

# 5. T-1104 / T-1105 / T-1106 全部锁定文件零改动(精简版闸门)
git diff ade1163..HEAD -- \
  backend/alembic/versions/20260529_1037_phase11_user_department_id_fk.py \
  backend/app/models/user.py \
  backend/app/services/_department_resolver.py \
  backend/app/services/department_service.py \
  backend/tests/test_phase11_dept_fk.py \
  backend/app/schemas/project.py \
  backend/app/routers/projects.py \
  backend/app/routers/users.py \
  backend/tests/test_phase11_project_members.py \
  frontend/src/api/projects.ts \
  frontend/src/api/users.ts \
  frontend/src/app/projects/page.tsx \
  frontend/src/components/member-picker.tsx \
  backend/app/models/project_followup.py \
  backend/app/models/project.py \
  backend/app/services/health_engine.py \
  backend/tests/test_phase11_followups.py \
  backend/alembic/versions/20260530_1203_phase11_project_followups.py \
  frontend/src/components/followup-timeline.tsx \
  'frontend/src/app/project/[id]/page.tsx' | wc -l   # 期望 0

# 6. conftest / _isolation / _db_url / .env / README / DEPLOY 零改动
git diff ade1163..HEAD -- \
  backend/conftest.py \
  backend/tests/_isolation.py \
  backend/tests/_db_url.py \
  backend/.env.example \
  README.md DEPLOY.md | wc -l   # 期望 0

# 7. AI 解析 / 企微 / 通知 / token guard 零改动
git diff ade1163..HEAD -- \
  backend/app/services/ai_engine.py \
  backend/app/services/kr_progress_extractor.py \
  backend/app/services/notification_service.py \
  backend/app/services/token_guard.py \
  backend/app/routers/wechat.py \
  backend/app/schemas/report.py | wc -l   # 期望 0

# 8. 工作区遗留 5 项未污染
git status --short | grep -E '^( M|\?\?)' | wc -l   # 期望 5

# 9. alembic heads 单头确认
cd backend && alembic heads | wc -l   # 期望 1(预期内容含 e6f7a8b9c0d1 或 f7a8b9c0d1e2;Codex 据此核对 down_revision)
```

---

## 4. 测试基线 + 闸门

| 闸门 | 命令 | 期望 |
|---|---|---|
| ruff(后端) | `cd backend && ruff check app/routers/reports.py app/models/daily_report.py app/models/daily_supervised_task.py app/schemas/morning_evening.py alembic/versions/20260530_*_phase13_*.py tests/test_phase13_daily_report_v2.py` | All passed |
| mypy(后端) | `cd backend && mypy app/routers/reports.py app/models/daily_report.py app/models/daily_supervised_task.py app/schemas/morning_evening.py` | 0 error |
| Alembic upgrade-downgrade-upgrade | `cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head` | 无 error / 重复 upgrade 幂等 / stdout 命中 `[T-1301 backfill]` |
| 新测试 | `cd backend && pytest tests/test_phase13_daily_report_v2.py -v` | `16 passed` |
| 全量 pytest | `cd backend && pytest -q` | `236 passed + 2 skipped`(或 251 若 T-1201 已落) |
| frontend lint | `cd frontend && npm run lint` | 0 error |
| frontend typecheck | `cd frontend && npm run typecheck` | 0 error |
| `alembic check` | (沿用 T-1101/T-1102/T-1103 Supervisor 特批跳过) | — |

---

## 5. 改动面文件清单(10 文件 + 4 边界冻结)

### 5.1 10 文件改动面

| # | 文件 | 类型 | 行数预算 | 改动方式 |
|---|---|---|---|---|
| 1 | `backend/app/models/daily_report.py` | 改 | +30 / -0 | Edit(2 ENUM + 4 字段插入) |
| 2 | `backend/app/models/daily_supervised_task.py` | 新建 | ~95 | Write |
| 3 | `backend/app/models/__init__.py` | 改 | +5 / -0 | Edit(2 import 段 + 5 项 __all__) |
| 4 | `backend/alembic/versions/20260530_HHMM_phase13_daily_report_morning_evening.py` | 新建 | ~190 | Write |
| 5 | `backend/app/schemas/morning_evening.py` | 新建 | ~165 | Write |
| 6 | `backend/app/routers/reports.py` | 改 | +~280 / -45 | Edit(imports + 重构 today-plan + 4 端点 + 1 helper) |
| 7 | `backend/tests/test_phase13_daily_report_v2.py` | 新建 | ~480 | Write |
| 8 | `frontend/src/api/reports.ts` | 改 | +~95 / -0 | Edit(末尾追加 5 函数 + 11 interface + 常量) |
| 9 | `frontend/src/app/submit-report/page.tsx` | 改 | +~450 / -50 | Edit(完全重构零选择 + 保留 legacy form/free 备用) |
| 10 | `docs/dev_tasks.md` | 改 | +~50 / -10 | Edit(chore(lock) + chore(progress) 共用) |

### 5.2 4 边界冻结面(grep 闸门必须返回 0)

```bash
# 边界 ①:T-1104/T-1105/T-1106 全部锁定文件(详见 §3.8 第 5 条)
# 边界 ②:配置/测试基础设施(详见 §3.8 第 6 条)
# 边界 ③:AI 解析 / 企微 / 通知 / token guard / schemas/report.py(详见 §3.8 第 7 条)
# 边界 ④:其他无关页 / 中间件 / main / database
git diff ade1163..HEAD -- \
  backend/app/main.py \
  backend/app/database.py \
  backend/app/middleware/ \
  backend/app/routers/wechat.py \
  backend/app/routers/auth.py \
  backend/app/routers/dashboard.py \
  frontend/src/app/dashboard \
  frontend/src/app/admin \
  frontend/src/app/users \
  frontend/src/app/projects \
  frontend/src/app/login \
  frontend/src/app/change-password \
  frontend/src/app/reports \
  frontend/src/components/sidebar.tsx \
  backend/pyproject.toml backend/requirements.txt backend/uv.lock \
  frontend/package.json frontend/package-lock.json | wc -l   # 期望 0
```

---

## 6. 6 决策签字(指挥官 Auto Mode `[2026-05-29 12:06:30]`)

| # | 决策 | 选项 | 签字 | 理由 |
|---|---|---|---|---|
| 1 | 督导追踪表设计 | (A) 独立 DailySupervisedTask 关联表 / (B) 给 ProjectFollowUp 加 kind enum 字段 / (C) ProjectFollowUp.content 文本前缀 [督导] 软标识 | **A** | T-1106 模型零踩踏(BLOCKER 红线);独立 state 机便于次日顶置 / 闭环统计 / 后续 backlog 扩;文本前缀脆弱、ALTER 字段污染共享表 |
| 2 | report_type 字段 | (A) 加 ENUM 字段 + 历史回填 + index / (B) 保留 raw_input_text 文本前缀 / (C) 双轨保留(ENUM + 前缀冗余) | **A** | 结构化查询友好;backfill UPDATE 一次性 + 默认 ad_hoc 兼容;index 命中 today-plan / morning-batch 查询主路径 |
| 3 | parent_plan_id self-FK | (A) self-FK + ON DELETE SET NULL / (B) 弱关联 report_date+user_id / (C) 中间表 daily_report_links | **A** | 精确锁定对账目标(防同日多份晨规划歧义);SET NULL 避免循环 cascade;中间表过度设计 |
| 4 | 工作类型标签固化方案 | (A) 前端固化 8 候选 + 后端零校验 ARRAY / (B) 后端 enum 强约束 / (C) system_settings 配置化 + 数据库表存 | **A** | first-cut 简化;后端零校验允许员工误传(审计追踪);配置化留 T-1302 backlog |
| 5 | my-active 端点放置 | (A) `/reports/projects/my-active`(reports.py)/ (B) `/projects/my-active`(projects.py) | **A** | 老板蓝图明确建议 reports.py;此端点是日报填报的**铺盘数据源**,语义归属 reports;放 projects.py 会污染 T-1105 锁定的 projects.py |
| 6 | 督导自动闭环匹配策略 | (A) OR(sprint_task_id 相等, project_id 相等)模糊匹配 / (B) 严格 sprint_task_id 相等 / (C) 严格 source_report_id 相等(只能闭关原 source) | **A** | 容忍员工对账时关联到上一层项目;严格 sprint_task_id 漏掉无任务级督导;严格 source_report_id 过窄,无法跨日闭环旧督导 |

---

## 7. Commit 计划(3 commit 闭环)

### 7.1 chore(lock)
```
chore(lock): T-1301 开工 — Phase 13 第一任 日报重构 + 零选择智能铺盘 + 晨晚闭环 + 督导追踪

Worker timestamp: [2026-05-30 HH:MM:SS]
```

### 7.2 feat
```
feat(reports): T-1301 日报重构 — 零选择智能铺盘 + 晨晚闭环 + 督导追踪

后端:
- 改 models/daily_report:扩 report_type/parent_plan_id/planned_status/work_tags 4 字段 + 2 ENUM
- 新建 models/daily_supervised_task:督导追踪溯源关联表(零 T-1106 模型踩踏)
- 改 models/__init__:插入式追加 5 项
- 新建 alembic 迁移 phase13_daily_report_morning_evening(2+1 ENUM + 4 列 + 历史 backfill + 新表 + 7 索引)
- 新建 schemas/morning_evening:8 Pydantic V2 schemas + WORK_TAG_CHOICES 常量
- 改 routers/reports.py:
  * 重构 GET /today-plan 改用 report_type ENUM(向后兼容 plan + 新增 items 数组)
  * 新增 GET /projects/my-active(零选择铺盘数据源)
  * 新增 POST /morning-batch(零选择批量晨规划)
  * 新增 POST /evening-batch(晚复核对账 + 督导自动推 ProjectFollowUp + 已完成闭环旧督导)
  * 新增 GET /pending-follow-ups(次日晨规划顶置督导)
  * 新增 _load_owned_morning_plan helper

前端:
- 改 api/reports:扩 5 函数 + 11 interface + WORK_TAG_CHOICES 常量
- 改 app/submit-report/page.tsx:完全重构零选择卡片打勾 UI(legacy form/free 模式保留 fallback)

测试:
- 新建 tests/test_phase13_daily_report_v2.py 16 case(Model 3 + my-active 4 + morning-batch 3 + evening-batch 4 + pending 2)

零回归:
- T-1104/T-1105/T-1106/T-1201 全部锁定文件零改动
- AI 解析 / 企微 / schemas/report.py / notification / token_guard 零改动
- web_submit_daily_report / list_reports / batch 端点零改动
- 测试基线 220 → 236 passed + 2 skipped

Worker timestamp: [2026-05-30 HH:MM:SS]
```

### 7.3 chore(progress)
```
chore(progress): close T-1301 — Phase 13 第一任 日报重构闭环

工程完工实绩:
- 10 文件改动面严格(1 改 daily_report + 1 新建 supervised + 1 改 __init__ + 1 新建 migration + 1 新建 schema + 1 改 router + 1 新建 test + 1 改 api + 1 改 page + 1 改 dev_tasks)
- 16 case 全 PASS / 全量 236 passed + 2 skipped / ruff + mypy + frontend lint/typecheck 全绿
- alembic upgrade-downgrade-upgrade 来回幂等(3 ENUM + 4 列 + backfill 字面量 [T-1301 backfill])

严禁项遵守证据:0 T-1104 / 0 T-1105 / 0 T-1106 / 0 T-1201 / 0 conftest / 0 _isolation / 0 _db_url / 0 .env / 0 README / 0 DEPLOY / 0 AI 服务 / 0 schemas/report.py / 0 wechat / 0 web_submit / 0 list_reports / 0 push / 0 amend / 0 rebase / 0 --no-verify / 0 自启 T-1302

Worker timestamp: [2026-05-30 HH:MM:SS]
```

---

## 8. 验收清单(指挥官二次验收 28 项)

### 8.1 改动面闸门(8 项)

- ① 从 `ade1163` 出发严格 3 commit 链路干净(chore(lock) → feat(reports) → chore(progress))
- ② feat commit 严格 9 文件(对齐 §5.1 文件 1-9,第 10 是 chore(lock)+chore(progress) 共用)
- ③ chore(lock) + chore(progress) 各严格 1 文件 `docs/dev_tasks.md`
- ④ §5.2 边界 ① ② ③ ④ 四块 grep 闸门**完全空**
- ⑤ §3.8 self-check 9 项探针 Codex 接手前**全 PASS**
- ⑥ Worker timestamp 三 commit 均带 `[YYYY-MM-DD HH:MM:SS]`
- ⑦ chore commit body 含完工概要 + 文件清单 + 严禁项遵守证据
- ⑧ 工作区遗留 5 项保留未污染

### 8.2 Migration + 数据层闸门(7 项)

- ⑨ 命名 `20260530_HHMM_phase13_daily_report_morning_evening.py`
- ⑩ `revision = "a8b9c0d1e2f3"` + `down_revision` 字面量(`e6f7a8b9c0d1` 或 `f7a8b9c0d1e2` 视 T-1201 顺序)
- ⑪ upgrade() 字面量全对齐 §3.1.4:3 ENUM + 4 列 + 7 FK + 7 索引
- ⑫ Backfill 字面量 stdout `[T-1301 backfill] morning_plan=N / evening_review=N / ad_hoc=N`
- ⑬ downgrade() 反向 4 步完整,`alembic upgrade-downgrade-upgrade` 来回幂等
- ⑭ `DailyReport` 4 新字段类型 / nullable / index / comment 全对齐 §3.1.1
- ⑮ `DailySupervisedTask` 字面量对齐 §3.1.2:7 FK + 2 复合索引 + status 状态机

### 8.3 Schema + Router 闸门(8 项)

- ⑯ `schemas/morning_evening.py` 8 schemas + WORK_TAG_CHOICES 字面量对齐 §3.2.1
- ⑰ `routers/reports.py` imports 块扩 15+ 项 + 末尾追加 4 端点 + 1 helper
- ⑱ `/today-plan` 重构后字面量:`report_type == ReportType.morning_plan` + 返回 `{"plan": ..., "items": [...]}`
- ⑲ `/projects/my-active` 字面量:`ProjectMember.left_at IS NULL + Project.status='active' + SprintTask.status IN [todo, in_progress, blocked] + assignee_id=current_user.id`
- ⑳ `/morning-batch` 字面量:单事务 + `pass_check=True` + report_type=morning_plan + work_tags 落盘
- ㉑ `/evening-batch` 字面量:reviews 三分支(done 闭环 / partial+delayed 双 INSERT / cancelled 仅复核)+ extras 走 ad_hoc + supervised_created / supervised_closed 计数
- ㉒ `/pending-follow-ups` 字面量:`status='open' + user_id=current + ASC created_at`
- ㉓ `_load_owned_morning_plan` 字面量 5 条件 RBAC + 隔离闸门

### 8.4 前端 + 测试闸门(4 项)

- ㉔ `api/reports.ts` 字面量对齐 §3.4.1:5 函数 + 11 interface + WORK_TAG_CHOICES + WorkTag type 全在文件末尾;严禁改既有 5 函数
- ㉕ `app/submit-report/page.tsx` 改造点 8 类齐全;legacy form/free 模式保留 fallback
- ㉖ `test_phase13_daily_report_v2.py` 16 case 命名 100% 对齐 §3.6.1 字面量(`grep -c "^async def test_" = 16`)+ 4 类分布严格
- ㉗ 测试零 mock / 零 monkeypatch / 零 print / 零 logger / 零 skip / 零 xfail

### 8.5 综合质量闸门(1 项)

- ㉘ `pytest -q` 全量 `236 passed + 2 skipped`(或 251 若 T-1201 已落)+ `ruff` + `mypy` + `alembic` + frontend `npm run lint && npm run typecheck` 全绿

**合计 28 项**。

---

## 9. 风险与 follow-up

### 9.1 风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 自动闭环匹配策略 OR(sprint_task_id, project_id)误闭关无关督导 | 中 | 中(漏督导) | 加 unit test 13 覆盖;后续如证伪可改严格 sprint_task_id 相等 |
| ProjectFollowUp 表被 T-1106 / T-1301 双源写入混杂(content 前缀 [督导] vs 普通跟进) | 低 | 低(数据混杂) | 写入时严格加 `[督导]` 前缀;前端展示可按前缀过滤;后续 T-1302 backlog 可给 ProjectFollowUp 加 kind enum 字段 |
| 历史 raw_input_text 文本前缀 `[晨规划]` 拼写不一致(`[晨规划:]`、`【晨规划】`)导致 backfill 漏 | 中 | 低(历史数据归类) | 仅 LIKE `[晨规划]%` + `[晚复盘]%` 严格前缀匹配,其余 ad_hoc;不做模糊匹配避免误归 |
| 零选择 UI 加载 4 件数据并发慢(getMyActiveProjects + getTodayPlan + getPendingFollowUps + getProjectsOverview)| 中 | 中(首屏体感) | Promise.all 并发加载;后续若 P95 > 1.5s 加 SSR / SWR 缓存;T-1302 backlog |
| 督导任务长期 open 不闭环造成次日列表膨胀 | 中 | 低(列表骚扰) | admin 后台 backlog T-1302:支持手工 force-close + 列表分页;本任不做 |

### 9.2 backlog(明确不归本任)

- **T-1302 候选**:ProjectFollowUp 加 kind enum + 督导 force-close + admin 督导看板
- **T-1303 候选**:工作类型标签 system_settings 配置化 + 自定义标签 + 标签统计仪表盘
- **T-1304 候选**:零选择 UI 性能优化(SWR / SSR / 分页) + 任务卡片排序自定义
- **T-1107/T-1108**(原 Phase 11 backlog):FK 第二阶段 + drop column
- **T-1202/T-1203/T-1204**(原 Phase 12 backlog):AI 对话功能扩展

### 9.3 与 T-1106 / T-1201 关系

T-1301 与 T-1106 / T-1201 **完全正交**:
- **T-1106** 锁定 ProjectFollowUp 模型,T-1301 仅 INSERT 不改字段 → 零冲突
- **T-1201** 锁定 ChatSession + ChatMessage + ChatRole + routers/chat.py,T-1301 改 routers/reports.py + 新建 daily_report 衍生模型 → 零冲突
- T-1301 与 T-1201 可**并行起工程**;若 T-1201 先落,Codex 仅需调整 T-1301 migration `down_revision` 为 `f7a8b9c0d1e2`

---

## 10. 关键决策记录

### 10.1 为什么用独立 DailySupervisedTask 而非给 ProjectFollowUp 加 kind 字段

- T-1106 ProjectFollowUp 已闭环验收(Codex 完工等指挥官二次验收),**严禁** 触碰其模型字段
- 独立关联表给"督导任务"独立的状态机(open/closed)+ 闭环溯源(closed_by_report_id),便于次日顶置 + 后续 admin 看板统计
- 关联表通过 `project_followup_id` FK 软关联 ProjectFollowUp;若将来 T-1302 给 ProjectFollowUp 加 kind 字段,可平滑迁移(把 kind=supervised 行用 DailySupervisedTask 接管)

### 10.2 为什么 report_type 用 PG native ENUM 而非 String + Check Constraint

- 对齐项目体例:`OKRStatus / TaskStatus / SprintStatus / ChatRole`(T-1201 待落)均用 PG native ENUM
- 类型安全:DB 层强制 3 角,防止脏 string 落盘
- 索引友好:ENUM 在 PG 中是 4-byte int,比 string 更快

### 10.3 为什么 my-active 端点放 reports.py 而非 projects.py

- 老板蓝图原文明确建议 `routers/projects.py` 或 `reports.py` 二选一;选 reports.py 因为:
  - 此端点是日报填报的**铺盘数据源**,语义归属 reports
  - T-1105 锁定 projects.py(create_project / batch_remove_members 等 10+ 函数),放 projects.py 触发 §2 第 13 条 BLOCKER
  - reports.py 已有 `_validate_project_task_consistency` helper,my-active 端点可复用查询基础设施

### 10.4 为什么晚复核 done 状态用 OR 闭环旧督导而非严格 source_report_id 相等

- 严格 source_report_id 相等只能闭关「同一晚复核重新对账」的督导(几乎不会发生),无法闭关「跨日新的完成行」的督导
- 业务期望:今天的"完成"晚复核应该闭环昨天/前天遗留的同任务督导,**容忍员工对账时关联到上一层项目**(若无具体 task)
- OR 匹配可能误关无关 project 督导(风险 §9.1 第 1 项),T-1302 backlog 可改严格策略

### 10.5 为什么保留 inputStyle='form'+'free' legacy 模式

- 渐进式迁移:零选择 UI 是大变更,保留 legacy 模式作为 fallback 降低**用户接受度风险**
- 兼容性:legacy 路径走 `/web-submit` AI 解析 + 现有项目/Sprint 下拉 + getProjectsOverview 等 — **零删除现有代码**,保留可逆性
- 后续 T-1303 backlog 可彻底移除 legacy 模式(经 1-2 个月观测)

### 10.6 为什么 work_tags 用 ARRAY(String) 而非关联子表 work_tag_assignments

- 单一字段读写性能最优(无 JOIN)
- 标签查询 pattern 简单(基本只用 ANY/CONTAINS),`ARRAY @> ARRAY['研发']` PG 原生高效
- 关联子表是 over-engineering;若将来需要标签使用统计可加物化视图,不需要拆子表

---

## 📣 附录:给 Worker(Codex)的物理交接单

> **更新时间戳**:`[2026-05-29 12:06:30]`(指挥官 Claude 起草完工)
>
> **接手前置守卫**(Codex 必跑 9 项探针,见 §3.8):
> 1. `git log --oneline -5 | head -1 | grep -F "chore(spec): T-1201"` 必须命中(本任基线 = T-1201 spec 已落盘)
> 2. `test -f backend/alembic/versions/20260530_1203_phase11_project_followups.py` 必须存在
> 3. T-1106 `project_followup.py` 模型零改动(`git diff ade1163..HEAD -- backend/app/models/project_followup.py | wc -l = 0`)
> 4. `test -f docs/T-1201_spec.md`(T-1201 spec 已落盘存在)
> 5. T-1104/T-1105/T-1106 全部锁定文件零改动(§3.8 第 5 条 grep wc = 0)
> 6. conftest / _isolation / _db_url / .env / README / DEPLOY 零改动
> 7. AI 解析 / 企微 / 通知 / token guard / schemas/report.py 零改动
> 8. 工作区遗留仍是 5 项(`git status --short | wc -l = 5`)
> 9. `cd backend && alembic heads | wc -l = 1`(预期 `e6f7a8b9c0d1` 或 `f7a8b9c0d1e2` 若 T-1201 先落)
>
> **8 步执行指令**(严格顺序):
>
> **Step 1 — chore(lock) 落盘**:
> ```bash
> # 编辑 docs/dev_tasks.md:Task 8 (T-1301) [ ] → [/] In Progress by Codex
> git add docs/dev_tasks.md
> git commit -m "$(cat <<'EOF'
> chore(lock): T-1301 开工 — Phase 13 第一任 日报重构 + 零选择智能铺盘 + 晨晚闭环 + 督导追踪
>
> Worker timestamp: [YYYY-MM-DD HH:MM:SS]
>
> Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
> EOF
> )"
> ```
>
> **Step 2 — 数据层落盘**:严格按 §3.1.1 字面量 Edit `models/daily_report.py`(+2 ENUM + 4 字段插入位置严格在 `mentioned_task_ids` 之后、`project_id` 之前);严格按 §3.1.2 字面量 Write `models/daily_supervised_task.py`;严格按 §3.1.3 字面量 Edit `models/__init__.py`(插入式 +5 行,**不**触碰 T-1106 ProjectFollowUp + 待落 T-1201 ChatSession 段);严格按 §3.1.4 字面量 Write 新 migration 文件(`HHMM` 填当前系统时间;若 T-1201 已先落需调 `down_revision` 为 `f7a8b9c0d1e2`)。
>
> **Step 3 — Schema 落盘**:严格按 §3.2.1 字面量 Write `schemas/morning_evening.py`(8 schemas + WORK_TAG_CHOICES 常量)。
>
> **Step 4 — Router 改造**:严格按 §3.3.1 字面量改造 `routers/reports.py`:① imports 块追加 15+ 项;② 替换 `/today-plan` 整段(L505-549 → 新实现);③ 在文件末尾追加 4 端点 + 1 helper;**严禁** 改 `web_submit_daily_report / list_reports / batch_soft_delete / batch_restore / get_report_detail / _validate_project_task_consistency` 6 函数。
>
> **Step 5 — 前端**:严格按 §3.4.1 字面量 Edit `api/reports.ts`(末尾追加 5 函数 + 11 interface + 常量);严格按 §3.5.1 字面量 Edit `app/submit-report/page.tsx`(改造 8 类齐全);**严禁** 删 FORM_FIELDS 常量 / 删 legacy submitLegacy 路径 / 删 attachments + voice 子系统 / 改 frontend/src/app/reports/page.tsx。
>
> **Step 6 — 测试落盘**:严格按 §3.6.1 字面量 Write `test_phase13_daily_report_v2.py`(16 case,4 类分布严格);每 case 入口 `_cleanup_phase13_test_data` helper;作用域 `phase13_` 前缀严格;零 mock / 零 monkeypatch。
>
> **Step 7 — 质量闸门**(全绿才能 commit feat):
> ```bash
> cd backend
> ruff check app/routers/reports.py app/models/daily_report.py app/models/daily_supervised_task.py app/schemas/morning_evening.py alembic/versions/20260530_*_phase13_*.py tests/test_phase13_daily_report_v2.py
> mypy app/routers/reports.py app/models/daily_report.py app/models/daily_supervised_task.py app/schemas/morning_evening.py
> alembic upgrade head && alembic downgrade -1 && alembic upgrade head  # 期望 stdout 含 [T-1301 backfill]
> pytest tests/test_phase13_daily_report_v2.py -v   # 期望 16 passed
> pytest -q   # 期望 236 passed + 2 skipped(或 251 若 T-1201 已落)
> cd ../frontend
> npm run lint
> npm run typecheck
> ```
>
> **Step 8 — feat + chore(progress) 落盘**:
> ```bash
> git add backend/app/models/daily_report.py \
>         backend/app/models/daily_supervised_task.py \
>         backend/app/models/__init__.py \
>         backend/alembic/versions/20260530_*_phase13_*.py \
>         backend/app/schemas/morning_evening.py \
>         backend/app/routers/reports.py \
>         backend/tests/test_phase13_daily_report_v2.py \
>         frontend/src/api/reports.ts \
>         frontend/src/app/submit-report/page.tsx
> git commit -m "$(cat <<'EOF'
> feat(reports): T-1301 日报重构 — 零选择智能铺盘 + 晨晚闭环 + 督导追踪
>
> 后端:
> - 改 models/daily_report:扩 report_type/parent_plan_id/planned_status/work_tags 4 字段 + 2 ENUM
> - 新建 models/daily_supervised_task:督导追踪溯源关联表(零 T-1106 模型踩踏)
> - 改 models/__init__:插入式追加 5 项
> - 新建 alembic 迁移 phase13_daily_report_morning_evening(2+1 ENUM + 4 列 + 历史 backfill + 新表 + 7 索引)
> - 新建 schemas/morning_evening:8 Pydantic V2 schemas + WORK_TAG_CHOICES 常量
> - 改 routers/reports.py:
>   * 重构 GET /today-plan 改用 report_type ENUM
>   * 新增 GET /projects/my-active(零选择铺盘数据源)
>   * 新增 POST /morning-batch(零选择批量晨规划)
>   * 新增 POST /evening-batch(晚复核对账 + 督导自动推 ProjectFollowUp + 已完成闭环旧督导)
>   * 新增 GET /pending-follow-ups
>
> 前端:
> - 改 api/reports:扩 5 函数 + 11 interface + WORK_TAG_CHOICES 常量
> - 改 app/submit-report/page.tsx:完全重构零选择卡片打勾 UI(legacy form/free 模式保留 fallback)
>
> 测试:
> - 新建 tests/test_phase13_daily_report_v2.py 16 case
>
> 零回归:
> - T-1104/T-1105/T-1106/T-1201 全部锁定文件零改动
> - AI 解析 / 企微 / schemas/report.py / notification / token_guard 零改动
> - web_submit_daily_report / list_reports / batch 端点零改动
> - 测试基线 220 → 236 passed + 2 skipped
>
> Worker timestamp: [YYYY-MM-DD HH:MM:SS]
>
> Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
> EOF
> )"
>
> # chore(progress)
> # 编辑 docs/dev_tasks.md:Task 8 (T-1301) [/] → [x] Done by Codex [HH:MM:SS]
> git add docs/dev_tasks.md
> git commit -m "$(cat <<'EOF'
> chore(progress): close T-1301 — Phase 13 第一任 日报重构闭环
>
> 工程完工实绩:
> - 10 文件改动面严格(1 改 daily_report + 1 新建 supervised + 1 改 __init__ + 1 新建 migration + 1 新建 schema + 1 改 router + 1 新建 test + 1 改 api + 1 改 page + 1 改 dev_tasks)
> - 16 case 全 PASS / 全量 236 passed + 2 skipped / ruff + mypy + frontend lint/typecheck 全绿
> - alembic upgrade-downgrade-upgrade 来回幂等(3 ENUM + 4 列 + backfill 字面量 [T-1301 backfill])
>
> 严禁项遵守证据:0 T-1104 / 0 T-1105 / 0 T-1106 / 0 T-1201 / 0 conftest / 0 _isolation / 0 _db_url / 0 .env / 0 README / 0 DEPLOY / 0 AI 服务 / 0 schemas/report.py / 0 wechat / 0 web_submit / 0 list_reports / 0 push / 0 amend / 0 rebase / 0 --no-verify / 0 自启 T-1302
>
> Worker timestamp: [YYYY-MM-DD HH:MM:SS]
>
> Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
> EOF
> )"
> ```
>
> **严禁项再确认(BLOCKER 红线 — 16 条已在 §2 罗列,Codex 接手前必须二次自查)**:
>
> 1. 🚫 严禁 `git push` / `git stash` / `git rebase` / `git commit --amend` / `--no-verify`
> 2. 🚫 严禁 自启 T-1107 / T-1108 / T-1202 / T-1203 / T-1302 / T-1303 / T-1304 / 其他 backlog
> 3. 🚫 严禁 改 T-1104 / T-1105 / T-1106 / T-1201 任何锁定文件(§1.4 表 + §2 第 2 条)
> 4. 🚫 严禁 改 `project_followup.py / project.py / project_member.py / sprint_task.py` 等共享模型字段(零 ALTER)
> 5. 🚫 严禁 改 `web_submit_daily_report / list_reports / batch_soft_delete / batch_restore / get_report_detail / _validate_project_task_consistency`
> 6. 🚫 严禁 改 `services/ai_engine / kr_progress_extractor / notification_service / token_guard / routers/wechat / schemas/report.py / frontend/app/reports/page.tsx`
> 7. 🚫 严禁 改 `pyproject / requirements / uv.lock / package.json / package-lock.json`(零依赖新增)
> 8. 🚫 严禁 删 `FORM_FIELDS` 常量 / 删 legacy submitLegacy / 删 attachments + voice 子系统(保留 fallback)
> 9. 🚫 严禁 触碰工作区遗留 5 项
> 10. 🚫 严禁 改 routers/projects.py(my-active 端点放 reports.py;§6 决策第 5 条)
>
> **状态切换信号**:`docs/dev_tasks.md` Task 8 从 `[/] In Progress by Codex` 切到 `[x] Done by Codex [YYYY-MM-DD HH:MM:SS]`,chore(progress) commit 落盘 — 指挥官以此为信号启动二次验收(28 项清单见 §8)。

---

**📌 spec 元数据**:
- 行数:~1300 行
- 章节数:10 章 + 📣 物理交接单
- 字面量字段精准锁定:Migration revision/down_revision/FK/index 命名 + Model 字段类型 + Schema Pydantic V2 + Router endpoint path/method + 前端 interface/函数签名
- 验收清单条目:28(§8)
- 严禁项条目:16 BLOCKER 红线(§2)
- 决策签字:6(§6)
- 改动面文件:9 工程 + 1 文档(§5.1)
- 闸门探针:9 self-check(§3.8)+ 4 边界 grep(§5.2)+ 7 质量闸门(§4)
