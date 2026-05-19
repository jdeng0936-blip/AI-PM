# Week 4 — 总经理 AI 对话(Function Calling)联调指南

> 完成时间:2026-05-19 | 阶段:V2.0 起步
>
> 本文档面向开发者 + 联调者 + 业务方,提供 Week 4 所有新功能的「能做什么 / 怎么测 / 怎么扩展」一站式说明。

---

## 一、Week 4 交付概览

| 模块 | 文件 | 价值 |
|------|------|------|
| **Tool 注册框架** | `backend/app/services/chat_tools/__init__.py` | `@tool` 装饰器 + 自动 JSON Schema + 容错 dispatch |
| **13 个查询 Tool** | `chat_tools/{reports,projects,people,weekly_report}.py` | 覆盖日报/风险/项目/人员/周报 5 大维度 |
| **多轮 Function Calling** | `backend/app/routers/chat.py` | 5 轮上限 + Tool trace + 引用源 |
| **周报自动生成** | `chat_tools/weekly_report.py` + `scheduled_tasks.run_weekly_report` | 周一 09:00 自动 + 手工触发端点 |
| **Chat UI 增强** | `frontend/src/app/chat/page.tsx` | Tool 调用动画 + 打字机 + Markdown + 周报按钮 |

---

## 二、13 个 Tool 速查表

### 日报维度(5 个)

| Tool | 描述 | 典型问题 |
|------|------|---------|
| `query_reports` | 按时间段查询日报,可按部门/用户过滤 | 「本周日报情况如何?」 |
| `count_delayed` | 卡点人员排行 | 「谁延期最多?」 |
| `score_ranking` | 评分排行(top/bottom) | 「评分最高的 5 个人」 |
| `avg_score_by_department` | 部门平均分聚合 | 「各部门表现对比」 |
| `list_missing_today` | 今日未提交名单 | 「今天谁没交日报?」 |

### 项目 / 风险维度(4 个)

| Tool | 描述 | 典型问题 |
|------|------|---------|
| `get_project_status` | 按名称/编号查项目状态 | 「206 项目什么状况?」 |
| `list_active_risks` | 未解决风险预警列表 | 「目前有哪些风险?」 |
| `list_active_projects` | 项目组合视图(健康度升序) | 「哪些项目最危险?」 |
| `project_health_distribution` | 红黄绿三色分布 | 「项目健康度概览」 |

### 人员维度(3 个)

| Tool | 描述 | 典型问题 |
|------|------|---------|
| `top_performers` | 综合表现 Top N(分数 + 提交率) | 「最优秀员工 Top 5」 |
| `bottom_performers` | 需要关注的人(低分 / 缺勤多) | 「谁需要关注?」 |
| `user_snapshot` | 单个员工档案(趋势 + 卡点) | 「郭震最近怎么样?」 |

### 周报(1 个,LLM 内自闭环二次调用)

| Tool | 描述 | 触发方式 |
|------|------|---------|
| `generate_weekly_report` | 聚合数据 + LLM 渲染 Markdown 周报 | ① 对话「帮我写本周周报」② 前端按钮 ③ 周一 09:00 定时 |

---

## 三、API 端点清单

| 方法 | 路径 | 权限 | 用途 |
|------|------|------|------|
| `POST` | `/api/v1/chat/ask` | admin | 自然语言提问(Function Calling) |
| `GET` | `/api/v1/chat/tools` | admin | 列出当前所有可用 Tool(调试用) |
| `POST` | `/api/v1/chat/weekly-report` | admin | 手工触发周报生成(走 LLM 渲染) |

### `/chat/ask` 请求 / 响应示例

```http
POST /api/v1/chat/ask
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "question": "本周谁延期最多?",
  "allowed_tools": null     // 可选,限定本次能用哪些 Tool
}
```

```json
{
  "question": "本周谁延期最多?",
  "answer": "本周延期最多的是 **陈翔**,卡在 LoRa 模块选型已连续 3 天...\n\n📊 数据来源: 调用了 1 次 Tool,基于 12 条记录",
  "tool_calls": [
    {
      "tool": "count_delayed",
      "arguments": { "date_range": "this_week", "limit": 5 },
      "result_preview": "{\"range\": {...}, \"ranking\": [{\"user\":\"陈翔\",\"blocker_days\":3,...}]}",
      "error": null
    }
  ],
  "rounds": 2,
  "model": "gemini-3-flash-preview"
}
```

---

## 四、联调步骤(从零到看到答案)

### 4.1 启动后端

```bash
cd backend
docker exec postgres psql -U postgres -c "CREATE DATABASE aipm_db_test OWNER aipm;" 2>/dev/null  # 测试库
docker exec postgres psql -U aipm -d aipm_db -c "\dt" | grep -E "users|daily_reports|notifications|attachments"
.venv311/bin/uvicorn app.main:app --reload --port 8000
```

预期日志:
```
✅ 徽远成 AI-PM 后端启动成功
⏰ APScheduler 已启动,注册了 6 个定时任务  ← 多了周一周报
```

### 4.2 启动前端

```bash
cd frontend && npm run dev
# 访问 http://localhost:5173/chat (需用 admin 登录)
```

### 4.3 测试 10 个典型问题

按下列顺序在 Chat 页测试,验证 Tool 调用是否正确:

| # | 问题 | 预期触发的 Tool |
|---|------|----------------|
| 1 | 本周谁延期最多? | `count_delayed(date_range="this_week")` |
| 2 | 采购部进度怎么样? | `query_reports(department="采购部")` 或 `avg_score_by_department` |
| 3 | 目前有哪些未解决的风险? | `list_active_risks` |
| 4 | 表现最好的 5 个员工是谁? | `top_performers(limit=5)` |
| 5 | 206 项目什么状况? | `get_project_status(project_query="206")` |
| 6 | 今天哪些人没交日报? | `list_missing_today` |
| 7 | 郭震最近表现怎么样? | `user_snapshot(user_name="郭震")` |
| 8 | 哪些项目最危险? | `list_active_projects` |
| 9 | 各部门评分对比 | `avg_score_by_department` |
| 10 | 帮我写本周管理周报 | `generate_weekly_report` |

**通过标准**:
- ✅ AI 回答与数据库实际数据一致
- ✅ Tool 调用过程可见(逐条揭示)
- ✅ 引用源标注「调用了 X 次 Tool,基于 Y 条记录」
- ✅ 单次问答 < 30 秒(单 Tool)/ < 90 秒(周报)

### 4.4 周报自动生成测试

#### 手工触发(前端)
1. Chat 页右上角点「📑 生成本周周报」
2. 等待 30-90s(deep_analysis 模型较慢)
3. 看到 6 段 Markdown 周报(总览/部门/风险/项目/个人/建议)

#### 手工触发(命令行)
```bash
curl -X POST http://localhost:8000/api/v1/chat/weekly-report \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"scope": "last_week"}'
```

#### 周一定时验证(无需等真周一)
```bash
# 临时把 CronTrigger 改为「下一分钟」,重启后端,观察推送
# 或直接 Python 调用:
.venv311/bin/python -c "
import asyncio
from app.services.scheduled_tasks import run_weekly_report
asyncio.run(run_weekly_report())
"
```

预期:
- 数据库 `notifications` 表新增 N 条记录(N = admin/manager 数量 × 3 个渠道)
- 企微/钉钉群推送本周周报(若 webhook 配置正确)

---

## 五、扩展指南:怎么加新 Tool

### 5.1 最小示例

新建 `backend/app/services/chat_tools/my_module.py`:

```python
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.chat_tools import tool


@tool(description="一句话描述这个 Tool 干什么(给 LLM 看的)")
async def my_new_tool(
    db: AsyncSession,
    keyword: str,
    limit: int = 10,
) -> dict:
    """
    Args:
        keyword: 搜索关键字
        limit: 返回数量上限
    """
    # ... 你的查询逻辑 ...
    return {"matched": [...], "count": ...}
```

### 5.2 注册到自动加载列表

`backend/app/services/chat_tools/__init__.py`:

```python
def _autoload() -> None:
    for mod in ("reports", "projects", "people", "weekly_report", "my_module"):
        ...
```

### 5.3 写测试

`backend/tests/test_chat_tools.py`:

```python
@pytest.mark.asyncio
async def test_my_new_tool(seeded_db):
    db = seeded_db["db"]
    result = await registry.dispatch("my_new_tool", db, {"keyword": "test"})
    assert "matched" in result
```

### 5.4 关键约束

| 约束 | 说明 |
|------|------|
| **第一个参数必须是 `db: AsyncSession`** | 框架会自动注入,LLM 不会看到这个参数 |
| **所有其他参数必须有类型注解** | 否则 JSON Schema 无法生成 |
| **返回 `dict`** | 必须 JSON 可序列化 |
| **失败用 `{"error": "..."}` 而不是抛异常** | 让 LLM 自主决策 |
| **不要拼接用户输入到 SQL** | 一律走 SQLAlchemy 参数化,杜绝注入 |
| **添加 Args docstring** | `Args:` 后每行 `name: 中文描述`,LLM 会按这些描述调用 |

---

## 六、安全 / 容错检查清单

| 项 | 实现 |
|----|------|
| LLM 看不到表名/字段名 | ✅ 所有 Tool 走预定义聚合 |
| Tool 异常不会污染主流程 | ✅ dispatch 包装为 `{"error": ...}` |
| 多余参数不报错 | ✅ dispatch 按 signature 过滤 |
| 防止无限循环 | ✅ MAX_TOOL_ROUNDS=5,达上限强制总结 |
| LLM 调用失败优雅降级 | ✅ httpx 异常 → 502 + 错误信息 |
| 仅 admin 可用 | ✅ `require_role(UserRole.admin)` |
| 周报失败不影响其他任务 | ✅ scheduled_tasks try/except 兜底 |

---

## 七、性能与成本提示

| 项 | 数值 |
|----|------|
| 单轮简单问答 | 1-3 次 Tool 调用,5-15s |
| 复杂综合分析 | 3-5 次 Tool 调用,15-30s |
| 周报生成 | 1 次聚合 + 1 次 LLM 长文渲染,30-90s |
| 默认模型 | `admin_chat` → gemini-3-flash-preview |
| 周报模型 | `deep_analysis` → gemini-2.5-pro(质量优先) |
| Token 消耗 | 单次问答约 1-3K,周报约 3-8K |

如需降低成本,可在 `llm_registry.yaml` 把 `admin_chat` 改为 flash 系列模型。

---

## 八、已知限制 / 后续优化

| 限制 | 说明 | 优化方向 |
|------|------|---------|
| **非真正的 SSE 流式** | 前端用「揭示动画」模拟,后端一次性返回 | 后续可改 SSE,但 Function Calling 协议本身不擅长流式 |
| **没有对话历史** | 每次 `/ask` 是无状态的 | 可加 `messages` 参数支持多轮上下文 |
| **Tool 结果不缓存** | 同样问题每次都查 DB | 可加 Redis 缓存(注意时效性) |
| **周报无可编辑性** | 一次性生成,管理层不能改 | 可加「编辑 + 重新生成」按钮 |
| **Tool schema 不支持枚举** | `date_range` 是字符串自由值 | 可在 schema 加 `enum` 字段约束(本框架已留扩展点) |

---

## 九、相关文档

- [system-overview.md](./system-overview.md) — 整体应用场景全图
- [whitepaper-system-design.md](./whitepaper-system-design.md) §6.6 — 产品视角的 AI 对话设计
- [implementation-plan.md](./implementation-plan.md) §6 — 原始技术方案(本周已重写实现)
