import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import select

async def reset():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.wechat_userid == 'admin'))
        admin = res.scalar_one_or_none()
        if admin:
            admin.must_change_password = False
            await db.commit()
            print("Admin must_change_password set to False")

if __name__ == '__main__':
    asyncio.run(reset())
