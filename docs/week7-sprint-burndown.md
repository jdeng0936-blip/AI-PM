# Week 7 — Sprint 归集 + 燃尽图 + 关键路径联调指南

> 完成时间:2026-05-19 | 阶段:V2.0 主线收官

---

## 一、Week 7 交付概览

| 模块 | 关键文件 | 价值 |
|------|---------|------|
| **任务级模型** | `models/sprint_task.py` | SprintTask + BurndownSnapshot,故事点 + 状态 + 关键路径标记 |
| **日报关联任务** | `models/daily_report.py` | 新增 `mentioned_task_ids` 字段(支持 AI 自动提取) |
| **燃尽服务** | `services/sprint_aggregator.py` | snapshot + 理想/实际/预测序列 + 项目速率历史 |
| **关键路径算法** | `services/critical_path.py` | 拓扑排序 + 加权最长路径 + 环检测 |
| **Sprint API** | `routers/sprints.py` 增强 | tasks/burndown/critical-path/velocity 全套 |
| **4 个新 Chat Tool** | `chat_tools/sprints.py` | sprint_status / burndown / critical_path / velocity |
| **前端 Sprint 看板** | `app/sprints/page.tsx` | 任务板 + Recharts 燃尽图 + 关键路径 + 速率柱状图 |
| **每日 18:00 快照** | `scheduler.py` | 给所有 active Sprint 自动写当日燃尽快照 |

---

## 二、数据模型

```
Project
  └── Sprint (周期/状态/计划点/完成点)
        ├── SprintTask (任务,带故事点)
        │     ├── status: todo / in_progress / blocked / done / cancelled
        │     ├── priority: p0 (关键) / p1 / p2 / p3
        │     ├── story_points + actual_story_points
        │     ├── depends_on: [task_uuid, ...]
        │     ├── is_on_critical_path: bool
        │     ├── kr_id → KeyResult(可选,自动同步 KR 进度)
        │     └── assignee_id → User
        └── BurndownSnapshot (每日燃尽快照)
              ├── snapshot_date
              ├── completed_points / remaining_points / total_points
              └── done_count / in_progress_count / blocked_count / todo_count
```

---

## 三、API 端点(8 个新增)

| 方法 | 路径 | 权限 | 用途 |
|------|------|------|------|
| `GET` | `/sprints/{id}/tasks` | 全员 | 列出 Sprint 任务 |
| `POST` | `/sprints/{id}/tasks` | admin/manager | 创建任务 |
| `PATCH` | `/sprints/tasks/{task_id}` | admin/manager | 更新任务(状态变更自动触发快照) |
| `DELETE` | `/sprints/tasks/{task_id}` | admin/manager | 删除任务 |
| `GET` | `/sprints/{id}/burndown` | 全员 | 燃尽序列(理想 + 实际 + 预测) |
| `POST` | `/sprints/{id}/snapshot` | admin/manager | 手工触发燃尽快照 |
| `GET` | `/sprints/{id}/critical-path?persist=` | 全员 | 计算关键路径,可选回写 |
| `GET` | `/sprints/project/{id}/velocity?last_n=` | 全员 | 项目历史速率 |

### 燃尽数据示例

```json
{
  "sprint": { "id":"...", "sprint_number":1, "goal":"...", ... },
  "total_points": 20,
  "task_count": 5,
  "ideal_line": [
    {"date":"2026-05-14","points":20.0},
    {"date":"2026-05-15","points":18.5}, ...
  ],
  "actual_line": [
    {"date":"2026-05-14","points":20,"completed":0,"blocked":1, ...},
    {"date":"2026-05-15","points":17,"completed":3, ...}
  ],
  "today_estimate": {
    "burn_rate_per_day": 3.0,
    "projected_end_date": "2026-05-20",
    "planned_end_date": "2026-05-22",
    "on_track": true,
    "days_delta": -2
  }
}
```

---

## 四、关键路径算法

### CPM 简化版

```
1. 构建 DAG:  task.depends_on → 邻接表
2. 拓扑排序(Kahn 算法)
3. 检测环:topo 节点数 < 总节点数 → has_cycle=true,环上节点跳过
4. 加权最长路径 DP:
   - dist[起点] = weight[起点]
   - 沿拓扑序传播:dist[next] = max(dist[next], dist[cur] + weight[next])
5. 回溯路径:从 max(dist) 终点反向收集
6. 可选回写:task.is_on_critical_path = True
```

### 权重定义
- `weight(task) = max(task.story_points, 1)`(无估算时按 1 算)

### 阻塞放大效应
关键路径上的任何阻塞 = Sprint 风险信号。
前端会用红色高亮 + Chat Tool 会单独列出 `blocked_count_on_path`。

---

## 五、4 个 Sprint Chat Tool

| Tool | 描述 | 典型问题 |
|------|------|---------|
| `sprint_status` | 当前 active Sprint 概况 | 「206 项目 Sprint 怎么样?」 |
| `sprint_burndown` | 燃尽简报 + 是否能按期 | 「Sprint 1 能按时完成吗?」 |
| `critical_path` | 关键路径任务 + 阻塞数 | 「206 项目当前关键路径上有什么?」 |
| `project_velocity` | 历史速率柱状图数据 | 「206 项目过去几个 Sprint 的速度?」 |

Tool 总数 **20 → 24**。

---

## 六、前端使用

访问 `/sprints`(sidebar「🔥 Sprint 燃尽」入口)

### 顶部:项目 + Sprint 选择
- 项目下拉(自动从 `/projects/overview` 拉取)
- Sprint 下拉(默认选当前 active)
- 健康度徽标
- 「🔄 刷新快照」按钮(admin/manager)

### 左:任务看板
- 按状态分组:进行中 / 阻塞 / 待开始 / 完成
- 每个任务卡片:优先级 + 关键路径标记 + 故事点
- 内联状态切换(下拉)+ 删除
- 「+ 新建任务」对话框

### 右上:Recharts 燃尽图
- 灰色虚线 = 理想燃尽
- 绿/红实线 = 实际燃尽(按预测是否能按时上色)
- 底部预测条:「✅ 预计 X 完成(计划 Y,提前 N 天)」

### 右中:关键路径
- 拓扑顺序展示
- 阻塞任务红色高亮
- 总故事点 + 任务数

### 右下:历史速率柱状图
- 计划点 vs 完成点对比(近 6 Sprint)
- 平均速率徽标

---

## 七、定时任务(累计 8 个)

| 时间 | 任务 |
|------|------|
| 00:30 每日 | 健康度全量重算 |
| 09:00 每日 | 晨报 AI 生成 |
| 09:00 周一 | 上周管理周报 |
| 09:30 每月 1 日 | OKR 季度归档(含复盘自动生成) |
| 17:30 每日 | 催报-友好提醒 |
| **18:00 每日** | **Sprint 燃尽快照** ← Week 7 新增 |
| 20:00 每日 | 催报-二次催促 |
| 22:00 每日 | 催报截止 + 通知总经理 |

### 手工触发快照(测试)

```bash
.venv311/bin/python -c "
import asyncio
from app.services.sprint_aggregator import run_daily_burndown_snapshots
asyncio.run(run_daily_burndown_snapshots())
"
```

---

## 八、联调步骤

### 8.1 准备数据

```bash
cd backend && .venv311/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

### 8.2 创建 Sprint + 任务

1. 在 `/projects` 找一个项目 ID
2. 调用 `POST /sprints/` 创建 Sprint(目前还需用 Postman 或 curl)
3. 用 admin 账号访问 `/sprints` → 选项目 → 选 Sprint → 「+ 新建任务」

### 8.3 创建依赖链测试关键路径

任务 A(3pt)→ 任务 B(5pt)→ 任务 C(8pt)

```bash
# 创建 A 后拿到 a_id,创建 B 时:
curl -X POST .../sprints/<sid>/tasks \
  -d '{"sprint_id":"<sid>","title":"B","story_points":5,"depends_on":["<a_id>"]}'
```

`/sprints/{id}/critical-path` 应返回 critical_length=16,关键路径 = [A, B, C]。

### 8.4 观察燃尽图

1. 创建几个任务,把一两个标为 done
2. 点「🔄 刷新快照」生成当日快照
3. 第二天(或手工触发定时任务)再生成一条快照
4. 燃尽图会出现实际线 + 预测信息

### 8.5 对话查询

`/chat` 提问:
- 「206 项目 Sprint 怎么样?」(`sprint_status`)
- 「Sprint 1 燃尽情况?」(`sprint_burndown`)
- 「关键路径上有哪些任务?」(`critical_path`)
- 「过去 6 个 Sprint 速率?」(`project_velocity`)

---

## 九、与其它模块的联动

| 联动方向 | 说明 |
|---------|------|
| **Sprint Task ↔ KR** | SprintTask.kr_id 可关联 OKR 中的 KR;完成 Task 自动推进 KR 进度(后续可加 hook) |
| **Sprint 完成 → 复盘** | Sprint 转 completed 时已加入燃尽终态锁定,后续可一行代码触发 Week 6 retro 服务生成 Sprint 复盘 |
| **日报 ↔ Task** | DailyReport.mentioned_task_ids 字段已就绪,留给后续 AI 自动从日报识别"今天推进了哪些任务" |
| **关键路径 ↔ 告警** | 关键路径上任务转 blocked 时,可触发 risk_alert(暂未自动接入,但模型支持) |
| **Velocity ↔ 资源水位预判** | velocity 数据可被未来的资源水位预判服务消费 |

---

## 十、验证证据

- ✅ **96/96 测试全过**(其中 Sprint 15 + Retro 17 + OKR 13 + 其他 51 回归)
- ✅ Tool 总数 20 → **24**(新增 4 个 Sprint Tool)
- ✅ API 端点 86 → **94**(新增 8 个 Sprint 端点)
- ✅ 定时任务 7 → **8**(新增每日 18:00 燃尽快照)
- ✅ Model 总数 17 → **19**(新增 SprintTask + BurndownSnapshot)
- ✅ 关键路径算法 bug(节点权重双计)在测试中捕获并已修复
- ✅ 同日重复快照幂等性(更新而非新增)有测试守门
- ✅ 环检测在测试中验证

---

## 十一、扩展点(留给 Week 8+)

| 方向 | 提示 |
|------|------|
| **AI 自动提取 task 推进** | 类似 Week 5 的 KR 提取,从日报识别「今天推进了 task X」自动改状态 |
| **资源负载水位(§7.2)** | 已有 Sprint + assignee + 故事点数据,可计算每人 Sprint 内任务密度,识别过载 |
| **甘特图** | task 已有 planned_start/end,可前端补一个跨 Sprint 甘特视图 |
| **Sprint 自动归集回顾** | Sprint 完成时调 Week 6 retro 服务生成「Sprint 复盘」,沉淀知识库 |
| **燃尽预警推送** | actual 持续高于 ideal 时,自动推送给项目负责人(走 Week 1 通知服务) |
| **Story Points AI 估算** | 新建任务时根据历史数据 LLM 推荐故事点 |

---

## 十二、相关文档

- [system-overview.md](./system-overview.md) — ⑤/⑧ 短/长周期管理补全
- [week6-retro.md](./week6-retro.md) — Sprint 完成时可触发复盘
- [week5-okr.md](./week5-okr.md) — Task 可绑 KR(待 hook)
- [whitepaper-system-design.md](./whitepaper-system-design.md) §5 — Project Lifecycle 完整章节
- [implementation-plan.md](./implementation-plan.md) §12 — 资源负载预判(Week 8 候选)
