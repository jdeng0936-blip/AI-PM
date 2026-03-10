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
    wechat_corp_id: str = ""
    wechat_corp_secret: str = ""
    wechat_agent_id: str = ""
    wechat_token: str = ""
    wechat_encoding_aes_key: str = ""

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

    # OSS 对象存储
    oss_endpoint: str = ""
    oss_bucket: str = ""
    oss_access_key: str = ""
    oss_secret_key: str = ""

    # 安全
    jwt_secret_key: str
    jwt_expire_hours: int = 24

    # CORS（生产环境前端域名，多个用逗号分隔）
    cors_allowed_origins: list = ["https://your-frontend-domain.com"]


# 全局单例，直接从其他模块 import 使用
settings = Settings()
