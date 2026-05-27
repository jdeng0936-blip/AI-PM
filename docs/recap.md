# AI-PM Recap

## 最新进度摘要
- [Phase 10] T-1001 §10 实物盘点 + plan 实际落地路径段落落盘(纯文档勘察,backend/frontend/tests 全冻结)
- **V2.6 阶段**: Deletion Governance 的集成测试与 ESLint 规范修复已完成，工作区已清理并提交 (`f7987dd`)。
- 当前阶段:Phase 10(勘察先行轮)
- **架构指引**: 详见 `docs/implementation-plan.md` Section 9；实际路由前缀对齐现有 `/api/v1/admin/kpi`。
- **Phase 7 Task 1**: 已创建 `mv_daily_user_stats` / `mv_weekly_dept_stats` Materialized Views 迁移，并在 scheduler 注册每日 00:45 刷新任务；本地 PostgreSQL 已验证 `alembic upgrade head`、MV refresh、`alembic check`。
- **Phase 7 Task 2**: 已新增 `/api/analytics/*` FastAPI 接口：user-trend / department-compare / project-health / sprint-efficiency；集成测试覆盖 MV 读取、manager 访问和 employee 越权拦截。
- **Phase 7 Task 3/4**: 已安装 Recharts、封装 `TrendLineChart` / `CompareBarChart`，并在 Dashboard 集成个人趋势、部门对比、项目健康、Sprint 效率四块图表；`npm run lint` 与 `npm run typecheck` 通过。
- **Phase 8 Task 1**: 已引入 `reportlab` / `pypdf`，新增 `scripts/fetch_export_font.py` 字体下载与 SHA256 校验脚本，建立 `app/services/export/` 字体 lazy 注册入口，并补充生产首次部署字体初始化说明；字体二进制不提交入库。
- **Phase 8 Task 2/3/4**: 已新增数据导出 service 层：日报多 Sheet Excel、月度评分 PDF、项目摘要 Excel；PDF 入口统一调用 `_ensure_font()`，项目摘要缺失/软删返回 HTTP 404。
- **Phase 8 Task 5/6**: 已在 `/api/v1/export` 暴露 reports / scores / project-summary 三个新端点，并新增 `tests/test_export_phase8.py` 覆盖 service、路由、权限、参数校验与 PDF 中文抽取。
- **Phase 8 Task 7/8**: 已扩展前端 `/export` 页面，支持日报多维汇总、月度评分 PDF、项目摘要三类新下载卡片；`docs/implementation-plan.md` 已补充实际 `/api/v1/export/...` 路径偏差说明。接口列表: `/reports`、`/scores`、`/project-summary`；选型:Excel 使用 `openpyxl`，PDF 使用 `reportlab`；限制:PDF 字体首次部署需下载约 17MB 到本地 ignored 目录。
- **Phase 9 Task 1 (T-901 + T-901-FIX)**: 已新增 `kpi_targets` 表与 `KpiTarget` ORM 模型(`KpiScope/KpiMetric/KpiPeriod` 三 Enum),两条 Alembic migration(建表 + UNIQUE NULLS NOT DISTINCT 修复)+ 4 行 seed,`alembic upgrade head` 与 `alembic check` 全绿。
- **Phase 9 Task 2 (T-902)**: 已落地 `app/schemas/kpi.py`(4 个 Pydantic V2 schema)+ `app/services/kpi_service.py`(`list_kpi_targets` / `upsert_kpi_target` / `calculate_kpi_achievement`);达成率服务复用 Phase 7 MV `mv_daily_user_stats` / `mv_weekly_dept_stats`,缺数据返回 `actual=None / status='no_data'`。
- **Phase 9 Task 3 (T-903)**: 已新增 `/api/v1/admin/kpi/` 三端点(GET 列表 / POST upsert / GET achievement),`require_role(admin, manager)` RBAC 守卫,period 参数 Pydantic 校验。
- **Phase 9 Task 4 (T-904)**: 已新增 `backend/tests/test_kpi_phase9.py` 9 个三层测试(Model 2 + Service 3 + Router 4),NULLS NOT DISTINCT 负向 + Enum 校验 + upsert UPDATE 路径 + no_data 路径 + RBAC + 422 全部覆盖。
- **Phase 9 Task 5 (T-905)**: 已新增 `frontend/src/app/admin/kpi/page.tsx` admin/manager 管理页(表格 + Modal 新建/编辑 + 编辑模式四元组锁 + 三层客户端校验 + hydrate 安全占位 + 422 detail 解析)。
- **Phase 9 Task 6 (T-906)**: 已新增 `frontend/src/components/dashboard/kpi-achievement-panel.tsx`(period 切换器 + `CompareBarChart` 目标蓝/实际绿双柱 + 7 列状态彩色 tag 详情表),在 `/dashboard` 通过 `canManageAlerts` 守卫嵌入,不动 Phase 7 `CompareBarChart` 与 T-905 管理页。
- **Phase 9 Task 7 (T-907)**: 文档收尾 + 后端测试补全 3 个用例(achievement 真路径计算 / router POST 创建 / manager RBAC),Phase 9 全闭环。
- **Phase 9 Task 8 (T-908)**: 修 metric 枚举漂移,后端 ORM/PG ENUM `sprint_completion` → `objective_completion`(单条 `ALTER TYPE RENAME VALUE` DDL 原子重命名 + seed 自动同步),前后端命名统一。Phase 9 PR 已自洽。

## 历史移交记录
- [2026-05-27 by Commander] Phase 10 启动 — Phase 9 KPI 已 push origin/main(`0b2a150`),Phase 10 不擅自臆造任务,改派 T-1001 勘察先行,落盘 plan §10 实际落地路径表后再起草后续 task。
- [2026-05-27] Phase 9 Task 8 (T-908) 完成:后端 KpiMetric `sprint_completion` → `objective_completion`,前后端枚举对齐,Phase 9 PR 闭环可推送。
- [2026-05-27] Phase 9 Task 7 完成:`docs/recap.md` + `docs/implementation-plan.md §9` 同步,后端测试补全 3 个用例。Phase 9 闭环。
- [2026-05-27] Phase 9 Task 6 (T-906) 完成:Dashboard `KpiAchievementPanel` 面板,target-vs-actual `CompareBarChart` + 状态彩色 tag 详情表;`/dashboard` 12.8 kB / 338 kB First Load。
- [2026-05-27] Phase 9 Task 5 (T-905) 完成:`/admin/kpi` 管理页,admin/manager RBAC + scope 联动 + 四元组编辑锁 + 422 detail 数组解析;`/admin/kpi` 4.17 kB / 220 kB First Load。
- [2026-05-27] Phase 9 Task 4 (T-904) 完成:`tests/test_kpi_phase9.py` 9 个三层测试,全套后端 `pytest tests/` 157 passed / 2 skipped 无回归。
- [2026-05-27] Phase 9 Task 3 (T-903) 完成:`/api/v1/admin/kpi/{,achievement}` 三端点,`require_role` admin/manager + period 枚举校验。
- [2026-05-27] Phase 9 Task 2 (T-902) 完成:`KpiTargetIn/Out + KpiAchievementRow/Response` Pydantic + `kpi_service` 三函数,达成率复用 Phase 7 MV。
- [2026-05-27] Phase 9 Task 1 / T-901-FIX 完成:`kpi_targets` 表 + UNIQUE NULLS NOT DISTINCT 修复,4 行 seed 与 BaseMixin 字段就位。
- [2026-05-27] Phase 8 Task 7/8 前端与文档完成：`/export` 页面新增三类导出卡片，implementation plan §8 同步实际 API 路径。
- [2026-05-27] Phase 8 Task 5/6 后端闭环完成：3 个导出 API + Pytest 集成测试与 PDF 中文校验。
- [2026-05-27] Phase 8 Task 2/3/4 导出 service 层完成：`reports_excel.py`、`scores_pdf.py`、`project_summary_excel.py` 与公共 Excel 样式模块。
- [2026-05-27] Phase 8 Task 1 数据导出基础设施完成：PDF/测试依赖、Noto Sans SC 字体脚本、字体忽略策略与部署说明。
- [2026-05-27] Phase 7 Task 3/4 前端图表完成：Recharts 组件封装 + Dashboard Analytics 模块。
- [2026-05-27] Phase 7 Task 2 Analytics API 完成：4 个接口 + Pytest 集成测试 + ruff 通过。
- [2026-05-27] Phase 7 Task 1 数据库预聚合层完成：Materialized Views + CONCURRENTLY 刷新调度。
- [2026-05-27] V2.6 删除清理 dry-run 和质量门禁加固完成。
- [2026-05-26] V2.4 Stage 3 设计与 V2.6 核心历史记录表建立。
