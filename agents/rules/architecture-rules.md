---
trigger: always_on
---

# 🛡️ SRI v2.0 开发约束与架构红线 (Development Rules)

本规约旨在约束 SRI 作战指挥室 v2.0 的开发架构、环境规范及编码守则，确保在高复杂度 AI 架构下代码的可扩展性与维护性。

> 最后更新：2026-02-28

---

## 📌 【架构定调：原生一体化数据库】

**终极决议：彻底弃用 ChromaDB 和 Sqlite，全面采用 PostgreSQL 16 + `pgvector` 插件。**
- **核心优势**：业务表与向量表在同一个数据库中，可以用原生 SQL 一条语句同时完成"查某本电子书(关系查询) + 查内容相似度(向量查询)"，彻底免除双库之间的数据同步烦恼。

---

## 第一部分：系统架构选型底座

### 1. API 框架 (后端侧)
- **框架**: FastAPI (Python 3.11+)
- **服务器**: Uvicorn
- **端口**: 8000

### 2. 数据与存储侧
- **核心数据库 (关系+向量集成)**: PostgreSQL 16 + pgvector plugin
- **缓存/队列**: Redis Stack (高频查询缓存、WebSocket状态、流控中间件)
- **文件存储**: 阿里云 OSS (aliyun.com)

### 3. AI 能力侧
- **LLM 网关**: LiteLLM Proxy (`litellm.ailingxi.online`)
- **模型路由**: GlobalLLMRouter（5 级回退：OpenAI → Gemini → Anthropic → xAI → Local）
- **RAG 检索**: pgvector 向量相似度检索（PostgreSQL 原生，不引入外部向量库）
- **图查询**: PostgreSQL 递归 CTE（模拟图遍历，不引入外部图数据库）
- **推理引擎**: LLM（检索结果 + 关系数据 → LLM 完成推理决策）
- **Agent 框架**: LangGraph (接替复杂的 if-else 流转)
- **AI 可观测性**: LangFuse (langfuse.com)
- **情报解析系统**: 遵循独家 4+1 情报模型 (`current_status`, `decision_chain`, `competitor_info`, `next_steps`, `gap_alerts`)

### 4. 外部接口生态
- **ASR 语音转文本引擎**: 科大讯飞 API (xfyun.cn) — *严禁采用无 ToB 合作协议的免费或不稳定服务。*
- **消息推送网关**: 企业微信 Webhook (审批消息推送通知)

---

## 🖥️ 第二部分：前端双端架构

> ⚠️ 两个前端均为**独立新建项目**，版本号不在此固定，以建项时最新稳定版为准。

### 架构分工

| 端 | 项目目录 | 使用者 | 职责定位 |
|----|---------|-------|---------|
| 🖥️ **管理端** | `next-admin/` | 领导、管理员、财务 | 审批流、数据看板、配置管理 |
| 💬 **Chat 端** | `next-chat/` | 一线销售人员 | AI 对话式日常工作台 |

两端共用同一套 FastAPI 后端，通过 JWT Token 鉴权区分角色与权限。

---

### 🖥️ 管理端技术栈（next-admin）

**定位**：复杂表单、审批状态机、数据看板，传统 Admin 交互模式。

| 层级 | 选型 | 说明 |
|------|------|------|
| **框架** | Next.js（App Router）| SSR + API Routes + Middleware 鉴权 |
| **语言** | TypeScript | 严格模式 |
| **CSS** | Tailwind CSS | 深色主题，复用现有 CSS 变量 |
| **组件库** | shadcn/ui + Radix UI | 可定制无样式基础组件 |
| **图标** | Lucide React | 统一图标库 |
| **图表** | Recharts | 领导看板 KPI 可视化 |
| **表格** | TanStack Table | BOM 明细、审批列表 |
| **表单** | React Hook Form + Zod | 复杂表单校验 |
| **全局状态** | Zustand | 持久化至 localStorage |
| **服务端状态** | TanStack Query | 接口缓存、自动刷新 |
| **HTTP** | Axios | 统一拦截器注入 Token |

**路由结构（App Router）**：
```
app/
├── (auth)/login/          # 登录页（公开）
└── (protected)/           # 受保护路由（Middleware 鉴权）
    ├── layout.tsx          # Sidebar + 主区域布局
    ├── sandbox/            # 作战沙盘
    ├── intel/              # 情报录入
    ├── first-scene/        # 第一现场
    ├── academy/            # AI 伴学
    ├── knowledge/          # 知识武器库
    ├── live-pitch/         # 炮火支援
    ├── leader/             # 领导看板
    ├── finance/            # 粮草审批
    ├── bidding/            # 招投标
    ├── deal-desk/          # 询报价
    └── contract/           # 合同联审
```

---

### 💬 Chat 端技术栈（next-chat）

**定位**：高频使用，Chat 对话体验优先，设计参考 Grok.com 极简风格。

| 层级 | 选型 | 说明 |
|------|------|------|
| **框架** | Next.js（App Router）| 与管理端统一技术栈 |
| **语言** | TypeScript | 严格模式 |
| **CSS** | Tailwind CSS | 高度自定义极简深色 |
| **组件库** | shadcn/ui（最小化引入）| Chat UI 完全自定义 |
| **AI 流式** | Vercel AI SDK（`ai` 包）| `useChat` hook，流式打字效果开箱即用 |
| **流式协议** | Server-Sent Events（SSE）| FastAPI 已支持，前端 SSE 接收 |
| **状态管理** | Zustand | 与管理端共享 auth 逻辑 |
| **Markdown渲染** | react-markdown + remark-gfm | AI 回复格式化渲染 |
| **动画** | Framer Motion | 消息入场、打字光标动效 |
| **语音录制** | Web Speech API / MediaRecorder | 浏览器原生录音 → 讯飞 ASR 转写 |
| **HTTP** | Axios | 调用 FastAPI 业务接口（Tool Calling）|

**Chat 端核心功能（通过 Tool Calling 调 FastAPI）**：
- 情报快速录入（口述/打字 → AI 4+1解析 → 自动入库）
- AI 参谋对话（项目策略分析、话术生成、周报撰写）
- RAG 技术问答（客户追问时秒出专业回答）
- 伴学测验（AI 出题 → 对话作答 → 即时点评打分）
- SOS 求援发起（Chat 提单，管理端处理）
- 项目状态快速查询

**UI 设计原则**：
- 无气泡边框，靠头像 + 名称区分 AI / 用户消息
- 底部固定大输入条，支持语音/附件/文字三合一
- 侧边栏极简可折叠（图标 + 文字）
- 背景色 `#0a0a0a` 极简深色

---

### 前端通用约定

- **路径别名**: `@/` → `src/`（两个前端项目统一）
- **API 代理**: 开发环境 `/api/*` → `http://localhost:8000`（`next.config.ts` rewrites）
- **`use client` 原则**: 含 `localStorage` / 浏览器 API 的组件必须标注 `'use client'`
- **LLM Key 禁止客户端暴露**: 所有 AI 调用必须走后端或 Next.js Server 端

---

## 📐 第三部分：业务数据模型 (核心表清单)

数据库建表结构必须包含（但不限于）以下核心实体：
- `users`: 用户/销售人员（角色: sales/director/vp/admin）
- `projects`: 作战项目（含 MEDDIC 7维赢率、审批状态机）
- `stakeholders`: 权力地图关键人
- `intel_logs`: 情报日志（支持多模态: text/image/audio/document）
- `deal_desks`: 报价底单（强状态机: draft → pending → approved/rejected）
- `bom_items`: 报价 BOM 明细行
- `contracts`: 合同联审（6步状态机流转）
- `contract_bom_items`: 合同 BOM 明细
- `sos_tickets`: 前线 SOS 紧急求援工单
- `appeals`: 撞单申诉仲裁记录

---

## 🛠️ 第四部分：环境变量与安全守则 (ENV Config)

所有敏感鉴权信息及服务配置，严禁硬编码至代码仓库中，必须存放在 `.env` 文件。

```bash
# === 1. 大模型通信 (LLM) ===
LITELLM_BASE_URL=https://litellm.ailingxi.online
LITELLM_API_KEY=your_litellm_key

# === 2. 持久化存储 (Database) ===
DATABASE_URL=postgresql://user:password@localhost:5432/sri_v2

# === 3. 阿里云对象存储 (OSS) ===
OSS_ACCESS_KEY_ID=aliyun_id
OSS_ACCESS_KEY_SECRET=aliyun_secret
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET_NAME=sri-sales-assets

# === 4. 科大讯飞语音引擎 (ASR) ===
XUNFEI_APP_ID=xunfei_app_id
XUNFEI_API_KEY=xunfei_api_key
XUNFEI_API_SECRET=xunfei_api_secret

# === 5. 企微与可观测性通知 ===
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

# === 6. LangFuse ===
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
```

---

## 🔒 第五部分：底层 AI 开发红线 (Agentic Rules)

### Rule 1: 禁止在客户端暴露大模型 Key
所有涉及 LLM 的推理，必须放在 FastAPI 后端执行，或 Next.js 的 Server 端执行（如 Route Handlers 或 Server Actions），并通过内部 Token 鉴权。

### Rule 2: 意图路由告别 If-Else
所有复杂的意图路由，必须配置给大模型内置的 Tool Calling（函数触发）或 LangGraph 工作流机制，不得在代码里硬堆砌正则匹配或 `elif "分析" in text`。

### Rule 3: 文件二进制严禁入库
这是架构底线。所有的图片、音频、PDF **必须** 流转存入 `阿里云 OSS`，并在 `PostgreSQL` 与其 `pgvector` 数据表中**仅存储其 URL 或对应的 OSS key**。

### Rule 4: 数据权限隔离优先 (Tenant Isolation)
无论是普通的 Postgres 关系库查询，还是深入到 `pgvector` 的相似度查询，**前置过滤条件必须带上访问者的权限标识或所属 Project ID**，绝不能允许跨权限偷窥"暗单"。

---

## 🧠 第六部分：AI 推理架构（RAG + CTE + LLM）

**核心原则：pgvector 负责"语义检索"，递归 CTE 负责"关系遍历"，LLM 负责"推理决策"。三者全部在 PostgreSQL + LiteLLM 体系内完成，零额外依赖。**

### 三层流水线架构

```
用户提问
  |
  +-- 1. pgvector 向量检索 --> 按语义相似度找到 Top-K 相关情报/文档
  |    使用: embedding 列 + cosine 距离 (<=>)
  |
  +-- 2. 递归 CTE 图查询  --> 沿关系链遍历（汇报链、决策路径、影响关系）
  |    使用: WITH RECURSIVE + stakeholders.reports_to_id
  |
  +-- 3. 普通 SQL 关系查询 --> 项目基本信息、阶段、赢率、里程碑
  |
  +-- 4. 三路数据精准拼入 Prompt --> LLM 推理 --> 最终回答
```

### 各层职责边界

| 层 | 技术 | 职责 | 不做什么 |
|----|------|------|----------|
| **检索层** | pgvector | 按语义相关性找到 Top-K 内容 | 不做推理、不做排序决策 |
| **关系层** | 递归 CTE | 遍历汇报链/决策链/影响路径 | 不做语义理解、不做策略分析 |
| **推理层** | LLM | 综合分析、策略建议、文案生成 | 不做数据检索（由前两层提供） |

### Rule 5: 推理分层不可越界
- **pgvector 只做检索，不做推理** — 不要期望向量数据库本身能"理解"或"推导"
- **递归 CTE 只做遍历，不做语义** — 图遍历返回结构化路径，语义理解交给 LLM
- **LLM 只做推理，不做检索** — LLM 接收精准的检索结果，不应全量加载数据让 LLM 自己翻找
- **严禁全量上下文灌入** — 必须先检索/过滤，只将相关内容送入 LLM，避免 token 浪费

### Embedding 字段规范
- 需要向量检索的表（如 `intel_logs`、知识库文档表）必须包含 `embedding Vector(1536)` 列
- Embedding 生成统一通过 LiteLLM 网关调用 embedding 模型
- 向量索引使用 HNSW（`CREATE INDEX ... USING hnsw (...) WITH (m=16, ef_construction=200)`）
- 所有向量查询必须带 `project_id` 或权限前置过滤（参见 Rule 4）

---

## 🗺️ 第七部分：演进路线

```
Phase 1（进行中）: 新建管理端 next-admin（Next.js）
Phase 2:           后端 SQLite -> PostgreSQL + pgvector 迁移
Phase 2.5:         基础 RAG -- 情报表加 embedding 列，实现语义检索 + LLM 推理
Phase 3:           新建 Chat 端 next-chat，实现核心 Chat 功能
Phase 3.5:         知识库 RAG -- 白皮书/技术文档切片 -> pgvector 索引 -> RAG 问答
Phase 4:           接入 LangGraph Agentic RAG + 递归 CTE 关系推理 + LangFuse 监控
Phase 5:           两端合并 Monorepo（Turborepo，共享 types/hooks/utils）
```
