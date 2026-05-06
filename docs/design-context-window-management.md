# Context Window Management

> Prevent context overflow by estimating token usage and compacting messages when approaching limits.

## 背景 (Background)

当前 agent loop 的消息列表无限增长。每一轮 Think/Act/Observe 都会向 `state.messages` 追加 assistant message 和 tool results。对于多步骤任务（8 步 × 每步可能多个工具调用），消息总量很容易超出 LLM 的 context window（DeepSeek 为 64K tokens）。

超出后 API 会直接报错，导致整个任务失败。即使不超出，过长的上下文也会：
1. 增加 API 调用延迟和成本
2. 降低 LLM 对关键信息的注意力

参考 Claude Code 的做法：在调用 LLM 前检测 token 用量，接近上限时自动压缩历史消息。

## 设计 (Design)

### 核心组件

新建 `ContextWindowManager` 类，负责 token 估算和消息压缩：

```python
@dataclass
class ContextWindowManager:
    max_context_tokens: int = 60000
    chars_per_token: float = 4.0
    preserve_recent_messages: int = 6

    def estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        ...

    def compact_if_needed(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ...
```

### Token 估算策略

使用字符数除以 `chars_per_token` 的简单估算，避免引入 tokenizer 依赖：
- 中英文混合场景下，~4 chars/token 是合理的近似值
- 对 message 的 content 和 tool_calls 的 arguments 都计入
- 不需要精确，只需要在 80-120% 精度范围内防止溢出

### 压缩策略

当估算 token 数超过 `max_context_tokens` 时触发压缩：

1. 保留所有 system messages（不可丢弃）
2. 保留第一条 user message（包含 goal）
3. 保留最近 `preserve_recent_messages` 条消息（LLM 需要最新上下文）
4. 中间部分替换为一条摘要占位消息

```
[system messages] + [first user msg] + [summary placeholder] + [last N messages]
```

### 集成点

在 `Think.run()` 中，调用 planner 之前对 messages 做 compaction：

```python
@dataclass
class Think:
    planner: AssistantPlanner
    context_manager: Optional[ContextWindowManager] = None

    async def run(self, state: AgentLoopState) -> Optional[Dict[str, Any]]:
        messages = state.messages
        if self.context_manager:
            messages = self.context_manager.compact_if_needed(messages)
        try:
            return await self.planner(messages, state.step)
        ...
```

注意：compaction 只影响传给 LLM 的消息副本，`state.messages` 保持完整（用于审计和调试）。

### 配置项

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_context_tokens` | `int` | `60000` | 触发压缩的 token 阈值 |
| `chars_per_token` | `float` | `4.0` | 字符到 token 的估算比率 |
| `preserve_recent_messages` | `int` | `6` | 压缩时保留的最近消息数 |

### 影响范围

| 文件 | 改动 |
|------|------|
| `src/core/agents/loop/context/__init__.py` | 新建，ContextWindowManager 实现 |
| `src/core/agents/loop/think/__init__.py` | 注入 ContextWindowManager，调用前做 compaction |
| `src/core/agents/loop/runner.py` | 组装 ContextWindowManager 并传入 Think |

## 向后兼容 (Backward Compatibility)

- `context_manager` 默认为 `None`，不传则不做任何压缩（行为与之前完全一致）
- 通过 `AgentLoopRunner` 的 `max_context_tokens` 参数启用
- 压缩不修改 `state.messages`，只影响传给 LLM 的副本

## 测试策略 (Testing)

1. 消息总量未超限 → 不压缩，原样传递
2. 消息总量超限 → 触发压缩，保留 system + first user + last N
3. 压缩后的消息包含摘要占位符
4. `state.messages` 不被修改（只压缩副本）
5. 极端情况：消息数 <= preserve_recent_messages + 1 → 无法压缩，原样传递
