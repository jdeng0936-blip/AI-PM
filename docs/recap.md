# AI-PM Recap

## 最新进度摘要
- **V2.6 阶段**: Deletion Governance 的集成测试与 ESLint 规范修复已完成，工作区已清理并提交 (`f7987dd`)。
- **当前阶段**: **Phase 8 数据导出**。
- **架构指引**: 详见 `docs/implementation-plan.md` Section 8；实际路由前缀对齐现有 `/api/v1/export`。
- **Phase 7 Task 1**: 已创建 `mv_daily_user_stats` / `mv_weekly_dept_stats` Materialized Views 迁移，并在 scheduler 注册每日 00:45 刷新任务；本地 PostgreSQL 已验证 `alembic upgrade head`、MV refresh、`alembic check`。
- **Phase 7 Task 2**: 已新增 `/api/analytics/*` FastAPI 接口：user-trend / department-compare / project-health / sprint-efficiency；集成测试覆盖 MV 读取、manager 访问和 employee 越权拦截。
- **Phase 7 Task 3/4**: 已安装 Recharts、封装 `TrendLineChart` / `CompareBarChart`，并在 Dashboard 集成个人趋势、部门对比、项目健康、Sprint 效率四块图表；`npm run lint` 与 `npm run typecheck` 通过。
- **Phase 8 Task 1**: 已引入 `reportlab` / `pypdf`，新增 `scripts/fetch_export_font.py` 字体下载与 SHA256 校验脚本，建立 `app/services/export/` 字体 lazy 注册入口，并补充生产首次部署字体初始化说明；字体二进制不提交入库。
- **Phase 8 Task 2/3/4**: 已新增数据导出 service 层：日报多 Sheet Excel、月度评分 PDF、项目摘要 Excel；PDF 入口统一调用 `_ensure_font()`，项目摘要缺失/软删返回 HTTP 404。
- **Phase 8 Task 5/6**: 已在 `/api/v1/export` 暴露 reports / scores / project-summary 三个新端点，并新增 `tests/test_export_phase8.py` 覆盖 service、路由、权限、参数校验与 PDF 中文抽取。

## 历史移交记录
- [2026-05-27] Phase 8 Task 5/6 后端闭环完成：3 个导出 API + Pytest 集成测试与 PDF 中文校验。
- [2026-05-27] Phase 8 Task 2/3/4 导出 service 层完成：`reports_excel.py`、`scores_pdf.py`、`project_summary_excel.py` 与公共 Excel 样式模块。
- [2026-05-27] Phase 8 Task 1 数据导出基础设施完成：PDF/测试依赖、Noto Sans SC 字体脚本、字体忽略策略与部署说明。
- [2026-05-27] Phase 7 Task 3/4 前端图表完成：Recharts 组件封装 + Dashboard Analytics 模块。
- [2026-05-27] Phase 7 Task 2 Analytics API 完成：4 个接口 + Pytest 集成测试 + ruff 通过。
- [2026-05-27] Phase 7 Task 1 数据库预聚合层完成：Materialized Views + CONCURRENTLY 刷新调度。
- [2026-05-27] V2.6 删除清理 dry-run 和质量门禁加固完成。
- [2026-05-26] V2.4 Stage 3 设计与 V2.6 核心历史记录表建立。
