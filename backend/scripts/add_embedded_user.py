import asyncio
from app.database import SessionLocal
from app.models.user import User, UserRole
from sqlalchemy import select

async def add_user():
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.name == '嵌入式小助手'))
        if not result.scalar():
            user = User(
                name='嵌入式小助手',
                wechat_userid='embedded_bot',
                department='技术部',
                job_title='嵌入式软件工程师',
                role=UserRole.employee
            )
            session.add(user)
            await session.commit()
            print('Added embedded user')
        else:
            print('User already exists')

if __name__ == "__main__":
    asyncio.run(add_user())
