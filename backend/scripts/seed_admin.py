"""
scripts/seed_admin.py — 创建默认管理员用户（总经理）
运行方式: cd backend && python -m scripts.seed_admin
"""
import asyncio
import sys
import os

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from passlib.context import CryptContext

from app.database import AsyncSessionLocal, engine, Base
from app.models.user import User, UserRole
from app.models.audit_log import AuditLog  # noqa: F401 — 确保表被注册

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── 预设用户（根据白皮书角色设计）──────────────────────────
SEED_USERS = [
    {
        "name": "总经理",
        "wechat_userid": "admin",
        "department": "管理层",
        "job_title": "总经理",
        "role": UserRole.admin,
        "password": "admin2026",
        "must_change_password": True,
    },
    {
        "name": "技术部长",
        "wechat_userid": "tech_director",
        "department": "技术部",
        "job_title": "技术部长",
        "role": UserRole.manager,
        "password": "aipm2026",
        "must_change_password": True,
    },
    {
        "name": "生产经理",
        "wechat_userid": "prod_manager",
        "department": "生产部",
        "job_title": "生产经理",
        "role": UserRole.employee,
        "password": "aipm2026",
        "must_change_password": True,
    },
    {
        "name": "采购经理",
        "wechat_userid": "purchase_manager",
        "department": "采购部",
        "job_title": "采购经理",
        "role": UserRole.employee,
        "password": "aipm2026",
        "must_change_password": True,
    },
    {
        "name": "财务部长",
        "wechat_userid": "finance_director",
        "department": "财务部",
        "job_title": "财务部长",
        "role": UserRole.manager,
        "password": "aipm2026",
        "must_change_password": True,
    },
    {
        "name": "商务经理",
        "wechat_userid": "business_manager",
        "department": "商务部",
        "job_title": "商务经理",
        "role": UserRole.employee,
        "password": "aipm2026",
        "must_change_password": True,
    },
    {
        "name": "销售部长",
        "wechat_userid": "sales_director",
        "department": "销售部",
        "job_title": "销售部长",
        "role": UserRole.manager,
        "password": "aipm2026",
        "must_change_password": True,
    },
    {
        "name": "仓管",
        "wechat_userid": "warehouse_keeper",
        "department": "仓储部",
        "job_title": "仓管",
        "role": UserRole.employee,
        "password": "aipm2026",
        "must_change_password": True,
    },
]


async def seed():
    # 先建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        for u in SEED_USERS:
            # 检查是否已存在
            result = await db.execute(
                select(User).where(User.wechat_userid == u["wechat_userid"])
            )
            if result.scalar_one_or_none():
                print(f"  ⏭️  用户 '{u['name']}' 已存在，跳过")
                continue

            user = User(
                name=u["name"],
                wechat_userid=u["wechat_userid"],
                department=u["department"],
                job_title=u["job_title"],
                role=u["role"],
                hashed_password=pwd_context.hash(u["password"]),
                must_change_password=u["must_change_password"],
                is_active=True,
            )
            db.add(user)
            print(f"  ✅ 创建用户: {u['name']} ({u['job_title']}) — 密码: {u['password']}")

        await db.commit()
        print("\n🎉 种子数据初始化完成！")
        print("─────────────────────────────────")
        print("总经理登录: 用户名 admin, 密码 admin2026")
        print("其他用户:   密码统一 aipm2026")


if __name__ == "__main__":
    print("🌱 AI-PM 种子数据初始化...")
    print("─────────────────────────────────")
    asyncio.run(seed())
