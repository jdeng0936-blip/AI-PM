"""
app/services/ai_engine.py — 大模型多模态处理引擎

调用内部 NewApi（底层为 Gemini 系列模型）。
将 raw_input_text + media_urls 合并为多模态 payload，
严格约束 AI 输出 JSON 格式，并通过 Pydantic V2 强校验。

⚠️ Rule 01-Stack-AI-Routing: 严禁硬编码物理模型名。
   所有模型选择通过 LLMSelector.get_model_for_task() 完成。
"""
import httpx
from app.config import settings
from app.schemas.report import AIParseResult
from app.services.llm_selector import LLMSelector

# ─────────────────────────────────────────────────────────────────────────────
# System Prompt — 严格对齐徽远成日报表所有字段
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
你现在是徽远成科技的"AI 项目经理"。
请解析用户发送的自然语言汇报及多模态佐证，进行逻辑质检，并输出纯 JSON（不含 markdown 代码块）。

【字段映射说明】
员工用企微汇报时，内容对应公司日报表的以下列，请逐一提取：
- tasks            → 今日任务
- acceptance_criteria → 验收标准
- support_needed   → 所需支持
- progress         → 完成进度（0-100 整数，若未提及则根据语义推算）
- reviewer         → 验收人（若未提及留 null）
- git_version      → 代码归档 Git 版本号（研发同学才有，否则留 null）
- blocker          → 核心卡点
- next_step        → 解决方案
- eta              → 预计解决时间（YYYY-MM-DD 格式，若未提及留 null）

【质检红线 — 违反任意一条则 pass_check 为 false】
1. progress < 100 且 blocker 为 null 或空字符串 → 必须要求说明卡点
2. 成果图片内容与文字进度明显矛盾 → 图文不符，拒绝通过
3. tasks 与 acceptance_criteria 完全不对应 → 提示补充验收标准
4. 汇报内容极度模糊（如"今天做了一些事"）→ 要求具体化

【输出 JSON Schema — 必须严格遵守，字段名不能改变】
{
  "parsed_content": {
    "tasks": "字符串",
    "acceptance_criteria": "字符串或null",
    "support_needed": "字符串或null",
    "progress": 整数0-100,
    "reviewer": "字符串或null",
    "git_version": "字符串或null",
    "blocker": "字符串或null",
    "next_step": "字符串或null",
    "eta": "YYYY-MM-DD 或 null"
  },
  "pass_check": true 或 false,
  "reject_reason": "若不通过，温和指出缺失细节；通过则为 null",
  "suggested_guidance": "若不通过，给出可直接复制修改的标准汇报模板；通过则为 null",
  "ai_score": 0到100的整数,
  "ai_comment": "50字内综合点评",
  "management_alert": "若存在跨部门卡点或严重滞后（≥3天），提取预警摘要；否则为 null"
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# 岗位差异化 Prompt 补充（白皮书：岗位日报模板差异）
# ─────────────────────────────────────────────────────────────────────────────
JOB_TITLE_PROMPT_SUFFIX: dict[str, str] = {
    "研发工程师": """
【岗位特别要求 — 研发】
- progress=100% 时必须填写 git_version（代码提交版本号）
- 评分加权：代码归档占 15%
""",
    "技术部长": """
【岗位特别要求 — 技术管理】
- 需汇报团队整体进度和资源协调情况
- 关注跨部门依赖和技术决策
""",
    "采购经理": """
【岗位特别要求 — 采购】
- 需关注供应商交期、到货状态
- 物料延迟自动触发风险（对应 ERP webhook）
- git_version 字段留 null
""",
    "仓管": """
【岗位特别要求 — 仓储】
- 需汇报入库/出库数量和异常
- 关注物料匹配和库存预警
- git_version 字段留 null
""",
    "项目经理": """
【岗位特别要求 — 项目管理】
- 需汇报里程碑进展和风险评估
- 关注团队成员卡点汇总
- 评分加权：协作指标占 20%
""",
}


def _get_prompt_for_job(job_title: str) -> str:
    """根据岗位返回定制化 System Prompt"""
    suffix = ""
    for key, val in JOB_TITLE_PROMPT_SUFFIX.items():
        if key in job_title:
            suffix = val
            break
    return SYSTEM_PROMPT + suffix


async def parse_report_with_ai(
    raw_text: str,
    media_urls: list[str],
    job_title: str = "",
) -> tuple[AIParseResult, int, int]:
    """
    调用 NewApi 解析员工日报（支持文字 + 图片多模态）。

    Returns:
        (AIParseResult, prompt_tokens, completion_tokens)
    """
    # 通过 LLMSelector 获取模型配置（Rule 01-Stack-AI-Routing）
    model_config = LLMSelector.get_model_for_task("report_parse")

    # 构建多模态消息体
    content_parts: list[dict] = [
        {"type": "text", "text": f"员工汇报内容：\n\n{raw_text}"}
    ]

    # 添加图片（Gemini 支持公开 URL 直接引用）
    for url in media_urls:
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "high"},
        })

    payload = {
        "model": model_config["name"],
        "messages": [
            {"role": "system", "content": _get_prompt_for_job(job_title)},
            {"role": "user",   "content": content_parts},
        ],
        "response_format": {"type": "json_object"},
        "temperature": model_config.get("temperature", 0.1),
        "max_tokens": model_config.get("max_tokens", 1024),
    }

    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            f"{settings.new_api_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.new_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    raw_json: str = data["choices"][0]["message"]["content"]
    usage: dict = data.get("usage", {})

    # Pydantic V2 强校验 — 任何字段缺失或类型错误都会抛出 ValidationError
    result = AIParseResult.model_validate_json(raw_json)

    return (
        result,
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
    )


async def generate_morning_briefing(reports_summary: str) -> str:
    """
    生成管理层晨报摘要（可选功能）。
    输入：所有员工今日报告的文本汇总。
    输出：Markdown 格式的管理层晨报。
    """
    # 通过 LLMSelector 获取模型配置（Rule 01-Stack-AI-Routing）
    model_config = LLMSelector.get_model_for_task("morning_briefing")

    payload = {
        "model": model_config["name"],
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是徽远成科技管理层助理。根据以下员工日报数据，"
                    "生成一份简洁的管理层晨报摘要，包含：总体进展、主要卡点、需关注人员。"
                    "使用 Markdown 格式，控制在 300 字以内。"
                ),
            },
            {"role": "user", "content": reports_summary},
        ],
        "temperature": model_config.get("temperature", 0.3),
        "max_tokens": model_config.get("max_tokens", 600),
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.new_api_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.new_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
