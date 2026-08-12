"""Agent loop runner implementation"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional

# state
from src.core.agents.state import AgentLoopResult, StopReason, ContextWindowManager, MemoryManager

# task routing (decomposition)
from .prompting import TaskRouter

# agent harness
from src.core.agents.runtime.harness import (
    AgentBudget,
    AgentLoopHarness,
    ApprovalDecision,
    ApprovalPolicy,
    ReconciliationDecision,
    ConstraintSet,
    ContinuousImprovement,
    FeedbackLoop,
    HarnessHook,
    WorkflowController,
)

# agent capabilities
from src.core.agents.capabilities import SkillContext, SkillExecutor, SkillRegistry
from src.core.agents.capabilities import PermissionGuard

from typing import TYPE_CHECKING

# agent engine
from .loop import Act, Observe, Think, AssistantPlanner
from .prompting import KnowledgeSelector, PromptAssembler

if TYPE_CHECKING:
    from .lifecycle import LifecycleManager


@dataclass
class AgentLoopRunner:
    """Agent loop runner that assembles stages and delegates lifecycle to a harness."""

    planner: AssistantPlanner
    registry: SkillRegistry
    executor: SkillExecutor
    max_steps: int = 8
    abort_on_tool_error: bool = False
    max_tool_result_length: int = 2000
    max_consecutive_errors: int = 3
    max_context_tokens: int = 60000
    llm_model: str = "gpt-4o"
    permission_guard: Optional[PermissionGuard] = None
    router: Optional[TaskRouter] = None
    is_cancelled: Optional[Callable[[], bool]] = None
    lifecycle: "Optional[LifecycleManager]" = None
    tool_dependencies: Optional[Mapping[str, Any]] = None
    context_builder: Optional[Callable[[Any], SkillContext]] = None
    thinker: Optional[Think] = None
    actor: Optional[Act] = None
    observer: Optional[Observe] = None
    harness: Optional[AgentLoopHarness] = None
    hooks: Optional[List[HarnessHook]] = None
    budget: Optional[AgentBudget] = None
    constraints: Optional[ConstraintSet] = None
    feedback_loop: Optional[FeedbackLoop] = None
    continuous_improvement: Optional[ContinuousImprovement] = None
    workflow: Optional[WorkflowController] = None
    memory_manager: Optional[MemoryManager] = None
    stream_callback: Optional[Callable[[str], Any]] = None
    chat_mode: bool = False
    strategy: Optional[str] = None
    enable_reflection: bool = False
    reflection_trigger_errors: int = 2
    memory_backend: str = "keyword"
    long_term_memory_path: Optional[str] = None
    embedding_provider: Optional[str] = None
    llm_provider: Optional[Any] = None  # 用于构造 compactor；None 时压缩回退到截断
    enable_summary_compaction: bool = False  # 开关：True 才启用 LLM 摘要压缩
    event_bus: Optional[Any] = None  # TraceEventBus，harness 用其发布 chat.* 事件
    approval_policy: Optional[ApprovalPolicy] = None
    execution_ledger: Optional[Any] = None

    def __post_init__(self) -> None:
        if self.budget is None:
            self.budget = AgentBudget(max_steps=self.max_steps)

        if self.constraints is None:
            self.constraints = ConstraintSet()

        if self.feedback_loop is None:
            self.feedback_loop = FeedbackLoop()

        if self.continuous_improvement is None:
            self.continuous_improvement = ContinuousImprovement()

        if self.memory_manager is None:
            self.memory_manager = MemoryManager()

        # OPT-4: 记忆后端配置
        if self.memory_backend == "embedding" and self.embedding_provider:
            from src.core.agents.state.memory.backends import EmbeddingRetriever
            embed_fn = self._resolve_embed_fn(self.embedding_provider)
            if embed_fn:
                self.memory_manager.retriever = EmbeddingRetriever(embed_fn=embed_fn)
        if self.long_term_memory_path:
            from pathlib import Path
            from src.core.agents.state.memory.long_term import LongTermMemory
            self.memory_manager.long_term = LongTermMemory(Path(self.long_term_memory_path))

        if self.thinker is None:
            compactor = None
            if self.enable_summary_compaction and self.llm_provider is not None:
                from src.core.agents.state.context.compactor import build_llm_compactor
                compactor = build_llm_compactor(self.llm_provider)
            context_manager = ContextWindowManager(
                max_tokens=self.max_context_tokens,
                model=self.llm_model,
                compactor=compactor,
            )
            knowledge_selector = KnowledgeSelector(self.registry)
            prompt_assembler = PromptAssembler(
                knowledge_selector=knowledge_selector,
                chat_mode=self.chat_mode,
            )
            self.thinker = Think(
                self.planner,
                context_manager=context_manager,
                prompt_assembler=prompt_assembler,
                memory_manager=self.memory_manager,
                is_cancelled=self.is_cancelled,
                stream_callback=self.stream_callback,
                event_bus=self.event_bus,
            )

        if self.actor is None:
            if self.permission_guard is not None:
                self.executor.permission_guard = self.permission_guard
            self.actor = Act(
                registry=self.registry,
                executor=self.executor,
                tool_dependencies=self.tool_dependencies,
                context_builder=self.context_builder,
                max_tool_result_length=self.max_tool_result_length,
                is_cancelled=self.is_cancelled,
                event_bus=self.event_bus,
                execution_ledger=self.execution_ledger,
            )

        if self.observer is None:
            self.observer = Observe(
                abort_on_tool_error=self.abort_on_tool_error,
                max_consecutive_errors=self.max_consecutive_errors,
                memory_manager=self.memory_manager,
            )

        if self.harness is None:
            # 这些字段在上面的 __post_init__ 中已确保非 None
            assert self.thinker is not None
            assert self.actor is not None
            assert self.observer is not None
            assert self.budget is not None
            assert self.constraints is not None
            assert self.feedback_loop is not None
            assert self.continuous_improvement is not None

            # 解析策略
            strategy_instance = None
            if self.strategy:
                from .planning import resolve_strategy
                strategy_instance = resolve_strategy(self.strategy)

            self.harness = AgentLoopHarness(
                thinker=self.thinker,
                actor=self.actor,
                observer=self.observer,
                budget=self.budget,
                is_cancelled=self.is_cancelled,
                hooks=list(self.hooks or []),
                constraints=self.constraints,
                feedback_loop=self.feedback_loop,
                continuous_improvement=self.continuous_improvement,
                workflow=self.workflow,
                lifecycle=self.lifecycle,
                strategy=strategy_instance,
                event_bus=self.event_bus,
                approval_policy=self.approval_policy,
            )
        # OPT-3: 启用反思
        if self.enable_reflection:
            from src.core.agents.runtime.harness.reflection import ReflectionProvider
            self.feedback_loop.providers.append(
                ReflectionProvider(
                    planner=self.planner,
                    trigger_errors=self.reflection_trigger_errors,
                )
            )

        if self.router is None:
            self.router = TaskRouter(planner=self.planner)

    @staticmethod
    def _resolve_embed_fn(provider_name: str):
        """解析 embedding provider。复用 LLM provider 体系或独立 embedding API。"""
        if provider_name == "openai":
            try:
                from openai import AsyncOpenAI
                import os
                client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))

                async def embed(text: str):
                    resp = await client.embeddings.create(
                        model="text-embedding-3-small", input=text
                    )
                    return resp.data[0].embedding

                return embed
            except ImportError:
                return None
        # 简单 stub：mock embedding（供测试用）
        if provider_name == "mock":
            import hashlib

            async def mock_embed(text: str):
                h = hashlib.md5(text.encode()).digest()
                return [float(b) / 255.0 for b in h[:16]]

            return mock_embed
        return None

    async def run(
        self,
        goal: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        initial_state: Optional[Any] = None,
        approval_decision: Optional[ApprovalDecision] = None,
        reconciliation_decision: Optional[ReconciliationDecision] = None,
    ) -> AgentLoopResult:
        assert self.harness is not None
        return await self.harness.run(
            goal=goal,
            messages=messages,
            metadata=metadata,
            trace_id=trace_id,
            initial_state=initial_state,
            approval_decision=approval_decision,
            reconciliation_decision=reconciliation_decision,
        )

    async def run_with_routing(
        self,
        goal: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        trace_id: Optional[str] = None,
    ) -> AgentLoopResult:
        if not self.router:
            return await self.run(
                goal=goal, messages=messages, metadata=metadata, trace_id=trace_id
            )

        sub_goals = await self.router.route(goal)
        if len(sub_goals) <= 1:
            return await self.run(
                goal=goal, messages=messages, metadata=metadata, trace_id=trace_id
            )

        import time as _time

        total_started = _time.monotonic()
        accumulated_messages = list(messages or [])
        results: List[str] = []
        last_result: Optional[AgentLoopResult] = None
        total_steps = 0
        total_tool_calls = 0

        remaining_steps = self.max_steps

        for index, sub_goal in enumerate(sub_goals, start=1):
            if remaining_steps <= 0:
                break

            run_messages = list(accumulated_messages)
            if results:
                run_messages.append(
                    {
                        "role": "system",
                        "content": "Previous sub-goal results:\n" + "\n".join(results),
                    }
                )
            run_messages.append(
                {
                    "role": "system",
                    "content": f"Current sub-goal {index}/{len(sub_goals)}: {sub_goal}",
                }
            )

            # 为子任务创建独立 runner，避免共享预算竞态
            sub_runner = AgentLoopRunner(
                planner=self.planner,
                registry=self.registry,
                executor=self.executor,
                max_steps=min(remaining_steps, self.max_steps),
                abort_on_tool_error=self.abort_on_tool_error,
                max_tool_result_length=self.max_tool_result_length,
                max_consecutive_errors=self.max_consecutive_errors,
                max_context_tokens=self.max_context_tokens,
                llm_model=self.llm_model,
                permission_guard=self.permission_guard,
                is_cancelled=self.is_cancelled,
                lifecycle=self.lifecycle,
                tool_dependencies=self.tool_dependencies,
                context_builder=self.context_builder,
            )
            last_result = await sub_runner.run(
                goal=sub_goal,
                messages=run_messages,
                metadata=metadata,
                trace_id=trace_id,
            )

            results.append(last_result.final_answer or "")
            remaining_steps -= last_result.total_steps
            total_steps += last_result.total_steps
            total_tool_calls += last_result.tool_calls_count

            if not last_result.success:
                return last_result

        assert last_result is not None
        return AgentLoopResult(
            trace_id=last_result.trace_id,
            success=True,
            final_answer="\n\n".join(result for result in results if result),
            stop_reason=StopReason.MODEL_FINAL,
            total_steps=total_steps,
            tool_calls_count=total_tool_calls,
            duration_seconds=_time.monotonic() - total_started,
        )
