# Phase 7: 历史趋势看板 (Historical Trends Dashboard)

## 当前状态与上下文
- V2.6 删除治理已完成代码加固和原子 Commit (提交哈希: `f7987dd`)。
- 业务流转入 **Phase 7**。目标是基于已有的日报和项目数据，建立数据汇聚视图（PostgreSQL Materialized Views），并通过图表（Recharts）向管理层直观展示。
- 当前正在执行：**Task 2 待认领**。Task 1 已由 Codex 完成。

## 任务看板

### 数据库层 (DB Views & Migrations)
- [x] **Task 1: 创建 Materialized Views 迁移脚本**
  - 创建 Alembic migration 文件。
  - 编写 `mv_daily_user_stats` 和 `mv_weekly_dept_stats` 的 SQL (参考 `implementation-plan.md` Section 7)。
  - 在 scheduler 中配置定时刷新（`REFRESH MATERIALIZED VIEW CONCURRENTLY`），暂定每日凌晨触发。

### 后端接口 (FastAPI)
- [ ] **Task 2: 实现 Analytics API 端点**
  - `GET /api/analytics/user-trend`: 查询个人30天评分趋势
  - `GET /api/analytics/department-compare`: 按部门对比 (提交率，平均分)
  - `GET /api/analytics/project-health`: 查询项目健康度趋势
  - `GET /api/analytics/sprint-efficiency`: 查询 Sprint 效率指标

### 前端 UI (React + Recharts)
- [ ] **Task 3: 引入图表库并封装公共组件**
  - 安装并引入 `recharts`。
  - 封装可复用的 `<TrendLineChart />` 和 `<CompareBarChart />`。
- [ ] **Task 4: 在总经理看板集成视图**
  - 在 Dashboard 页面顶部增加数据展示卡片/模块。
  - 接入 API，渲染真实的历史趋势对比图表。

---
> **执行协议提醒 (Codex 请注意)**：
> 1. 每次认领任务前，请将上方对应方括号修改为 `[/]`，并立即提交 `chore(lock): wip for task X`。
> 2. 完成后修改为 `[x]` 并进行相关的原子 `feat` 或 `fix` 提交。
> 3. 更新 `docs/recap.md`。
