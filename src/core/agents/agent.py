"""
Agent - 统一的 Agent 创建和使用接口

提供简洁的 API 来创建、配置和使用 Agent
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from src.core.agents.foundation import AgentLoopState, AgentLoopResult
from src.core.agents.capabilities import (
    SkillRegistry,
    SkillExecutor,
    get_global_registry,
    load_agentic_tools,
    DeepSeekSettings,
    Skill,
    SkillType,
    RiskLevel,
)
from src.core.agents.orchestration import AgentLoopRunner


@dataclass
class AgentConfig:
    """Agent 配置"""

    # LLM 配置
    llm_api_key: str
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com/chat/completions"
    llm_temperature: float = 0.2

    # 执行配置
    max_steps: int = 8
    max_context_tokens: int = 60000
    max_tool_result_length: int = 2000
    abort_on_tool_error: bool = False
    max_consecutive_errors: int = 3

    # 工具配置
    tool_areas: Optional[List[str]] = None  # ["database", "http", "task", "utils"]
    tool_dependencies: Optional[Mapping[str, Any]] = None

    # 其他配置
    enable_routing: bool = False
    is_cancelled: Optional[Callable[[], bool]] = None


class Agent:
    """
    Agent 统一接口

    使用示例：
    ```python
    # 1. 创建 Agent
    agent = Agent.create(
        llm_api_key="your-api-key",
        tool_areas=["database", "http"]
    )

    # 2. 注册自定义 skill
    @agent.skill(name="custom_tool", description="My custom tool")
    def my_tool(param1: str, param2: int) -> str:
        return f"Result: {param1} {param2}"

    # 3. 运行任务
    result = await agent.run("Complete this task")
    print(result.final_answer)
    ```
    """

    def __init__(
        self,
        runner: AgentLoopRunner,
        registry: SkillRegistry,
        config: AgentConfig,
        planner_settings: DeepSeekSettings,
    ):
        self._runner = runner
        self._registry = registry
        self._config = config
        self._planner_settings = planner_settings

    @classmethod
    def create(
        cls,
        llm_api_key: str,
        llm_model: str = "deepseek-chat",
        llm_base_url: str = "https://api.deepseek.com/chat/completions",
        llm_temperature: float = 0.2,
        max_steps: int = 8,
        tool_areas: Optional[List[str]] = None,
        tool_dependencies: Optional[Mapping[str, Any]] = None,
        enable_routing: bool = False,
        **kwargs,
    ) -> "Agent":
        """
        创建 Agent 实例

        Args:
            llm_api_key: LLM API 密钥
            llm_model: LLM 模型名称
            llm_base_url: LLM API 地址
            llm_temperature: 温度参数
            max_steps: 最大执行步数
            tool_areas: 要加载的工具区域列表
            tool_dependencies: 工具依赖注入
            enable_routing: 是否启用任务路由
            **kwargs: 其他配置参数

        Returns:
            Agent 实例
        """
        config = AgentConfig(
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            llm_temperature=llm_temperature,
            max_steps=max_steps,
            tool_areas=tool_areas,
            tool_dependencies=tool_dependencies,
            enable_routing=enable_routing,
            **kwargs,
        )

        # 加载工具
        if tool_areas:
            load_agentic_tools(tool_areas)

        # 创建 registry 和 executor
        registry = get_global_registry()
        executor = SkillExecutor()

        # 创建 planner settings
        planner_settings = DeepSeekSettings(
            api_key=config.llm_api_key,
            model=config.llm_model,
            base_url=config.llm_base_url,
            temperature=config.llm_temperature,
        )

        # 创建 planner 工厂函数
        # 注意：DeepSeekPlanner 需要 goal 参数，我们在这里创建一个包装器
        from src.core.agents.capabilities.llm import DeepSeekPlanner

        async def planner_factory(messages: List[Dict[str, Any]], step: int) -> Dict[str, Any]:
            """
            Planner 工厂函数

            由于 DeepSeekPlanner 需要 goal 参数，我们在运行时动态创建实例
            """
            # 从 messages 中提取 goal
            goal = "Complete the task"
            for msg in messages:
                if msg.get("role") == "system":
                    content = msg.get("content", "")
                    if "goal" in content.lower() or "任务" in content:
                        goal = content
                        break

            # 创建 DeepSeekPlanner 实例
            planner_instance = DeepSeekPlanner(
                goal=goal,
                registry=registry,
                settings=planner_settings,
            )
            return await planner_instance(messages, step)

        # 创建 runner
        runner = AgentLoopRunner(
            planner=planner_factory,
            registry=registry,
            executor=executor,
            max_steps=config.max_steps,
            abort_on_tool_error=config.abort_on_tool_error,
            max_tool_result_length=config.max_tool_result_length,
            max_consecutive_errors=config.max_consecutive_errors,
            max_context_tokens=config.max_context_tokens,
            tool_dependencies=config.tool_dependencies,
            is_cancelled=config.is_cancelled,
        )

        return cls(runner, registry, config, planner_settings)

    def skill(
        self,
        name: str,
        description: str,
        parameters: Optional[Dict[str, Dict[str, Any]]] = None,
        dependencies: Optional[List[str]] = None,
        risk_level: str | RiskLevel = RiskLevel.READ,
        scope: str = "agent:*",
        domain: str = "general",
        tags: Optional[List[str]] = None,
        **metadata,
    ):
        """
        装饰器：注册自定义 skill

        使用示例：
        ```python
        @agent.skill(
            name="search_database",
            description="Search in database",
            parameters={
                "query": {"type": "string", "description": "Search query"}
            }
        )
        def search_db(query: str) -> str:
            return f"Results for: {query}"
        ```

        Args:
            name: Skill 名称
            description: Skill 描述
            parameters: 参数定义（格式：{"param_name": {"type": "string", "description": "..."}）
            dependencies: 依赖列表
            risk_level: 风险级别（READ/WRITE/DESTRUCTIVE）
            scope: 作用域
            domain: 领域
            tags: 标签列表
            **metadata: 其他元数据
        """
        def decorator(func):
            # 生成 skill_id
            import uuid
            skill_id = f"{name}_{uuid.uuid4().hex[:8]}"

            # 创建 Skill 对象
            skill_obj = Skill(
                skill_id=skill_id,
                name=name,
                description=description,
                skill_type=SkillType.EXECUTABLE,
                handler=func,
                parameters=parameters or {},
                dependencies=dependencies or [],
                risk_level=risk_level if isinstance(risk_level, RiskLevel) else RiskLevel(risk_level),
                scope=scope,
                domain=domain,
                tags=tags or [],
                **metadata,
            )
            # 注册到 registry
            self._registry.register(skill_obj)
            return func

        return decorator

    def register_skill(self, skill_obj: Skill):
        """
        直接注册 skill 对象

        Args:
            skill_obj: Skill 实例
        """
        self._registry.register(skill_obj)

    async def run(
        self,
        goal: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> AgentLoopResult:
        """
        运行 Agent 执行任务

        Args:
            goal: 任务目标
            messages: 初始消息列表
            metadata: 元数据
            trace_id: 追踪 ID

        Returns:
            执行结果
        """
        if self._config.enable_routing:
            return await self._runner.run_with_routing(
                goal=goal,
                messages=messages,
                metadata=metadata,
                trace_id=trace_id,
            )
        else:
            return await self._runner.run(
                goal=goal,
                messages=messages,
                metadata=metadata,
                trace_id=trace_id,
            )

    @property
    def registry(self) -> SkillRegistry:
        """获取 skill registry"""
        return self._registry

    @property
    def config(self) -> AgentConfig:
        """获取配置"""
        return self._config

    @property
    def planner_settings(self) -> DeepSeekSettings:
        """获取 planner 配置"""
        return self._planner_settings


__all__ = ["Agent", "AgentConfig"]
