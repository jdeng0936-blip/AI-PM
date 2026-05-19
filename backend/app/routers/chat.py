"""
app/routers/chat.py — 总经理 AI 对话查询(Function Calling 多轮编排)

工作流:
  Step 0: 用户提问 → 拼装 system + user 消息
  Step 1: LLM 决策:回答 or 调用 Tool
  Step 2: 若 Tool 调用,执行 → 把结果以 tool message 喂回 LLM → 回到 Step 1
  Step 3: LLM 给出最终自然语言回答 + 引用源

设计要点:
- 最多 5 轮 Tool 调用,防止 LLM 无限循环
- 所有 Tool 失败都返回 {"error": ...} 而不是抛异常,LLM 自主决策
- 记录每次调用 trace(tool_name + args + result_summary),前端可展开"思考过程"
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.rbac import require_role
from app.models.user import UserRole
from app.services.chat_tools import registry
from app.services.llm_selector import LLMSelector

router = APIRouter(prefix="/api/v1/chat", tags=["Admin AI Chat"])

logger = logging.getLogger("aipm.chat")

_admin_only = require_role(UserRole.admin)

MAX_TOOL_ROUNDS = 5


SYSTEM_PROMPT = """你是徽远成科技的 AI 战情助手,服务总经理(admin 角色)。

【你的能力】
- 你拥有一组业务数据查询 Tool,可以查询日报、风险预警、项目状态、人员表现等
- 你必须通过 Tool 获取数据,严禁凭印象编造数字/姓名/项目名

【回答规则】
1. 优先用最匹配的 Tool 取数据,需要多维度信息时可连续调用多个 Tool
2. 拿到数据后用简洁的中文回答总经理,关键数字用粗体或列表呈现
3. 答案末尾用一行『📊 数据来源: 调用了 X 次 Tool,基于 Y 条记录』标注引用
4. 数据不足时坦诚说明,不要假装知道
5. 时间相关问题默认窗口是「近 7 天」,除非用户明确指定

【风格】
- 简洁专业,像给 CEO 汇报
- 避免冗长,关键结论先行,细节按需补充
- 中文回答
"""


# ────────────────────────────────────────────────────────────────
# Schemas
# ────────────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    # 可选:限定本次对话只暴露这些 tool(测试/隔离用)
    allowed_tools: Optional[list[str]] = None


class ToolCallTrace(BaseModel):
    tool: str
    arguments: dict[str, Any]
    result_preview: str
    error: Optional[str] = None


class ChatResponse(BaseModel):
    question: str
    answer: str
    tool_calls: list[ToolCallTrace] = []
    rounds: int
    model: str


# ────────────────────────────────────────────────────────────────
# LLM 调用
# ────────────────────────────────────────────────────────────────


async def _call_llm(
    *,
    model_config: dict[str, Any],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    timeout: float = 90.0,
) -> dict[str, Any]:
    """单次调用 LLM,返回完整 response.message 对象(含可能的 tool_calls)"""
    payload = {
        "model": model_config["name"],
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": model_config.get("temperature", 0.3),
        "max_tokens": model_config.get("max_tokens", 2048),
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
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
    return data["choices"][0]["message"]


def _result_preview(result: dict[str, Any], max_len: int = 280) -> str:
    """把 tool 结果压缩为单行预览,供前端展示"""
    try:
        text = json.dumps(result, ensure_ascii=False, default=str)
    except Exception:
        text = str(result)
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


# ────────────────────────────────────────────────────────────────
# Endpoint
# ────────────────────────────────────────────────────────────────


@router.get("/tools")
async def list_tools(_user=Depends(_admin_only)) -> dict:
    """暴露当前所有可用 Tool 列表(管理员调试用)"""
    return {
        "count": len(registry.all()),
        "tools": [
            {"name": t.name, "description": t.description}
            for t in registry.all()
        ],
    }


class WeeklyReportRequest(BaseModel):
    scope: str = Field(default="last_week", description="last_week | this_week")


@router.post("/weekly-report")
async def trigger_weekly_report(
    req: WeeklyReportRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    """手工触发周报生成(管理员从前端按钮调用,不走 LLM tool calling)"""
    from app.services.chat_tools.weekly_report import generate_weekly_report
    result = await generate_weekly_report(db, scope=req.scope)
    return result


@router.post("/ask", response_model=ChatResponse)
async def admin_ai_chat(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _user=Depends(_admin_only),
):
    """总经理自然语言对话查询(基于 Function Calling)"""
    question = req.question.strip()
    model_config = LLMSelector.get_model_for_task("admin_chat")

    tools = registry.openai_schemas(only=req.allowed_tools)
    if not tools:
        raise HTTPException(503, "未注册任何对话 Tool")

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    traces: list[ToolCallTrace] = []
    final_answer: str = ""

    for round_idx in range(MAX_TOOL_ROUNDS):
        try:
            assistant_msg = await _call_llm(
                model_config=model_config, messages=messages, tools=tools,
            )
        except httpx.HTTPError as exc:
            logger.exception("LLM call failed at round %d", round_idx)
            raise HTTPException(502, f"LLM 调用失败: {exc}")

        tool_calls = assistant_msg.get("tool_calls") or []

        # LLM 给出了最终答案 → 收尾
        if not tool_calls:
            final_answer = assistant_msg.get("content") or ""
            break

        # 把 assistant 消息(含 tool_calls)塞回历史
        messages.append(
            {
                "role": "assistant",
                "content": assistant_msg.get("content") or "",
                "tool_calls": tool_calls,
            }
        )

        # 逐个执行 tool_calls
        for tc in tool_calls:
            tc_id = tc.get("id") or ""
            fn = tc.get("function") or {}
            tool_name = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {}

            result = await registry.dispatch(tool_name, db, args)
            traces.append(
                ToolCallTrace(
                    tool=tool_name,
                    arguments=args,
                    result_preview=_result_preview(result),
                    error=result.get("error") if isinstance(result, dict) else None,
                )
            )

            # 喂回 tool message
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "name": tool_name,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
    else:
        # 5 轮内未收敛 → 强制让 LLM 总结
        messages.append(
            {
                "role": "user",
                "content": "已达到工具调用上限,请基于现有信息直接给出最终回答,不要再调用工具。",
            }
        )
        try:
            final_msg = await _call_llm(
                model_config=model_config, messages=messages, tools=[],
            )
            final_answer = final_msg.get("content") or "无法在限定轮数内得到答案。"
        except Exception:
            final_answer = "AI 在限定轮数内未能完成查询。"

    return ChatResponse(
        question=question,
        answer=final_answer.strip(),
        tool_calls=traces,
        rounds=len(traces) and (round_idx + 1) or 1,
        model=model_config["name"],
    )
