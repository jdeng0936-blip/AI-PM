import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.database import AsyncSessionLocal
from app.models.project import Project
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Project).order_by(Project.created_at.desc()).limit(5))
        projects = res.scalars().all()
        for p in projects:
            print(f"ID: {p.id}, Code: {p.code}, Name: {p.name}, Status: {p.status}, Track: {p.track}")

if __name__ == '__main__':
    asyncio.run(check())
