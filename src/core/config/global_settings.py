from typing import Dict

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .settings import DatabaseConfig, LogConfig, AlertConfig


class GlobalConfigSettings(BaseSettings):
    """应用全局配置"""

    # ============ 应用基础配置 ============
    app_name: str = Field(default="TaskPilot", description="应用名称")
    environment: str = Field(
        default="development", description="运行环境: development/pre/production"
    )
    debug: bool = Field(default=False, description="调试模式")

    # ============ 数据库配置 ============
    default_db: DatabaseConfig = Field(default_factory=DatabaseConfig)

    # ============ 可观测性配置 ============
    log: LogConfig = Field(default_factory=LogConfig)
    alert: AlertConfig = Field(default_factory=AlertConfig)

    # ============ 任务系统配置 ============
    task_table: str = Field(
        default="task_manager", description="任务管理表名"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
