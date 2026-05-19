"""
app/config.py — 全局环境变量配置（基于 Pydantic Settings）
所有配置均从 .env 文件读取，绝不硬编码敏感信息。
"""
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 运行环境（dev / prod）
    aipm_env: str = "dev"

    # 数据库
    database_url: str

    # Redis
    redis_url: str

    # 企业微信（env 中为 WECOM_*，此处兼容两种命名）
    wechat_corp_id: str = Field(
        default="",
        validation_alias=AliasChoices("WECHAT_CORP_ID", "WECOM_CORP_ID"),
    )
    wechat_corp_secret: str = Field(
        default="",
        validation_alias=AliasChoices("WECHAT_CORP_SECRET", "WECOM_SECRET"),
    )
    wechat_agent_id: str = Field(
        default="",
        validation_alias=AliasChoices("WECHAT_AGENT_ID", "WECOM_AGENT_ID"),
    )
    wechat_token: str = Field(
        default="",
        validation_alias=AliasChoices("WECHAT_TOKEN", "WECOM_TOKEN"),
    )
    wechat_encoding_aes_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "WECHAT_ENCODING_AES_KEY", "WECOM_ENCODING_AES_KEY"
        ),
    )
    # 企微群机器人 Webhook(可选,用于战情日报/风险预警群推)
    wechat_bot_webhook: str = Field(
        default="",
        validation_alias=AliasChoices("WECHAT_BOT_WEBHOOK", "WECOM_BOT_WEBHOOK"),
    )

    # 钉钉群机器人(Webhook + 加签 secret)
    dingtalk_bot_webhook: str = Field(
        default="",
        validation_alias=AliasChoices("DINGTALK_BOT_WEBHOOK", "DINGTALK_WEBHOOK"),
    )
    dingtalk_bot_secret: str = Field(
        default="",
        validation_alias=AliasChoices("DINGTALK_BOT_SECRET", "DINGTALK_SECRET"),
    )
    # 钉钉企业应用(可选,用于精准推送给个人)
    dingtalk_app_key: str = Field(
        default="", validation_alias=AliasChoices("DINGTALK_APP_KEY")
    )
    dingtalk_app_secret: str = Field(
        default="", validation_alias=AliasChoices("DINGTALK_APP_SECRET")
    )
    dingtalk_agent_id: str = Field(
        default="", validation_alias=AliasChoices("DINGTALK_AGENT_ID")
    )

    # 大模型网关（兼容 LITELLM_* 和 NEW_API_* 两种命名）
    new_api_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("NEW_API_BASE_URL", "LITELLM_BASE_URL"),
    )
    new_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("NEW_API_KEY", "LITELLM_API_KEY"),
    )
    # NOTE: 物理模型名已迁移到 llm_registry.yaml (Rule 01-Stack-AI-Routing)
    new_api_model: str = "gemini-2.5-flash"

    # Token 限流阈值（每日最大 Token 消耗）
    daily_token_limit: int = 500_000

    # OSS 对象存储(兼容 OSS_ACCESS_KEY_ID/OSS_BUCKET_NAME 等别名)
    oss_endpoint: str = Field(
        default="", validation_alias=AliasChoices("OSS_ENDPOINT")
    )
    oss_bucket: str = Field(
        default="",
        validation_alias=AliasChoices("OSS_BUCKET", "OSS_BUCKET_NAME"),
    )
    oss_access_key: str = Field(
        default="",
        validation_alias=AliasChoices("OSS_ACCESS_KEY", "OSS_ACCESS_KEY_ID"),
    )
    oss_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("OSS_SECRET_KEY", "OSS_ACCESS_KEY_SECRET"),
    )
    # OSS 公网 URL 前缀(可选,默认从 endpoint+bucket 推导)
    oss_public_url_base: str = Field(
        default="", validation_alias=AliasChoices("OSS_PUBLIC_URL_BASE")
    )
    # 本地降级模式:OSS 未配置时把文件存到该目录(开发期使用)
    local_upload_dir: str = Field(
        default="./uploads", validation_alias=AliasChoices("LOCAL_UPLOAD_DIR")
    )

    # 讯飞 ASR
    xunfei_app_id: str = Field(
        default="", validation_alias=AliasChoices("XUNFEI_APP_ID")
    )
    xunfei_api_key: str = Field(
        default="", validation_alias=AliasChoices("XUNFEI_API_KEY")
    )
    xunfei_api_secret: str = Field(
        default="", validation_alias=AliasChoices("XUNFEI_API_SECRET")
    )
    asr_provider: str = Field(
        default="xunfei", validation_alias=AliasChoices("ASR_PROVIDER")
    )

    # 安全
    jwt_secret_key: str
    jwt_expire_hours: int = 24

    # CORS（生产环境前端域名，多个用逗号分隔）
    cors_allowed_origins: list = ["https://your-frontend-domain.com"]


# 全局单例，直接从其他模块 import 使用
settings = Settings()
