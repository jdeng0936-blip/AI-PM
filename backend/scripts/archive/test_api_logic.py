import asyncio
from app.database import AsyncSessionLocal
from app.routers.projects import projects_overview
from app.models.user import User
from sqlalchemy import select

async def run():
    async with AsyncSessionLocal() as db:
        # 获取任意一个用户作为 _user 参数
        user_res = await db.execute(select(User).limit(1))
        user = user_res.scalar_one_or_none()
        if not user:
            print("找不到任何用户！")
            return
        print(f"使用的模拟用户: {user.name}, Role: {user.role}, Tenant: {user.tenant_id}")
        
        # 模拟调用 projects_overview
        res = await projects_overview(
            page=1,
            page_size=20,
            include_archived=False,
            health_status=None,
            db=db,
            _user=user
        )
        print("API 返回结果:")
        print(res)

if __name__ == "__main__":
    asyncio.run(run())
