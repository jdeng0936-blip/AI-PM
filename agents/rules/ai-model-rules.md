---
trigger: always_on
---

# 🧠 AI 大模型调用规则（AI Model Rules）

> 本文档定义了所有项目中大模型调用的统一规范。
> 所有 AI 模块必须通过 LiteLLM 网关路由，根据场景分级选择最合适的模型。
> **配套文件**：整体架构规约见 [architecture-rules.md](./architecture-rules.md)

> ⚠️ 与 architecture-rules.md 的关系说明：
> - architecture-rules 中的「GlobalLLMRouter 多级回退」是**服务可用性**保障（模型不可用时切换）
> - 本文档的「场景→模型映射」是**主动选型规则**（根据任务类型选最合适的模型）
> - 两者不冲突：先按本文档选型，若该模型不可用再走回退链

---

## 1. 网关配置

| 配置项 | 值 |
|---|---|
| **Base URL** | 由 `.env` 中 `LITELLM_BASE_URL` 指定 |
| **API Key** | 由 `.env` 中 `LITELLM_API_KEY` 指定（严禁硬编码）|
| **协议** | OpenAI 兼容（`/v1/chat/completions`）|

---

## 2. 可用模型清单

| 模型 ID | 输入成本 | 输出成本 | 速度 | 推理能力 | 多模态 |
|---|---|---|---|---|---|
| `gemini-2.5-flash` | $0.30 | $2.50 | ⚡⚡⚡ 极快 | ★★★☆ | ✅ |
| `gpt-5-mini` | $0.25 | $2.00 | ⚡⚡⚡ 极快 | ★★★☆ | ✅ |
| `gemini-3-flash-preview` | $0.50 | $3.00 | ⚡⚡⚡ 快 | ★★★★ | ✅ |
| `gpt-5.1` | $1.25 | — | ⚡⚡ 中 | ★★★★ | ✅ |
| `gemini-2.5-pro` | $1.25 | $10.00 | ⚡⚡ 中 | ★★★★★ | ✅ |
| `gemini-3-pro-preview` | $2.00 | $12.00 | ⚡⚡ 中 | ★★★★★ | ✅ |
| `gpt-5.2` | $1.75 | $14.00 | ⚡ 慢 | ★★★★★ | ✅ |
| `claude-haiku-4-5-20251001` | $1.00 | $5.00 | ⚡⚡⚡ 快 | ★★★★ | ✅ |
| `claude-sonnet-4-20250514` | $3.00 | $15.00 | ⚡⚡ 中 | ★★★★★ | ✅ |
| `claude-opus-4-5-20251101` | $5.00 | $25.00 | ⚡ 慢 | ★★★★★+ | ✅ |

---

## 3. 场景分级 → 模型选型规则

### 🟢 FAST（快速轻量） — 结构化提取 / 简单分类

> 输入短、输出固定格式，追求**低延迟、低成本**。

| 典型场景 | 推荐模型 | Temperature |
|---|---|---|
| 自由文本 → 结构化 JSON 提取 | `gemini-2.5-flash` | 0.2 |
| 关键实体识别/命名实体提取 | `gpt-5-mini` | 0.2 |
| 简单评分/评估/打分 | `gemini-2.5-flash` | 0.3 |
| 意图分类/标签分类 | `gemini-2.5-flash` | 0.2 |

**选型理由**：Prompt 固定、输出为 JSON，不需要深度推理，用最便宜最快的模型。

---

### 🟡 MEDIUM（中等推理） — 对话 / 分析 / 报告

> 需要理解上下文、进行一定推理，但不需要顶级创造力。

| 典型场景 | 推荐模型 | Temperature |
|---|---|---|
| AI 对话（流式） | `gemini-3-flash-preview` | 0.5 |
| 报告/周报/摘要生成 | `gemini-3-flash-preview` | 0.5 |
| RAG 知识库问答 | `gemini-3-flash-preview` | 0.3 |
| 出题/测验 | `gemini-3-flash-preview` | 0.8 |
| 趋势分析/数据洞察 | `gemini-3-flash-preview` | 0.4 |

**选型理由**：需要多轮上下文理解，`gemini-3-flash-preview` 在速度与能力之间最佳平衡。

---

### 🔴 HEAVY（深度推理） — 策略生成 / 复杂分析

> 需要高质量输出、深度推理、复杂分析。

| 典型场景 | 推荐模型 | Temperature |
|---|---|---|
| 深度分析报告 | `gemini-2.5-pro` | 0.5 |
| 策略/方案建议 | `gemini-2.5-pro` | 0.5 |
| 高质量文案/邮件 | `gpt-5.1` | 0.6–0.7 |
| 复杂关系图谱推理 | `gemini-2.5-pro` | 0.3 |
| 风险预测/预判 | `gemini-2.5-pro` | 0.4 |

**选型理由**：核心价值输出，需要策略性思维和高质量文本，使用强推理模型。

---

### 🟣 VISION（多模态） — 图片/文档理解

| 典型场景 | 推荐模型 | Temperature |
|---|---|---|
| 图片 + 文字混合理解 | `gemini-2.5-flash` | 0.2 |
| 文档/截图 OCR + 解析 | `gemini-2.5-flash` | 0.2 |

**选型理由**：需要视觉理解，`gemini-2.5-flash` 支持多模态且成本低。

---

## 4. 代码接入方式

所有调用统一使用 OpenAI SDK，只需修改 `base_url` 和 `api_key`：

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.getenv("LITELLM_BASE_URL"),
    api_key=os.getenv("LITELLM_API_KEY"),  # 从 .env 读取，禁止硬编码
)

# 示例：快速场景
response = client.chat.completions.create(
    model="gemini-2.5-flash",       # 根据场景选择模型
    messages=[...],
    temperature=0.2,
)

# 示例：流式输出
stream = client.chat.completions.create(
    model="gemini-3-flash-preview",  # 对话场景
    messages=[...],
    temperature=0.5,
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content, end="")
```

---

## 5. 降级策略

当首选模型不可用时，按以下优先级自动降级：

| 等级 | 快速场景 | 中等场景 | 重度场景 |
|---|---|---|---|
| 首选 | `gemini-2.5-flash` | `gemini-3-flash-preview` | `gemini-2.5-pro` |
| 备选1 | `gpt-5-mini` | `claude-haiku-4-5-20251001` | `gpt-5.1` |
| 备选2 | `gemini-3-flash-preview` | `gpt-5.1` | `claude-sonnet-4-20250514` |

---

## 6. 成本控制原则

1. **能用 Flash 绝不用 Pro** — 简单任务永远选最便宜的模型
2. **按场景分级** — 每个 API 端点在代码中明确标注使用哪个等级的模型
3. **控制 max_tokens** — 快速场景限制 1024 tokens，中等场景 2048，重度场景 4096
4. **避免重复调用** — 结构化提取失败时先做本地校验，不要盲目重试
