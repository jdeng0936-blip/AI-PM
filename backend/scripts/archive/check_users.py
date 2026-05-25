import asyncio
from app.database import engine
from sqlalchemy import text

async def run():
    async with engine.begin() as conn:
        res = await conn.execute(text("SELECT id, name, role, tenant_id FROM users"))
        users = res.fetchall()
        for u in users:
            print(f"ID: {u.id}, Name: {u.name}, Role: {u.role}, Tenant: {u.tenant_id}")
            
if __name__ == "__main__":
    asyncio.run(run())
