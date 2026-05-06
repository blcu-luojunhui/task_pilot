# Parallel Tool Execution

> Execute multiple tool calls concurrently using asyncio.gather for reduced latency.

## 背景 (Background)

当 LLM 在一次响应中返回多个 tool calls 时，当前实现逐个串行执行。如果每个工具调用耗时 1 秒，3 个工具就需要 3 秒。这些工具调用是 LLM 在同一轮决策中选择的，天然互相独立，可以并发执行。

参考 Claude Code 的做法：同一轮中的多个 tool calls 并行执行，总耗时等于最慢的那个工具。

## 设计 (Design)

### 核心逻辑

用 `asyncio.gather` 替换 `Act.run()` 中的串行 for 循环：

```python
async def run(self, state: AgentLoopState, tool_calls: List[ToolCall]) -> List[Dict[str, Any]]:
    if len(tool_calls) == 1:
        return [await self._execute_one(state, tool_calls[0])]

    tasks = [self._execute_one(state, call) for call in tool_calls]
    return list(await asyncio.gather(*tasks))
```

### 安全性分析

| 关注点 | 结论 |
|--------|------|
| 异常传播 | `_execute_one` 内部已捕获所有异常并返回 error dict，不会抛出 |
| 数据竞争 | asyncio 单线程事件循环，`list.append` 是安全的 |
| 结果顺序 | `asyncio.gather` 保证结果顺序与输入顺序一致 |
| 单个失败影响 | 不影响其他工具执行，每个工具独立处理错误 |

### 配置项

无需新增配置。并行执行是纯粹的性能优化，行为语义不变。

### 影响范围

| 文件 | 改动 |
|------|------|
| `src/core/agents/loop/act/__init__.py` | 修改 `run` 方法，引入 `asyncio` |

### 性能收益

假设一轮中有 N 个工具调用，每个平均耗时 T：
- 串行：总耗时 = N × T
- 并行：总耗时 ≈ max(T₁, T₂, ..., Tₙ) ≈ T

对于 HTTP 请求、数据库查询等 I/O 密集型工具，收益尤为明显。

## 向后兼容 (Backward Compatibility)

- 单个 tool call 时走原路径，行为完全不变
- 多个 tool calls 时结果顺序与输入顺序一致
- `tool_call_history` 中记录的顺序可能与串行时不同（不影响功能）

## 测试策略 (Testing)

1. 单个 tool call → 正常执行
2. 多个 tool calls → 并发执行，总耗时接近单个最慢工具的耗时
3. 部分工具失败 → 不影响其他工具，各自独立返回结果
4. 所有工具失败 → 全部返回 error dict
