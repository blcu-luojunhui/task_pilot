# Error Recovery: LLM 自决策

> Replace hard abort on tool error with consecutive error tracking, letting the LLM decide recovery strategy.

## 背景 (Background)

当前实现中 `abort_on_tool_error=True` 意味着任何一次工具执行失败都会立即终止整个 agent loop。这过于激进：

1. 很多工具错误是临时性的（网络超时、参数格式错误）
2. LLM 有能力根据错误信息调整策略（换参数重试、换工具、直接给出答案）
3. 一次失败就终止浪费了前面所有步骤的计算成本

参考 Claude Code 的做法：错误信息作为 tool result 返回给 LLM，由 LLM 自行决定下一步。只有连续多次失败才强制终止，防止无限循环。

## 设计 (Design)

### 核心逻辑

将 `abort_on_tool_error` 默认改为 `False`，新增 `max_consecutive_errors` 参数。Observe 阶段追踪连续错误次数：

```python
# Observe.run() 中的新逻辑
has_errors = any(r.get("is_error") for r in tool_results)
if has_errors:
    state.consecutive_tool_errors += 1
else:
    state.consecutive_tool_errors = 0

# 仅在以下情况终止：
# 1. 显式开启 abort_on_tool_error（向后兼容）
# 2. 连续错误达到阈值
if self.abort_on_tool_error and has_errors:
    state.stop_reason = StopReason.TOOL_ERROR_ABORT
elif state.consecutive_tool_errors >= self.max_consecutive_errors:
    state.stop_reason = StopReason.TOOL_ERROR_ABORT
```

### 配置项

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `abort_on_tool_error` | `bool` | `False` | 是否在首次工具错误时立即终止 |
| `max_consecutive_errors` | `int` | `3` | 连续工具错误达到此阈值时强制终止 |

### 影响范围

| 文件 | 改动 |
|------|------|
| `src/core/agents/loop/state/__init__.py` | 新增 `consecutive_tool_errors: int = 0` 字段 |
| `src/core/agents/loop/observe/__init__.py` | 改写终止逻辑，支持连续错误计数 |
| `src/core/agents/loop/runner.py` | 默认值改为 `False`，新增 `max_consecutive_errors` 参数 |

### 错误恢复流程

```
Tool 执行失败
  → 错误信息作为 tool result 返回
  → consecutive_tool_errors += 1
  → 检查是否达到阈值
    → 未达到: 继续下一轮 Think（LLM 看到错误后自行决策）
    → 已达到: 设置 TOOL_ERROR_ABORT 终止

Tool 执行成功
  → consecutive_tool_errors = 0（重置计数器）
```

## 向后兼容 (Backward Compatibility)

- 显式传入 `abort_on_tool_error=True` 的调用方行为不变
- 默认行为从"首次错误终止"变为"连续 3 次错误终止"
- `max_consecutive_errors` 设为 1 等价于旧的 `abort_on_tool_error=True` 行为

## 测试策略 (Testing)

1. 单次工具错误 → 不终止，LLM 继续执行
2. 连续 3 次错误 → 终止
3. 错误后成功 → 计数器重置，不终止
4. `abort_on_tool_error=True` → 首次错误立即终止（向后兼容）
5. 自定义 `max_consecutive_errors` 生效
