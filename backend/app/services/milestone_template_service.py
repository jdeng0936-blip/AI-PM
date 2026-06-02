"""
app/services/milestone_template_service.py — Phase 14 立项里程碑模板
"""

from app.models.project import ProjectTrack
from app.models.project_milestone import MilestoneNodeType
from app.schemas.milestone import MilestoneTemplateNode

STANDARD_MILESTONE_TEMPLATES: dict[str, list[MilestoneTemplateNode]] = {
    "software": [
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_req,
            title="需求确认与范围冻结",
            suggested_initial_points=10,
            node_order=1,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_req,
            title="需求文档/原型评审",
            suggested_initial_points=10,
            node_order=2,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.custom,
            title="UI/UX 设计完成",
            suggested_initial_points=10,
            node_order=3,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_mvp,
            title="研发实现完成",
            suggested_initial_points=30,
            node_order=4,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.custom,
            title="联调自测通过",
            suggested_initial_points=10,
            node_order=5,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_validate,
            title="测试验证通过",
            suggested_initial_points=20,
            node_order=6,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_launch,
            title="交付上线/客户验收",
            suggested_initial_points=10,
            node_order=7,
        ),
    ],
    "hardware": [
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.custom,
            title="ID/工业设计确认",
            suggested_initial_points=10,
            node_order=1,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.hardware_review,
            title="需求规格与方案评审",
            suggested_initial_points=15,
            node_order=2,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.hardware_review,
            title="结构/硬件设计完成",
            suggested_initial_points=25,
            node_order=3,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.custom,
            title="BOM/采购准备完成",
            suggested_initial_points=10,
            node_order=4,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.hardware_proto,
            title="样机制作完成",
            suggested_initial_points=20,
            node_order=5,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.custom,
            title="联调测试通过",
            suggested_initial_points=15,
            node_order=6,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.hardware_finalize,
            title="试产导入/交付验收",
            suggested_initial_points=5,
            node_order=7,
        ),
    ],
    "dual": [
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.custom,
            title="ID/需求定义完成",
            suggested_initial_points=10,
            node_order=1,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_req,
            title="需求文档/范围冻结",
            suggested_initial_points=10,
            node_order=2,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.hardware_review,
            title="方案设计评审通过",
            suggested_initial_points=10,
            node_order=3,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_mvp,
            title="软件研发完成",
            suggested_initial_points=20,
            node_order=4,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.hardware_proto,
            title="硬件/结构样机完成",
            suggested_initial_points=20,
            node_order=5,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.custom,
            title="软硬联调通过",
            suggested_initial_points=10,
            node_order=6,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_validate,
            title="测试验证通过",
            suggested_initial_points=10,
            node_order=7,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.custom,
            title="试产导入完成",
            suggested_initial_points=5,
            node_order=8,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_launch,
            title="交付上线/客户验收",
            suggested_initial_points=5,
            node_order=9,
        ),
    ],
    "support": [
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.temporary_done,
            title="完成",
            suggested_initial_points=0,
            node_order=1,
        ),
    ],
    "other": [
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.temporary_done,
            title="完成",
            suggested_initial_points=0,
            node_order=1,
        ),
    ],
}


def get_standard_template(track: ProjectTrack, is_temporary: bool) -> list[MilestoneTemplateNode]:
    """Return the backend-owned milestone template for a project track."""
    if is_temporary:
        return [
            MilestoneTemplateNode(
                node_type=MilestoneNodeType.temporary_done,
                title="完成",
                suggested_initial_points=0,
                node_order=1,
            )
        ]

    return STANDARD_MILESTONE_TEMPLATES.get(track.value, STANDARD_MILESTONE_TEMPLATES["other"])
