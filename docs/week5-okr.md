# Week 5 — OKR 战略对齐联调指南

> 完成时间:2026-05-19 | 阶段:V2.0 战略层第一块
>
> 本文档涵盖 Week 5 完成的 OKR 模块所有能力 — 数据模型、API、AI 自动提取、Chat Tool、前端看板、定时任务。

---

## 一、Week 5 交付概览

| 模块 | 关键文件 | 价值 |
|------|---------|------|
| **KR 进度日志模型** | `models/okr.py::KRProgressLog` + KRProgressSource 枚举 | 每次进度变更可审计(AI / 手工 / Sprint / 系统) |
| **OKR 完整 CRUD** | `routers/okr.py` (15 个端点) | 周期/目标/KR 全套 + 进度日志查询 + 树状视图 |
| **AI 自动提取 KR 进度** | `services/kr_progress_extractor.py` | 日报通过质检后自动识别 KR 数值更新 |
| **4 个 OKR Chat Tool** | `chat_tools/okr.py` | 总经理 AI 对话可查询 OKR |
| **前端 OKR 看板** | `app/okr/page.tsx` + `api/okr.ts` | O/KR 树 + 进度条 + 变更历史 Drawer + CRUD |
| **季度自动归档** | `scheduled_tasks.run_quarterly_okr_summary` | 季度末自动总结达成情况 + 推送管理层 |

---

## 二、数据模型

```
OKRCycle (周期, 季度/月度/年度)
  └── Objective (目标)
        ├── KeyResult (关键结果)
        │     └── KRProgressLog (进度变更审计日志, Week 5 新增)
        └── owner: User
```

### KRProgressSource(进度变更来源)

| 值 | 含义 |
|----|------|
| `manual` | 管理员/经理手工更新 |
| `ai_extracted` | AI 从日报自动提取 |
| `sprint_close` | Sprint 关闭时聚合(预留) |
| `system` | 系统自动(如季度归档) |

---

## 三、API 端点(15 个)

| 方法 | 路径 | 权限 | 用途 |
|------|------|------|------|
| `GET` | `/okr/cycles` | 全员 | 列出所有 OKR 周期 |
| `POST` | `/okr/cycles` | admin | 创建周期 |
| `PATCH` | `/okr/cycles/{id}` | admin | 更新周期(名称/状态/日期) |
| `DELETE` | `/okr/cycles/{id}` | admin | 删除周期(级联删 O/KR/log) |
| `GET` | `/okr/objectives?cycle_id=` | 全员 | 列出目标 |
| `POST` | `/okr/objectives` | admin/manager | 创建目标 |
| `PATCH` | `/okr/objectives/{id}` | admin/manager | 更新目标 |
| `DELETE` | `/okr/objectives/{id}` | admin/manager | 删除目标 |
| `GET` | `/okr/key-results?objective_id=` | 全员 | 列出 KR |
| `POST` | `/okr/key-results` | admin/manager | 创建 KR |
| `PATCH` | `/okr/key-results/{id}` | admin/manager | 更新 KR(进度变更自动落日志) |
| `DELETE` | `/okr/key-results/{id}` | admin/manager | 删除 KR |
| `GET` | `/okr/key-results/{id}/progress-logs` | 全员 | 查看 KR 变更历史 |
| `GET` | `/okr/tree?cycle_id=` | 全员 | 一次拿到完整 O/KR 树 + 汇总 |

---

## 四、AI 自动提取 KR 进度 — 工作流

```
员工提交日报
    ↓
AI 质检通过 → 落库 daily_reports
    ↓
extract_and_update_kr_progress_safe()
    ↓
查找该员工 owner 的 active KR 列表
    ↓
[若有] 调 LLM(kr_progress 模型),传入日报原文 + KR JSON
    ↓
LLM 输出候选更新数组(含置信度 + 原文证据)
    ↓
逐条校验:
  - confidence ≥ 0.6 才采纳
  - kr.owner_id 必须等于 report.user_id(防跨用户)
  - 类型转换失败 → 跳过
    ↓
写 KR.current_value + KRProgressLog (source=ai_extracted)
    ↓
重算 Objective.progress
    ↓
随主流程一起 commit
```

### 安全设计

| 风险 | 防御 |
|------|------|
| LLM 编造 KR id | dispatch 前用 `kr.owner_id == report.user_id` 校验 |
| LLM 模糊匹配导致误更新 | 置信度 < 0.6 自动跳过 |
| LLM 返回非法值 | float() 转换失败 → 跳过 |
| LLM 调用失败 | `extract_and_update_kr_progress_safe` 吞异常,不影响日报主流程 |
| 同一日报重复触发 | KR.current_value 变更幅度小于 1e-6 时跳过 |

### 示例

**日报原文**:
> 今天优化了 LoRA 推理路径,把端到端延迟从 800ms 降到了 450ms,已经过了 KR1 的目标线。

**LLM 输出**:
```json
[
  {
    "kr_id": "kr-uuid-1",
    "new_value": 450,
    "confidence": 0.92,
    "evidence": "把端到端延迟从 800ms 降到了 450ms"
  }
]
```

**结果**:
- `key_results.current_value`: 800 → 450
- `kr_progress_logs` 新增一条 `source=ai_extracted, confidence=0.92`
- `objectives.progress` 重新计算

---

## 五、4 个 OKR Chat Tool

| Tool | 描述 | 典型问题 |
|------|------|---------|
| `list_active_objectives` | 当前 active 周期的所有 O | 「本季度有哪些目标?」 |
| `kr_status` | 某目标下所有 KR 的详细进度 | 「206 样机的 KR 进度怎么样?」 |
| `kr_at_risk` | 滞后的 KR(<阈值,默认 40%) | 「哪些 KR 进度落后?」 |
| `objective_snapshot` | 单个目标完整快照 + 变更日志 | 「206 项目目标的最近变化?」 |

总经理在 `/chat` 页提问后,LLM 会自动选择合适的 OKR Tool。

---

## 六、前端 OKR 看板使用

访问 `/okr`(sidebar「OKR 战略」入口)

### 顶部操作区
- **周期选择器**:切换不同 cycle 查看
- **+ 新周期** / **+ 新建目标**:仅 admin/manager 可见
- **健康度三色徽标**:on_track / at_risk / behind 数量

### 主体:O/KR 树
- 点 `▶` 展开 Objective 看其 KR
- 每个 KR 显示:进度条 + 当前/目标值 + 信心指数徽标(>70% 显示 ✨)
- 右侧操作按钮:
  - 🕘 变更历史(Drawer 形式打开)
  - ✏ 编辑进度(仅 admin/manager)
  - 🗑 删除(仅 admin/manager)

### 变更历史 Drawer
- 时间倒序显示每次变更
- 来源徽标区分 🤖 AI 提取 / ✋ 手工 / 🔁 Sprint / ⚙ 系统
- AI 提取条目额外显示置信度百分比

---

## 七、定时任务清单(累计 7 个)

| 时间 | 任务 |
|------|------|
| 00:30 每日 | 健康度全量重算 |
| 09:00 每日 | 晨报 AI 生成 |
| 09:00 周一 | 上周管理周报 |
| 09:30 每月 1 日 | **OKR 季度归档(仅季度首日生效)** ← Week 5 新增 |
| 17:30 每日 | 催报-友好提醒 |
| 20:00 每日 | 催报-二次催促 |
| 22:00 每日 | 催报截止 + 通知总经理 |

### 季度归档逻辑
- 触发条件:每月 1 日 09:30 检查「昨天是否是季度末」
- 季度末枚举:3.31 / 6.30 / 9.30 / 12.31
- 找到 `cycle_type=quarterly` 且 `status=active` 且 `end_date <= yesterday` 的最近周期
- 聚合统计 + 转为 `completed` 状态
- 推送达成总结给所有 admin/manager(企微 + 钉钉 + 站内信)

---

## 八、联调步骤

### 8.1 启动 + 准备数据

```bash
# 后端
cd backend && .venv311/bin/uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && npm run dev
```

### 8.2 创建第一个周期 + 目标 + KR

1. admin 登录 → 访问 `/okr`
2. 点「+ 新周期」→ 填「2026Q2 / 2026-04-01 / 2026-06-30」
3. 点「+ 新建目标」→ 填标题与权重
4. 在目标卡片上点 `+` → 新建 KR(填目标值/单位)

### 8.3 触发 AI 自动提取

1. 用「目标负责人」账号提交日报,内容里明确提到 KR 的数值进展
2. 日报通过质检后,API 返回里会带 `kr_updates` 数组
3. 回到 `/okr` 页面,点 KR 的 🕘 → 看到一条 🤖 AI 提取的记录

### 8.4 用对话查询 OKR

在 `/chat` 提问:
- 「本季度有哪些目标?」
- 「206 样机这个目标的 KR 都怎么样?」
- 「有哪些 KR 进度低于 40%?」

应看到 LLM 自动调用了 `list_active_objectives` / `kr_status` / `kr_at_risk`。

### 8.5 测试季度归档(无需等真季度末)

```bash
# Python 直接调用,模拟季度归档
.venv311/bin/python -c "
import asyncio
from app.services.scheduled_tasks import run_quarterly_okr_summary
asyncio.run(run_quarterly_okr_summary())
"
# 注意:如果今天不是季度首日,函数会直接 return。
# 测试时可临时修改 _is_quarter_end 让它对今天 True。
```

---

## 九、扩展点(留给 Week 6+)

| 扩展方向 | 提示 |
|---------|------|
| **KR 与 Sprint 绑定** | `KeyResult.sprint_id` 已有字段,Week 5 没接入 UI。Sprint 完成时可自动推 `sprint_close` 源 |
| **KR 与项目绑定** | `Objective.project_id` 已有,前端尚未展示 |
| **跨用户 OKR(协作 KR)** | 当前 KR 强绑 `owner_id`,如需多人协作可改成 `kr_collaborators` 关联表 |
| **置信度衰减** | KR 长期未更新可定时降低 confidence,提示 owner 复查 |
| **OKR 周报联动** | Week 4 周报模板可扩展加入「本周 OKR 进度变化」段 |

---

## 十、验证证据汇总

- ✅ 测试 64/64 通过(其中 OKR 13 个 + 其他模块 51 个回归)
- ✅ Tool 注册总数从 13 增至 **17**
- ✅ 后端路由总数 **82**(比 Week 4 末 + 8 个 OKR 端点)
- ✅ 数据库新表:`kr_progress_logs`(自动 create_all)
- ✅ TypeScript 零错误,前端 OKR 页面零编译警告
- ✅ Sidebar 新增「🎯 OKR 战略」入口
- ✅ 季度判定纯函数测试用例覆盖 8 个边界

---

## 十一、相关文档

- [system-overview.md](./system-overview.md) — 应用全图,⑨ 战略层已部分实现
- [week4-chat-tools.md](./week4-chat-tools.md) — Chat 框架基础,Week 5 在此扩展了 4 个 OKR Tool
- [whitepaper-system-design.md](./whitepaper-system-design.md) §7.1 — OKR 产品视角设计
- [implementation-plan.md](./implementation-plan.md) §11 — 原始技术方案(Week 5 已落地)
