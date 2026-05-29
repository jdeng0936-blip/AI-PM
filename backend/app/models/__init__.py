"""app/models/__init__.py"""

# --- Mixin ---
# --- 附件模型 ---
from app.models.attachment import Attachment, AttachmentKind
from app.models.audit_log import AuditLog
from app.models.audit_log_archive import AuditLogArchive
from app.models.base_mixin import BaseMixin
from app.models.capacity import CapacityLevel, CapacitySnapshot
from app.models.daily_report import DailyReport
from app.models.deletion_history import DeletionHistory
from app.models.department import Department
from app.models.gate_review import GateReview

# --- 知识库模型 ---
from app.models.knowledge import KnowledgeCategory, KnowledgeItem, RetroScope

# --- KPI 目标设定模型 (Phase 9) ---
from app.models.kpi_target import KpiMetric, KpiPeriod, KpiScope, KpiTarget

# --- 通知推送模型 ---
from app.models.notification import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationTemplate,
)

# --- OKR 战略对齐模型 ---
from app.models.okr import (
    KeyResult,
    KRProgressLog,
    KRProgressSource,
    Objective,
    OKRCycle,
    OKRCycleType,
    OKRStatus,
)

# --- IPD 项目管理模型 ---
from app.models.project import Project
from app.models.project_followup import ProjectFollowUp
from app.models.project_member import ProjectMember
from app.models.project_stage import ProjectStage
from app.models.risk_alert import RiskAlert
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import (
    BurndownSnapshot,
    SprintTask,
    TaskPriority,
    TaskStatus,
)
from app.models.usage_log import TenantUsageLog

# --- 基础模型 ---
from app.models.user import User

__all__ = [
    "User",
    "DailyReport",
    "DeletionHistory",
    "Department",
    "RiskAlert",
    "TenantUsageLog",
    "AuditLog",
    "AuditLogArchive",
    "Project",
    "ProjectFollowUp",
    "ProjectStage",
    "GateReview",
    "Sprint",
    "SprintStatus",
    "SprintTask",
    "BurndownSnapshot",
    "TaskStatus",
    "TaskPriority",
    "CapacitySnapshot",
    "CapacityLevel",
    "ProjectMember",
    "OKRCycle",
    "Objective",
    "KeyResult",
    "KRProgressLog",
    "KRProgressSource",
    "OKRCycleType",
    "OKRStatus",
    "KnowledgeItem",
    "KnowledgeCategory",
    "RetroScope",
    "Notification",
    "NotificationChannel",
    "NotificationStatus",
    "NotificationTemplate",
    "Attachment",
    "AttachmentKind",
    "KpiTarget",
    "KpiScope",
    "KpiMetric",
    "KpiPeriod",
]
