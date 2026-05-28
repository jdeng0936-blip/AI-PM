"""
tests/_isolation.py — 测试隔离 helper:统一清空所有外部敏感 settings

议题:T-1103 议题 A — T-1102 议题 A 在 test_notifications.py 单文件加了
`_clean_notification_settings(monkeypatch)` autouse fixture,只覆盖通知通道
13 项 settings。但**其他 test file 中任何引用 settings 的 service 调用**
(notify / asr / oss / email / sentry / erp_webhook)仍依赖跑测试者本机 .env
状态。本 helper 抽出统一清空逻辑,供 `conftest.py` 全局 autouse=True 调用,
让任何 test(包括未来新写的)都自动享受 isolation。

为何不破坏现有 test:monkeypatch.setattr 是函数 scope,fixture autouse 在 test
body 之前 setattr 空值,test 内若需要测「已配置时的真实分支」(如
test_asr.py::test_xunfei_configured_when_provider_is_xunfei),test 内自己再
setattr 真值,later setattr wins(monkeypatch 顺序覆盖而非 stack)。
"""

from __future__ import annotations

from typing import Any

# 锁定 28 项外部敏感字段(覆盖 wechat / dingtalk / smtp / asr / oss / new_api /
# sentry / erp_webhook 8 个外部依赖类别)。新增字段时,**只在此 list 追加**,
# 严禁在 conftest.py / 单元 test 中分散维护别名。
_EXTERNAL_SETTINGS_FIELDS: tuple[str, ...] = (
    # 企业微信(6 项)
    "wechat_corp_id",
    "wechat_corp_secret",
    "wechat_agent_id",
    "wechat_token",
    "wechat_encoding_aes_key",
    "wechat_bot_webhook",
    # 钉钉(5 项)
    "dingtalk_bot_webhook",
    "dingtalk_bot_secret",
    "dingtalk_app_key",
    "dingtalk_app_secret",
    "dingtalk_agent_id",
    # 邮件 SMTP(4 项)
    "smtp_server",
    "smtp_user",
    "smtp_password",
    "smtp_from_email",
    # 大模型网关(2 项)
    "new_api_base_url",
    "new_api_key",
    # 讯飞 ASR(3 项)
    "xunfei_app_id",
    "xunfei_api_key",
    "xunfei_api_secret",
    # OSS 对象存储(5 项)
    "oss_endpoint",
    "oss_bucket",
    "oss_access_key",
    "oss_secret_key",
    "oss_public_url_base",
    # ERP webhook(1 项)
    "erp_webhook_secret",
    # Sentry(2 项)
    "sentry_dsn",
    "sentry_environment",
)


def clean_external_settings(monkeypatch: Any) -> None:
    """
    把所有外部敏感 settings 字段 setattr 为空字符串,让 service 层的
    `is_configured()` 等检查走「未配置」分支,test 走干净基线。

    test 内若需要测「已配置」分支,直接在 test body 中 monkeypatch.setattr
    覆盖即可(later setattr wins)。

    Args:
        monkeypatch: pytest 的 monkeypatch fixture 实例(MonkeyPatch 类型),
            函数 scope,test 结束自动还原。

    Notes:
        - 不修改 `database_url` / `redis_url` / `jwt_secret_key`(测试核心依赖,
          不应被清空,否则 conftest.py setup_test_db / app.config 自身解析失败)。
        - `aipm_env` / `enable_dev_*` 等运行环境开关也不清空(测试基础设施依赖)。
        - 使用 `raising=False` 防御未来字段重命名,fixture 仍 graceful 通过。
    """
    # 延迟 import 避免 conftest.py 启动时循环依赖
    from app.config import settings

    for field in _EXTERNAL_SETTINGS_FIELDS:
        monkeypatch.setattr(settings, field, "", raising=False)
