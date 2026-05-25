"""
app/services/ai_engine_mock.py — 本地降级解析(无 LiteLLM/NewApi 时使用)

定位:
  - parse_report_with_ai 在 NEW_API_KEY 未配置或 LLM 调用失败时降级到这里
  - 不调任何外部 API,纯 Python heuristic 提取关键信号
  - 输出严格符合 AIParseResult Pydantic 契约,与真实 LLM 路径无差异
  - 评分规则对齐 ai_engine.py 的 SYSTEM_PROMPT(简化版)

设计原则:
  - 保证 pass_check 行为基本合理(短/空文本会被 reject)
  - 不假装"AI 真的懂",ai_comment 显式标 [Mock] 前缀,demo 时一眼能识别
  - blocker 检测足够触发 risk_alerts 链路,验证完整管道
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from app.schemas.report import AIParseResult, ParsedContent

# ─── 信号识别 heuristic ─────────────────────────────────────────────

_REPORT_TYPE_PATTERNS = {
    "晨规划": ("[晨规划]", "晨规划", "今日计划", "今日打算", "计划做", "打算做"),
    "晚复盘": ("[晚复盘]", "晚复盘", "晚复核", "复盘", "反思", "教训"),
    "日报": ("[日报]", "今日完成", "已交付", "今天完成", "今日工作"),
}

_PROGRESS_RE = re.compile(r"(?:进度|完成|推进到?|做到了?)\s*[:为是到\s]*?(\d{1,3})\s*%?")

_BLOCKER_KWS = (
    "卡点",
    "卡住",
    "卡在",
    "阻塞",
    "blocker",
    "影响",
    "延迟",
    "无法",
    "等待",
    "等 ",
    "故障",
    "异常",
)


def _detect_report_type(text: str) -> str:
    for t, kws in _REPORT_TYPE_PATTERNS.items():
        if any(k in text for k in kws):
            return t
    return "日报"


def _detect_progress(text: str) -> int:
    """优先抓 '完成 80%'/'进度 70%' 数字;退化用关键词推断;最差给 60。"""
    m = _PROGRESS_RE.search(text)
    if m:
        return max(0, min(100, int(m.group(1))))
    if any(k in text for k in ("完成", "已交付", "完工", "已上线")):
        return 90
    if any(k in text for k in ("刚启动", "刚开始", "刚")):
        return 20
    if any(k in text for k in ("卡住", "阻塞", "等待")):
        return 40
    return 60


def _detect_blocker(text: str) -> str | None:
    """行级关键词扫描,返回首条命中的整行(截断 200 字)。"""
    for line in text.split("\n"):
        if any(kw in line for kw in _BLOCKER_KWS):
            return line.strip()[:200] or None
    return None


def _score(text: str, parsed: ParsedContent) -> int:
    """对齐 ai_engine.py SYSTEM_PROMPT 累加评分制(简化)。"""
    score = 50
    if len(parsed.tasks) > 50:
        score += 10
    if parsed.acceptance_criteria:
        score += 8
    score += 5  # progress 字段一定有(非空)
    if parsed.deliverable:
        score += 5
    if parsed.git_version:
        score += 5
    if parsed.blocker:
        score += 5
    if parsed.next_step:
        score += 5
    if re.search(r"\d", text):
        score += 3
    if len(text) > 200:
        score += 4

    # 扣分项
    if parsed.progress < 100 and not parsed.blocker:
        score -= 10
    if "今天做了一些事" in text or len(text.strip()) < 20:
        score -= 15

    return max(0, min(100, score))


# ─── 主入口 ─────────────────────────────────────────────────────────


async def mock_parse_report(
    raw_text: str,
    media_urls: list[str],
) -> tuple[AIParseResult, int, int]:
    """无 LLM API 时的本地 mock 解析。

    Returns:
        (AIParseResult, prompt_tokens=0, completion_tokens=0)
        prompt/completion tokens 固定为 0,因为没有真实 LLM 调用,
        token_guard 不会因 mock 累计配额。
    """
    text = (raw_text or "").strip()

    rtype = _detect_report_type(text)

    # tasks:取首段(最多 300 字);空文本兜底
    first_para = re.split(r"\n\n+", text)[0] if text else ""
    tasks = first_para[:300] if first_para else (text[:300] or "(空)")

    progress = _detect_progress(text)
    blocker = _detect_blocker(text)

    parsed = ParsedContent(
        report_type=rtype,
        tasks=tasks,
        acceptance_criteria=None,
        support_needed=None,
        progress=progress,
        deliverable=None,
        reviewer=None,
        git_version=None,
        blocker=blocker,
        next_step=None,
        # 有卡点时给一个 3 天后的兜底 ETA,让 risk_alert 链路有数据
        eta=(date.today() + timedelta(days=3)) if blocker else None,
    )

    ai_score = _score(text, parsed)
    pass_check = ai_score >= 60

    if pass_check:
        ai_comment = (
            f"[Mock] {rtype} 已接收,进度 {progress}%。"
            + ("有卡点提醒,已转给管理层。" if blocker else "无卡点。")
            + "建议下次补充验收标准与交付物描述。"
        )
        reject_reason = None
        suggested_guidance = None
    else:
        ai_comment = f"[Mock] {rtype} 信息量不足({ai_score} 分),建议补充任务细节与进度。"
        reject_reason = "内容过短或缺少关键信息(任务描述、进度、卡点)"
        suggested_guidance = (
            "建议格式:\n"
            "【今日任务】具体做了/打算做什么\n"
            "【完成进度】当前 X% / 预计推进到 Y%\n"
            "【卡点】如有,描述当前阻塞\n"
            "【下一步】解决方案或下一步动作"
        )

    management_alert = f"[Mock] 检测到潜在卡点:{blocker[:100]}" if blocker and pass_check else None

    return (
        AIParseResult(
            parsed_content=parsed,
            pass_check=pass_check,
            reject_reason=reject_reason,
            suggested_guidance=suggested_guidance,
            ai_score=ai_score,
            ai_comment=ai_comment[:200],
            management_alert=management_alert,
        ),
        0,
        0,
    )
