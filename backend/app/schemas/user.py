"""
app/schemas/user.py — 用户认证 & 管理 Pydantic V2 Schemas
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── 认证相关 ──────────────────────────────────────────────────
class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., description="用户名（wechat_userid 或 phone 或 name）")
    password: str = Field("", description="密码（开发模式可为空）")


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordRequest(BaseModel):
    """修改密码"""
    old_password: str = ""
    new_password: str = Field(..., min_length=6, max_length=64)


# ── 用户管理 CRUD ─────────────────────────────────────────────
class UserCreate(BaseModel):
    """新增用户"""
    name: str = Field(..., max_length=32)
    wechat_userid: str = Field(..., max_length=64)
    phone: Optional[str] = Field(None, max_length=20)
    department: str = Field("", max_length=64)
    role: str = Field("employee", description="employee / manager / admin")
    password: str = Field("aipm2026", min_length=6, max_length=64,
                          description="初始密码，默认 aipm2026")


class UserUpdate(BaseModel):
    """修改用户信息"""
    name: Optional[str] = Field(None, max_length=32)
    phone: Optional[str] = Field(None, max_length=20)
    department: Optional[str] = Field(None, max_length=64)
    role: Optional[str] = Field(None, description="employee / manager / admin")
    is_active: Optional[bool] = None


class UserOut(BaseModel):
    """用户输出（列表 / 详情）"""
    id: str
    name: str
    wechat_userid: str
    phone: Optional[str] = None
    department: str
    role: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    """用户列表分页响应"""
    items: list[UserOut]
    total: int
    page: int
    page_size: int


# ── 前向引用修复 ──────────────────────────────────────────────
LoginResponse.model_rebuild()
