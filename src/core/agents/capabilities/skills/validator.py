"""
参数验证器

验证 Skill 执行参数的合法性
"""

from typing import Any, Dict, Mapping

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

        # 验证参数类型与 JSON Schema 子集
        for param_name, param_value in params.items():
            if param_name in skill.parameters:
                param_spec = skill.parameters[param_name]
                ParameterValidator.validate_schema(
                    param_value,
                    param_spec,
                    path=param_name,
                    skill_name=skill.name,
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
        if expected_type == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        type_map = {
            "string": str,
            "boolean": bool,
            "array": (list, tuple),
            "object": dict,
            "null": type(None),
        }

        expected = type_map.get(expected_type)
        if expected is None:
            return True  # 未知类型，跳过验证

        return isinstance(value, expected)

    @classmethod
    def validate_schema(
        cls,
        value: Any,
        schema: Mapping[str, Any],
        *,
        path: str,
        skill_name: str,
    ) -> None:
        """Validate the JSON Schema subset emitted by TaskPilot tool specs."""
        expected_type = schema.get("type")
        if expected_type and not cls.validate_type(value, expected_type):
            raise SkillValidationError(
                f"Parameter '{path}' for skill '{skill_name}' expected type "
                f"'{expected_type}', got '{type(value).__name__}'"
            )

        if "enum" in schema and value not in schema["enum"]:
            raise SkillValidationError(
                f"Parameter '{path}' for skill '{skill_name}' must be one of "
                f"{schema['enum']!r}"
            )

        if expected_type == "array" and isinstance(value, (list, tuple)):
            item_schema = schema.get("items")
            if isinstance(item_schema, Mapping):
                for index, item in enumerate(value):
                    cls.validate_schema(
                        item,
                        item_schema,
                        path=f"{path}[{index}]",
                        skill_name=skill_name,
                    )

        if expected_type == "object" and isinstance(value, dict):
            properties = schema.get("properties", {})
            required = schema.get("required", [])
            for required_name in required:
                if required_name not in value:
                    raise SkillValidationError(
                        f"Missing required parameter '{path}.{required_name}' "
                        f"for skill '{skill_name}'"
                    )
            if isinstance(properties, Mapping):
                unknown = set(value) - set(properties)
                if schema.get("additionalProperties") is False and unknown:
                    raise SkillValidationError(
                        f"Unknown parameters for '{path}' in skill '{skill_name}': "
                        + ", ".join(sorted(unknown))
                    )
                for name, item in value.items():
                    item_schema = properties.get(name)
                    if isinstance(item_schema, Mapping):
                        cls.validate_schema(
                            item,
                            item_schema,
                            path=f"{path}.{name}",
                            skill_name=skill_name,
                        )


__all__ = ["ParameterValidator", "SkillValidationError"]
