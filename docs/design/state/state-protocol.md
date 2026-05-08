# State & Protocol — 运行时状态与消息协议

> `src/core/agents/state/models.py` — `AgentLoopState`, `AgentLoopResult`, `StopReason`, `ToolCallRecord`, `AgentState`
> `src/core/agents/state/protocol/models.py` — `ToolCall`
> `src/core/agents/state/protocol/messages.py` — `assistant_message`, `tool_result_message`, `normalize_tool_calls`
> `src/core/agents/state/utils.py` — `generate_agent_trace_id`

---

## 为什么存在这个功能？

Agent 执行是一个多步骤的过程，每一步都需要追踪和维护状态：
- 当前执行到了第几步
- 消息历史（system/user/assistant/tool 消息列表）
- 哪些工具被调用了、参数是什么、返回了什么
- 是否有连续错误
- 是否被外部暂停/停止
- 最终的执行结果

如果没有统一的状态模型，这些信息会分散在 Think/Act/Observe 的局部变量中，难以跨阶段访问、难以序列化快照、难以在 hook 中观测。

## 为什么选这个设计？

**Dataclass 状态对象 + 不可变消息列表 + 协议层做格式转换**：

- `AgentLoopState` 是一个 dataclass，包含执行所需的所有可变状态
- `messages` 是 `List[Dict[str, Any]]`，每轮 Think/Act/Observe 追加消息（append-only）
- `ToolCall` 是标准化的内部工具调用表示，`normalize_tool_calls()` 负责从 OpenAI/Claude 格式转换
- `AgentLoopResult` 是不可变的执行结果 dataclass，在运行结束后构建

对比可选方案：
- 用数据库存储状态：太重，每条消息都写 DB 增加延迟
- 用事件溯源（Event Sourcing）：对单 Agent 场景过度设计
- 用上下文变量（ContextVar）：不支持跨协程共享和序列化

## 解决什么问题？

1. **状态可追踪** — `trace_id` 贯穿整个执行链路
2. **快照可序列化** — `AgentLoopState` 是 dataclass，可以直接 JSON 序列化为快照
3. **Provider 格式差异屏蔽** — 内部统一用 `ToolCall`，外部 OpenAI/Claude 格式差异由 `normalize_tool_calls` 处理
4. **停止原因明确** — `StopReason` 枚举覆盖所有终止场景

## 核心数据模型

### AgentLoopState — 执行时状态

```python
@dataclass
class AgentLoopState:
    goal: str                                    # 任务目标
    messages: List[Dict[str, Any]]               # 消息历史
    max_steps: int = 8                           # 最大步数
    trace_id: str = ""                           # 追踪 ID

    # 运行时状态
    step: int = 0                                # 当前步数
    stop_reason: Optional[StopReason] = None     # 终止原因
    final_answer: Optional[str] = None           # 最终答案
    consecutive_tool_errors: int = 0             # 连续工具错误计数

    # 工具调用记录
    tool_calls: List[ToolCallRecord]             # 完整的工具调用历史

    # 生命周期
    lifecycle_state: AgentState | None = None    # 当前生命周期状态
```

### AgentLoopResult — 执行结果

```python
@dataclass
class AgentLoopResult:
    trace_id: str                    # 追踪 ID
    success: bool                    # 是否成功
    final_answer: Optional[str]      # 最终答案
    stop_reason: Optional[StopReason]# 终止原因
    total_steps: int                 # 总步数
    tool_calls_count: int            # 工具调用次数
    duration_seconds: float          # 执行耗时
```

### ToolCall — 标准化工具调用

```python
@dataclass
class ToolCall:
    id: str                          # 调用 ID
    name: str                        # 工具名
    arguments: Dict[str, Any]        # 参数
```

### StopReason — 终止原因枚举

```
MODEL_FINAL          → LLM 给出最终答案（正常）
MAX_STEPS            → 达到最大步数
BUDGET_EXHAUSTED     → 预算耗尽
LLM_ERROR_ABORT      → LLM 调用失败
TOOL_ERROR_ABORT     → 工具连续失败
USER_CANCELLED       → 用户取消
USER_PAUSED          → 用户暂停
CONSTRAINT_VIOLATION → 约束违反
ERROR                → 未知错误
```

## 在 Agent 流程中承担什么责任？

```
AgentLoopHarness.run(goal) 开始时：
  └─ 创建 AgentLoopState(goal=goal, messages=[...], trace_id=..., max_steps=...)

每轮 Think → Act → Observe：
  ├─ Think:   state.messages 被 PromptAssembler + ContextWindowManager 处理后传给 LLM
  ├─ Act:     state.tool_calls.append(ToolCallRecord(...)) + state.messages.append(tool_result)
  └─ Observe: 设置 state.stop_reason / state.consecutive_tool_errors

运行结束时：
  └─ AgentLoopResult(success=state.stop_reason==MODEL_FINAL, ...)
```

## 消息格式

### assistant_message

```python
def assistant_message(content, tool_calls=None):
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,  # 可选
    }
```

### tool_result_message

```python
def tool_result_message(tool_call_id, content, name=None, is_error=False):
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
        "name": name,
        "is_error": is_error,
    }
```

### normalize_tool_calls — 格式适配

```python
# OpenAI 格式 → 内部 ToolCall
normalize_tool_calls([
    {
        "id": "call_123",
        "function": {"name": "db_query", "arguments": '{"query": "SELECT 1"}'}
    }
])
# → [ToolCall(id="call_123", name="db_query", arguments={"query": "SELECT 1"})]

# Claude 格式 → 内部 ToolCall（自动识别并转换）
```

## 技术栈

- Python dataclass + Enum
- JSON 序列化
- `generate_agent_trace_id()` — `agent-<uuid12>` 格式

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| `state.messages` 无限增长 | 配合 ContextWindowManager 压缩，但原始 state 不修改 |
| `ToolCallRecord` 与 `ToolCall` 是两个不同类，职责重叠 | 统一为一个 `ToolCall` 类 |
| `normalize_tool_calls` 的 Claude 格式识别依赖 content block 结构 | 需要显式标记 provider 类型以跳过格式猜测 |
| messages 用 `Dict[str, Any]` 而非强类型 | 用 TypedDict 或 Pydantic model |

## 使用案例

### 查看执行结果详情

```python
result = await agent.run("查询昨天的订单")

print(f"trace_id: {result.trace_id}")
print(f"success: {result.success}")
print(f"stop_reason: {result.stop_reason}")
print(f"steps: {result.total_steps}")
print(f"tool calls: {result.tool_calls_count}")
print(f"duration: {result.duration_seconds:.2f}s")

if not result.success:
    # 根据 stop_reason 做不同的重试策略
    if result.stop_reason == StopReason.MAX_STEPS:
        agent.config.max_steps = 20  # 增加步数重试
    elif result.stop_reason == StopReason.TOOL_ERROR_ABORT:
        print("检查工具依赖是否正常")
```

### 在 hook 中观测状态变化

```python
async def state_logger(event):
    state = event.state
    print(f"[{event.name}] step={state.step}/{state.max_steps} "
          f"errors={state.consecutive_tool_errors} "
          f"lifecycle={state.lifecycle_state} "
          f"msgs={len(state.messages)}")

runner = AgentLoopRunner(..., hooks=[state_logger])
```

### 生成 trace_id

```python
from src.core.agents.state import generate_agent_trace_id

trace_id = generate_agent_trace_id()
# → "agent-a1b2c3d4e5f6"

# 在 run 时传入自定义 trace_id
result = await agent.run("任务", trace_id="my-custom-trace-001")
```
