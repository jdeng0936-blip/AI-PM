from __future__ import annotations
"""
app/services/ai_engine_mock.py — Mock AI 解析引擎（开发环境）

不调用真实 API，基于关键词规则生成合理的 AI 解析结果。
输出格式与真实 AI 引擎 100% 一致（AIParseResult）。

对齐 Excel 日报表 12 列字段：
  今日任务 / 验收标准 / 所需支持 / 完成进度 / 成果演示 /
  验收人 / Git版本号 / 核心卡点 / 解决方案 / 预计解决时间
"""
import re
from datetime import date
from app.schemas.report import AIParseResult, ParsedContent


def _extract_section(text: str, *keywords: str) -> str | None:
    """提取【关键词】后面的内容，直到下一个【或文本结束"""
    for kw in keywords:
        patterns = [
            rf'【{kw}】[：:\s]*(.+?)(?=【|$)',
            rf'{kw}[：:]\s*(.+?)(?:\n\n|\n【|$)',
        ]
        for p in patterns:
            m = re.search(p, text, re.DOTALL)
            if m:
                return m.group(1).strip()
    return None


def _extract_progress(text: str) -> int:
    """从文本中提取进度数字"""
    m = re.search(r'(\d{1,3})\s*%', text)
    if m:
        return min(int(m.group(1)), 100)
    # 关键词推算
    if any(k in text for k in ['完成', '搞定', '交付', '上线', '通过']):
        return 90
    if any(k in text for k in ['进行中', '开发中', '联调']):
        return 60
    if any(k in text for k in ['开始', '启动', '需求']):
        return 20
    return 50


def _extract_blocker(text: str) -> str | None:
    """提取卡点"""
    # 优先从结构化格式提取
    section = _extract_section(text, '核心卡点', '卡点', '阻塞项', '遇到问题')
    if section and section not in ('无', '暂无', 'N/A', '无阻塞'):
        return section
    # 正则兜底
    patterns = [
        r'(?:阻塞|blocked|卡住|等待)[：:]*\s*(.+?)(?:\n|$)',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_git_version(text: str) -> str | None:
    """提取 Git 版本号"""
    section = _extract_section(text, 'Git版本号', 'Git版本', 'Git', 'git', '代码版本')
    if section:
        return section
    # 正则匹配常见 commit hash 或 tag
    m = re.search(r'\b([a-f0-9]{7,40})\b', text)
    if m:
        return m.group(1)
    m = re.search(r'v\d+\.\d+[\.\d]*', text)
    if m:
        return m.group(0)
    return None


def _extract_reviewer(text: str) -> str | None:
    """提取验收人"""
    section = _extract_section(text, '验收人', '审核人')
    if section:
        return section
    return None


def _extract_eta(text: str) -> date | None:
    """提取预计解决时间"""
    section = _extract_section(text, '预计解决时间', '预计完成', 'ETA')
    if section:
        m = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', section)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
    return None


def _score_report(text: str, progress: int, blocker: str | None,
                  acceptance: str | None, git: str | None,
                  deliverable: str | None) -> int:
    """根据内容质量评分 — 对齐 Excel 完整性要求"""
    score = 50  # 基础分

    # 内容长度
    if len(text) > 100:
        score += 5
    if len(text) > 200:
        score += 5

    # 结构化字段完整度
    if acceptance:
        score += 8  # 有验收标准 → 高分
    if deliverable:
        score += 5  # 有成果演示
    if git:
        score += 5  # 有 Git 版本
    if re.search(r'\d', text):
        score += 3  # 有量化数据

    # 进度
    if progress >= 80:
        score += 10
    elif progress >= 50:
        score += 5
    elif progress < 30 and not blocker:
        score -= 10

    # 卡点有说明 → 加分
    if blocker and len(blocker) > 10:
        score += 5

    return max(0, min(100, score))


async def mock_parse_report(
    raw_text: str,
    media_urls: list[str] | None = None,
) -> tuple[AIParseResult, int, int]:
    """
    Mock AI 解析 — 返回格式与 parse_report_with_ai() 完全一致。
    对齐 Excel 日报表全部 12 列字段。
    Returns: (AIParseResult, prompt_tokens, completion_tokens)
    """
    # ── 结构化提取 ──
    tasks = _extract_section(raw_text, '今日任务', '今日完成', '今日工作', '工作内容')
    if not tasks:
        lines = [l.strip() for l in raw_text.strip().split('\n') if l.strip()]
        tasks = lines[0] if lines else raw_text[:100]

    acceptance = _extract_section(raw_text, '验收标准', '验收条件', 'AC')
    support = _extract_section(raw_text, '所需支持', '需要支持', '需要协助')
    progress = _extract_progress(raw_text)
    deliverable = _extract_section(raw_text, '成果演示', '交付物', '演示', '产出')
    reviewer = _extract_reviewer(raw_text)
    git = _extract_git_version(raw_text)
    blocker = _extract_blocker(raw_text)
    solution = _extract_section(raw_text, '解决方案', '应对方案', '解决办法', '下一步')
    eta = _extract_eta(raw_text)

    # ── 评分 ──
    score = _score_report(raw_text, progress, blocker, acceptance, git, deliverable)

    # ── 质检判断 ──
    pass_check = True
    reject_reason = None
    suggested_guidance = None

    if len(raw_text.strip()) < 15:
        pass_check = False
        reject_reason = "日报内容过于简短，无法评估实际工作进展"
        suggested_guidance = (
            "标准模板：\n"
            "【今日任务】具体任务描述\n"
            "【验收标准】可量化的完成标志\n"
            "【完成进度】XX%\n"
            "【成果演示】可展示的交付物\n"
            "【核心卡点】如有\n"
            "【解决方案】针对卡点的方案"
        )
        score = max(score, 30)

    elif score < 60:
        pass_check = False
        # 计算还差多少分
        gap = 60 - score
        # 核心不足（描述太简短是最常见原因）
        core_issues = []
        if len(raw_text.strip()) < 80:
            core_issues.append('描述不够详细（建议50字以上，说清做了什么、怎么做的）')
        if progress == 50:  # 默认值，说明没有明确提及进度
            core_issues.append('未提及具体进度（如"完成80%"或"刚启动20%"）')
        
        # 加分建议（非必填，但可以帮助达标）
        bonus_tips = []
        if not acceptance:
            bonus_tips.append("验收标准（+8分）：什么条件算完成")
        if not deliverable:
            bonus_tips.append("成果/交付物（+5分）：可展示的产出")
        if not git:
            bonus_tips.append("Git版本号（+5分）：如有代码提交")
        
        if core_issues:
            reject_reason = f"评分 {score} 分（差 {gap} 分达标），主要问题：{'；'.join(core_issues)}"
        else:
            reject_reason = f"评分 {score} 分（差 {gap} 分达标），信息量不足"
        
        suggested_guidance = "📌 快速达标方法（补充任意几项即可，无需全部填写）：\n"
        if len(raw_text.strip()) < 80:
            suggested_guidance += "• 【核心】把工作内容描述得更具体（做了什么、用了什么方法、结果如何）\n"
        if progress == 50:
            suggested_guidance += '• 【核心】补充明确进度数字，如"进度80%"\n'
        if bonus_tips:
            suggested_guidance += "• 以下为加分项（非必填）：\n"
            for tip in bonus_tips:
                suggested_guidance += f"  - {tip}\n"
        suggested_guidance += "💡 提示：Git版本号仅适用于有代码提交的项目，非研发岗位可忽略"

    # 注意：progress < 50 且无卡点的情况已在评分中扣分（score -= 10），
    # 不再作为独立的驳回条件，避免与评分逻辑冲突。

    # ── 管理层预警 ──
    management_alert = None
    if blocker and any(k in raw_text for k in ['跨部门', '等待', '延期', '急需']):
        management_alert = f"⚠️ 跨部门卡点预警：{blocker}"
    elif progress < 30 and blocker:
        management_alert = f"⚠️ 严重滞后预警：进度仅 {progress}%，卡点：{blocker}"

    # ── AI 评语 ──
    if score >= 90:
        ai_comment = "工作推进有力，进展明确，文档齐全，验收标准清晰。"
    elif score >= 75:
        ai_comment = "整体表现良好，任务关键信息完整。"
    elif score >= 60:
        ai_comment = "基本合格，建议补充验收标准和成果演示。"
    else:
        ai_comment = "日报信息不足，请按模板补充验收标准、进度、成果物。"

    # ── 所需支持 fallback（从卡点推断）──
    if not support and blocker and '需要' in raw_text:
        support = blocker

    # ── 汇报类型识别 ──
    report_type = "日报"
    if any(k in raw_text for k in ['晨规划', '计划', '目标', '预期', '打算']):
        report_type = "晨规划"
    elif any(k in raw_text for k in ['总结', '复盘', '反思', '教训']):
        report_type = "晚复盘"

    parsed = ParsedContent(
        report_type=report_type,
        tasks=tasks,
        acceptance_criteria=acceptance,
        support_needed=support,
        progress=progress,
        deliverable=deliverable,
        reviewer=reviewer,
        git_version=git,
        blocker=blocker,
        next_step=solution,
        eta=eta,
    )

    result = AIParseResult(
        parsed_content=parsed,
        pass_check=pass_check,
        reject_reason=reject_reason,
        suggested_guidance=suggested_guidance,
        ai_score=score,
        ai_comment=ai_comment,
        management_alert=management_alert,
    )

    # 模拟 Token 用量
    p_tokens = len(raw_text) * 2
    c_tokens = 350

    return result, p_tokens, c_tokens
