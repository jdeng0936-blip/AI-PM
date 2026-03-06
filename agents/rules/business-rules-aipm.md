---
trigger: always_on
---

# 📋 AI-PM 业务约束 (Business Rules)

> 本文档定义了 AI-PM（智能项目管理系统）的业务层约束。
> 技术底座和 AI 调用规范见通用的 [architecture-rules.md](./architecture-rules.md) 和 [ai-model-rules.md](./ai-model-rules.md)。

---

## 1. 数据模型（核心表清单）

### 基础实体
- `users`: 用户（角色: employee/manager/admin；含 department, job_title）
- `audit_logs`: 操作审计日志
- `notifications`: 系统通知
- `departments`: 部门

### 日报模块
- `daily_reports`: 日报（含 AI 评分、质检结果、结构化 JSON）
- `report_templates`: 岗位日报模板（JSONB 定义共有/特有字段）
- `report_attachments`: 日报附件（OSS URL，支持 image/document/audio）
- `attendance_status`: 出勤/请假/出差状态

### 项目管理模块
- `projects`: 项目（IPD 门径流程）
- `project_stages`: 项目阶段
- `project_members`: 项目成员
- `sprints`: Sprint 迭代
- `tasks`: 任务（含 story_points 故事点）
- `gate_reviews`: 门径评审

### 战略模块
- `okr_cycles`: OKR 周期
- `objectives`: 公司级目标
- `key_results`: 关键结果
- `kr_task_links`: KR ↔ 任务绑定
- `kpi_targets`: KPI 目标基线

### 知识资产
- `retrospective_reports`: AI 复盘报告
- `knowledge_assets`: FAQ/风险预案/最佳实践（含 pgvector embedding）

---

## 2. 场景 → 模型映射

> 基于通用 ai-model-rules.md 的分级规则，AI-PM 的具体映射如下：

### 🟢 FAST 场景
| AI-PM 功能 | 函数 | 模型 | Temperature |
|---|---|---|---|
| 日报文本 → JSON 解析 | `parse_report()` | `gemini-2.5-flash` | 0.2 |
| 日报质检（格式/字数） | `quality_check()` | `gemini-2.5-flash` | 0.2 |
| KR 进度自动提取 | `auto_update_kr_from_report()` | `gemini-2.5-flash` | 0.2 |

### 🟡 MEDIUM 场景
| AI-PM 功能 | 函数 | 模型 | Temperature |
|---|---|---|---|
| 日报 AI 评分与点评 | `score_report()` | `gemini-3-flash-preview` | 0.5 |
| 总经理 AI 对话查询 | `admin_chat()` | `gemini-3-flash-preview` | 0.3 |
| Sprint 负载预判 | `check_sprint_feasibility()` | `gemini-3-flash-preview` | 0.5 |
| AI 周报生成 | `generate_weekly_report()` | `gemini-3-flash-preview` | 0.5 |

### 🔴 HEAVY 场景
| AI-PM 功能 | 函数 | 模型 | Temperature |
|---|---|---|---|
| AI 阶段复盘报告 | `generate_retrospective()` | `gemini-2.5-pro` | 0.5 |
| 项目风险深度预测 | `predict_project_risk()` | `gemini-2.5-pro` | 0.4 |
| OKR 进度智能分析 | `analyze_okr_progress()` | `gemini-2.5-pro` | 0.5 |

---

## 3. 系统角色设计

扁平汇报结构，所有人员向总经理汇报：

| 角色 | 系统内 role | 权限 |
|------|-----------|------|
| 总经理 | `admin` | 全局看板 + AI 对话 + 用户管理 + KPI 设定 |
| 部门负责人 | `manager` | 查看本部门数据 |
| 普通员工 | `employee` | 提交日报 + 查看个人数据 |

预设岗位：技术部长、生产经理、采购经理、财务部长、商务经理、销售部长、仓管、研发工程师

---

## 4. 前端路由结构

```
app/
├── (auth)/login/               # 登录页（公开）
└── (protected)/                # 受保护路由
    ├── layout.tsx              # Sidebar + 主区域
    ├── dashboard/              # 总经理战情看板
    ├── reports/                # 日报管理
    ├── projects/               # 项目管理
    ├── sprints/                # Sprint 管理
    ├── okr/                    # OKR 目标管理
    ├── analytics/              # 历史趋势看板
    ├── knowledge/              # 知识资产库
    ├── users/                  # 用户管理（admin）
    └── settings/               # 系统设置
```

---

## 5. MVP 实施路线

```
Phase V0.5 (2周):  Chat-to-Form + 结构化解析
Phase V1.0 (2周):  完整质检 + 评分 + 跨日监督
Phase V2.0 (1月):  战情看板 + 自动周报 + 预警
Phase V3.0 (1月):  长期项目跟踪 + Sprint
Phase V4.0 (1月):  战略增强 (OKR + Capacity + 复盘)
```
