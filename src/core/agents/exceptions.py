"""
Agent 统一异常体系

所有 Agent 相关的异常都继承自 AgentError，
调用方可以按层次捕获不同类型的错误。
"""


class AgentError(Exception):
    """Agent 系统基础异常"""
    pass


# ==================== 配置相关 ====================

class AgentConfigError(AgentError):
    """Agent 配置错误"""
    pass


# ==================== LLM 相关 ====================

class LLMError(AgentError):
    """LLM 调用基础异常"""
    pass


class LLMProviderError(LLMError):
    """LLM Provider 调用失败（网络、认证等）"""

    def __init__(self, provider: str, message: str, status_code: int = 0):
        self.provider = provider
        self.status_code = status_code
        super().__init__(f"[{provider}] {message} (status={status_code})")


class LLMRateLimitError(LLMProviderError):
    """LLM 速率限制"""

    def __init__(self, provider: str, retry_after: float = 0):
        self.retry_after = retry_after
        super().__init__(provider, f"Rate limit exceeded, retry after {retry_after}s", 429)


class LLMTimeoutError(LLMError):
    """LLM 调用超时"""
    pass


class LLMResponseError(LLMError):
    """LLM 响应格式异常（无法解析）"""
    pass


# ==================== 执行相关 ====================

class ExecutionError(AgentError):
    """执行层异常"""
    pass


class ToolExecutionError(ExecutionError):
    """工具执行失败"""

    def __init__(self, tool_name: str, message: str, original_error: Exception = None):
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(f"Tool '{tool_name}' failed: {message}")


class ToolPermissionError(ExecutionError):
    """工具权限被拒绝"""

    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"Tool '{tool_name}' denied: {reason}")


class ToolNotFoundError(ExecutionError):
    """工具未找到"""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found in registry")


# ==================== 路由相关 ====================

class RoutingError(AgentError):
    """任务路由异常"""
    pass


# ==================== 生命周期相关 ====================

class LifecycleError(AgentError):
    """生命周期状态转换异常"""

    def __init__(self, from_state: str, to_state: str):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(f"Cannot transition from {from_state} to {to_state}")


# ==================== 多 Agent 相关 ====================

class CoordinationError(AgentError):
    """多 Agent 协调异常"""
    pass


class MessageDeliveryError(CoordinationError):
    """消息投递失败"""

    def __init__(self, receiver: str, reason: str):
        self.receiver = receiver
        super().__init__(f"Failed to deliver message to '{receiver}': {reason}")


__all__ = [
    "AgentError",
    "AgentConfigError",
    # LLM
    "LLMError",
    "LLMProviderError",
    "LLMRateLimitError",
    "LLMTimeoutError",
    "LLMResponseError",
    # Execution
    "ExecutionError",
    "ToolExecutionError",
    "ToolPermissionError",
    "ToolNotFoundError",
    # Routing
    "RoutingError",
    # Lifecycle
    "LifecycleError",
    # Multi-Agent
    "CoordinationError",
    "MessageDeliveryError",
]
