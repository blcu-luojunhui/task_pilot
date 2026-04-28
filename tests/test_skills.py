import asyncio
import unittest

from src.core.agents.skills import (
    Skill,
    SkillType,
    SkillContext,
    SkillRegistry,
    skill,
    get_global_registry,
    SkillExecutor,
    ToolSpecSerializer,
    OpenAIAdapter,
)


class TestSkillModel(unittest.TestCase):
    def test_create_executable(self):
        async def handler(ctx, **params):
            return "ok"

        s = Skill.executable(
            name="test_skill",
            description="A test skill",
            handler=handler,
            parameters={"x": {"type": "string", "description": "input"}},
            dependencies=["db"],
        )

        self.assertEqual(s.name, "test_skill")
        self.assertEqual(s.skill_type, SkillType.EXECUTABLE)
        self.assertEqual(s.dependencies, ["db"])
        self.assertIsNotNone(s.handler)

    def test_create_knowledge(self):
        s = Skill.knowledge(
            name="domain_knowledge",
            description="Some knowledge",
            domain="web",
            content="# Knowledge\nSome content here",
            guidelines=["Do this", "Don't do that"],
        )

        self.assertEqual(s.skill_type, SkillType.KNOWLEDGE)
        self.assertIn("Knowledge", s.to_prompt_text())

    def test_to_tool_spec(self):
        async def handler(ctx, **params):
            return "ok"

        s = Skill.executable(
            name="tool_skill",
            description="A tool",
            handler=handler,
            parameters={
                "query": {"type": "string", "description": "Search query", "required": True},
                "limit": {"type": "integer", "description": "Max results", "default": 10},
            },
        )

        serializer = ToolSpecSerializer(OpenAIAdapter())
        spec = serializer.serialize(s)
        self.assertEqual(spec["name"], "tool_skill")
        self.assertIn("query", spec["parameters"]["properties"])
        self.assertIn("query", spec["parameters"]["required"])

    def test_execute(self):
        async def handler(ctx, value: str = "default"):
            return f"result: {value}"

        s = Skill.executable(
            name="exec_test",
            description="test",
            handler=handler,
            parameters={
                "value": {"type": "string", "description": "input value", "default": "default"}
            },
        )

        executor = SkillExecutor()
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute(s, None, value="hello")
        )
        self.assertEqual(result, "result: hello")

    def test_knowledge_cannot_execute(self):
        s = Skill.knowledge(name="k", description="knowledge")

        executor = SkillExecutor()
        with self.assertRaises(Exception):
            asyncio.get_event_loop().run_until_complete(executor.execute(s, None))


class TestSkillRegistry(unittest.TestCase):
    def test_register_and_get(self):
        registry = SkillRegistry()

        async def handler(ctx):
            return "ok"

        s = Skill.executable(name="my_skill", description="test", handler=handler)
        registry.register(s)

        found = registry.get("my_skill")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "my_skill")

    def test_list_by_type(self):
        registry = SkillRegistry()

        async def handler(ctx):
            return "ok"

        registry.register(
            Skill.executable(name="exec1", description="e1", handler=handler)
        )
        registry.register(
            Skill.knowledge(name="know1", description="k1", domain="web")
        )
        registry.register(
            Skill.knowledge(name="know2", description="k2", domain="data")
        )

        self.assertEqual(len(registry.list_executable()), 1)
        self.assertEqual(len(registry.list_knowledge()), 2)
        self.assertEqual(len(registry.list_knowledge(domain="web")), 1)

    def test_to_tools_prompt(self):
        registry = SkillRegistry()

        async def handler(ctx):
            return "ok"

        registry.register(
            Skill.executable(
                name="search",
                description="Search the web",
                handler=handler,
                parameters={"q": {"type": "string", "description": "query"}},
            )
        )

        prompt = registry.to_tools_prompt()
        self.assertIn("search", prompt)
        self.assertIn("Search the web", prompt)


class TestSkillDecorator(unittest.TestCase):
    def test_decorator_registers_globally(self):
        @skill(
            name="decorated_skill",
            description="A decorated skill",
            dependencies=["db"],
            parameters={"x": {"type": "string", "description": "input"}},
        )
        async def my_func(ctx, x: str):
            return x

        registry = get_global_registry()
        found = registry.get("decorated_skill")
        self.assertIsNotNone(found)
        self.assertEqual(found.skill_type, SkillType.EXECUTABLE)
        self.assertEqual(found.dependencies, ["db"])


if __name__ == "__main__":
    unittest.main()
