# Phase 8: 数据导出 (Data Export — Excel & PDF)

## 当前状态与上下文

- V2.6 删除治理 + 质量闸门加固已合并(最新提交 `f7987dd`,138 tests passed)。
- Phase 7 历史趋势看板已落地(`/api/analytics/*`、Materialized Views、前端 Recharts)。
- 当前 `backend/app/routers/export.py` 已有 2 个旧接口可作为参考但 **不要删改**(保留兼容):
  - `GET /api/v1/export/daily-reports` — 单 Sheet Excel
  - `GET /api/v1/export/daily-reports-csv` — CSV
- 业务流转入 **Phase 8**。目标:让总经理 / 部门负责人能离线拿到「日报多维汇总 Excel」「月度评分 PDF」「项目摘要 Excel」三类文件,直接用于汇报。
- 路径规约:`/api/v1/export/{reports,scores,project-summary}` —— 保持与现有路由 `prefix="/api/v1/export"` 一致(对 `implementation-plan.md §8` 的 `/api/export/...` 做 `/v1/` 对齐)。

## 任务看板

### 依赖与基础设施 (Deps & Foundation)
- [ ] **Task 1: 引入 reportlab / pypdf / 中文字体获取脚本(一次性收口所有依赖问题)**
  - **requirements.txt 追加三项**(分块标注):
    - `reportlab>=4.0,<5.0` — PDF 生成(纯 Python,无系统依赖,优于 weasyprint)
    - `pypdf>=4.0,<6.0` — PDF 文本抽取,**仅测试用**,放在 `# ── 数据导出测试 (Phase 8) ──` 注释块下
  - **中文字体获取策略**:**不**将字体二进制 commit 进 git(体积 ~10MB,git 不友好)。
    - 新建 `backend/scripts/fetch_export_font.py`:
      ```python
      # 从 jsDelivr CDN(国内可达)拉取 NotoSansSC-Regular.ttf
      URL = "https://cdn.jsdelivr.net/gh/notofonts/notofonts.github.io@main/fonts/NotoSansSC/full/ttf/NotoSansSC-Regular.ttf"
      TARGET = Path(__file__).parent.parent / "app/services/export/fonts/NotoSansSC-Regular.ttf"
      # 用 httpx/urllib 下载,SHA256 校验后落盘
      ```
    - SHA256 期望值在脚本内硬编码(下载后第一次跑出来记下来),后续校验失败直接 raise。
    - `backend/app/services/export/fonts/` 目录建立,加 `.gitkeep` + `.gitignore`(忽略 `*.ttf`/`*.otf`)。
    - 在 `backend/README.md` 或 `docs/PRODUCTION_DEPLOY.md` 加一节「Phase 8 首次部署需跑 `python scripts/fetch_export_font.py`」。
  - **如果当前环境无网络**:回退方案是在 macOS 找 `/System/Library/Fonts/PingFang.ttc` 临时跑通本地测试,但 CI/生产仍依赖 fetch 脚本。这种回退**只在开发机用**,不要 commit 任何指向系统字体的硬编码路径。
  - **service 初始化**:在 `app/services/export/__init__.py` 写一次性 lazy 注册:
    ```python
    def _ensure_font():
        if "NotoSansSC" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("NotoSansSC", FONT_PATH))
    ```
    所有 PDF 入口先调 `_ensure_font()`,字体文件缺失则抛 `RuntimeError("请先运行 fetch_export_font.py")`,提示信息明确。
  - **验证标准**:
    1. `python scripts/fetch_export_font.py` 跑通,字体落盘 + SHA256 通过。
    2. `python -c "from reportlab.pdfgen import canvas; ..."` 写一个测试 PDF,用 `pypdf` 读出来包含「测试」二字。
    3. `pip install -r requirements.txt` 在 clean venv 内成功。

### 后端 Service 层 (services/export/)
- [ ] **Task 2: `services/export/reports_excel.py` — 多 Sheet 日报汇总**
  - 函数签名:`async def build_reports_workbook(db, *, start_date, end_date, department=None) -> BytesIO`。
  - 3 个 Sheet:
    1. **汇总** — 期间提交率、平均分、合格率、退回率、Top 5 高分员工。
    2. **每日明细** — 复用现有 `daily-reports` 的列结构,新增「部门」列筛选支持。
    3. **部门小结** — 按部门 group by:提交人数 / 平均分 / 合格率 / 卡点数。
  - 样式继续沿用现有 `header_fill / pass_fill / fail_fill / thin_border` 三件套,提取为 `_styles.py` 公共模块。
  - 冻结每 Sheet 首行,Sheet 1 末尾追加一张原生 Excel 柱状图(`BarChart`,数据来自部门小结)。

- [ ] **Task 3: `services/export/scores_pdf.py` — 月度评分 PDF 报告**
  - 函数签名:`async def build_scores_pdf(db, *, month: str, department=None) -> BytesIO`,`month` 形如 `"2026-05"`。
  - 内容版面(A4 纵向,自上而下):
    1. 封面标题 + 期间 + 部门(全部门时显示「全公司」)+ 生成时间。
    2. 关键指标卡(提交人数 / 平均分 / 合格率 / 卡点未解决数),四格表格。
    3. 部门评分对比 —— `reportlab.platypus.Table`,带 zebra 行底色。
    4. Top 10 / Bottom 5 员工评分 —— 两张并列表格,Bottom 5 用红字提示。
    5. 风险预警明细 —— 当月未解决 + 已升级的 `risk_alerts` 列表(最多前 20 条)。
    6. 页脚:页码 `Page X / Y` + 生成时间戳。
  - 中文字体注册见 Task 1,不能让 reportlab 默认 Helvetica 处理中文。

- [ ] **Task 4: `services/export/project_summary_excel.py` — 单项目多 Sheet 摘要**
  - 函数签名:`async def build_project_summary_workbook(db, *, project_id: UUID) -> BytesIO`。
  - 4 个 Sheet:
    1. **项目概况** — 名称 / 编码 / track / 当前阶段 / 健康度 / 负责人 / 创建时间。
    2. **里程碑与 Sprint** — 当前及历史 Sprint(`sprint_number`、起止日期、完成率、燃尽情况)。
    3. **关联日报** — 该项目下所有 `daily_reports`(按日期倒序,过滤 `deleted_at IS NULL`)。
    4. **风险与卡点** — `risk_alerts` 历史 + `daily_reports.parsed_content.blocker` 提取。
  - 若 `project_id` 不存在或已软删,抛 `HTTPException(404, "项目不存在或已删除")`。

### 后端 Router 层 (routers/export.py)
- [ ] **Task 5: 在现有 `export.py` 追加 3 个端点**
  - `GET /api/v1/export/reports?format=xlsx&start_date=&end_date=&department=`
    - `format` 仅接受 `xlsx`,其余返回 400。
    - 默认日期范围:近 7 天(沿用现有 default 行为)。
    - RBAC:`require_role(UserRole.admin, UserRole.manager)`。
    - 文件名 `AI日报汇总_{start_date}_{end_date}.xlsx`,RFC 5987 编码沿用现有写法。
  - `GET /api/v1/export/scores?format=pdf&month=YYYY-MM&department=`
    - `month` 必填,正则 `^\d{4}-(0[1-9]|1[0-2])$`,不合法返回 422。
    - `format` 仅接受 `pdf`。
    - RBAC:`require_role(UserRole.admin, UserRole.manager)`。
    - `media_type="application/pdf"`,文件名 `评分报告_{month}.pdf`。
  - `GET /api/v1/export/project-summary?format=xlsx&project_id=UUID`
    - `project_id` 必填。
    - RBAC:`require_role(UserRole.admin, UserRole.manager)` —— 项目负责人是否允许,待 Task 5 评估;先收紧到 admin/manager。
    - 文件名 `项目摘要_{project.code}_{date.today()}.xlsx`。
  - **保留** `daily-reports` 和 `daily-reports-csv` 两个旧接口不动。
  - 所有端点统一异常包装:openpyxl / reportlab 抛出时返回 500 + 中文错误信息,日志走 `logger.exception`。

### 测试 (tests/)
- [ ] **Task 6: 服务层 + 路由层测试**
  - 新增 `backend/tests/test_export_phase8.py`,沿用 `test_deletion_cleanup.py` 的本地 `db_session` fixture 模式(避免踩 pytest-asyncio 1.x loop_scope 坑)。
  - 单元测试:
    - `test_build_reports_workbook_returns_three_sheets` — 用 openpyxl 重新打开 BytesIO 校验 3 个 Sheet 标题。
    - `test_build_reports_workbook_filters_by_department` — seed 两个部门数据,验证「每日明细」Sheet 只出现指定部门行。
    - `test_build_scores_pdf_renders_chinese_without_tofu` — 用 `pypdf`(Task 1 已装)抽取首页文本,断言包含「评分报告」「平均分」等中文,且 **不**出现 `■`(■ 豆腐块) 字符。
    - `test_build_project_summary_workbook_404_when_deleted` — 项目软删后调用应抛 HTTPException 404。
    - `test_pdf_skipped_when_font_missing` — 显式删除字体文件后,PDF 入口应抛 `RuntimeError` 含「fetch_export_font.py」字样;之后用 `pytest.fixture` 自动恢复字体(或用 `monkeypatch` 改 FONT_PATH 到临时 dir 模拟缺失)。
  - 集成测试(走 `client` fixture):
    - 三个端点的 200 路径 + content-type + filename header 校验。
    - 权限测试:普通员工身份调用应返回 403。
    - 参数校验:`/scores?month=2026-13` 返回 422,`/reports?format=docx` 返回 400。
  - **CI 注意**:测试跑前需保证 `scripts/fetch_export_font.py` 已执行 —— 在 conftest 加一个 session-scoped autouse fixture,若字体缺失则 `pytest.skip` 整个 PDF 测试模块,而不是让整套测试挂掉。

### 前端 UI (frontend/src/app/export/)
- [ ] **Task 7: 扩展 `/export` 页面**
  - 当前 `frontend/src/app/export/page.tsx` 只支持「日报 Excel/CSV」,新增三个 card:
    1. **日报多维汇总(xlsx)** — 起止日期 + 部门下拉,调 `/api/v1/export/reports`。
    2. **月度评分报告(pdf)** — 月份选择器(`<input type="month">`)+ 部门下拉,调 `/api/v1/export/scores`。
    3. **项目摘要(xlsx)** — 项目选择器(复用 dashboard 已有项目列表 API),调 `/api/v1/export/project-summary`。
  - 文件下载继续使用 `fetch + Blob + a.href` 模式(保持与现有 `ExportPage` 一致)。
  - 错误处理:接口返回非 2xx 时弹 toast,显示 `resp.text()` 或固定中文文案。
  - 通过 `npm run lint` 不留 ESLint 警告。

### 文档与收尾
- [ ] **Task 8: 文档同步**
  - 更新 `docs/recap.md` 追加 Phase 8 章节,包括:接口列表 / 选型理由 / 已知限制(如「PDF 字体落盘后镜像体积 +3MB」)。
  - 在 `docs/implementation-plan.md §8` 末尾补一段「实际落地路径」对齐 `/api/v1/export/...` 前缀的偏差说明。
  - 检查 `requirements.txt` diff:仅新增 `reportlab` 和(可选)`pypdf`,不要顺手升级其他包。

## 质量闸门(Codex 提交前必跑)

```bash
cd backend && .venv/bin/ruff check . && .venv/bin/mypy app/services/export/ app/routers/export.py
cd backend && .venv/bin/pytest tests/test_export_phase8.py -v
cd frontend && npm run lint && npm run typecheck
```

全绿后才能打 `feat(export):` 原子提交。

---

> **执行协议提醒 (Codex 请注意)**:
> 1. 每次认领任务前,将上方对应方括号修改为 `[/]`,并立即提交 `chore(lock): wip for task X`。
> 2. 完成后修改为 `[x]` 并进行相关原子 `feat(export):` 或 `fix(export):` 提交。
> 3. **不要删改** `/api/v1/export/daily-reports` 与 `/daily-reports-csv` 两个旧接口 —— 它们是 backward compat 保留品。
> 4. PDF 中文字体文件较大,如 license 允许请直接 commit 进仓库;若不允许则改用 `assets-loader` 启动时下载,并在 README 提示。
> 5. 完工后更新 `docs/recap.md`,然后由 QA Agent(我)接手跑全套质量闸门 + 数据库级集成测试补强。
