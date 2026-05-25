import asyncio
import logging

from app.services.scheduled_tasks import (
    remind_unreported_deadline,
    remind_unreported_friendly,
    remind_unreported_urgent,
)

logging.basicConfig(level=logging.INFO)


async def run_tests():
    print("=== Testing Friendly Reminder ===")
    await remind_unreported_friendly()

    print("\n=== Testing Urgent Reminder ===")
    await remind_unreported_urgent()

    print("\n=== Testing Deadline Reminder ===")
    await remind_unreported_deadline()


if __name__ == "__main__":
    asyncio.run(run_tests())
