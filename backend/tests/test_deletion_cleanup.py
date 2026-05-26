from __future__ import annotations

from app.services.deletion_cleanup import render_deletion_cleanup_dry_run_markdown


def test_render_deletion_cleanup_dry_run_markdown_contains_tables_and_impacts():
    markdown = render_deletion_cleanup_dry_run_markdown(
        {
            "mode": "dry_run",
            "retention_days": 30,
            "generated_at": "2026-05-26T13:30:00+00:00",
            "cutoff": "2026-04-26T13:30:00+00:00",
            "tables": {
                "daily_reports": 2,
                "projects": 1,
                "sprint_tasks": 3,
                "risk_alerts": 4,
                "knowledge_items": 5,
            },
            "impacts": {
                "risk_alerts_cascade_from_daily_reports": 6,
                "daily_reports_detach_from_projects": 7,
                "knowledge_items_detach_from_projects": 8,
                "project_members_cascade_from_projects": 9,
                "daily_reports_detach_from_sprint_tasks": 10,
            },
            "open_history_batches": 11,
            "total_candidates": 15,
        }
    )

    assert "dry-run,不会硬删数据" in markdown
    assert "日报: 2 条" in markdown
    assert "临时项目: 1 个" in markdown
    assert "未恢复 deletion_history 批次: 11 批" in markdown
    assert "日报硬删将级联 RiskAlert: 6 条" in markdown
    assert "任务硬删将解绑日报任务关联: 10 条" in markdown
