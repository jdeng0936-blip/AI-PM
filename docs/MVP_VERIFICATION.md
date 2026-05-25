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

通过数:____ / 10
```

### 决策

| 通过数 | 决策 | 下一步 |
|---|---|---|
| **10** | ✅ **MVP 通过,可交付** | 把 `docs/HANDOVER.md` 转给同事,进入 Phase 2.1 |
| **8-9** | ⚠️ **基本通过,记小尾巴** | 列出 ❌ 项的具体表现,1-2 天修完再验一遍 |
| **5-7** | 🟡 **半成品** | ❌ 项分类:UI 问题 / 数据问题 / 后端 bug,优先级 P0 的全修完 |
| **≤ 4** | 🔴 **暂不交付** | 不要硬上线。回去搞清楚是 seed 数据问题还是代码 bug |

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
