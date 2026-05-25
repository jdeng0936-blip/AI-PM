import asyncio
import hashlib
import hmac
import json

from httpx import AsyncClient

from app.config import settings
from app.main import app


async def test_integration():
    print("--- 启动 ERP Webhook v2 单元与集成测试 ---")

    # 备份 secret
    old_secret = settings.erp_webhook_secret

    # 模拟 Payload
    payload_data = {"material": "MCU模块", "status": "已到货", "material_code": "M-CODE-999", "po_number": "PO-NO-999"}

    payload_bytes = json.dumps(payload_data).encode("utf-8")

    try:
        # 1. 验证 401 (无签名)
        settings.erp_webhook_secret = "test-webhook-secret-key-2026"
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/api/v1/erp/webhook/status_update", json=payload_data)
            print("Test 1 - Missing Signature (Expect 401):", response.status_code)
            assert response.status_code == 401

            # 2. 验证 401 (错误签名)
            response = await ac.post(
                "/api/v1/erp/webhook/status_update", headers={"X-ERP-Signature": "invalid-signature"}, json=payload_data
            )
            print("Test 2 - Invalid Signature (Expect 401):", response.status_code)
            assert response.status_code == 401

            # 3. 验证 200 (正确签名)
            sig = hmac.new(settings.erp_webhook_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

            response = await ac.post(
                "/api/v1/erp/webhook/status_update", headers={"X-ERP-Signature": sig}, json=payload_data
            )
            print("Test 3 - Valid Signature (Expect 200):", response.status_code)
            print("Test 3 - Response JSON:", response.json())
            assert response.status_code == 200

            # 4. 验证 Dev 模式下 (空 Secret 跳过校验)
            settings.erp_webhook_secret = ""
            response = await ac.post("/api/v1/erp/webhook/status_update", json=payload_data)
            print("Test 4 - Dev Skip Verification (Expect 200):", response.status_code)
            assert response.status_code == 200

            print("\n集成测试全部顺利通过！")
    finally:
        # 恢复 secret
        settings.erp_webhook_secret = old_secret


if __name__ == "__main__":
    asyncio.run(test_integration())
