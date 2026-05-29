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
            title="需求文档完成",
            suggested_initial_points=10,
            node_order=1,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_mvp,
            title="MVP 完成",
            suggested_initial_points=30,
            node_order=2,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_validate,
            title="功能验证通过",
            suggested_initial_points=30,
            node_order=3,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.software_launch,
            title="正式上线/客户验收",
            suggested_initial_points=30,
            node_order=4,
        ),
    ],
    "hardware": [
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.hardware_review,
            title="方案评审通过",
            suggested_initial_points=20,
            node_order=1,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.hardware_proto,
            title="样机完成",
            suggested_initial_points=40,
            node_order=2,
        ),
        MilestoneTemplateNode(
            node_type=MilestoneNodeType.hardware_finalize,
            title="产品定型/客户验收",
            suggested_initial_points=40,
            node_order=3,
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

    if track == ProjectTrack.dual:
        software_nodes = STANDARD_MILESTONE_TEMPLATES["software"]
        hardware_nodes = [
            MilestoneTemplateNode(
                node_type=node.node_type,
                title=node.title,
                suggested_initial_points=node.suggested_initial_points,
                node_order=node.node_order + len(software_nodes),
            )
            for node in STANDARD_MILESTONE_TEMPLATES["hardware"]
        ]
        return software_nodes + hardware_nodes

    return STANDARD_MILESTONE_TEMPLATES.get(track.value, STANDARD_MILESTONE_TEMPLATES["other"])
