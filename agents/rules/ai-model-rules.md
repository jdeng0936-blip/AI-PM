---
trigger: always_on
---

# 🧠 AI 大模型调用规则（AI_MODEL_RULES）

> 本文档定义了项目中所有大模型调用的统一规范。  
> 所有 AI 模块必须通过 LiteLLM 网关路由，根据场景选择最合适的模型。  
> **配套文件**：整体架构规约见 [ARCHITECTURE_RULES.md](./ARCHITECTURE_RULES.md)

> ⚠️ 与 ARCHITECTURE_RULES.md 的关系说明：  
> - ARCHITECTURE_RULES 中的「GlobalLLMRouter 5级回退」是**服务可用性**保障（某个模型挂了才切换）  
> - 本文档的「场景→模型映射」是**主动选型规则**（根据任务类型选最合适的模型）  
> - 两者并不冲突：先按本文档选型，若该模型不可用再走 ARCHITECTURE_RULES 的回退链

---

## 1. 网关配置

| 配置项 | 值 |
|---|---|
| **Base URL** | `https://litellm.ailingxi.online` |
| **API Key** | `sk-FH8c57sfBpvy70CEfAkUcg`（测试用，生产环境改用 `.env` 变量）|
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

## 3. 场景 → 模型映射规则

### 🟢 FAST（快速轻量） — 简单录入 / 结构化提取

> 这类任务输入短、输出固定格式，追求**低延迟、低成本**。

| 场景 | 对应功能 | 推荐模型 | Temperature |
|---|---|---|---|
| 情报结构化录入 | `parse_visit_log()` | `gemini-2.5-flash` | 0.2 |
| 关键人提取 | `extract_stakeholders` | `gpt-5-mini` | 0.2 |
| 回答评估/评分 | `critique_answer()` | `gemini-2.5-flash` | 0.3 |

**选型理由**：这些场景的 Prompt 固定、输出为 JSON，不需要深度推理。使用最便宜最快的模型即可。

---

### 🟡 MEDIUM（中等推理） — 对话 / 分析 / 报告

> 这类任务需要理解上下文、进行一定推理，但不需要顶级创造力。

| 场景 | 对应功能 | 推荐模型 | Temperature |
|---|---|---|---|
| AI 参谋对话（流式） | `chat_with_project_stream()` | `gemini-3-flash-preview` | 0.5 |
| 记忆增强对话（流式） | `chat_with_memory_stream()` | `gemini-3-flash-preview` | 0.5 |
| 伴学出题 | `generate_quiz()` | `gemini-3-flash-preview` | 0.8 |
| 团队体检报告 | `generate_team_report()` | `gemini-3-flash-preview` | 0.5 |
| RAG 知识库问答 | `generate_rag_answer_stream()` | `gemini-3-flash-preview` | 0.3 |
| 战术护目镜 | `generate_tactical_advice()` | `gemini-3-flash-preview` | 0.4 |

**选型理由**：需要理解多轮上下文和项目情报，但对推理深度要求适中。`gemini-3-flash-preview` 在速度与能力之间取得最佳平衡。

---

### 🔴 HEAVY（深度推理） — 策略生成 / 高质量文案

> 这类任务需要高质量输出、深度推理、复杂博弈分析。

| 场景 | 对应功能 | 推荐模型 | Temperature |
|---|---|---|---|
| NBA 报告生成 | `generate_nba` | `gemini-2.5-pro` | 0.5 |
| 商务跟进邮件 | `generate_followup_email()` | `gemini-2.5-pro` | 0.6 |
| 微信跟进话术 | `generate_followup_email(wechat)` | `gpt-5.1` | 0.7 |
| 技术方案摘要 | `generate_tech_summary()` | `gemini-2.5-pro` | 0.5 |
| 内线弹药生成 | `generate_insider_ammo()` | `gpt-5.1` | 0.75 |
| 沙盘话术（全类型） | `generate_sales_pitch()` | `gemini-2.5-pro` | 0.4–0.7 |
| 权力关系图谱 | `generate_power_map` | `gemini-2.5-pro` | 0.3 |

**选型理由**：这些场景是系统的核心价值输出，需要策略性思维和高质量文本。使用更强的推理模型确保输出质量。

---

### 🟣 VISION（多模态） — 图片理解

| 场景 | 对应功能 | 推荐模型 | Temperature |
|---|---|---|---|
| 图片+文字情报解析 | `parse_visit_log_with_image()` | `gemini-2.5-flash` | 0.2 |

**选型理由**：需要视觉理解能力，`gemini-2.5-flash` 支持多模态且成本低。

---

## 4. 代码接入方式

所有调用统一使用 OpenAI SDK，只需修改 `base_url` 和 `api_key`：

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url=os.getenv("LITELLM_BASE_URL", "https://litellm.ailingxi.online/v1"),
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
