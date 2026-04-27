from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseConfig(BaseSettings):
    """数据库配置"""

    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = ""
    db: str = "taskpilot"
    charset: str = "utf8mb4"
    minsize: int = 5
    maxsize: int = 20

    model_config = SettingsConfigDict(
        env_prefix="", case_sensitive=False, extra="ignore"
    )


class LogConfig(BaseSettings):
    """日志配置"""

    level: str = Field(default="INFO", description="日志级别")
    queue_size: int = Field(default=10000, description="日志队列大小")

    model_config = SettingsConfigDict(
        env_prefix="LOG_", env_file=".env", case_sensitive=False, extra="ignore"
    )


class AlertConfig(BaseSettings):
    """告警配置"""

    queue_size: int = Field(default=1000, description="告警队列大小")

    model_config = SettingsConfigDict(
        env_prefix="ALERT_", env_file=".env", case_sensitive=False, extra="ignore"
    )
