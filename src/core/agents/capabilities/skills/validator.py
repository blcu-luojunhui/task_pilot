"""
参数验证器

验证 Skill 执行参数的合法性
"""

from typing import Any, Dict

from .model import Skill


class SkillValidationError(ValueError):
    """Skill 参数验证错误"""

    pass


class ParameterValidator:
    """参数验证器"""

    @staticmethod
    def validate(skill: Skill, params: Dict[str, Any]) -> None:
        """
        验证参数是否符合 Skill 定义

        Args:
            skill: Skill 对象
            params: 执行参数

        Raises:
            SkillValidationError: 参数验证失败
        """
        if not skill.is_executable:
            raise SkillValidationError(
                f"Skill '{skill.name}' is not executable (type: {skill.skill_type.value})"
            )

        if not skill.handler:
            raise SkillValidationError(f"Skill '{skill.name}' has no handler")

        # 验证必填参数
        for param_name, param_spec in skill.parameters.items():
            is_required = param_spec.get("required", "default" not in param_spec)

            if is_required and param_name not in params:
                raise SkillValidationError(
                    f"Missing required parameter '{param_name}' for skill '{skill.name}'"
                )

        # 验证参数类型
        for param_name, param_value in params.items():
            if param_name in skill.parameters:
                param_spec = skill.parameters[param_name]
                expected_type = param_spec.get("type", "string")
                if not ParameterValidator.validate_type(param_value, expected_type):
                    actual_type = type(param_value).__name__
                    raise SkillValidationError(
                        f"Parameter '{param_name}' for skill '{skill.name}' "
                        f"expected type '{expected_type}', got '{actual_type}'"
                    )

        # 验证未知参数
        defined_params = set(skill.parameters.keys())
        provided_params = set(params.keys())
        unknown_params = provided_params - defined_params

        if unknown_params:
            raise SkillValidationError(
                f"Unknown parameters for skill '{skill.name}': {', '.join(unknown_params)}"
            )

    @staticmethod
    def validate_type(value: Any, expected_type: str) -> bool:
        """
        验证值的类型

        Args:
            value: 待验证的值
            expected_type: 期望类型（string, integer, number, boolean, array, object）

        Returns:
            是否匹配类型
        """
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": (list, tuple),
            "object": dict,
        }

        expected = type_map.get(expected_type)
        if expected is None:
            return True  # 未知类型，跳过验证

        return isinstance(value, expected)


__all__ = ["ParameterValidator", "SkillValidationError"]
