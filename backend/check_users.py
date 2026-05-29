import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User


async def check():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).limit(5))
        users = res.scalars().all()
        for u in users:
            print(
                f"User: {u.wechat_userid} ({u.name}), Role: {u.role}, must_change: {u.must_change_password}, is_active: {u.is_active}"
            )


if __name__ == "__main__":
    asyncio.run(check())
