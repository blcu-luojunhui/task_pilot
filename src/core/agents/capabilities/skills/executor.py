"""
Skill 执行器

负责 Skill 的执行逻辑，包括超时、重试、错误处理
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from .context import SkillContext
from .model import Skill
from .validator import ParameterValidator, SkillValidationError

logger = logging.getLogger(__name__)


class SkillExecutionError(Exception):
    """Skill 执行错误"""

    def __init__(self, skill_name: str, message: str, original_error: Optional[Exception] = None):
        self.skill_name = skill_name
        self.original_error = original_error
        super().__init__(f"Skill '{skill_name}' execution failed: {message}")


class SkillExecutor:
    """Skill 执行器"""

    def __init__(
        self,
        timeout: float = 30.0,
        retry: int = 0,
        retry_delay: float = 1.0,
        validate_params: bool = True,
    ):
        """
        初始化执行器

        Args:
            timeout: 执行超时时间（秒）
            retry: 重试次数
            retry_delay: 重试延迟（秒）
            validate_params: 是否验证参数
        """
        self.timeout = timeout
        self.retry = retry
        self.retry_delay = retry_delay
        self.validate_params = validate_params
        self.validator = ParameterValidator()

    async def execute(self, skill: Skill, ctx: SkillContext, **params) -> Any:
        """
        执行 Skill

        Args:
            skill: Skill 对象
            ctx: SkillContext 实例
            **params: 执行参数

        Returns:
            执行结果

        Raises:
            SkillValidationError: 参数验证失败
            SkillExecutionError: 执行失败
        """
        # 参数验证
        if self.validate_params:
            try:
                self.validator.validate(skill, params)
            except SkillValidationError as e:
                logger.error(f"Parameter validation failed for skill '{skill.name}': {e}")
                raise

        # 执行（带重试）
        last_error = None
        for attempt in range(self.retry + 1):
            try:
                result = await self._execute_with_timeout(skill, ctx, params)
                return result
            except asyncio.TimeoutError as e:
                last_error = e
                logger.warning(
                    f"Skill '{skill.name}' execution timeout (attempt {attempt + 1}/{self.retry + 1})"
                )
                if attempt < self.retry:
                    await asyncio.sleep(self.retry_delay)
            except Exception as e:
                last_error = e
                logger.error(
                    f"Skill '{skill.name}' execution error (attempt {attempt + 1}/{self.retry + 1}): {e}",
                    exc_info=True,
                )
                if attempt < self.retry:
                    await asyncio.sleep(self.retry_delay)

        # 所有重试都失败
        raise SkillExecutionError(
            skill_name=skill.name,
            message=str(last_error),
            original_error=last_error,
        )

    async def _execute_with_timeout(
        self,
        skill: Skill,
        ctx: SkillContext,
        params: Dict[str, Any],
    ) -> Any:
        """带超时的执行（兼容同步和异步 handler）"""
        import inspect

        try:
            if inspect.iscoroutinefunction(skill.handler):
                result = await asyncio.wait_for(
                    skill.handler(ctx, **params),
                    timeout=self.timeout,
                )
            else:
                # 同步函数直接调用
                result = skill.handler(ctx, **params)
            return result
        except asyncio.TimeoutError:
            logger.error(f"Skill '{skill.name}' execution timeout after {self.timeout}s")
            raise


# 默认执行器实例
default_executor = SkillExecutor()


async def execute_skill(skill: Skill, ctx: SkillContext, **params) -> Any:
    """
    便捷函数：使用默认执行器执行 Skill

    Args:
        skill: Skill 对象
        ctx: SkillContext 实例
        **params: 执行参数

    Returns:
        执行结果
    """
    return await default_executor.execute(skill, ctx, **params)


__all__ = ["SkillExecutor", "SkillExecutionError", "execute_skill", "default_executor"]
