from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
from statistics import mean
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.daily_report import DailyReport
from app.models.risk_alert import RiskAlert
from app.models.user import User
from app.services.export import _ensure_font


@dataclass(frozen=True, slots=True)
class ScoreReportRow:
    report: DailyReport
    user_name: str
    department: str


@dataclass(frozen=True, slots=True)
class RiskDetailRow:
    report_date: date
    user_name: str
    department: str
    status: str
    days_unresolved: int
    description: str


async def build_scores_pdf(
    db: AsyncSession, *, month: str, department: str | None = None, tenant_id: str = "default"
) -> BytesIO:
    font_name = _ensure_font()
    start_date, end_date_exclusive = _month_range(month)
    rows = await _fetch_score_rows(
        db, start_date=start_date, end_date_exclusive=end_date_exclusive, department=department, tenant_id=tenant_id
    )
    risk_rows = await _fetch_risk_rows(
        db,
        start_date=start_date,
        end_date_exclusive=end_date_exclusive,
        department=department,
        tenant_id=tenant_id,
    )
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"评分报告_{month}",
    )
    styles = _build_styles(font_name)
    story: list[Any] = []

    period_label = f"{start_date} 至 {end_date_exclusive - timedelta(days=1)}"
    scope_label = department or "全公司"
    story.extend(
        [
            Paragraph("月度评分报告", styles["title"]),
            Spacer(1, 12),
            Paragraph(f"期间: {period_label}", styles["center"]),
            Paragraph(f"部门: {scope_label}", styles["center"]),
            Paragraph(f"生成时间: {generated_at}", styles["center"]),
            Spacer(1, 24),
        ]
    )

    metrics = _build_metrics(rows, risk_rows)
    story.append(_build_metric_cards(metrics, font_name))
    story.append(Spacer(1, 18))
    story.append(Paragraph("部门评分对比", styles["heading"]))
    story.append(_build_department_table(rows, font_name))
    story.append(Spacer(1, 18))
    story.append(Paragraph("员工评分排行", styles["heading"]))
    story.append(_build_employee_rank_tables(rows, font_name))
    story.append(PageBreak())
    story.append(Paragraph("风险预警明细", styles["heading"]))
    story.append(_build_risk_table(risk_rows, font_name, styles["small"]))

    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: _NumberedCanvas(
            *args,
            generated_at=generated_at,
            font_name=font_name,
            **kwargs,
        ),
    )
    output.seek(0)
    return output


async def _fetch_score_rows(
    db: AsyncSession,
    *,
    start_date: date,
    end_date_exclusive: date,
    department: str | None,
    tenant_id: str,
) -> list[ScoreReportRow]:
    conditions = [
        DailyReport.report_date >= start_date,
        DailyReport.report_date < end_date_exclusive,
        DailyReport.tenant_id == tenant_id,
        User.tenant_id == tenant_id,
        DailyReport.deleted_at.is_(None),
    ]
    if department:
        conditions.append(User.department == department)

    stmt = (
        select(DailyReport, User.name, User.department)
        .join(User, DailyReport.user_id == User.id)
        .where(and_(*conditions))
        .order_by(DailyReport.ai_score.desc(), DailyReport.report_date.desc())
    )
    result = await db.execute(stmt)
    return [
        ScoreReportRow(report=report, user_name=user_name, department=user_department or "未分配")
        for report, user_name, user_department in result.all()
    ]


async def _fetch_risk_rows(
    db: AsyncSession,
    *,
    start_date: date,
    end_date_exclusive: date,
    department: str | None,
    tenant_id: str,
) -> list[RiskDetailRow]:
    conditions = [
        DailyReport.report_date >= start_date,
        DailyReport.report_date < end_date_exclusive,
        DailyReport.tenant_id == tenant_id,
        RiskAlert.tenant_id == tenant_id,
        User.tenant_id == tenant_id,
        DailyReport.deleted_at.is_(None),
        RiskAlert.deleted_at.is_(None),
        RiskAlert.status.in_(["unresolved", "escalated"]),
    ]
    if department:
        conditions.append(User.department == department)

    stmt = (
        select(RiskAlert, DailyReport.report_date, User.name, User.department)
        .join(DailyReport, RiskAlert.report_id == DailyReport.id)
        .join(User, RiskAlert.user_id == User.id)
        .where(and_(*conditions))
        .order_by(RiskAlert.days_unresolved.desc(), RiskAlert.created_at.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    return [
        RiskDetailRow(
            report_date=report_date,
            user_name=user_name,
            department=user_department or "未分配",
            status=risk.status,
            days_unresolved=risk.days_unresolved or 0,
            description=risk.description,
        )
        for risk, report_date, user_name, user_department in result.all()
    ]


def _build_metrics(rows: list[ScoreReportRow], risk_rows: list[RiskDetailRow]) -> list[tuple[str, str]]:
    scores = [row.report.ai_score for row in rows if row.report.ai_score is not None]
    checked = [row.report.pass_check for row in rows if row.report.pass_check is not None]
    pass_count = sum(1 for value in checked if value is True)
    return [
        ("提交人数", str(len({row.report.user_id for row in rows}))),
        ("平均分", f"{round(mean(scores), 1) if scores else 0.0}"),
        ("合格率", f"{_percentage(pass_count, len(checked))}%"),
        ("卡点未解决数", str(len(risk_rows))),
    ]


def _build_department_table(rows: list[ScoreReportRow], font_name: str) -> Table:
    grouped: dict[str, list[ScoreReportRow]] = defaultdict(list)
    for row in rows:
        grouped[row.department].append(row)

    data: list[list[Any]] = [["部门", "提交人数", "日报数", "平均分", "合格率", "卡点数"]]
    for department, dept_rows in sorted(grouped.items()):
        scores = [row.report.ai_score for row in dept_rows if row.report.ai_score is not None]
        checked = [row.report.pass_check for row in dept_rows if row.report.pass_check is not None]
        pass_count = sum(1 for value in checked if value is True)
        data.append(
            [
                department,
                len({row.report.user_id for row in dept_rows}),
                len(dept_rows),
                round(mean(scores), 1) if scores else 0.0,
                f"{_percentage(pass_count, len(checked))}%",
                sum(1 for row in dept_rows if _has_blocker(row.report.parsed_content)),
            ]
        )

    if len(data) == 1:
        data.append(["暂无数据", "-", "-", "-", "-", "-"])

    table = Table(data, repeatRows=1, colWidths=[32 * mm, 22 * mm, 18 * mm, 22 * mm, 22 * mm, 20 * mm])
    table.setStyle(_table_style(font_name, row_count=len(data)))
    return table


def _build_employee_rank_tables(rows: list[ScoreReportRow], font_name: str) -> Table:
    ranked = _rank_employees(rows)
    top_data: list[list[Any]] = [["员工", "部门", "平均分"]]
    bottom_data: list[list[Any]] = [["员工", "部门", "平均分"]]

    top_data.extend([[name, dept, score] for name, dept, score in ranked[:10]])
    bottom_data.extend([[name, dept, score] for name, dept, score in sorted(ranked, key=lambda item: item[2])[:5]])
    if len(top_data) == 1:
        top_data.append(["暂无数据", "-", "-"])
    if len(bottom_data) == 1:
        bottom_data.append(["暂无数据", "-", "-"])

    top_table = Table(top_data, repeatRows=1, colWidths=[28 * mm, 30 * mm, 20 * mm])
    top_table.setStyle(_table_style(font_name, row_count=len(top_data)))
    bottom_table = Table(bottom_data, repeatRows=1, colWidths=[28 * mm, 30 * mm, 20 * mm])
    bottom_style = _table_style(font_name, row_count=len(bottom_data))
    bottom_style.add("TEXTCOLOR", (0, 1), (-1, -1), colors.HexColor("#B91C1C"))
    bottom_table.setStyle(bottom_style)

    outer = Table(
        [
            [Paragraph("Top 10", _mini_heading(font_name)), Paragraph("Bottom 5", _mini_heading(font_name))],
            [top_table, bottom_table],
        ],
        colWidths=[82 * mm, 82 * mm],
    )
    outer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return outer


def _build_risk_table(risk_rows: list[RiskDetailRow], font_name: str, paragraph_style: ParagraphStyle) -> Table:
    data: list[list[Any]] = [["日期", "员工", "部门", "状态", "未解决天数", "描述"]]
    if not risk_rows:
        data.append(["暂无风险", "-", "-", "-", "-", "-"])
    else:
        for row in risk_rows:
            data.append(
                [
                    str(row.report_date),
                    row.user_name,
                    row.department,
                    row.status,
                    row.days_unresolved,
                    Paragraph(row.description, paragraph_style),
                ]
            )

    table = Table(data, repeatRows=1, colWidths=[24 * mm, 24 * mm, 30 * mm, 24 * mm, 22 * mm, 58 * mm])
    table.setStyle(_table_style(font_name, row_count=len(data)))
    return table


def _build_metric_cards(metrics: list[tuple[str, str]], font_name: str) -> Table:
    data = [[f"{label}\n{value}" for label, value in metrics]]
    table = Table(data, colWidths=[40 * mm] * 4, rowHeights=[24 * mm])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), font_name),
                ("FONTSIZE", (0, 0), (-1, -1), 11),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EFF6FF")),
                ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#93C5FD")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BFDBFE")),
            ]
        )
    )
    return table


def _rank_employees(rows: list[ScoreReportRow]) -> list[tuple[str, str, float]]:
    grouped: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for row in rows:
        if row.report.ai_score is None:
            continue
        grouped[(str(row.report.user_id), row.user_name, row.department)].append(row.report.ai_score)

    ranked = [
        (user_name, department, round(mean(scores), 1))
        for (_, user_name, department), scores in grouped.items()
        if scores
    ]
    ranked.sort(key=lambda item: item[2], reverse=True)
    return ranked


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ChineseTitle",
            parent=sample["Title"],
            fontName=font_name,
            fontSize=24,
            leading=30,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "heading": ParagraphStyle(
            "ChineseHeading",
            parent=sample["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1F2937"),
        ),
        "center": ParagraphStyle(
            "ChineseCenter",
            parent=sample["Normal"],
            fontName=font_name,
            fontSize=10,
            leading=15,
            alignment=TA_CENTER,
        ),
        "small": ParagraphStyle(
            "ChineseSmall",
            parent=sample["Normal"],
            fontName=font_name,
            fontSize=8,
            leading=11,
        ),
    }


def _table_style(font_name: str, *, row_count: int) -> TableStyle:
    style = TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ]
    )
    for row_idx in range(1, row_count):
        if row_idx % 2 == 0:
            style.add("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#F8FAFC"))
    return style


def _mini_heading(font_name: str) -> ParagraphStyle:
    return ParagraphStyle(
        "MiniHeading",
        fontName=font_name,
        fontSize=11,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1F2937"),
    )


def _month_range(month: str) -> tuple[date, date]:
    year_str, month_str = month.split("-", 1)
    year = int(year_str)
    month_num = int(month_str)
    start_date = date(year, month_num, 1)
    if month_num == 12:
        return start_date, date(year + 1, 1, 1)
    return start_date, date(year, month_num + 1, 1)


def _has_blocker(parsed_content: dict | None) -> bool:
    blocker = str((parsed_content or {}).get("blocker") or "").strip()
    return bool(blocker and blocker not in {"无", "暂无", "none", "None", "N/A", "n/a", "-"})


def _percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


class _NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, generated_at: str, font_name: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []
        self._generated_at = generated_at
        self._font_name = font_name

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(page_count)
            super().showPage()
        super().save()

    def _draw_page_number(self, page_count: int) -> None:
        self.setFont(self._font_name, 8)
        width, _ = A4
        self.drawRightString(
            width - 16 * mm, 10 * mm, f"Page {self._pageNumber} / {page_count}  生成: {self._generated_at}"
        )
