# AI-PM 业务 MVP 验证清单

> **使用对象**:你(PO / 验证人,jdeng)
> **目标**:本机走完这 10 条金路径,**用客观打勾的方式判定 MVP 是否可交付**。
> **总耗时**:约 60 分钟一遍。
> **前置条件**:已跑通 `scripts/seed_demo_data.py`,DB 至少有 378 条日报 + 3 项目 + 23 用户。
>
> **判定标准**:
> - **10 条全 ✅** → MVP 通过,可交付给同事接手部署
> - **8-9 条 ✅** → 记下 ❌ 项,做 1-2 天修复后再验
> - **≤ 7 条 ✅** → 暂不交付,需要回到开发阶段

---

## 0. 验证前的环境准备(5 min)

```bash
# 1. 容器健康
docker ps --filter "name=aipm" --format 'table {{.Names}}\t{{.Status}}'
# 期望:aipm-postgres Up healthy, aipm-redis Up healthy

# 2. 启后端(开一个终端)
cd /Users/hycdq2026/Downloads/AI-PM-main/backend
.venv/bin/uvicorn app.main:app --reload --port 8000

# 期望终端输出:
#   ✅ 徽远成 AI-PM 后端启动成功
#   ⏰ APScheduler 已启动,注册了 11 个定时任务

# 3. 启前端(另开终端)
cd /Users/hycdq2026/Downloads/AI-PM-main/frontend
npm run dev

# 期望:Local: http://localhost:3000

# 4. 健康自检 — 系统多维度健康
curl -s http://localhost:8000/health/detailed | python3 -m json.tool
```

**Checkpoint 0** ☐
- 后端 11 任务全部注册
- `/health/detailed` 返回 `status: "ok"`,4 个 check 全绿(database/redis/sentry/scheduler)
- 前端 `http://localhost:3000` 可访问

---

## 1. 金路径 #1 — admin 登录 + Dashboard 全景(5 min)

### 操作
1. 浏览器打开 `http://localhost:3000`
2. 用 **admin / admin2026** 登录(首次登录会弹改密界面,改成自己记得住的密码,后续都用新密码)
3. 进入 Dashboard

### 预期结果 ☐
- [ ] Dashboard 顶部显示**3 个项目卡片**:
  - `P2026-001 206 智能样机研发与量产` — **yellow** 健康度 78 分
  - `P2026-002 智能仓储调度系统` — **green** 健康度 88 分
  - `P2026-003 客户智能合同审核` — **green** 健康度 95 分
- [ ] 风险预警区显示 **≥ 5 条** 预警条目(共 8 条,部分 resolved 可能不显示)
- [ ] 看到一些预警是 "讯飞 ASR 偶发 502"、"206 核心 IC 延迟 3 天到货" 等
- [ ] 最近日报流显示 ≥ 10 条今日/昨日日报

### ❌ 失败排查
- 看不到项目 → 检查 `docker exec aipm-postgres psql -U aipm -d aipm_db -c "select count(*) from projects;"` 是否 = 3
- 看不到日报 → 同上换成 `daily_reports`,应 = 378
- 健康度颜色错乱 → 数据没问题但前端逻辑可能有 bug,优先级低,记录后继续

---

## 2. 金路径 #2 — 项目详情 + IPD 5 阶段 + Gate 通过记录(7 min)

### 操作
1. 从 Dashboard 点击 **P2026-001 206 智能样机** 卡片(或访问 `/projects` 列表)
2. 查看项目详情页

### 预期结果 ☐
- [ ] 看到 IPD **5 个阶段卡片** 横向排列:
  - 阶段 1 概念与立项期 — **green** 100% 已通过 Gate ✅
  - 阶段 2 计划与设计期 — **green** 100% 已通过 Gate ✅
  - 阶段 3 双轨并行开发期 — **yellow** 62% 进行中(高亮当前)
  - 阶段 4 集成与测试期 — **locked** 未开始
  - 阶段 5 量产与交付期 — **locked** 未开始
- [ ] 项目成员列表显示 **7 人**(林跃文/郑韬慧/张毅/郭震/新雷/技术部长/采购经理)
- [ ] 每个人有 track 标注(hardware/software/both)
- [ ] 阶段 2/3 的 **里程碑** JSONB 可见,有"硬件方案评审 done"、"PCB 样机贴片 done"、"固件 v0.5 烧录 in_progress" 等条目
- [ ] 预算栏显示 145 万 / 280 万(52% 已用)

### 探索性挑战
- 试着切换到 **P2026-002 智能仓储**,确认它是 stage 4 + 已通过 Gate 1/2/3
- 试切到 **P2026-003 合同审核**,确认它在 stage 1(立项期,70% 进度)

---

## 3. 金路径 #3 — 提日报 + AI 自动评分(关键链路!10 min)

> ⚠️ **这是 MVP 的核心链路**。AI 日报功能是否真的工作直接决定 MVP 价值。
> 前提:`.env` 里 `LITELLM_BASE_URL` + `LITELLM_API_KEY` 已配,**且网关能通**。
> 如果没配,这一条会卡在"AI 评分"环节,需要降级测试。

### 操作 A:用 admin 看历史日报已被 AI 评分
1. 从导航进入 **日报 / 报告** 页(`/reports` 或 `/submit-report`)
2. 选今天往前 7 天范围,查看张毅 / 新雷的日报

### 预期结果 A ☐
- [ ] 每条日报都有 **ai_score**(60-95 之间,大多 80+)
- [ ] 每条日报有 **ai_comment**(中文,如"日报结构完整,卡点描述具体且有可执行方案")
- [ ] parsed_content 9 字段全部可见(tasks/progress/blocker/eta/...)
- [ ] 张毅的日报会看到"压测发现并发 500 QPS 时数据库连接池打满"这种业务文本

### 操作 B:**真触发一次 AI 评分**(可选,需 LLM 网关通)
1. 切换到普通员工身份(用 **zhang_yi / aipm2026** 登录,如果你之前没改这个用户密码)
2. 进入 `/submit-report` 页面
3. 输入一段日报文本,如:
   ```
   今天搞定了 206 设备状态聚合接口的联调,前端可以接了。
   卡点:压测时连接池打满,明天加 Redis 缓存。
   ```
4. 提交,等 AI 评分

### 预期结果 B ☐
- [ ] **3-10 秒内**返回 ai_score(数字)+ ai_comment(中文)
- [ ] parsed_content 9 字段被 AI 自动提取(tasks / progress / blocker / next_step / eta 至少 5 个非空)

### ❌ 失败排查
- **AI 不回应**:看 `docker logs aipm-backend 2>&1 | grep -iE "litellm|ai_engine"` — 多半是 LITELLM_API_KEY 没配或网关挂
- **响应慢 > 30s**:LLM 网关高延迟,先用 historic data 验证 UI 即可
- **报"DAILY_TOKEN_LIMIT 超额"**:`.env` 改 DAILY_TOKEN_LIMIT=5000000 重启后端

---

## 4. 金路径 #4 — OKR 三层树 + KR 进度可视化(5 min)

### 操作
1. 导航进入 **OKR** 页(`/okr`)
2. 选 **2026Q2** 周期

### 预期结果 ☐
- [ ] 看到 **4 个 Objective**:
  - 总经理:Q2 完成 206 智能样机 TR6(progress 62%)
  - 技术部长:智能仓储系统上线试运行(progress 78%)
  - 销售部长:Q2 销售合同审核效率提升 50%(progress 15%)
  - 技术部长:团队工程效能与质量基线建设(progress 70%)
- [ ] 每个 O 展开有 **2-3 个 KR**
- [ ] KR 显示 **current_value / target_value + 单位**,如:
  - `固件 v1.0 通过 UAT,缺陷 <= 5` 当前 8 / 目标 5(超标,red)
  - `AI 集成响应延迟 ≤ 800ms` 当前 920 / 目标 800(超标,red)
  - `压测峰值 ≥ 1500 QPS` 当前 1820 / 目标 1500(完成,green)
- [ ] **置信度(confidence)** 显示 0.4-0.95 不等
- [ ] 进度条颜色:进度 < 50% red,50-80% yellow,> 80% green

### 探索
- 试着点开 "Q2 完成 206 智能样机 TR6",看 KR 详情有没有 owner / unit / description

---

## 5. 金路径 #5 — Sprint 燃尽图(7 min)

### 操作
1. 导航 **Sprint** 页(`/sprints`)
2. 选 P2026-001 → **Sprint 2(active,进行中)**

### 预期结果 ☐
- [ ] 顶部显示 Sprint 元信息:
  - Sprint #2(active)
  - 目标:"完成设备状态聚合 + 告警推送,推 Sprint 1 P1 余项收口。"
  - 计划点 36 / 已完成 18
  - 健康度 82 分
- [ ] **燃尽图** 显示:
  - X 轴 14 天日期(过去 14 天到今天)
  - 蓝色"理想线" 从 36 → 0 直线下降
  - 橙色"实际线" 不是直线,有起伏(seed 加了 ±1 波动)
- [ ] 任务列表显示 **8 个任务**,状态分布:
  - 3-4 个 `done` ✅
  - 1 个 `blocked` 🚧
  - 2-3 个 `in_progress` ⏳
  - 1-2 个 `todo` 📋
- [ ] **关键路径任务** 有红色 / 显眼标识(MQTT 设备接入、后端设备状态聚合 等)

### 探索
- 切到 Sprint 1(completed),看是否能看到 **retrospective**(回顾)字段 — "went_well:接口契约写得清楚..."

---

## 6. 金路径 #6 — 资源水位看板 + AI 调配建议(5 min)

### 操作
1. 导航 **资源水位 / 容量** 页(`/capacity`)
2. 选当前 active Sprint(P2026-001 Sprint #2)

### 预期结果 ☐
- [ ] 看到 **3-5 位软件成员** 的水位卡片(张毅/郭震/新雷)
- [ ] 每个成员显示:
  - 已分配点数 / 容量(如 `12 / 10`,意味着 120%)
  - **占用率百分比** + 等级颜色(idle/healthy/high/overload)
  - 关键路径任务数(1-3 个)
  - 已 done 点数
- [ ] **过载成员** 显示 **AI 调配建议**,如:"建议把 1 个 P2 任务从该成员转出,或者把 Sprint 1 P3 任务延后。当前占用率 120%,超出健康水位。"
- [ ] **闲置成员** 显示建议:"占用率仅 X%,可承接更多 P1 任务"

---

## 7. 金路径 #7 — 30 天趋势分析(5 min)

### 操作
1. 导航 **趋势 / 数据分析** 页(`/trends`)
2. 选时间范围:**过去 30 天**

### 预期结果 ☐
- [ ] 看到 **个人评分趋势曲线**:
  - 每个员工有 21 个数据点(过去 30 天 × 工作日)
  - ai_score 在 60-95 之间波动
  - 大多数线整体平稳,反映 demo 数据真实性
- [ ] **部门对比** 视图:技术部 / 商务部 / 销售部 平均分柱状图
- [ ] **日报数量统计**:总计 378 条
- [ ] **progress 字段聚合曲线**:随时间线性上升(seed 时按 day_offset 调整 progress 让曲线漂亮)

---

## 8. 金路径 #8 — AI 周报生成(关键链路!8 min)

> ⚠️ **第二条核心 AI 链路**。验证 LLM 是否能把过去一周日报聚合成结构化周报。

### 操作 A:从前端触发
1. 导航 **趋势** 页或 **Chat** 页,找"生成周报"按钮(或调 API)
2. 选范围:**过去 7 天**

### 操作 B:直接调 API(更可控)
```bash
# 用 admin token(浏览器登录后从 DevTools cookie 或 localStorage 拷出 access_token)
TOKEN="<你的 JWT>"
curl -X POST http://localhost:8000/api/v1/chat/weekly-report \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scope": "person", "target_id": null}' | python3 -m json.tool
```

### 预期结果 ☐
- [ ] **10-30 秒内**返回结构化周报,包含:
  - 总览:本周完成 X 件事,卡点 Y 件
  - 按项目分组的成果(P2026-001/002/003 各自一段)
  - **本周亮点**(从高分日报里提)
  - **本周风险**(从 management_alert 里提)
  - **下周建议** / 重点关注
- [ ] 文本逻辑通顺,**引用了实际数据**(比如"压测 1820 QPS 完成 KR"、"讯飞 ASR 502 问题持续")

### ❌ 失败排查
- 同金路径 #3 的 LLM 失败排查
- 如果 LLM 没配,可以用 Mock 数据演示:跳过此条但要记录 ⚠️

---

## 9. 金路径 #9 — AI 复盘库 / 知识检索(5 min)

### 操作
1. 导航 **AI 复盘 / 知识库** 页(`/retro`)
2. 浏览 5 条种子知识条目

### 预期结果 ☐
- [ ] 看到 **5 个分类** 各有内容:
  - FAQ:`如何申请项目预算追加?`
  - 最佳实践:`如何写一份让 AI 高分的日报`
  - 经验教训:`Gate 评审常见失败原因(经验教训)`
  - 模板:`Sprint 回顾会模板`
  - 复盘报告:`2025Q4 206 项目复盘报告`
- [ ] 每条有 view_count + helpful_count(seed 时 5-80 / 2-25 随机)
- [ ] 点开后看到 markdown 渲染(标题层级、列表、加粗都正常)

### 探索
- 试搜索 "Gate" → 应该至少命中 2 条(经验教训 + 复盘报告)
- 试搜索 "Sprint" → 应该命中模板 + 复盘报告

> ⚠️ **已知限制**:种子数据 **没有写入 embedding 向量**(避免 demo 阶段强依赖 OpenAI API)。所以纯文本搜索可以工作,**向量相似度检索** 需要后续补一个 embedding 回填脚本才能完整验证。

---

## 10. 金路径 #10 — 多角色切换 + 部长视角(8 min)

> 验证权限隔离 + 经理 / 员工视角的差异。

### 操作
1. 退出 admin,用 **tech_director / aipm2026**(技术部长)登录
2. 看 Dashboard

### 预期结果 ☐
- [ ] 技术部长能看到 **技术部下属** 的日报(张毅/郭震/新雷/林跃文/郑韬慧)
- [ ] 能看到自己负责的 OKR(智能仓储上线 + 团队工程效能基线)
- [ ] **看不到** 销售部长 / 财务部长的私有 OKR(如果做了行级权限)
- [ ] 没有 /admin/* 入口(只有 admin 可以)

### 然后切到员工
3. 退出,用 **zhang_yi / aipm2026**(高级研发工程师)登录
4. 看 Dashboard

### 预期结果 ☐
- [ ] 张毅能提自己的日报 + 看自己历史日报
- [ ] 看到自己负责的 KR(单测覆盖率、UAT 覆盖率、CI 通过率)
- [ ] 看到自己分配到的 Sprint Task(MQTT 设备接入、后端聚合接口、UAT 用例梳理...)
- [ ] **看不到** Dashboard 的"管理层风险预警"(如果做了角色隔离)

---

## 11. 金路径 #11 — V2.2 结构化关联(项目 / Sprint 任务挂钩,8 min)

> 验证晨规划/日报与项目/任务/OKR KR 的结构化挂钩链路。
> 相关 commits:`afe7df6` → `c38ac49` → `301f22d` → `37285d6` → `ffe471d`

### 操作 A:提交一份带关联的晨规划
1. 用 **zhang_yi / aipm2026** 登录(或本地改过密码)
2. 进 `/submit-report`,切到 ☀️ 晨规划
3. 在 **"🔗 关联项目 / 任务"** 卡片:
   - 项目下拉选 `[P2026-001] 206 智能样机研发与量产 ⚠️`
   - 任务下拉等加载完(状态 disabled → 切回 enabled),选 `[P0·5pt·todo] MQTT 设备接入协议联调`(或任一带 P0 的)
4. 任意填写晨规划内容,提交

### 预期结果 A ☐
- [ ] 提交后右下角返回 JSON 含 `project_id` 和 `sprint_task_id`(非 null)
- [ ] 进 `/reports` 列表页,新行的"🔗 关联"列显示 📁 `P2026-001` + 📋 `MQTT 设备接入协议联调`
- [ ] 点开该行抽屉,头部下方有两个 chip:📁 灰色 / 📋 紫色

### 操作 B:验证联动 + 校验(挑战 happy/sad path)
1. 在 `/submit-report` 项目下拉切到另一个项目 → 任务下拉应**自动清空**(因为之前选的 task 不属于新项目)
2. 项目下拉切到 `[P2026-003] 客户智能合同审核` → 任务下拉显示"该项目当前无 active Sprint"(因为 P2026-003 还在立项期,没 Sprint)
3. 浏览器 DevTools 复现 backend 校验:
   ```bash
   # 拿 admin 的 wechat_userid 直接调 simulate(无 JWT)
   PROJ_ID=$(docker exec aipm-postgres psql -U aipm -d aipm_db -tA -c "SELECT id FROM projects WHERE code = 'P2026-003'")
   TASK_ID=$(docker exec aipm-postgres psql -U aipm -d aipm_db -tA -c "SELECT st.id FROM sprint_tasks st JOIN sprints s ON st.sprint_id=s.id WHERE s.project_id IN (SELECT id FROM projects WHERE code='P2026-001') LIMIT 1")
   curl -X POST http://localhost:8000/api/v1/simulate/daily-report \
     -H 'Content-Type: application/json' \
     -d "{\"wechat_userid\":\"admin\",\"raw_text\":\"V2.2 unit\",\"project_id\":\"$PROJ_ID\",\"sprint_task_id\":\"$TASK_ID\"}" \
     -w "\nHTTP=%{http_code}"
   ```

### 预期结果 B ☐
- [ ] 切项目时任务下拉清空 + disabled 短暂出现"加载中…"
- [ ] P2026-003 下任务下拉文案"该项目当前无 active Sprint"
- [ ] 不一致 curl 返回 `HTTP=400` + `{"detail":"Sprint 任务不属于所选项目,请重新选择"}`

### 操作 C:晚复核继承晨规划
1. 同一员工切到 🌙 晚复核
2. 上方"今日晨规划参考"卡片显示前面那份晨规划
3. **项目 + 任务下拉应自动填充**了晨规划里选的那两个

### 预期结果 C ☐
- [ ] 项目下拉自动选中 P2026-001
- [ ] 任务下拉自动选中"MQTT 设备接入协议联调"

### ❌ 失败排查
- 提交报错 500 → 看 `tail -50 /tmp/aipm_uvicorn_v22.log`,如果是 `ai_engine_mock` 缺失这是 **pre-existing bug**(与 V2.2 无关,需另行修复)
- 项目下拉空 → `docker exec aipm-postgres psql -U aipm -d aipm_db -c "select count(*) from projects;"` 应 = 3
- 任务下拉空但项目有 active Sprint → 看 `sprints.status` 是不是 `active`
- 抽屉头部没有 chip → 检查老日报可能 `project_id IS NULL`(seed 阶段 56% 概率不挂),换一条新提交的

### 已知限制
- 当前**只在 Web 端 submit-report** 暴露关联选择器;企微提交链路 (wechat.py) 暂未支持(决策 2A:Phase 2.2 不动企微,留待 V2.3 + AI 自动推断)
- 老的 378 条种子日报里 56% 没有挂项目(管理层 + 未分配项目用户),这是预期

---

## 12. 金路径 #12 — V2.3 临时工单项目化(8 min)

> 验证"用轻量项目承载日常临时工单"全链路:创建临时项目 → 员工日报关联 → 资源水位 → Dashboard 看板。
> 相关变更:`projects.is_temporary` 字段 + `compute_project_capacity` + `/dashboard/temp-ticket-summary` + `seed_temp_projects()`
> 前置:跑过 `python -m scripts.seed_demo_data` 或 `--only=temp_projects`,确认 `P2026-T01 日常支撑与临时工单` 已存在

### 操作 A:用管理员账号创建一个临时工单项目
1. 用 **admin / admin2026** 登录,进 `/projects`
2. 右上角 **新建项目** → 弹窗顶部勾选 **🎫 临时工单项目(轻量模式)**
3. 表单字段(V2.3 Stage 2 调整):
   - 项目名称、项目编号、**描述 / 任务简述**、**轨道**(下拉切换成"日常支撑 / 其它临时"二选一)、**计划交付时间**(可选)
   - **隐藏**:预算总额(临时工单不引入预算概念)
4. 输入名称:"测试日常支撑",编号留空,轨道保持默认"日常支撑" → 点 **立项**

### 预期结果 A ☐
- [ ] toast 提示 `🎫 临时工单项目 P2026-T02 创建成功`(编号自动 +1,因 seed 已有 T01)
- [ ] 列表自动开启"显示临时工单"过滤器,新项目带紫色 🎫 临时工单 chip 显示
- [ ] 副标题显示 `🎫 轻量项目 · 日常支撑 · 无 IPD 阶段`(中文 track 正确)
- [ ] 列表里所有临时项目的 track 显示中文"日常支撑/其它临时",不是英文 raw value
- [ ] DB 验证:
  ```bash
  docker exec aipm-postgres psql -U aipm -d aipm_db -c \
    "select code, is_temporary, current_stage from projects where code like 'P2026-T%';"
  # 应看到 P2026-T01(seed) + P2026-T02(刚建),is_temporary=true
  docker exec aipm-postgres psql -U aipm -d aipm_db -c \
    "select count(*) from project_stages where project_id in (select id from projects where is_temporary=true);"
  # 应 = 0(临时项目不展开 5 阶段)
  docker exec aipm-postgres psql -U aipm -d aipm_db -c \
    "select sprint_number, goal, status from sprints where project_id in (select id from projects where is_temporary=true);"
  # 每个临时项目应有 1 行:sprint_number=0, goal='Backlog (临时工单归集池)', status=active
  ```

### 操作 B:员工提交日报关联到临时项目
1. 注销切到 **zhang_yi / aipm2026**,进 `/submit-report` 切到 ☀️ 晨规划
2. 在 **"🔗 关联项目 / 任务"** 卡片,展开项目下拉 → **临时工单项目应置顶**,选 `🎫 [P2026-T01] 日常支撑与临时工单 · 临时工单`
3. 选中后下拉**下方应出现紫色提示**:"已选临时工单项目,本日报将自动归入「Backlog 池」,无须挂具体任务"
4. 右侧任务下拉应 disabled,占位文案"— 临时工单无须选任务 —"
5. 任意填写晨规划内容,提交

### 预期结果 B ☐
- [ ] 提交后 JSON 含 `project_id` 指向 P2026-T01,`sprint_task_id` 为 null
- [ ] `/reports` 列表页新行的"🔗 关联"列只显示 📁 `P2026-T01`(无 📋 任务)
- [ ] 后端校验未报错(临时项目无 task,sprint_task_id=null 是允许的)

### 操作 C:Dashboard 临时工单看板验证
1. 注销切回 **admin / admin2026**,进 `/dashboard`
2. 在"AI 日报明细"和"项目健康矩阵"之间,应出现新的 **🎫 临时工单看板** 区块
3. 左卡 **本月临时工单工时 TOP N**:看 seed 的 7 条临时日报对应 3 个员工(张毅 / 郭震 / 新雷)的排名
4. 右卡 **临时 vs 主干 工时占比** 环形图:紫色扇区是临时工单占比、蓝色扇区是主干

### 预期结果 C ☐
- [ ] TOP 列表显示 3 行:郭震(3 条·12h)、张毅(2-3 条·8-12h)、新雷(2 条·8h),数字可能因刚提交的操作 B 日报有偏移
- [ ] 环形图:临时占比 ≈ 5-10%,主干占大头(基于 seed 中 daily_reports 总量)
- [ ] 直接 curl 后端确认:
  ```bash
  curl -s 'http://localhost:8000/api/v1/dashboard/temp-ticket-summary?top_n=5' \
    -H "Cookie: session=..." | python3 -m json.tool
  # 看 window / ratio / top_members 结构与卡片一致
  ```
- [ ] 项目维度聚合也能工作:
  ```bash
  PID=$(docker exec aipm-postgres psql -U aipm -d aipm_db -tA -c "select id from projects where code='P2026-T01'")
  curl -s "http://localhost:8000/api/v1/capacity/project/$PID/summary" | python3 -m json.tool
  # 返回 is_temporary=true,mode=report_count,members 列表与 TOP N 一致
  ```

### ❌ 失败排查
- 弹窗勾选 `is_temporary` 后表单没收缩 → 检查 `frontend/src/app/projects/page.tsx` 是否有 `!projectForm.is_temporary` 条件渲染
- 创建临时项目报错 500 → 看日志,大概率是 alembic 没跑 `a1f3b7c2d801`,执行 `alembic upgrade head`
- Dashboard 看板不显示 → 看浏览器 Network,/dashboard/temp-ticket-summary 应返回 200;若 403 说明账号不是 manager+
- 项目下拉里没有 🎫 临时工单 → `getProjectsOverview(false, null, true)` 第 3 个参数 includeTemporary 漏传,刷新清缓存重试
- 环形图全紫或全蓝 → ratio.total_hours=0,说明该窗口内没有挂任何 project_id 的日报,跑 `python -m scripts.seed_demo_data --only=temp_projects`

### 已知限制
- 工时口径是 **mode=report_count**(每条日报记 0.5 工日 = 4h)。当 `daily_reports` 加上 `hours_worked` 字段后,可切到 mode=hours_worked
- 临时项目固定 health_status=green,不参与红黄绿矩阵(默认 `include_temporary=false` 过滤)
- 临时项目**不挂 OKR / Gate**,V2.3 不动这条线;若未来要让某条工单影响 KR,需要前端额外提供 KR 关联入口

---

## 13. 金路径 #13 — V2.4 Stage 1 全站统一筛选(6 min)

> 验证三个列表页(项目总览 / Dashboard 日报明细 / 用户管理)统一 FilterBar + useListFilters Hook 的多维筛选能力,以及 URL params 同步(刷新不丢)。
> 相关变更:新增 `frontend/src/lib/hooks/use-list-filters.ts` + `frontend/src/components/filter-bar.tsx`;改造 projects/dashboard/users 三个页面接入。

### 操作 A:项目总览页 — 3 维筛选 + URL 同步
1. 用 **admin / admin2026** 登录,进 `/projects`
2. 在搜索框下方应看到新的 **筛选条**(紫色 Filter 图标 + 4 个下拉:轨道 / 状态 / 阶段 + "清空全部")
3. 点 **轨道** 下拉 → 勾"日常支撑"+"其它临时" → 列表收缩到只剩临时项目(需要先点右上"显示临时工单"toggle 让临时项目进入数据集)
4. 点 **状态** 下拉 → 勾"进行中" → 列表进一步收缩
5. 顶部应看到两个紫色 chip:`轨道: 日常支撑 / 其它临时` 和 `状态: 进行中`,每个 chip 都能单独 X 移除
6. **刷新页面 (Cmd-R)** → URL 里 `?proj_track=support,other&proj_status=active` 仍在 → 筛选状态完整保持

### 预期结果 A ☐
- [ ] 筛选条 UI 与项目页风格一致(紫色 accent / rounded-lg / 紧凑布局)
- [ ] 多选下拉打开时,选中项显示蓝色对号
- [ ] 数据范围行显示 `共 N 条 · 显示 M 条`(M ≤ N)
- [ ] 刷新后筛选状态不丢失
- [ ] "清空全部 (N)" 按钮一键还原全表
- [ ] 三色统计条 / 搜索框 / 显示已归档 / 显示临时工单 toggle 全部**仍然独立工作**(没被收编进 FilterBar)

### 操作 B:Dashboard 日报明细 — 4 维筛选 + 区间控件
1. 进 `/dashboard`,滚到 **AI 日报明细** section(标题应显示 `共 N 条 · 显示 M 条`)
2. 标题下方应看到 FilterBar,包含 4 个控件:部门(multi)/ 质检(boolean)/ AI 分(range)/ 进度(range)
3. **部门**下拉选 "技术部" → 列表只剩该部门
4. **质检**下拉选 "合格" → 进一步过滤
5. **AI 分** 控件改成 `85 ~ 100` → 高分日报浮出
6. **进度** 改成 `60 ~ 100` → 进一步过滤
7. 看顶部 4 个 chip 都正确显示

### 预期结果 B ☐
- [ ] 部门选项是 distinct 出来的(技术部 / 商务部 / ...,不会写死)
- [ ] AI 分 / 进度的 range 控件可输入数字(min/max 限制 0-100)
- [ ] 区间未变(0-100)时不算激活,chip 不显示
- [ ] 列表为 0 时显示"无符合筛选条件的日报"占位
- [ ] URL 里键名带 `rep_` 前缀(不与 `/projects` 的 `proj_` 冲突)

### 操作 C:用户管理 — 4 维筛选 + 后端 search 协作
1. 进 `/users`,在搜索框下方应看到 FilterBar(角色 / 部门 / 出勤 / 账号)
2. **角色** 选 "部门经理" → 表格只剩 manager
3. **账号** 选 "启用" → 进一步过滤
4. 同时在搜索框输入 "张" → 模糊匹配(走后端 search) + 前端筛选 叠加
5. 表头"共 N 条 · 筛选后 M 条" 应正确变化

### 预期结果 C ☐
- [ ] 后端拉的是 100 条/页(打开 Network 看 `?page_size=100`)
- [ ] 搜索 + FilterBar 可叠加(`张` 搜出 5 个,选 manager 后只剩 1-2 个)
- [ ] 用户 ≤ 100 人时分页按钮**不显示**(`total > USERS_PAGE_SIZE` 才出)
- [ ] URL 里键名带 `usr_` 前缀

### ❌ 失败排查
- 筛选无效 → 浏览器 DevTools 看 React state,确认 `useListFilters` 返回的 `filteredItems` 数量在变
- URL 不同步 → 看 `useListFilters` Hook 的 useEffect 是否被调到(syncToUrl 默认 true,urlPrefix 必须传)
- multi-select 下拉打开后立刻关闭 → 是 onBlur 时序问题,确认 setTimeout 150ms 还在
- 刷新后 URL params 还在但筛选没生效 → spec 的 options.value 必须与 URL 里的字符串严格匹配(注意 `current_stage` 是 number,但 spec.options.value 都是 string `'1'-'5'`,Hook 内部用 `String(itemVal)` 做了转换)

### 已知限制(Stage 2 修复)
- 用户列表 pageSize=100 是 Stage 1 权宜,Stage 2 会还原成 20 + 补后端 `role/department/is_active` query params
- FilterBar 选项 count(如"经理 (5)" 这种动态计数)Stage 1 不显示,Stage 2 加批量删除时一起做
- 多选下拉用原生 input checkbox,移动端体验有提升空间(V2.5)

---

## 14. 金路径 #14 — V2.4 Stage 2 批量软删与多选联动(10 min)

> 验证三个列表页(/reports / /projects / /users)的多选 + 批量软删/归档/禁用,以及后端 deleted_at 字段对全局聚合的隔离效果。
> 相关变更:`backend/alembic/versions/20260526_1000_v2_4_add_deleted_at.py` + 三个 batch endpoints + `useMultiSelect` Hook + `<ListActionBar />`。

### 操作 A:/reports 批量软删 + 全局聚合不受影响
1. 用 **admin / admin2026** 登录,进 `/reports`
2. 表头第一列新出现一个 **全选 checkbox**;每行最左也是 checkbox
3. 勾选 2-3 条日报 → 顶部 sticky **紫色 ActionBar** 出现:`已选 N 项 · [清除] · [🗑 批量软删]`
4. 点 [批量软删] → confirm → toast `已删除 N 条`
5. **关键回归**:
   - 同一页面列表中那 N 条立刻消失
   - 切到 `/dashboard`,"今日 AI 日报"统计的总数应**等于删除前 - 实际删除条数(限当日)**
   - 切到 `/stats` 或 `/trends`,部门评分均值**不应该**因为删除而暴跌(被删的也参与了历史平均)— 注:实际趋势接口已经加了 `deleted_at IS NULL` 过滤,所以是会从趋势中消失,符合预期

### 预期结果 A ☐
- [ ] 选中态有视觉反馈(行背景或紫色边框)
- [ ] FilterBar 切换 / 翻页时,选中态**自动清空**(防止跨页"鬼影"选中)
- [ ] 直接查 DB:`docker exec aipm-postgres psql -U aipm -d aipm_db -c "select id, report_date, deleted_at from daily_reports where deleted_at is not null limit 5;"` 应看到被删的几条 `deleted_at` 非 NULL
- [ ] AI 评分关联数据(ai_score / management_alert)**仍在 DB 里**,只是不再被前端列表 / 聚合接口读到

### 操作 B:Dashboard "AI 日报明细" 区块同步可批量软删
1. 进 `/dashboard`,滚到 **AI 日报明细** section
2. 标题右侧应有 **"全选 / 取消全选"** 小按钮(只对当前 FilterBar 后剩下的行有效)
3. 勾选若干条 → 同样的 ActionBar 出现 → [批量软删]
4. 删除后 dashboard 自动 refetch,该 section 列表收缩

### 预期结果 B ☐
- [ ] FilterBar 改部门 / 分数区间 → 选中态自动清空(因为 filteredReports 引用变了)
- [ ] 选中态高亮(紫色边框)
- [ ] 与 /reports 走同一个 `DELETE /api/v1/reports/batch` 端点(Network 面板验证)

### 操作 C:/projects 严格分路批量(临时软删 / 主干归档)
1. 进 `/projects`,右上"显示临时工单"打开
2. **场景 1 — 全是临时**:勾选 P2026-T01 + 你前面建的 P2026-T02 → ActionBar 显示 `[🗑 批量软删]` + hint "全部为临时工单 — 可批量软删"
3. 点删除 → confirm → toast `已删除 N 个临时项目`
4. **场景 2 — 全是主干**:勾选 P2026-001 + P2026-002 → ActionBar 显示 `[📦 批量归档]`(背景灰色)+ hint "全部为主干项目 — 仅批量归档"
5. **场景 3 — 混合**:勾选 1 个临时 + 1 个主干 → ActionBar 显示 `[📦 批量归档]` + hint "混合选中 — 只能批量归档(临时项目也走归档,避免歧义)"
6. **场景 4 — 后端硬保护**:打开 Network 面板,手工 curl 测一下混合 ids 直接调 `/projects/batch`:
   ```bash
   # 拿 token 后
   curl -X DELETE http://localhost:8000/api/v1/projects/batch \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"ids": ["<临时项目id>", "<主干项目id>"]}'
   # 应返回 400 + non_temp_ids: ["<主干项目id>"]
   ```

### 预期结果 C ☐
- [ ] 三种场景按钮颜色和文案正确切换
- [ ] 临时项目批量软删后,主干项目"红黄绿矩阵"(`/projects/overview` 三色统计)**仍然准确**(临时项目本来就不进矩阵)
- [ ] 删完临时项目后,挂在它下面的历史日报 `project_id` 仍指向它,但前端 dashboard 临时工单看板的 TOP5 工时会减少(被删的项目不进聚合)
- [ ] 后端 400 拦截混合 ids 生效

### 操作 D:/users 批量禁用 + 启用(只允许 admin/manager)
1. 进 `/users`,勾选 2-3 个**启用**的员工 → ActionBar 显示 `[🚫 批量停用]`(hint "全部为启用 — 可批量停用")
2. 点停用 → confirm → toast `已停用 N 个用户`
3. 切 FilterBar 的"账号" → 选"停用" → 勾选刚停的几个 + 其它历史停用的 → ActionBar 显示 `[✅ 批量启用]`(只 admin 可见)
4. 点启用 → 还原
5. **关键**:全程**没有任何"批量删除"按钮**(策略:user 真删会破坏 daily_report.user_id FK)

### 预期结果 D ☐
- [ ] 表头有全选 / indeterminate(部分选中)状态
- [ ] 停用后被禁员工的 daily_report 历史**仍可在 /reports 查到**
- [ ] manager 看不到"批量启用"(只 admin 可见)
- [ ] DB 验证:`select id, name, is_active from users where is_active = false;` 包含刚禁用的

### ❌ 失败排查
- 删完前端列表没更新 → 检查 batch 调用后是否触发 fetch 重拉;不要做乐观更新
- 全选 checkbox 没 indeterminate → 看 ref={(el) => el.indeterminate = ...} 是否生效
- ActionBar 不出现 → 看 selectedCount 是否正确(useMultiSelect 依赖 items 引用稳定,filter 变会自动清空,这是预期行为)
- 后端混合 ids 没拦截 → curl 直接打 `/projects/batch` 看返回;前端按钮逻辑 + 后端硬保护双重防护
- /trends 数据消失 → 检查趋势接口的 deleted_at 过滤是否加上(本 Stage B2 已加)

### 已知限制(Stage 3 / V2.5 修复)
- 不支持"撤销"(toast 内 5 秒撤回);删错只能 admin 直接改 DB `UPDATE ... SET deleted_at = NULL`
- 没有"已删除回收站"页面(`include_deleted=true` query param)
- chat_tools / kr_progress_extractor 等 AI 工具读 daily_reports 时**没有**加 deleted_at 过滤(AI 会看到"已删的"数据),Stage 3 补
- 其它列表(Sprint 任务 / 项目成员 / RiskAlert / KnowledgeItem)的批量操作 → V2.5
- 用户列表 pageSize=100 兜底(Stage 1 引入)→ **V2.4 Stage 3 已还原为 20 + 后端 query 支持**

---

## 15. 金路径 #15 — V2.4 Stage 3 软删配套(过滤长尾 + users 还原 + 撤销 + 回收站,8 min)

**前置**:V2.4 Stage 2(#14)已通过;backend 已重启加载新端点(`/reports/batch-restore` / `/projects/batch-restore` / `/projects/deleted` / `/users?role=...`)。

### 15.1 软删过滤长尾(C1,~1 min)

后端 grep 验证 7 个文件已加 `deleted_at IS NULL` 过滤:

```bash
for f in backend/app/services/chat_tools/{reports,weekly_report,people}.py \
         backend/app/services/retro/collectors.py \
         backend/app/routers/{gates,simulate,export}.py; do
  s=$(grep -c "select(DailyReport\|join(DailyReport\|DailyReport.user_id.in_" "$f")
  d=$(grep -c "DailyReport.deleted_at.is_(None)" "$f")
  echo "$f → select-ref:$s / filter:$d"
done
```

预期:每行 `filter >= 1`(至少 1 处过滤;部分文件 select 多于 filter 是因为同一 query 多列引用算多次)。

端到端:删一条日报 → `/chat` 调 AI 周报"上周谁交了日报"→ 已删的不出现在回答里。

### 15.2 users 还原(C2,~2 min)

1. 看 `frontend/src/app/users/page.tsx:22` `USERS_PAGE_SIZE = 20` ✅
2. /users 页面切 FilterBar:
   - 切"角色 = 部门经理" → Network 触发 `?role=manager`,返回总数减少
   - 切"账号 = 停用" → Network 触发 `?is_active=false`,看到已禁用用户
   - 多选"角色 = 经理 + 员工" → Network `?role=manager,employee`(csv)正常返回
3. curl 验证(从浏览器 localStorage 取 admin JWT):
   ```bash
   TOKEN="<admin-jwt>"
   curl -s -H "Authorization: Bearer $TOKEN" \
     "http://localhost:8000/api/v1/users?role=manager&is_active=true" | jq '.total'
   ```
4. 翻页:< 20 人时不显示分页按钮(预期);> 20 人时显示

### 15.3 撤销(C3,~2 min)

四处 toast undo 全验:

1. /reports 勾 2 条 → 批量删 → toast 出现"撤销"按钮 → 5 秒内点 → 列表恢复 ✅
2. /dashboard 早班日报勾 2 条(若 dashboard 显示日报)→ 批量删 → toast 撤销 → 恢复 ✅
3. /projects 勾 2 个临时项目 → 批量删 → toast 撤销 → 恢复(此处需 admin 角色)✅
4. /projects 勾 2 个主干项目 → 批量归档 → toast 撤销 → 状态变回"进行中"✅
5. 等 5 秒后 toast 消失,撤销按钮不可点(预期,回收站是兜底)

### 15.4 回收站(C4,~2 min)

1. admin 登录 → 侧边栏"管理"分组看到"🗑 回收站"图标项 → 点击进入
2. 默认显示"已删日报" Tab,看到上方一步删的日报(若未被撤销)
3. 切"已删临时项目" Tab,看到已软删的临时工单
4. 勾 2 条日报 → 顶部紫色 ActionBar 出现 → 点"恢复选中" → toast "已恢复 2 条" → 列表自动刷新去掉那两条
5. 回到 /reports 验证恢复的日报又出现在主列表 ✅
6. **权限测试**:logout → employee 登录 → 直接访问 `http://localhost:3000/admin/recycle-bin` → toast "需 admin 权限" + 跳走 ✅
7. **服务端兜底**:仍以 employee 身份 curl
   ```bash
   curl -s -H "Authorization: Bearer $EMP_TOKEN" \
     "http://localhost:8000/api/v1/reports?include_deleted=true" | jq '.total'
   ```
   预期:返回的是该员工**未软删**的日报数(后端强制 fallback,非 admin 的 include_deleted=true 不生效)

### 15.5 总验收

- [ ] 15.1-15.4 全部通过
- [ ] backend pre-commit hook 全过;tsc 无 error
- [ ] V2.4 大需求至此关单(Stage 1 筛选 + Stage 2 软删 + Stage 3 配套)

---

## 最终判定

```
☐ 金路径 #1 — Dashboard 全景
☐ 金路径 #2 — 项目详情 + IPD 5 阶段
☐ 金路径 #3 — AI 日报评分(核心)
☐ 金路径 #4 — OKR 三层树
☐ 金路径 #5 — Sprint 燃尽图
☐ 金路径 #6 — 资源水位 + AI 调配建议
☐ 金路径 #7 — 30 天趋势分析
☐ 金路径 #8 — AI 周报生成(核心)
☐ 金路径 #9 — 复盘 / 知识库
☐ 金路径 #10 — 多角色权限切换
☐ 金路径 #11 — V2.2 项目/任务结构化关联
☐ 金路径 #12 — V2.3 临时工单项目化
☐ 金路径 #13 — V2.4 Stage 1 全站统一筛选
☐ 金路径 #14 — V2.4 Stage 2 批量软删与多选联动
☐ 金路径 #15 — V2.4 Stage 3 软删配套(长尾过滤 + 撤销 + 回收站)

通过数:____ / 15
```

### 决策

| 通过数 | 决策 | 下一步 |
|---|---|---|
| **14** | ✅ **MVP 通过,可交付** | 把 `docs/HANDOVER.md` 转给同事,进入 Phase 2.1 |
| **12-13** | ⚠️ **基本通过,记小尾巴** | 列出 ❌ 项的具体表现,1-2 天修完再验一遍 |
| **9-11** | 🟡 **半成品** | ❌ 项分类:UI 问题 / 数据问题 / 后端 bug,优先级 P0 的全修完 |
| **≤ 8** | 🔴 **暂不交付** | 不要硬上线。回去搞清楚是 seed 数据问题还是代码 bug |

### ❌ 项记录模板

每条 ❌ 项,在这下面写:
```
- 路径 #X — 哪一步失败
  现象: [具体错误]
  日志: docker logs aipm-backend | tail -20
  影响:  P0 阻塞 / P1 影响体验 / P2 可绕过
  修复:  [一行计划]
```

---

## 附录:常用排查命令速查

```bash
# 看后端日志
docker logs aipm-backend 2>&1 | tail -50          # 如果用 docker
# 或者本机 uvicorn 终端窗口往上翻

# 看具体表的数据
docker exec aipm-postgres psql -U aipm -d aipm_db -c "SELECT * FROM daily_reports ORDER BY created_at DESC LIMIT 5;"

# 重新种数据(清空 + 重种)
cd backend && .venv/bin/python -m scripts.seed_demo_data --reset

# 只补某个模块(比如发现 OKR 没了)
.venv/bin/python -m scripts.seed_demo_data --only=okr

# 健康检查
curl -s http://localhost:8000/health/detailed | python3 -m json.tool

# 查看 alembic 状态
.venv/bin/alembic current
.venv/bin/alembic check
```

---

**最后一句**:这份清单设计成 60 分钟跑完,不是 8 小时全测。**目标是「敢说 MVP 能交付」,而不是「测试覆盖率 100%」**。两者价值不同 — 前者是 PO 的判断,后者是 QA 的工作。

跑完后,把 ❌ 项记下来,我们一起决定:**修了再交,还是带着已知问题交付 + 写到 HANDOVER 的"已知 issue" 列表**。
