from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthConfig(BaseSettings):
    token_prefix: str = Field(default="sk-", description="Token 前缀")
    refresh_token_prefix: str = Field(default="rt-", description="Refresh Token 前缀")
    default_daily_token_limit: int = Field(default=100000, description="默认每日 Token 配额")
    token_expire_days: int = Field(default=7, description="Token 有效期天数，0 表示永不过期")
    refresh_token_expire_days: int = Field(default=30, description="Refresh Token 有效期天数，0 表示永不过期")

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )
