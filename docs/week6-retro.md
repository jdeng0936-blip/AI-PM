# Week 6 — AI 自动复盘联调指南

> 完成时间:2026-05-19 | 阶段:V2.0 战略层第二块

---

## 一、Week 6 交付概览

| 模块 | 关键文件 | 价值 |
|------|---------|------|
| **4 种复盘 collectors** | `services/retro/collectors.py` | OKR周期 / 项目 / 月度 / 事故 数据聚合 |
| **4 套复盘 Prompt** | `services/retro/prompts.py` | 结构化输出 + 强制根因/经验提炼 |
| **复盘生成器** | `services/retro/generator.py` | LLM 渲染 + 沉淀到 KnowledgeItem |
| **3 个复盘 Chat Tool** | `chat_tools/retro.py` | search/list_recent/get_retro |
| **4 个复盘 API** | `routers/retro.py` | generate/list/detail/delete |
| **前端复盘库页** | `app/retro/page.tsx` | 列表 + 详情 + 生成对话框 |
| **季度自动复盘** | `scheduled_tasks.run_quarterly_okr_summary` 增强 | 季度归档时自动生成 OKR 复盘 |

---

## 二、4 种复盘类型

| Scope | 触发时机 | 数据范围 |
|-------|---------|---------|
| `okr_cycle` | OKR 周期结束(手工 / 季度归档自动) | Cycle + Objectives + KRs + 进度日志 + 时段业务数据 |
| `project` | 项目完成 / 阶段验收 | Project 元数据 + 立项-结项时段业务数据 |
| `monthly` | 月度管理回顾 | 整月业务数据 + 新建项目 |
| `incident` | 重大风险解决后 | risk_alert 周期 + 当事人这段时间的日报 |

---

## 三、API 端点

| 方法 | 路径 | 权限 | 用途 |
|------|------|------|------|
| `POST` | `/retro/generate` | admin/manager | 手工触发生成 |
| `GET` | `/retro/items` | 全员 | 列出复盘(按 scope/project 过滤) |
| `GET` | `/retro/items/{id}` | 全员 | 详情(浏览量 +1) |
| `DELETE` | `/retro/items/{id}` | admin | 删除 |

### 请求示例

```http
POST /api/v1/retro/generate
{
  "scope": "okr_cycle",
  "target_id": "<cycle-uuid>",
  "persist": true
}
```

```json
{
  "scope": "okr_cycle",
  "title": "OKR 周期复盘 · 2026Q1",
  "markdown": "## 周期概览\n...",
  "knowledge_item_id": "<uuid>"
}
```

---

## 四、3 个复盘 Chat Tool

| Tool | 描述 | 总经理典型提问 |
|------|------|---------------|
| `search_retros` | 关键字搜索复盘(标题/标签/正文) | 「206 项目有相关复盘吗?」 |
| `list_recent_retros` | 最近 N 条复盘,可按 scope 过滤 | 「最近的事故复盘?」 |
| `get_retro` | 拿到指定复盘的完整 Markdown | 「把上一份周期复盘读给我」 |

Tool 总数 **17 → 20**。

---

## 五、季度自动复盘工作流

```
每月 1 日 09:30 触发 (CronTrigger)
    ↓
_is_quarter_end(昨天) → True 才继续
    ↓
找到最近的 quarterly + active + end_date<=yesterday 的 OKRCycle
    ↓
聚合 KR 达成分布(已达成 / 进行中 / 滞后)
    ↓
Cycle 转为 completed
    ↓
调用 generate_retrospective_safe(scope='okr_cycle', target_id=cycle.id)
    ├─ collectors.collect_okr_cycle()
    ├─ prompts.render_okr_cycle_prompt()
    ├─ LLM (gemini-2.5-pro, retrospective 模型)
    └─ 沉淀为 KnowledgeItem(category=retrospective)
    ↓
推送达成总结 + 复盘报告链接给 admin/manager
    (企微 + 钉钉 + 站内信三渠道)
```

**失败兜底**:复盘失败不会阻止归档,推送内容会自动省略「复盘链接」段。

---

## 六、复盘报告结构(OKR 周期为例)

LLM 必须按以下 5 段输出:

```markdown
## 周期概览          ← 1-2 段定性描述
## 目标级达成分析     ← 每个 O 单独分析
## 根因总结(必填)   ← 3-5 条提炼,「问题→根因→影响」
## 经验提炼(必填)   ← 3-5 条可迁移方法论
## 下个周期建议       ← 沿用 / 改进 / 试验
```

每种 scope 的结构详见 `services/retro/prompts.py`。

---

## 七、前端使用

访问 `/retro`(sidebar「AI 复盘库」入口)

### 顶部:筛选 + 搜索
- **类型 Chip**:全部 / OKR 周期 / 项目 / 月度 / 事故
- **搜索框**:即时匹配标题或标签
- **「✨ 生成复盘」按钮**:admin/manager 可见

### 左侧:复盘列表
- 卡片显示类型徽标 + 标题 + 时间
- 「✨ AI 自动生成」标识区分 AI 来源
- 点击切换右侧详情

### 右侧:Markdown 详情
- 完整 Markdown 渲染
- 标签 / 时间 / 来源等元信息

### 生成对话框
- 4 种类型 Tab 切换
- OKR 周期:从下拉选已有 cycle
- 项目:手填项目 UUID(后续可改下拉)
- 月度:年月输入
- 事故:手填 risk_alert UUID

---

## 八、联调步骤

### 8.1 启动 + 准备

```bash
cd backend && .venv311/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

确保已有:
- 至少一个 OKR 周期含 Objectives + KR
- 至少 1 周的日报数据

### 8.2 手工生成 OKR 周期复盘

1. 用 admin 账号访问 `/retro`
2. 点「✨ 生成复盘」→ 选「OKR 周期」→ 选 cycle → 提交
3. 等待 30-120s(`gemini-2.5-pro` 深度推理)
4. 完成后自动选中新生成的条目,右侧显示 Markdown

### 8.3 对话查询复盘

在 `/chat` 提问:
- 「最近的 OKR 复盘是什么?」(触发 `list_recent_retros`)
- 「206 项目相关有复盘吗?」(触发 `search_retros`)
- 「把上一份周期复盘读给我」(触发 `get_retro`)

### 8.4 测试季度自动归档(无需等真季度末)

```bash
.venv311/bin/python -c "
import asyncio
from app.services.scheduled_tasks import run_quarterly_okr_summary
asyncio.run(run_quarterly_okr_summary())
"
# 注:今天不是季度首日时,函数 return 不执行。
# 测试用可临时修改 _is_quarter_end。
```

预期:
- 旧 cycle.status 变为 completed
- knowledge_items 新增一条 category=retrospective
- 管理层收到「OKR 达成总结 + 复盘报告链接」通知

---

## 九、安全 / 容错检查

| 风险 | 防御 |
|------|------|
| LLM 调用挂导致复盘失败 | `generate_retrospective_safe` 吞异常,返回 None |
| 季度归档时复盘失败 | 不阻止 cycle.status 写入 + 推送 |
| 用户传入不存在的 cycle_id | 抛 ValueError,API 返回 400 |
| 缺参数 | 抛 ValueError,API 返回 400 |
| 知识库越权读 | retro_id 查询时强制 category=retrospective,杜绝混查其他知识 |
| 删除越权 | DELETE 仅 admin |

---

## 十、验证证据

- ✅ **81/81 测试通过**(其中 Retro 17 + OKR 13 + Chat Tools 21 + 其他 30)
- ✅ Tool 总数从 17 → **20**
- ✅ API 端点新增 4 个,总数 82 → **86**
- ✅ 季度归档逻辑被增强,失败不影响主流程
- ✅ TypeScript 零错误,前端复盘库页面就绪
- ✅ Sidebar 新增「🔁 AI 复盘库」入口

---

## 十一、扩展点(留给 Week 7+)

| 方向 | 提示 |
|------|------|
| **复盘向量检索** | KnowledgeItem.embedding 字段已就绪,可接入 embedding 后做语义搜索「类似项目踩过的坑」 |
| **复盘对比** | 同一项目的多次复盘可对比演化(团队/工艺改进) |
| **复盘模板** | 抽出「best of」复盘作为模板,引导未来复盘聚焦关键问题 |
| **复盘订阅** | 用户可订阅某项目/某员工的复盘自动推送 |
| **Sprint 自动复盘** | 接入 Sprint 关闭事件触发 sprint_close 复盘 |
| **OKR 制定时检索复盘** | 创建 Objective 时自动检索历史相关复盘,前置经验注入 |

---

## 十二、相关文档

- [system-overview.md](./system-overview.md) — ⑨ 战略层补全
- [week5-okr.md](./week5-okr.md) — OKR 基础设施(本周复盘的核心数据源)
- [week4-chat-tools.md](./week4-chat-tools.md) — Tool 框架(本周扩展 3 个 retro Tool)
- [whitepaper-system-design.md](./whitepaper-system-design.md) §7.3 — AI 自动复盘产品视角
- [implementation-plan.md](./implementation-plan.md) §13 — 原始技术方案(Week 6 已落地)
