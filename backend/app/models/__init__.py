"""app/models/__init__.py"""
# --- Mixin ---
from app.models.base_mixin import BaseMixin

# --- 基础模型 ---
from app.models.user import User
from app.models.daily_report import DailyReport
from app.models.risk_alert import RiskAlert
from app.models.usage_log import TenantUsageLog

# --- IPD 项目管理模型 ---
from app.models.project import Project
from app.models.project_stage import ProjectStage
from app.models.gate_review import GateReview
from app.models.sprint import Sprint, SprintStatus
from app.models.sprint_task import (
    SprintTask, BurndownSnapshot, TaskStatus, TaskPriority,
)
from app.models.project_member import ProjectMember

# --- OKR 战略对齐模型 ---
from app.models.okr import (
    OKRCycle, Objective, KeyResult, KRProgressLog, KRProgressSource,
    OKRCycleType, OKRStatus,
)

# --- 知识库模型 ---
from app.models.knowledge import KnowledgeItem, KnowledgeCategory, RetroScope

# --- 通知推送模型 ---
from app.models.notification import (
    Notification, NotificationChannel, NotificationStatus, NotificationTemplate,
)

# --- 附件模型 ---
from app.models.attachment import Attachment, AttachmentKind

__all__ = [
    "User", "DailyReport", "RiskAlert", "TenantUsageLog",
    "Project", "ProjectStage", "GateReview", "Sprint", "SprintStatus",
    "SprintTask", "BurndownSnapshot", "TaskStatus", "TaskPriority",
    "ProjectMember",
    "OKRCycle", "Objective", "KeyResult", "KRProgressLog", "KRProgressSource",
    "OKRCycleType", "OKRStatus",
    "KnowledgeItem", "KnowledgeCategory", "RetroScope",
    "Notification", "NotificationChannel", "NotificationStatus", "NotificationTemplate",
    "Attachment", "AttachmentKind",
]
