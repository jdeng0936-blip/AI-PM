"""
app/services/kr_progress_extractor.py — 从日报自动提取 KR 进度

工作流(被 simulate.py 质检通过后调用):
  1. 查询该用户作为 owner 的所有 active KR
  2. 拉取这些 KR 所属 Objective 在 active 周期内
  3. 用 Gemini Flash 一次调用,让 LLM 判断这份日报里是否包含某些 KR 的进度更新
  4. 命中后:写入 kr_progress_logs + 更新 KR.current_value + 重算 Objective.progress

LLM 输出 JSON 数组,每元素形如:
  {
    "kr_id": "<uuid>",
    "new_value": 450,
    "confidence": 0.85,
    "evidence": "日报中提到『推理延迟从800ms降至450ms』"
  }
未识别到任何 KR 更新时返回 []。

容错:
- LLM 调用/解析失败 → 静默跳过(不影响日报主流程)
- new_value 类型不合法 → 跳过该条
- confidence < 0.6 阈值 → 自动跳过(避免误更新)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.daily_report import DailyReport
from app.models.okr import (
    KeyResult,
    KRProgressLog,
    KRProgressSource,
    Objective,
    OKRCycle,
    OKRStatus,
)
from app.services.llm_selector import LLMSelector

logger = logging.getLogger("aipm.kr_extractor")

# 仅当 LLM 自评置信度 ≥ 阈值时才执行进度更新
CONFIDENCE_THRESHOLD = 0.6


# ────────────────────────────────────────────────────────────────
# 主入口
# ────────────────────────────────────────────────────────────────


async def extract_and_update_kr_progress(
    db: AsyncSession,
    *,
    report: DailyReport,
    raw_text: str,
) -> list[dict[str, Any]]:
    """
    从一份刚提交且通过质检的日报中,尝试更新该用户名下 KR 的进度。

    返回:命中的更新列表(供日志/调试),失败/未命中时返回 []。
    """
    user_krs = await _fetch_active_krs_for_user(db, user_id=report.user_id, tenant_id=report.tenant_id)
    if not user_krs:
        return []

    try:
        candidates = await _ask_llm_for_kr_updates(raw_text, user_krs)
    except Exception:
        logger.exception("kr extraction LLM call failed")
        return []

    applied: list[dict[str, Any]] = []
    for cand in candidates:
        kr_id_raw = cand.get("kr_id")
        new_value = cand.get("new_value")
        confidence = float(cand.get("confidence", 0))
        evidence = cand.get("evidence") or ""

        if confidence < CONFIDENCE_THRESHOLD:
            logger.info(
                "skip low-confidence kr update: kr=%s conf=%.2f",
                kr_id_raw,
                confidence,
            )
            continue
        try:
            kr_uuid = UUID(kr_id_raw)
        except (TypeError, ValueError):
            continue
        try:
            # new_value 是 LLM JSON 输出的 Any;float() 接受 number|str|None,这里
            # try 内 TypeError 已兜底 None / dict 等异常类型
            new_val_f = float(new_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue

        kr = (
            await db.execute(
                select(KeyResult).where(
                    KeyResult.id == kr_uuid,
                    KeyResult.owner_id == report.user_id,
                    KeyResult.tenant_id == report.tenant_id,
                )
            )
        ).scalar_one_or_none()
        if not kr:
            # 安全约束:LLM 不能跨用户改 KR
            continue
        if abs(kr.current_value - new_val_f) < 1e-6:
            continue  # 无变化

        previous = kr.current_value
        kr.current_value = new_val_f
        kr.confidence = max(kr.confidence, confidence)

        log = KRProgressLog(
            kr_id=kr.id,
            report_id=report.id,
            previous_value=previous,
            new_value=new_val_f,
            source=KRProgressSource.ai_extracted,
            confidence=confidence,
            note=(evidence or "")[:500],
            created_by=report.user_id,
            tenant_id=report.tenant_id,
        )
        db.add(log)

        # 重算 Objective 进度
        await _recalc_objective_progress(db, kr.objective_id, report.tenant_id)

        applied.append(
            {
                "kr_id": str(kr.id),
                "kr_title": kr.title,
                "previous": previous,
                "new": new_val_f,
                "confidence": confidence,
                "evidence": evidence[:200],
            }
        )
        logger.info(
            "kr progress updated: %s %s→%s conf=%.2f",
            kr.title,
            previous,
            new_val_f,
            confidence,
        )

    # 上层 simulate.py 会统一 commit
    return applied


# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────


async def _fetch_active_krs_for_user(
    db: AsyncSession,
    user_id: UUID,
    tenant_id: str,
) -> list[KeyResult]:
    """返回该用户作为 owner、且所属周期/目标都 active 的 KR"""
    stmt = (
        select(KeyResult)
        .join(Objective, KeyResult.objective_id == Objective.id)
        .join(OKRCycle, Objective.cycle_id == OKRCycle.id)
        .where(
            KeyResult.owner_id == user_id,
            KeyResult.tenant_id == tenant_id,
            Objective.tenant_id == tenant_id,
            OKRCycle.tenant_id == tenant_id,
            Objective.status == OKRStatus.active,
            OKRCycle.status == OKRStatus.active,
        )
    )
    return list((await db.execute(stmt)).scalars().all())


async def _recalc_objective_progress(db: AsyncSession, objective_id: UUID, tenant_id: str) -> None:
    krs = (
        await db.execute(select(KeyResult).where(KeyResult.objective_id == objective_id, KeyResult.tenant_id == tenant_id))
    ).scalars().all()
    obj = (
        await db.execute(select(Objective).where(Objective.id == objective_id, Objective.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if obj and krs:
        obj.progress = round(sum(k.progress for k in krs) / len(krs), 1)


def _strip_json_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


async def _ask_llm_for_kr_updates(
    raw_text: str,
    krs: list[KeyResult],
) -> list[dict[str, Any]]:
    """让 LLM 从日报文本里抽取 KR 进度更新建议"""
    kr_brief = [
        {
            "kr_id": str(kr.id),
            "title": kr.title,
            "description": kr.description or "",
            "metric_type": kr.metric_type,
            "target_value": kr.target_value,
            "current_value": kr.current_value,
            "unit": kr.unit or "",
        }
        for kr in krs
    ]

    system_prompt = (
        "你是徽远成科技的 OKR 自动跟踪助手。"
        "你的唯一任务是:从员工日报中找出有明确数据更新的 KR,并给出新的 current_value。"
        "\n\n严格规则:"
        "\n1. 只有日报中明确提到具体数值/百分比/计数,且能与某个 KR 对应时,才返回该 KR"
        "\n2. 不要根据『感觉』『差不多』等模糊描述更新进度"
        "\n3. confidence 必须真实反映匹配强度(0.0-1.0)。模糊匹配 ≤ 0.5,精确匹配 ≥ 0.8"
        "\n4. evidence 必须引用日报原文片段"
        "\n5. 没有匹配时返回空数组 []"
        "\n\n返回严格 JSON 数组,例如:"
        '\n[{"kr_id":"...","new_value":75,"confidence":0.9,"evidence":"日报原文..."}]'
    )

    user_content = (
        f"【员工提交的日报】\n{raw_text}\n\n"
        f"【该员工当前关联的 KR 列表(JSON)】\n"
        f"{json.dumps(kr_brief, ensure_ascii=False, indent=2)}\n\n"
        "请返回 JSON 数组(无任何解释文字、无 markdown 代码块)。"
    )

    model_config = LLMSelector.get_model_for_task("kr_progress")
    payload = {
        "model": model_config["name"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": model_config.get("temperature", 0.2),
        "max_tokens": model_config.get("max_tokens", 1024),
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
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

    raw = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "[]"
    cleaned = _strip_json_fences(raw)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON content for KR extraction: %r", raw[:200])
        return []

    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


async def extract_and_update_kr_progress_safe(
    db: AsyncSession,
    *,
    report: DailyReport,
    raw_text: str,
) -> list[dict[str, Any]]:
    """主流程友好版本:任何异常都吞掉,返回空列表"""
    try:
        return await extract_and_update_kr_progress(db, report=report, raw_text=raw_text)
    except Exception:
        logger.exception("kr extraction outer failure")
        return []
