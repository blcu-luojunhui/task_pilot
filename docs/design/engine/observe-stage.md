# Observe 阶段 — 停止判断与错误恢复

> `src/core/agents/engine/loop.py` — `Observe`

---

## 为什么存在这个功能？

Act 阶段执行完工具后，Agent 需要决定：是继续下一轮 Think，还是终止执行？这个决策不能交给 LLM（LLM 可能无限循环），也不能用简单规则（一次失败就终止过于粗暴）。

Observe 阶段负责**基于本轮结果判断是否应该停止，以及记录连续错误计数**。

## 为什么选这个设计？

**连续错误追踪 + 多条件停止判断**：

- 非终止条件（本轮有 tool call 或 content → 追加到消息历史，继续循环）
- 连续错误计数：本轮至少一个工具失败 → `consecutive_tool_errors += 1`；全部成功 → 重置为 0
- 终止条件优先级：`abort_on_tool_error` (即时) → `consecutive_tool_errors >= max_consecutive_errors` → LLM 返回 `content` 且无 `tool_calls` 视为最终答案

对比可选方案：
- 让 LLM 自行声明"我完成了"：LLM 可能不声明或错误声明
- 任何错误立即终止：过于激进，一次网络超时就终止是浪费

## 解决什么问题？

1. **LLM 自主恢复** — 工具失败后，LLM 在下一轮 Think 可以看到错误信息并调整策略
2. **防止无限循环** — 连续 N 次失败后强制终止
3. **明确的终止语义** — 7 种 StopReason 精确表达终止原因

## 在 Agent 流程中承担什么责任？

```
Harness 主循环
  │
  └─ Observe.run(state, assistant_message, tool_results)
       │
       ├─ 记录 assistant_message 到 state.messages
       ├─ 记录 tool_results 到 state.messages
       │
       ├─ 更新连续错误计数：
       │    has_errors = any(r.get("is_error") for r in tool_results)
       │    if has_errors: state.consecutive_tool_errors += 1
       │    else:          state.consecutive_tool_errors = 0
       │
       ├─ 停止判断：
       │    ├─ abort_on_tool_error && has_errors → TOOL_ERROR_ABORT
       │    ├─ consecutive_tool_errors >= max_consecutive_errors → TOOL_ERROR_ABORT
       │    ├─ 有 content 且无 tool_calls → MODEL_FINAL（正常完成）
       │    └─ 其他 → 不设置 stop_reason，继续下一轮
       │
       └─ 返回 → Harness 检查 state.is_terminated()
```

## StopReason 完整枚举

| 值 | 触发条件 | 触发位置 |
|----|----------|----------|
| `MODEL_FINAL` | LLM 返回 content 且无 tool_calls | Observe |
| `MAX_STEPS` | 达到 max_steps | Budget / WorkflowController |
| `BUDGET_EXHAUSTED` | 超时或 tool_calls 超限 | Budget / WorkflowController |
| `LLM_ERROR_ABORT` | LLM API 调用失败 | Think |
| `TOOL_ERROR_ABORT` | 连续工具错误或 abort_on_tool_error | Observe |
| `USER_CANCELLED` | 外部调用 stop() | LifecycleManager / Harness |
| `USER_PAUSED` | 外部调用 pause()（v3 新增） | Harness |
| `CONSTRAINT_VIOLATION` | 约束规则被触发 | WorkflowController |
| `ERROR` | 未捕获的异常 | Harness (try/except) |

## 错误恢复流程

```
Tool 执行失败
  → 错误信息作为 tool result 返回给 LLM（is_error=True）
  → consecutive_tool_errors += 1
  → 检查阈值：
      ✗ 未达到 → 继续 Think（LLM 看到错误后可调整策略）
      ✓ 已达到 → TOOL_ERROR_ABORT 终止

Tool 执行成功
  → consecutive_tool_errors = 0（重置）
```

## 技术栈

- Python dataclass
- `AgentLoopState` 上的 `consecutive_tool_errors` 计数器
- `StopReason` 枚举

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| 只追踪"连续"错误，不区分错误类型 | 按错误类型分类计数（网络错误 vs 权限错误 vs 参数错误），不同类型阈值不同 |
| `MODEL_FINAL` 判断依赖 LLM 不返回 tool_calls | 可能误判——LLM 忘了调用工具就直接给了答案。可增加 confidence 检查 |
| 错误恢复完全依赖 LLM 自行决策 | 增加预置恢复策略（如网络错误 → 自动重试 1 次） |
| terminal 判断逻辑散落在 Observe + Workflow + Think 中 | 统一到 `StopReasonEvaluator` |

## 使用案例

### 调整错误容忍度

```python
runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    abort_on_tool_error=True,     # 任意工具错误立即终止
    max_consecutive_errors=1,     # 等效效果
)
```

### 宽松错误策略（生产推荐）

```python
runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    abort_on_tool_error=False,    # 不立即终止
    max_consecutive_errors=5,     # 连续 5 次失败才终止
)
```

### 检查运行结果

```python
result = await agent.run("查询订单数据")

print(f"成功: {result.success}")
print(f"终止原因: {result.stop_reason}")
print(f"总步数: {result.total_steps}")
print(f"工具调用次数: {result.tool_calls_count}")

if result.stop_reason == StopReason.TOOL_ERROR_ABORT:
    print("工具连续失败，需要检查工具依赖是否正常")
elif result.stop_reason == StopReason.MAX_STEPS:
    print("步数不够，考虑增加 max_steps 或优化 prompt")
elif result.stop_reason == StopReason.MODEL_FINAL:
    print("正常完成")
```
