"""
app/models/user.py — 员工/权限表
对应企微员工身份，是所有业务表的外键来源。
"""
import uuid
import enum
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, enum.Enum):
    employee = "employee"   # 普通员工：可提交日报
    manager  = "manager"    # 部门经理：可查看晨报、下属报告
    admin    = "admin"      # 管理员：可访问所有 /admin/* 接口


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4
    )
    # 企微身份唯一标识（FromUserName 字段）
    wechat_userid: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    phone: Mapped[str | None] = mapped_column(
        String(20), unique=True, index=True, nullable=True
    )
    department: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), nullable=False, default=UserRole.employee
    )
    # ── 认证字段 ───────────────────────────────────────────────
    hashed_password: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="bcrypt 哈希密码，企微用户可为空"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<User name={self.name} role={self.role}>"
