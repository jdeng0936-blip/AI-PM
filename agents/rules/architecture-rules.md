---
trigger: always_on
---

# 🛡️ 通用开发约束与架构红线 (Architecture Rules)

> 本规约定义了所有项目的统一技术底座、架构选型与 AI 开发红线。
> 项目特定的数据模型、路由结构等约束在各项目的 `business-rules-*.md` 中单独维护。

> 最后更新：2026-03-06

---

## 📌 【架构定调：原生一体化数据库】

**PostgreSQL 16 + `pgvector` 插件为唯一数据存储底座。**
- 业务表与向量表在同一个数据库中，可用原生 SQL 一条语句同时完成关系查询 + 向量相似度查询
- 无需引入外部向量数据库（如 ChromaDB / Milvus），零数据同步开销

---

## 第一部分：系统架构选型底座

### 1. API 框架 (后端侧)
- **框架**: FastAPI (Python 3.11+)
- **服务器**: Uvicorn
- **默认端口**: 8000

### 2. 数据与存储侧
- **核心数据库 (关系+向量)**: PostgreSQL 16 + pgvector plugin
- **缓存/队列**: Redis Stack (高频查询缓存、WebSocket状态、流控中间件)
- **文件存储**: 阿里云 OSS (aliyun.com)

### 3. AI 能力侧
- **LLM 网关**: LiteLLM Proxy（统一 OpenAI 兼容协议）
- **模型路由**: GlobalLLMRouter（多级回退保障可用性）
- **RAG 检索**: pgvector 向量相似度检索（PostgreSQL 原生）
- **图查询**: PostgreSQL 递归 CTE（模拟图遍历，不引入外部图数据库）
- **推理引擎**: LLM（检索结果 + 关系数据 → LLM 推理决策）
- **Agent 框架**: LangGraph (接替复杂 if-else 流转)
- **AI 可观测性**: LangFuse (langfuse.com)

### 4. 外部接口
- **ASR 语音转文本**: 科大讯飞 API (xfyun.cn) — 严禁采用无 ToB 合作协议的免费/不稳定服务
- **消息推送**: 企业微信 Webhook

---

## 🖥️ 第二部分：前端技术栈

### 管理端技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| **框架** | Next.js（App Router）| SSR + API Routes + Middleware 鉴权 |
| **语言** | TypeScript | 严格模式 |
| **CSS** | Tailwind CSS | — |
| **组件库** | shadcn/ui + Radix UI | 可定制无样式基础组件 |
| **图标** | Lucide React | 统一图标库 |
| **图表** | Recharts | KPI / 看板可视化 |
| **表格** | TanStack Table | 列表 + 明细 |
| **表单** | React Hook Form + Zod | 复杂表单校验 |
| **全局状态** | Zustand | 持久化至 localStorage |
| **服务端状态** | TanStack Query | 接口缓存、自动刷新 |
| **HTTP** | Axios | 统一拦截器注入 Token |

### Chat 端技术栈（如需对话式交互）

| 层级 | 选型 | 说明 |
|------|------|------|
| **框架** | Next.js（App Router）| 与管理端统一 |
| **AI 流式** | Vercel AI SDK（`ai` 包）| `useChat` hook，流式打字效果 |
| **流式协议** | Server-Sent Events（SSE）| FastAPI 原生支持 |
| **Markdown渲染** | react-markdown + remark-gfm | AI 回复格式化 |
| **动画** | Framer Motion | 消息入场、打字光标 |
| **语音录制** | Web Speech API / MediaRecorder | 浏览器原生录音 → ASR |

### 前端通用约定

- **路径别名**: `@/` → `src/`
- **API 代理**: 开发环境 `/api/*` → `http://localhost:8000`（`next.config.ts` rewrites）
- **`use client` 原则**: 含 `localStorage` / 浏览器 API 的组件必须标注 `'use client'`
- **LLM Key 禁止客户端暴露**: 所有 AI 调用必须走后端或 Next.js Server 端

---

## ️ 第三部分：环境变量与安全守则

所有敏感鉴权信息及服务配置，严禁硬编码至代码仓库中，必须存放在 `.env` 文件。

```bash
# === 1. 大模型通信 (LLM) ===
LITELLM_BASE_URL=https://your-litellm-proxy.example.com
LITELLM_API_KEY=your_litellm_key

# === 2. 持久化存储 (Database) ===
DATABASE_URL=postgresql://user:password@localhost:5432/your_db

# === 3. 阿里云对象存储 (OSS) ===
OSS_ACCESS_KEY_ID=your_aliyun_id
OSS_ACCESS_KEY_SECRET=your_aliyun_secret
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET_NAME=your-bucket-name

# === 4. 科大讯飞语音引擎 (ASR) ===
XUNFEI_APP_ID=your_app_id
XUNFEI_API_KEY=your_api_key
XUNFEI_API_SECRET=your_api_secret

# === 5. 企微通知 ===
WECOM_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

# === 6. LangFuse 可观测性 ===
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...

# === 7. JWT 安全 ===
JWT_SECRET_KEY=your-jwt-secret-change-in-production
```

---

## 🔒 第四部分：AI 开发红线 (Agentic Rules)

### Rule 1: 禁止在客户端暴露大模型 Key
所有涉及 LLM 的推理，必须放在 FastAPI 后端执行，或 Next.js 的 Server 端执行（如 Route Handlers 或 Server Actions），并通过内部 Token 鉴权。

### Rule 2: 意图路由告别 If-Else
所有复杂的意图路由，必须配置给大模型内置的 Tool Calling（函数触发）或 LangGraph 工作流机制，不得在代码里硬堆砌正则匹配或 `elif "分析" in text`。

### Rule 3: 文件二进制严禁入库
这是架构底线。所有图片、音频、PDF **必须** 流转存入 `阿里云 OSS`，在 PostgreSQL 中**仅存储其 URL 或 OSS key**。

### Rule 4: 数据权限隔离优先 (Tenant Isolation)
无论是关系库查询还是 pgvector 相似度查询，**前置过滤条件必须带上访问者的权限标识或所属 Project/Team ID**，防止跨权限数据泄露。

---

## 🧠 第五部分：AI 推理架构（RAG + CTE + LLM）

**核心原则：pgvector 负责"语义检索"，递归 CTE 负责"关系遍历"，LLM 负责"推理决策"。三者全部在 PostgreSQL + LiteLLM 体系内完成，零额外依赖。**

### 三层流水线架构

```
用户提问
  |
  +-- 1. pgvector 向量检索 --> 按语义相似度找到 Top-K 相关内容
  |    使用: embedding 列 + cosine 距离 (<=>)
  |
  +-- 2. 递归 CTE 图查询  --> 沿关系链遍历（汇报链、依赖路径等）
  |    使用: WITH RECURSIVE
  |
  +-- 3. 普通 SQL 查询    --> 基本信息、状态、统计
  |
  +-- 4. 三路数据拼入 Prompt --> LLM 推理 --> 最终回答
```

### 各层职责边界

| 层 | 技术 | 职责 | 不做什么 |
|----|------|------|----------|
| **检索层** | pgvector | 按语义相关性找到 Top-K 内容 | 不做推理、不做排序决策 |
| **关系层** | 递归 CTE | 遍历关系链/依赖路径 | 不做语义理解、不做策略分析 |
| **推理层** | LLM | 综合分析、策略建议、文案生成 | 不做数据检索 |

### Rule 5: 推理分层不可越界
- **pgvector 只做检索，不做推理**
- **递归 CTE 只做遍历，不做语义**
- **LLM 只做推理，不做检索** — 必须接收精准检索结果，不应全量数据灌入
- **严禁全量上下文灌入** — 必须先检索/过滤，只将相关内容送入 LLM

### Embedding 字段规范
- 需要向量检索的表必须包含 `embedding Vector(1536)` 列
- Embedding 生成统一通过 LiteLLM 网关调用 embedding 模型
- 向量索引使用 HNSW（`CREATE INDEX ... USING hnsw (...) WITH (m=16, ef_construction=200)`）
- 所有向量查询必须带权限前置过滤（参见 Rule 4）
