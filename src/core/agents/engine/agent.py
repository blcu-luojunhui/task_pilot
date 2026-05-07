"""
Agent - 统一的 Agent 创建和使用接口

提供简洁的 API 来创建、配置和使用 Agent
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from src.core.agents.capabilities.llm.base import LLMMessage
from src.core.agents.state import AgentLoopState, AgentLoopResult, AgentState
from src.core.agents.state.snapshot import StateSnapshot
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
from src.core.agents.capabilities.llm.base import LLMProvider, LLMConfig
from src.core.agents.capabilities.llm.providers import (
    OpenAIProvider,
    ClaudeProvider,
    DeepSeekProvider,
)
from src.core.agents.exceptions import AgentConfigError
from .lifecycle import LifecycleManager
from .runner import AgentLoopRunner


# 支持的 LLM Provider 映射
_PROVIDER_MAP = {
    "openai": OpenAIProvider,
    "claude": ClaudeProvider,
    "deepseek": DeepSeekProvider,
}

# 各 Provider 的默认配置
_PROVIDER_DEFAULTS = {
    "openai": {"model": "gpt-4", "base_url": "https://api.openai.com/v1"},
    "claude": {
        "model": "claude-3-opus-20240229",
        "base_url": "https://api.anthropic.com/v1",
    },
    "deepseek": {"model": "deepseek-chat", "base_url": "https://api.deepseek.com"},
}


@dataclass
class AgentConfig:
    """Agent 配置"""

    # LLM 配置
    llm_provider: str = "deepseek"  # openai, claude, deepseek
    llm_api_key: str = ""
    llm_model: Optional[str] = None  # None 表示使用 provider 默认值
    llm_base_url: Optional[str] = None  # None 表示使用 provider 默认值
    llm_temperature: float = 0.2

    # 执行配置
    max_steps: int = 8
    max_context_tokens: int = 60000
    max_tool_result_length: int = 2000
    abort_on_tool_error: bool = False
    max_consecutive_errors: int = 3

    # 工具配置
    tool_areas: Optional[List[str]] = None
    tool_dependencies: Optional[Mapping[str, Any]] = None

    # 其他配置
    enable_routing: bool = False
    is_cancelled: Optional[Callable[[], bool]] = None
    verbose: bool = False  # 是否打印执行流程日志
    show_prompt: bool = False  # 是否打印发给 LLM 的完整 prompt

    def __post_init__(self):
        """配置验证"""
        if not self.llm_api_key:
            raise AgentConfigError("llm_api_key is required")
        if self.llm_provider not in _PROVIDER_MAP:
            raise AgentConfigError(
                f"Unsupported llm_provider: '{self.llm_provider}'. "
                f"Supported: {list(_PROVIDER_MAP.keys())}"
            )
        if self.max_steps <= 0:
            raise AgentConfigError("max_steps must be > 0")
        if not (0 <= self.llm_temperature <= 2):
            raise AgentConfigError("llm_temperature must be in [0, 2]")
        if self.max_context_tokens <= 0:
            raise AgentConfigError("max_context_tokens must be > 0")
        if self.max_tool_result_length <= 0:
            raise AgentConfigError("max_tool_result_length must be > 0")
        if self.max_consecutive_errors <= 0:
            raise AgentConfigError("max_consecutive_errors must be > 0")


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
        provider: LLMProvider,
        lifecycle: Optional[LifecycleManager] = None,
    ):
        self._runner = runner
        self._registry = registry
        self._config = config
        self._provider = provider
        self._lifecycle = lifecycle or LifecycleManager()
        self._snapshot_dir: Optional[Path] = None
        self._last_snapshot_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        llm_api_key: str,
        llm_provider: str = "deepseek",
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        llm_temperature: float = 0.2,
        max_steps: int = 8,
        tool_areas: Optional[List[str]] = None,
        tool_dependencies: Optional[Mapping[str, Any]] = None,
        enable_routing: bool = False,
        verbose: bool = False,
        show_prompt: bool = False,
        **kwargs,
    ) -> "Agent":
        """
        创建 Agent 实例

        Args:
            llm_api_key: LLM API 密钥
            llm_provider: LLM 提供商 (openai, claude, deepseek)
            llm_model: LLM 模型名称（None 使用 provider 默认值）
            llm_base_url: LLM API 地址（None 使用 provider 默认值）
            llm_temperature: 温度参数
            max_steps: 最大执行步数
            tool_areas: 要加载的工具区域列表
            tool_dependencies: 工具依赖注入
            enable_routing: 是否启用任务路由
            verbose: 是否展示日志
            show_prompt: 是否展示 prompt
            **kwargs: 其他配置参数

        Returns:
            Agent 实例
        """
        # 解析 provider 默认值
        defaults = _PROVIDER_DEFAULTS.get(llm_provider, _PROVIDER_DEFAULTS["deepseek"])
        resolved_model = llm_model or defaults["model"]
        resolved_base_url = llm_base_url or defaults["base_url"]

        config = AgentConfig(
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            llm_model=resolved_model,
            llm_base_url=resolved_base_url,
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

        # 打印系统注册的 tools
        _logger = logging.getLogger("agent.loop")
        system_skills = registry.list_executable()
        if system_skills:
            _logger.info("系统注册了 %d 个 tools:", len(system_skills))
            for s in system_skills:
                _logger.info("  • %s - %s", s.name, s.description[:50])

        # 创建 LLM Provider
        provider_cls = _PROVIDER_MAP.get(llm_provider)
        if not provider_cls:
            raise ValueError(
                f"Unknown LLM provider: {llm_provider}. Supported: {list(_PROVIDER_MAP.keys())}"
            )

        llm_config = LLMConfig(
            api_key=config.llm_api_key,
            model=resolved_model,
            base_url=resolved_base_url,
            temperature=config.llm_temperature,
        )
        provider = provider_cls(llm_config)

        # 创建 planner 工厂函数
        async def planner_factory(messages: List[Dict[str, Any]], step: int) -> Dict[str, Any]:
            """
            统一的 Planner 工厂函数

            使用 LLMProvider 抽象层，支持任意 LLM
            """

            # 转换消息格式（保留 tool_calls 和 tool_call_id）
            llm_messages = []
            for m in messages:
                llm_messages.append(
                    LLMMessage(
                        role=m["role"],
                        content=m.get("content", ""),
                        tool_calls=m.get("tool_calls"),
                        tool_call_id=m.get("tool_call_id"),
                    )
                )

            # 构建工具列表
            tools = []
            for skill in registry.list_executable():
                # 将 skill.parameters 包装为标准 JSON Schema
                params = skill.parameters or {}
                if params and params.get("type") == "object":
                    # 已经是标准 JSON Schema
                    schema = params
                elif params:
                    # 简单字段字典 → 标准 JSON Schema
                    properties = {}
                    required_fields = []
                    for field_name, field_def in params.items():
                        # 复制字段定义，移除非标准的 "required" 键
                        clean_def = {k: v for k, v in field_def.items() if k != "required"}
                        properties[field_name] = clean_def
                        # 收集 required 字段
                        if field_def.get("required", False):
                            required_fields.append(field_name)
                    schema = {
                        "type": "object",
                        "properties": properties,
                    }
                    if required_fields:
                        schema["required"] = required_fields
                else:
                    schema = {"type": "object", "properties": {}}

                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": skill.name,
                            "description": skill.description,
                            "parameters": schema,
                        },
                    }
                )

            # 调用 LLM
            response = await provider.chat(
                messages=llm_messages,
                tools=tools if tools else None,
                temperature=config.llm_temperature,
            )

            # 转换为内部格式（标准化 tool_calls）
            result = {
                "role": "assistant",
                "content": response.content,
            }
            if response.tool_calls:
                from src.core.agents.state.protocol import normalize_tool_calls

                normalized = normalize_tool_calls(response.tool_calls)
                result["tool_calls"] = [tc.to_dict() for tc in normalized]

            return result

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

        # 如果开启 verbose，设置 harness 日志器为 verbose 模式
        if verbose:
            runner.harness.event_logger.verbose = True

        # 如果开启 show_prompt，设置 thinker 打印完整 prompt
        if show_prompt:
            runner.thinker.show_prompt = True

        lifecycle = LifecycleManager()
        runner.lifecycle = lifecycle

        return cls(runner, registry, config, provider, lifecycle=lifecycle)

    # ── 生命周期控制 ──────────────────────────────────────

    def pause(self):
        """
        暂停 Agent 执行。

        如果 Agent 正在 run() 中执行，调用此方法后 Agent 会在当前 step 完成后暂停，
        run() 协程不会返回，而是阻塞等待 resume()。
        """
        try:
            self._lifecycle.transition_to(AgentState.PAUSED, reason="user paused")
            _logger = logging.getLogger("agent.loop")
            _logger.info("Agent 已暂停")
        except ValueError as e:
            _logger = logging.getLogger("agent.loop")
            _logger.warning(f"无法暂停 Agent（当前状态: {self._lifecycle.state}）: {e}")

    def resume(self):
        """
        恢复 Agent 执行。

        恢复之前被 pause() 暂停的 Agent，run() 协程将继续从暂停点执行。
        """
        try:
            self._lifecycle.transition_to(AgentState.RUNNING, reason="user resumed")
            _logger = logging.getLogger("agent.loop")
            _logger.info("Agent 已恢复")
        except ValueError as e:
            _logger = logging.getLogger("agent.loop")
            _logger.warning(f"无法恢复 Agent（当前状态: {self._lifecycle.state}）: {e}")

    def stop(self):
        """
        停止 Agent 执行。

        调用后 run() 将在当前 step 完成后返回，stop_reason 为 USER_CANCELLED。
        """
        try:
            self._lifecycle.transition_to(AgentState.STOPPED, reason="user stopped")
            _logger = logging.getLogger("agent.loop")
            _logger.info("Agent 已请求停止")
        except ValueError as e:
            _logger = logging.getLogger("agent.loop")
            _logger.warning(f"无法停止 Agent（当前状态: {self._lifecycle.state}）: {e}")

    # ── 快照管理 ──────────────────────────────────────────

    def set_snapshot_dir(self, snapshot_dir: str | Path):
        """
        设置快照存储目录。

        Args:
            snapshot_dir: 快照文件存放路径
        """
        self._snapshot_dir = Path(snapshot_dir)
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        保存当前状态快照。

        通常在 pause() 之后调用，以保存暂停时的执行状态。
        需要先调用 set_snapshot_dir() 设置存储目录。

        Args:
            metadata: 附加元数据

        Returns:
            快照 ID，如果不具备保存条件则返回 None
        """
        if not self._snapshot_dir:
            _logger = logging.getLogger("agent.loop")
            _logger.warning("未设置 snapshot_dir，无法保存快照。请先调用 set_snapshot_dir()")
            return None

        loop_state = self._lifecycle._current_loop_state
        if loop_state is None:
            _logger = logging.getLogger("agent.loop")
            _logger.warning("没有当前执行状态，无法保存快照")
            return None

        snapshot = StateSnapshot(self._snapshot_dir)
        snapshot_id = snapshot.save(
            agent_id=self._lifecycle._current_loop_state.trace_id,
            loop_state=loop_state,
            lifecycle_state=self._lifecycle.state,
            metadata=metadata,
        )
        self._last_snapshot_id = snapshot_id
        _logger = logging.getLogger("agent.loop")
        _logger.info(f"快照已保存: {snapshot_id}")
        return snapshot_id

    async def run_from_snapshot(
        self,
        snapshot_id: str,
        snapshot_dir: Optional[str | Path] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentLoopResult:
        """
        从快照恢复执行。

        Args:
            snapshot_id: 快照 ID
            snapshot_dir: 快照目录（默认使用 set_snapshot_dir 设置的目录）
            metadata: 附加元数据

        Returns:
            执行结果

        Raises:
            FileNotFoundError: 快照不存在
            RuntimeError: Agent 当前不在可恢复状态
        """
        directory = Path(snapshot_dir) if snapshot_dir else self._snapshot_dir
        if not directory:
            raise RuntimeError("未设置 snapshot_dir")

        snapshot = StateSnapshot(directory)
        loop_state, lifecycle_state, snap_metadata = snapshot.load(snapshot_id)

        # 合并元数据
        merged_metadata = {**(snap_metadata or {}), **(metadata or {})}

        # 更新生命周期管理器状态
        if lifecycle_state == AgentState.PAUSED:
            self._lifecycle.state = AgentState.PAUSED
            self._lifecycle._pause_event.clear()
            self._lifecycle._stop_requested = False
        else:
            # 非 paused 状态，直接开始运行
            self._lifecycle.state = AgentState.IDLE

        self._lifecycle._current_loop_state = loop_state

        _logger = logging.getLogger("agent.loop")
        _logger.info(f"从快照恢复: {snapshot_id}, step={loop_state.step}")

        return await self._runner.run(
            goal=loop_state.goal,
            messages=loop_state.messages,
            metadata=merged_metadata,
            trace_id=loop_state.trace_id,
        )

    # ── Skill 注册 ────────────────────────────────────────

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
                risk_level=risk_level
                if isinstance(risk_level, RiskLevel)
                else RiskLevel(risk_level),
                scope=scope,
                domain=domain,
                tags=tags or [],
                **metadata,
            )
            # 注册到 registry
            self._registry.register(skill_obj)
            _logger = logging.getLogger("agent.loop")
            _logger.info("业务注册 tool: %s - %s", name, description[:50])
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
        # 重置生命周期状态（允许从 STOPPED/ERROR 重新开始）
        if self._lifecycle.state in (AgentState.STOPPED, AgentState.ERROR):
            self._lifecycle.reset()
        if self._lifecycle.state == AgentState.IDLE:
            self._lifecycle.transition_to(AgentState.RUNNING, reason="run started")

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
    def provider(self) -> LLMProvider:
        """获取 LLM Provider"""
        return self._provider

    @property
    def lifecycle_state(self) -> AgentState:
        """获取当前生命周期状态"""
        return self._lifecycle.state

    @property
    def is_paused(self) -> bool:
        """是否已暂停"""
        return self._lifecycle.state == AgentState.PAUSED

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        return self._lifecycle.state == AgentState.RUNNING


__all__ = ["Agent", "AgentConfig"]
