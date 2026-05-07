"""
Core Agents - Agent 系统

新架构：
├── engine/          - 控制层（Agent 大脑）
├── capabilities/  - 能力层（LLM, Tools, Skills）
├── state/         - 状态层（State, Protocol, Context, Memory）
├── execution/     - 执行层（Executor, Router, Dispatcher）
├── runtime/       - 运行时环境（Session, Env, Hooks, Harness）
└── multi_agents/   - 多 Agent 系统（预留）
"""

# 主要接口 - 从 engine 导出
from .engine.agent import Agent, AgentConfig
from .engine.lifecycle import LifecycleManager
from .engine.types import (
    ActionType,
    ThoughtType,
    Thought,
    Action,
    Observation,
    Step,
)
from .engine.loop import Think, Act, Observe, AssistantPlanner

# 状态层 - 从 state 导出
from .state import (
    AgentState,
    StateTransition,
    StopReason,
    ToolCallRecord,
    AgentLoopState,
    AgentLoopResult,
    generate_agent_trace_id,
    ToolCall,
    assistant_message,
    tool_result_message,
    get_tool_calls,
    normalize_tool_calls,
    ContextWindowManager,
    ShortTermMemory,
    LongTermMemory,
    MemoryEntry,
    StateSnapshot,
)

# 能力层 - 从 capabilities 导出
from .capabilities import (
    Skill,
    SkillType,
    RiskLevel,
    SkillContext,
    SkillExecutor,
    SkillRegistry,
    skill,
    get_global_registry,
    load_skills_from_dir,
    PermissionGuard,
    load_agentic_tools,
    TOOL_AREAS,
    DEFAULT_TOOL_AREAS,
    DeepSeekPlanner,
    DeepSeekSettings,
)
from .capabilities.registry import CapabilityRegistry, get_global_capability_registry

# 执行层 - 从 execution 导出
from .execution import (
    ExecutionStatus,
    ExecutionResult,
    ToolExecutionResult,
    SkillExecutionResult,
    Dispatcher,
)

# 运行时 - 从 runtime 导出
from .runtime.hooks import Hook, LoggingHook, TracingHook, HookContext
from .runtime.harness.runner import HarnessRunner, RunnerConfig
from .runtime.harness.debugger import Debugger, TraceEvent
from .runtime.harness.evaluator import Evaluator, EvaluationResult, EvaluationMetric
from .runtime.harness.fixtures import FixtureManager, MockTool

# 多 Agent - 从 multi_agent 导出
from .multi_agent import (
    MultiAgentCoordinator,
    MessageType,
    MessagePriority,
    Message,
    MessageBus,
    MessageHandler,
    TaskAssignment,
)

__all__ = [
    # Core
    "Agent",
    "AgentConfig",
    "LifecycleManager",
    "ActionType",
    "ThoughtType",
    "Thought",
    "Action",
    "Observation",
    "Step",
    "Think",
    "Act",
    "Observe",
    "AssistantPlanner",
    # State
    "AgentState",
    "StateTransition",
    "StopReason",
    "ToolCallRecord",
    "AgentLoopState",
    "AgentLoopResult",
    "generate_agent_trace_id",
    "ToolCall",
    "assistant_message",
    "tool_result_message",
    "get_tool_calls",
    "normalize_tool_calls",
    "ContextWindowManager",
    "ShortTermMemory",
    "LongTermMemory",
    "MemoryEntry",
    "StateSnapshot",
    # Capabilities
    "Skill",
    "SkillType",
    "RiskLevel",
    "SkillContext",
    "SkillExecutor",
    "SkillRegistry",
    "skill",
    "get_global_registry",
    "load_skills_from_dir",
    "PermissionGuard",
    "load_agentic_tools",
    "TOOL_AREAS",
    "DEFAULT_TOOL_AREAS",
    "DeepSeekPlanner",
    "DeepSeekSettings",
    "CapabilityRegistry",
    "get_global_capability_registry",
    # Execution
    "ExecutionStatus",
    "ExecutionResult",
    "ToolExecutionResult",
    "SkillExecutionResult",
    "Dispatcher",
    # Runtime
    "Hook",
    "LoggingHook",
    "TracingHook",
    "HookContext",
    "HarnessRunner",
    "RunnerConfig",
    "Debugger",
    "TraceEvent",
    "Evaluator",
    "EvaluationResult",
    "EvaluationMetric",
    "FixtureManager",
    "MockTool",
    # Multi-Agent
    "MultiAgentCoordinator",
    "MessageType",
    "MessagePriority",
    "Message",
    "MessageBus",
    "MessageHandler",
    "TaskAssignment",
]
