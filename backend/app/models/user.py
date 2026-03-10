"""
app/models/user.py — 员工/权限表
对应企微员工身份，是所有业务表的外键来源。

注意：User 模型不使用 BaseMixin（因为 BaseMixin 的 created_by FK 指向 users.id，
会导致循环依赖），而是手动定义通用字段。
"""
import uuid
import enum
from datetime import datetime, date
from typing import Optional

from sqlalchemy import String, Boolean, DateTime, Date, Enum, Integer
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class UserRole(str, enum.Enum):
    employee = "employee"   # 普通员工：可提交日报
    manager  = "manager"    # 部门经理：可查看晨报、下属报告
    admin    = "admin"      # 管理员：可访问所有 /admin/* 接口


class UserStatus(str, enum.Enum):
    active    = "active"      # 在岗
    on_leave  = "on_leave"    # 请假
    on_travel = "on_travel"   # 出差
    sick_leave = "sick_leave" # 病假


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
    phone: Mapped[Optional[str]] = mapped_column(
        String(20), unique=True, index=True, nullable=True
    )
    department: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), nullable=False, default=UserRole.employee
    )
    # ── 认证字段 ───────────────────────────────────────────────
    hashed_password: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True, comment="bcrypt 哈希密码，企微用户可为空"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="是否启用"
    )
    # ── 岗位与首次改密 ──────────────────────────────────────────
    job_title: Mapped[str] = mapped_column(
        String(50), nullable=False, default="",
        comment="岗位：技术部长/研发工程师/采购经理/仓管 等"
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="首次登录强制改密"
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最近登录时间"
    )
    # ── 请假/出差状态 ─────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        Enum(UserStatus), nullable=False, default=UserStatus.active,
        comment="员工状态：active/on_leave/on_travel/sick_leave"
    )
    status_until: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, comment="状态截止日期（自动恢复 active）"
    )
    # ── 资源负载 ──────────────────────────────────────────────────
    story_points_capacity: Mapped[int] = mapped_column(
        Integer, nullable=False, default=8,
        comment="Sprint 故事点容量（默认8点/Sprint）"
    )

    # ── 通用字段（Rule 01-Stack-Database）──────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=True, comment="记录最后更新时间"
    )
    tenant_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default="default", index=True,
        comment="租户隔离标识"
    )

    def __repr__(self) -> str:
        return f"<User name={self.name} role={self.role}>"
