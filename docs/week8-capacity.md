# Week 8 — 资源负载水位预判联调指南

> 完成时间:2026-05-19 | 阶段:**V2.0 大主线 100% 收官 🎉**

---

## 一、Week 8 交付概览

| 模块 | 关键文件 | 价值 |
|------|---------|------|
| **CapacitySnapshot 模型** | `models/capacity.py` + CapacityLevel 枚举 | 每人每 Sprint 的水位快照,4 级颜色映射 |
| **水位计算引擎** | `services/capacity_engine.py` | 含 velocity 调整 / 状态折减 / 智能调配 / 部门聚合 |
| **Capacity API** | `routers/capacity.py`(7 端点) | 单 Sprint / 全局过载 / 闲置 / 部门 / 用户时间线 |
| **5 个 Chat Tool** | `chat_tools/capacity.py` | workload_status / overloaded / underutilized / rebalance / department |
| **前端水位看板** | `app/capacity/page.tsx` | 个人水位条 + 部门柱状图 + AI 调配建议 |
| **周一刷新 + 过载预警** | `scheduler.py` + `_push_overload_alerts` | 每周一 08:30 自动刷新 + 推送过载名单到管理层 |

---

## 二、水位等级 4 档

| 等级 | 占用率阈值 | 颜色 | 含义 |
|------|-----------|------|------|
| `idle` | < 30% | 🔵 蓝 | 显著闲置,可接收任务 |
| `healthy` | 30%-80% | 🟢 绿 | 健康负载 |
| `high` | 80%-100% | 🟡 黄 | 高位但未爆,关注即可 |
| `overload` | ≥ 100% | 🔴 红 | 过载,需要立刻调配 |

---

## 三、水位计算公式

```
effective_capacity = base_capacity × status_factor × velocity_factor

其中:
- base_capacity      = User.story_points_capacity (默认 8 pt/Sprint)
- status_factor      = active:1.0 | on_travel:0.5 | sick_leave:0.3 | on_leave:0.0
- velocity_factor    = 历史平均完成点 / base_capacity (限 [0.5, 1.8])
                       样本不足时返回 1.0

allocated_points = Σ story_points(任务∈{todo, in_progress, blocked})
completed_points = Σ actual_story_points(任务=done)

utilization = allocated_points / effective_capacity   (0.0 ~ 2.0+)
```

**关键设计**:
- 容量被实时人员状态(休假/出差)折减,假期人员任务全归"过载"
- velocity 调整让"实际产能高于标称"的人不会被错误判为过载
- 限制 velocity_factor ∈ [0.5, 1.8] 避免历史样本少时剧烈抖动

---

## 四、调配算法

`suggest_rebalance(sprint_id)` 工作流:

```
1. 查询过载人员 + 闲置人员
2. 同部门 idle 优先匹配,跨部门兜底
3. 对每个过载成员:
   - 找其名下 todo + 非关键路径 任务(按故事点降序)
   - 计算「需移走的点数」= allocated - effective × 0.8
   - 贪心:每次找有空余容量的接收方,把任务挪过去
   - 候选方的已分配点实时累加,影响下一轮匹配
4. 返回 moves 列表:[{task_id, from_user, to_user, points, department_match}, ...]
```

**保护机制**:
- 关键路径任务不动(挪了反而拖累交付)
- in_progress / blocked 不动(已有上下文)
- 仅推荐 todo 任务(零切换成本)

---

## 五、API 端点(7 个)

| 方法 | 路径 | 权限 | 用途 |
|------|------|------|------|
| `GET` | `/capacity/sprint/{id}` | 全员 | 单 Sprint 全员水位(实时计算) |
| `POST` | `/capacity/sprint/{id}/snapshot` | admin/manager | 手工刷新水位快照 |
| `GET` | `/capacity/sprint/{id}/rebalance` | 全员 | AI 调配建议 |
| `GET` | `/capacity/overloaded` | 全员 | 全局过载人员(快照表) |
| `GET` | `/capacity/underutilized` | 全员 | 全局闲置人员(快照表) |
| `GET` | `/capacity/department-summary` | 全员 | 部门级聚合 |
| `GET` | `/capacity/users/{id}/timeline` | 全员 | 某用户跨 Sprint 水位演变 |

---

## 六、5 个 Chat Tool

| Tool | 描述 | 典型问题 |
|------|------|---------|
| `workload_status` | 项目当前 Sprint 水位分布 | 「206 项目谁过载?」 |
| `list_overloaded_members` | 全局过载名单 | 「现在哪些人过载?」 |
| `list_underutilized_members` | 全局闲置名单 | 「谁还有空?」 |
| `rebalance_suggestion` | AI 调配建议 | 「206 项目怎么调配资源?」 |
| `department_workload` | 部门级水位 | 「各部门负载对比」 |

Tool 总数 **24 → 29**。

---

## 七、前端使用

访问 `/capacity`(sidebar「🌡️ 资源水位」入口)

### 顶部
- 项目 + Sprint 选择器
- 「🔄 刷新快照」(admin/manager)
- 「✨ AI 调配建议」按钮 → 弹出调配方案

### 团队水位分布条
- 一个横向条,4 色比例显示 overload/high/healthy/idle 占比
- 数字徽标

### 中央:个人水位条列表
- 按占用率降序排列
- 红色边框 = 过载
- 进度条 0%-150%(超过 100% 显示溢出红区)
- 100% 刻度有白色竖线标记
- 任务摘要:📋N 任务 / ⚠️阻塞 / ⚡关键路径 / ✓完成点
- 状态徽标(休假/出差)+ velocity 系数

### 右上:部门级柱状图(Recharts)
- 横向条:容量 vs 占用
- 占用条按部门 level 着色
- 下方文字列表显示占用率 + 等级

### 右下:AI 调配建议
- 移动卡片:`from_user → to_user`,显示故事点 + 同部门标识
- 无过载时显示「无需调配」
- 超过 8 条显示折叠提示

---

## 八、定时任务(累计 9 个)

| 时间 | 任务 |
|------|------|
| 00:30 每日 | 健康度全量重算 |
| **08:30 周一** | **资源水位刷新 + 过载预警** ← Week 8 新增 |
| 09:00 每日 | 晨报 AI 生成 |
| 09:00 周一 | 上周管理周报 |
| 09:30 每月 1 日 | OKR 季度归档 + 自动复盘 |
| 17:30 每日 | 催报-友好提醒 |
| 18:00 每日 | Sprint 燃尽快照 |
| 20:00 每日 | 催报-二次催促 |
| 22:00 每日 | 催报截止通知 |

### 过载预警推送内容(企微/钉钉群机器人)

```markdown
### 🌡️ 资源水位过载预警

当前有 **3** 位成员处于过载状态(占用 ≥ 100%):

- **张三**(软件研发部): 187% (15/8pt), ⚠️1 阻塞
- **李四**(采购部): 125% (10/8pt)
- **王五**(生产部): 110% (11/10pt)

建议管理层及时调配,或前往「资源水位」页面查看 AI 调配建议。
```

---

## 九、联调步骤

### 9.1 准备数据

```bash
cd backend && .venv311/bin/uvicorn app.main:app --reload --port 8000
cd frontend && npm run dev
```

需要数据:
- 至少 1 个项目 + 1 个 active Sprint
- Sprint 内至少 3 个任务,分别 assignee 到不同用户
- 任务故事点分布合理(有人多有人少)

### 9.2 构造过载场景

通过 Sprint 燃尽看板创建几个任务,全部 assign 给一个人,总点数超过 user.story_points_capacity(默认 8):

```bash
# 给某用户分配 15pt 任务,容量 8pt → 必然过载
curl -X POST .../sprints/<sid>/tasks \
  -d '{"sprint_id":"<sid>","title":"任务A","story_points":5,"assignee_id":"<uid>"}'
```

### 9.3 前端查看

1. 访问 `/capacity`
2. 选项目 + Sprint → 看到该用户红色过载条
3. 点「✨ AI 调配建议」→ 看到推荐转移给闲置同事

### 9.4 测试周一定时任务(无需等周一)

```bash
.venv311/bin/python -c "
import asyncio
from app.services.capacity_engine import run_weekly_capacity_refresh
asyncio.run(run_weekly_capacity_refresh())
"
```

预期:
- `capacity_snapshots` 表写入快照
- 过载人员 → notifications 推送给 admin/manager

### 9.5 对话查询

`/chat` 提问:
- 「现在哪些人过载?」(`list_overloaded_members`)
- 「206 项目怎么调配?」(`rebalance_suggestion`)
- 「各部门负载怎么样?」(`department_workload`)

---

## 十、与其他模块的联动

| 联动方向 | 说明 |
|---------|------|
| **SprintTask ↔ Capacity** | Task 状态变更 → 实时改变 allocated → 影响下次快照 |
| **User.status ↔ Capacity** | 休假/出差用户 effective_capacity 折减,任务过载会被标记 |
| **Velocity ↔ Capacity** | Week 7 速率历史直接作为 velocity_factor 输入,实际能力强者容量上调 |
| **关键路径 ↔ Rebalance** | 调配建议绕开关键路径任务 |
| **过载 ↔ Notification** | 周一自动推送过载名单到企微/钉钉群 |
| **未来:OKR ↔ Capacity** | KR 关联 Task,可显示「这个 KR 要做的任务,owner 是否过载」 |

---

## 十一、验证证据

- ✅ **115/115 测试全过**(其中 Capacity 19 + Sprint 15 + 全模块 81 个回归)
- ✅ Tool 总数 24 → **29**(新增 5 个 Capacity Tool)
- ✅ API 端点 94 → **101**(新增 7 个 Capacity 端点)
- ✅ 定时任务 8 → **9**(新增周一 08:30 水位刷新)
- ✅ Model 总数 19 → **20**(新增 CapacitySnapshot)
- ✅ 等级边界 8 个测试用例覆盖
- ✅ 休假/出差/病假状态折减全部测试守门
- ✅ 调配算法保护机制(关键路径 + in_progress 不动)测试守门
- ✅ 同部门优先 + 跨部门兜底测试守门
- ✅ TypeScript 零错误,前端水位看板完整

---

## 十二、V2.0 总收官 🎉

```
✅ V0.5 / V1.0 / V1.1
✅ V2.0 战略增强层:
    ✅ §7.1 OKR 战略对齐(Week 5)
    ✅ §7.2 资源负载水位预判(Week 8) ← 本周完成
    ✅ §7.3 AI 自动复盘(Week 6)
✅ V2.0 长周期跟踪:
    ✅ §5  Sprint/燃尽图/关键路径/Velocity(Week 7)
✅ V2.0 总经理 AI 对话:
    ✅ §6.6 Function Calling + 29 Tool(Week 4)
```

**白皮书完成度: ~94% → ~100%(主干全部完成)**

剩余 P3 优化项(非主线):
- 移动端响应式 + PWA
- 知识库语义检索(pgvector embedding)
- 燃尽实时预警推送
- AI 自动从日报抽取 Task 推进

---

## 十三、相关文档

- [system-overview.md](./system-overview.md) — 应用全图(战略层全绿)
- [week7-sprint-burndown.md](./week7-sprint-burndown.md) — Capacity 计算依赖的故事点数据来源
- [week6-retro.md](./week6-retro.md) — 复盘可参考历史 Capacity 数据
- [whitepaper-system-design.md](./whitepaper-system-design.md) §7.2 — 原产品视角设计
- [implementation-plan.md](./implementation-plan.md) §12 — 原技术方案(Week 8 已落地)
