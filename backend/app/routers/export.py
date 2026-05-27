"""
app/routers/export.py — 数据导出 API

GET /api/v1/export/daily-reports — 按日期范围导出日报为 Excel (.xlsx)
"""

import io
import logging
from datetime import date, timedelta
from typing import Optional
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.rbac import require_role
from app.models.daily_report import DailyReport
from app.models.project import Project
from app.models.user import User, UserRole
from app.services.export.project_summary_excel import build_project_summary_workbook
from app.services.export.reports_excel import build_reports_workbook
from app.services.export.scores_pdf import build_scores_pdf

router = APIRouter(prefix="/api/v1/export", tags=["数据导出"])
logger = logging.getLogger(__name__)

EXCEL_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA_TYPE = "application/pdf"


def _attachment_headers(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}


@router.get("/daily-reports")
async def export_daily_reports(
    start_date: Optional[date] = Query(None, description="起始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """
    导出日报为 Excel (.xlsx)，列对齐原始 Excel 日报表。
    默认导出最近 7 天。
    """
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=6)

    stmt = (
        select(DailyReport, User.name, User.department)
        .join(User, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start_date,
                DailyReport.report_date <= end_date,
                DailyReport.deleted_at.is_(None),  # V2.4 Stage 3 C1
            )
        )
        .order_by(DailyReport.report_date.desc(), DailyReport.ai_score.desc())
    )
    rows = (await db.execute(stmt)).all()

    # ── 生成 Excel ──
    wb = Workbook()
    ws = wb.active
    ws.title = "AI日报汇总"

    # 表头样式
    header_font = Font(name="微软雅黑", bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="3B82F6", end_color="3B82F6", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB"),
    )

    headers = [
        "日期",
        "姓名",
        "部门",
        "AI评分",
        "状态",
        "今日任务",
        "完成进度",
        "验收标准",
        "所需支持",
        "核心卡点",
        "解决方案",
        "预计解决",
        "验收人",
        "Git版本",
        "AI评语",
    ]

    # 列宽
    widths = [12, 8, 10, 8, 6, 35, 8, 20, 15, 20, 20, 12, 8, 12, 30]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w

    # 写入表头
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # 写入数据
    pass_fill = PatternFill(start_color="DCFCE7", fill_type="solid")
    fail_fill = PatternFill(start_color="FEE2E2", fill_type="solid")
    data_align = Alignment(vertical="center", wrap_text=True)

    for row_idx, r in enumerate(rows, 2):
        pc = r.DailyReport.parsed_content or {}
        is_pass = r.DailyReport.pass_check

        values = [
            str(r.DailyReport.report_date),
            r.name,
            r.department,
            r.DailyReport.ai_score,
            "合格" if is_pass else "退回",
            pc.get("tasks", ""),
            f"{pc.get('progress', '')}%" if pc.get("progress") is not None else "",
            pc.get("acceptance_criteria", ""),
            pc.get("support_needed", ""),
            pc.get("blocker", ""),
            pc.get("next_step", ""),
            pc.get("eta", ""),
            pc.get("reviewer", ""),
            pc.get("git_version", ""),
            r.DailyReport.ai_comment or "",
        ]

        for col, val in enumerate(values, 1):
            cell = ws.cell(row=row_idx, column=col, value=val)
            cell.alignment = data_align
            cell.border = thin_border
            if is_pass is not None:
                cell.fill = pass_fill if is_pass else fail_fill

    # 冻结首行
    ws.freeze_panes = "A2"

    # 输出
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"AI日报_{start_date}_{end_date}.xlsx"
    # RFC 5987: use filename* for non-ASCII chars
    from urllib.parse import quote

    encoded_filename = quote(filename)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


@router.get("/daily-reports-csv")
async def export_daily_reports_csv(
    start_date: Optional[date] = Query(None, description="起始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """
    导出日报为 CSV 格式。
    """
    import csv

    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=6)

    stmt = (
        select(DailyReport, User.name, User.department)
        .join(User, DailyReport.user_id == User.id)
        .where(
            and_(
                DailyReport.report_date >= start_date,
                DailyReport.report_date <= end_date,
                DailyReport.deleted_at.is_(None),  # V2.4 Stage 3 C1
            )
        )
        .order_by(DailyReport.report_date.desc(), DailyReport.ai_score.desc())
    )
    rows = (await db.execute(stmt)).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "日期",
            "姓名",
            "部门",
            "AI评分",
            "状态",
            "今日任务",
            "完成进度",
            "验收标准",
            "核心卡点",
            "解决方案",
            "AI评语",
        ]
    )

    for r in rows:
        pc = r.DailyReport.parsed_content or {}
        writer.writerow(
            [
                str(r.DailyReport.report_date),
                r.name,
                r.department,
                r.DailyReport.ai_score,
                "合格" if r.DailyReport.pass_check else "退回",
                pc.get("tasks", ""),
                f"{pc.get('progress', '')}%",
                pc.get("acceptance_criteria", ""),
                pc.get("blocker", ""),
                pc.get("next_step", ""),
                r.DailyReport.ai_comment or "",
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
    from urllib.parse import quote

    filename = f"AI日报_{start_date}_{end_date}.csv"
    encoded_filename = quote(filename)

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        },
    )


@router.get("/reports")
async def export_reports_phase8(
    format: str = Query("xlsx", description="导出格式,仅支持 xlsx"),
    start_date: Optional[date] = Query(None, description="起始日期"),
    end_date: Optional[date] = Query(None, description="结束日期"),
    department: Optional[str] = Query(None, description="部门筛选"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """导出日报多维汇总 Excel。"""
    if format != "xlsx":
        raise HTTPException(status_code=400, detail="reports 仅支持 xlsx 格式")
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=6)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date 不能晚于 end_date")

    try:
        output = await build_reports_workbook(
            db,
            start_date=start_date,
            end_date=end_date,
            department=department,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("生成日报多维汇总 Excel 失败")
        raise HTTPException(status_code=500, detail="生成日报多维汇总 Excel 失败") from exc

    filename = f"AI日报汇总_{start_date}_{end_date}.xlsx"
    return StreamingResponse(output, media_type=EXCEL_MEDIA_TYPE, headers=_attachment_headers(filename))


@router.get("/scores")
async def export_scores_phase8(
    format: str = Query("pdf", description="导出格式,仅支持 pdf"),
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="月份,格式 YYYY-MM"),
    department: Optional[str] = Query(None, description="部门筛选"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """导出月度评分 PDF。"""
    if format != "pdf":
        raise HTTPException(status_code=400, detail="scores 仅支持 pdf 格式")

    try:
        output = await build_scores_pdf(db, month=month, department=department)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("生成月度评分 PDF 失败")
        raise HTTPException(status_code=500, detail="生成月度评分 PDF 失败") from exc

    filename = f"评分报告_{month}.pdf"
    return StreamingResponse(output, media_type=PDF_MEDIA_TYPE, headers=_attachment_headers(filename))


@router.get("/project-summary")
async def export_project_summary_phase8(
    format: str = Query("xlsx", description="导出格式,仅支持 xlsx"),
    project_id: UUID = Query(..., description="项目 UUID"),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_role(UserRole.admin, UserRole.manager)),
):
    """导出单项目多 Sheet 摘要。"""
    if format != "xlsx":
        raise HTTPException(status_code=400, detail="project-summary 仅支持 xlsx 格式")

    try:
        output = await build_project_summary_workbook(db, project_id=project_id)
        project = await _get_project_for_filename(db, project_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("生成项目摘要 Excel 失败")
        raise HTTPException(status_code=500, detail="生成项目摘要 Excel 失败") from exc

    filename = f"项目摘要_{project.code}_{date.today()}.xlsx"
    return StreamingResponse(output, media_type=EXCEL_MEDIA_TYPE, headers=_attachment_headers(filename))


async def _get_project_for_filename(db: AsyncSession, project_id: UUID) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id, Project.deleted_at.is_(None)))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在或已删除")
    return project
