from pydantic import Field, field_validator, ValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict

from .database import TaskPilotMySQLConfig
from .observability import LogConfig, AlertConfig


class OpenAICompatibleLLMConfig(BaseSettings):
    """OpenAI 兼容 LLM 配置，默认适配 DeepSeek"""

    api_key: str = Field(default="", description="LLM API Key")
    base_url: str = Field(
        default="https://api.deepseek.com",
        description="OpenAI-compatible base URL",
    )
    model: str = Field(default="deepseek-chat", description="模型名称")
    max_tokens: int = Field(default=2048, description="最大输出 token")
    temperature: float = Field(default=0.2, description="采样温度")
    max_steps: int = Field(default=8, description="最大 loop 步数")
    timeout: float = Field(default=30.0, description="单次 LLM 请求超时秒数")
    max_retries: int = Field(default=2, description="LLM 请求重试次数")
    retry_backoff_seconds: float = Field(default=1.0, description="重试退避秒数")

    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


class ProjectConfigSettings(BaseSettings):
    """应用全局配置"""

    # ============ 应用基础配置 ============
    app_name: str = Field(default="TaskPilot", description="应用名称")
    environment: str = Field(
        default="development", description="运行环境: development/pre/production"
    )
    debug: bool = Field(default=False, description="调试模式")

    # ============ 数据库配置 ============
    task_pilot_mysql: TaskPilotMySQLConfig = Field(default_factory=TaskPilotMySQLConfig)

    # ============ 可观测性配置 ============
    log: LogConfig = Field(default_factory=LogConfig)
    alert: AlertConfig = Field(default_factory=AlertConfig)

    # ============ Agent / LLM 配置 ============
    llm: OpenAICompatibleLLMConfig = Field(default_factory=OpenAICompatibleLLMConfig)

    # ============ 任务系统配置 ============
    task_table: str = Field(default="task_manager", description="任务管理表名")
    timezone: str = Field(default="Asia/Shanghai", description="应用时区")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"development", "pre", "production"}
        if v not in allowed:
            raise ValueError(f"environment must be one of {allowed}, got: {v}")
        return v

    @field_validator("debug")
    @classmethod
    def validate_debug_in_production(cls, v: bool, info: ValidationInfo) -> bool:
        env = info.data.get("environment", "development")
        if env == "production" and v:
            raise ValueError("debug must be False in production environment")
        return v

    @field_validator("task_table")
    @classmethod
    def validate_task_table(cls, v: str) -> str:
        if not v or not v.replace("_", "").isalnum():
            raise ValueError(f"task_table must be alphanumeric with underscores, got: {v}")
        return v
