import asyncio

from sqlalchemy import inspect

from app.config import settings
from app.database import engine
from app.models.risk_alert import RiskAlert


async def main():
    print("1. Config Secret Loaded:", settings.erp_webhook_secret)
    print("2. RiskAlert has material_code in Python:", hasattr(RiskAlert, "material_code"))
    print("3. RiskAlert has po_number in Python:", hasattr(RiskAlert, "po_number"))

    # 物理数据库列检测
    async with engine.connect() as conn:

        def check_physical_columns(connection):
            inspector = inspect(connection)
            columns = {c["name"] for c in inspector.get_columns("risk_alerts")}
            return columns

        columns = await conn.run_sync(check_physical_columns)
        has_material_code = "material_code" in columns
        has_po_number = "po_number" in columns
        print("4. DB Physical column material_code exists:", has_material_code)
        print("5. DB Physical column po_number exists:", has_po_number)

        if has_material_code and has_po_number:
            print("6. DB Physical columns verified: Success")
        else:
            print("6. DB Physical columns verified: Failure")


if __name__ == "__main__":
    asyncio.run(main())
