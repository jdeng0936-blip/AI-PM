import asyncio
import uuid
import sys
import logging
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from app.database import get_db, engine
from app.models.user import User, UserRole
from app.routers.reports import submit_morning_batch
from app.schemas.morning_evening import MorningBatchRequest, MorningPlanCardIn

async def main():
    async with engine.connect() as conn:
        pass
    async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    
    async with async_session() as db:
        # get an active user
        from sqlalchemy import select
        user = (await db.execute(select(User).where(User.role == UserRole.employee).limit(1))).scalar_one_or_none()
        if not user:
            print("No user found")
            return
            
        print(f"Testing for user {user.id}")
        
        # mock a temporary project
        from app.models.project import Project, ProjectMember
        project = (await db.execute(select(Project).join(ProjectMember).where(ProjectMember.user_id == user.id, Project.is_temporary == True).limit(1))).scalar_one_or_none()
        
        if not project:
            print("No temp project found")
            project_id = uuid.uuid4() # dummy
        else:
            project_id = project.id
            
        print(f"Using project {project_id}")
        
        try:
            req = MorningBatchRequest(
                items=[MorningPlanCardIn(project_id=project_id, note="")]
            )
            print("Pydantic validation passed")
        except Exception as e:
            print("Pydantic error:", e)
            return

        try:
            res = await submit_morning_batch(req, db, user)
            print("Success:", res)
        except Exception as e:
            print("Router error:", e)
            
if __name__ == "__main__":
    asyncio.run(main())
