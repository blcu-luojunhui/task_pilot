from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthConfig(BaseSettings):
    token_prefix: str = Field(default="sk-", description="Token 前缀")
    refresh_token_prefix: str = Field(default="rt-", description="Refresh Token 前缀")
    default_daily_token_limit: int = Field(default=100000, description="默认每日 Token 配额")
    token_expire_days: int = Field(default=7, description="Token 有效期天数，0 表示永不过期")
    refresh_token_expire_days: int = Field(default=30, description="Refresh Token 有效期天数，0 表示永不过期")

    # 邀请码
    registration_require_invite: bool = Field(default=True, description="注册是否需要邀请码")

    # 邮箱白名单
    allowed_email_domains: str = Field(
        default="qq.com,163.com,126.com,gmail.com,outlook.com,hotmail.com,"
                "sina.com,sohu.com,yeah.net,foxmail.com,proton.me,"
                "protonmail.com,icloud.com,yahoo.com,zoho.com,"
                "live.com,aliyun.com,mail.ustc.edu.cn,pku.edu.cn,"
                "tsinghua.edu.cn,ruc.edu.cn,fudan.edu.cn,sjtu.edu.cn,"
                "zju.edu.cn,nju.edu.cn,whu.edu.cn,hust.edu.cn",
        description="允许注册的邮箱域名，逗号分隔",
    )

    # 防盗
    register_rate_per_hour: int = Field(default=3, description="每 IP 每小时最大注册次数")
    login_rate_per_minute: int = Field(default=20, description="每 IP 每分钟最大登录次数")
    login_max_failures: int = Field(default=5, description="连续登录失败锁定阈值")
    login_lock_minutes: int = Field(default=15, description="登录锁定时长（分钟）")

    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )
