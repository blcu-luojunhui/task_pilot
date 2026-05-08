# AgentLoopHarness — 主循环引擎与运行时治理

> `src/core/agents/runtime/harness/harness.py` — `AgentLoopHarness`
> `src/core/agents/runtime/harness/workflow.py` — `WorkflowController`
> `src/core/agents/runtime/harness/budget.py` — `AgentBudget`
> `src/core/agents/runtime/harness/constraints.py` — `ConstraintSet`
> `src/core/agents/runtime/harness/feedback.py` — `FeedbackLoop`
> `src/core/agents/runtime/harness/improvement.py` — `ContinuousImprovement`

---

## 为什么存在这个功能？

Agent 的核心是一个 Think → Act → Observe 循环，但这个循环不是"裸跑"的——它需要被运行时治理机制包裹：

1. **预算控制** — 最多几步、多少 tool call、多长时间，超出即停
2. **约束检查** — 某些操作在特定 phase 不允许（如禁止在最终轮调用写工具）
3. **生命周期检查** — 每步检查是否被外部暂停/停止
4. **反馈注入** — 在步骤间插入系统级提示（"你已经执行了 5 步，请尽快给出答案"）
5. **持续改进** — 记录每次运行的统计数据（步数、耗时、错误次数）用于后续分析
6. **事件发射** — 每步的前后、每个阶段的前后发出事件，供 hook 监听

如果没有 Harness 这一层，这些横切关注点会散落在 Think/Act/Observe 的具体实现中，导致核心逻辑与治理逻辑混杂。

## 为什么选这个设计？

**Harness 作为循环持有者 + Controller 作为策略决策者**：

- `AgentLoopHarness` 持有 Think/Act/Observe 的引用，驱动主循环，负责事件发射
- `WorkflowController` 在每个决策点（before_step / after_think / before_act / after_step）被调用，统一返回 `WorkflowDecision`（包含 stop_reason + event_name），Harness 只负责执行决策
- `AgentBudget` 做计数量检查（step 数、tool call 数、耗时）——纯函数，无副作用
- `ConstraintSet` 做声明式规则检查——每个 `Constraint` 是一个 `check(phase, state, payload) -> Optional[ConstraintViolation]` 函数
- `FeedbackLoop` 做步骤间系统提示注入
- `ContinuousImprovement` 做事后数据采集

对比可选方案：
- 将治理逻辑放在 Think/Act/Observe 内部：破坏单一职责，且无法跨阶段协调（如 before_step 需要看到 budget + constraints + lifecycle 的综合判断）
- 用装饰器/中间件链：asyncio 下装饰器对协程的包装不够灵活，且难以在不同决策点注入不同逻辑

## 解决什么问题？

1. **横切关注点集中管理** — 预算、约束、反馈、生命周期等统一在 Harness 层级处理
2. **可扩展的决策点** — 15 种事件 + 4 个 workflow 决策点，hook 可以在任意位置介入
3. **预算溢出自动终止** — 达到 max_steps / max_duration / max_tool_calls 时自动设置 stop_reason
4. **约束违反即时拦截** — 在工具执行前（before_act）可以拦截不合规操作

## 在 Agent 流程中承担什么责任？

```
AgentLoopHarness.run(goal)
  │
  ├─ emit("run_start")
  ├─ 同步 lifecycle 初始状态
  │
  └─ while not state.is_terminated():
       │
       ├─ ★ lifecycle.wait_if_paused()        ← 暂停检查
       ├─ ★ lifecycle.is_stop_requested()      ← 停止检查
       │
       ├─ workflow.before_step(state, elapsed)  ← 预算/约束/超时
       │    └─ AgentBudget.check_before_step()
       │    └─ ConstraintSet.check("before_step")
       │
       ├─ emit("step_start")
       │
       ├─ Think:  thinker.run(state)           ← LLM 调用
       │
       ├─ workflow.after_think(state, msg)     ← 检查 LLM 响应
       │
       ├─ workflow.before_act(state, msg)      ← 约束检查（如禁止写操作）
       │
       ├─ Act:    actor.run(state, tool_calls) ← 工具执行
       ├─ Observe: observer.run(state)          ← 停止判断
       │
       ├─ FeedbackLoop.run(state, payload)     ← 注入系统反馈
       │
       ├─ workflow.after_step(state, ...)      ← 步后检查
       │
       └─ emit("step_end")
  │
  ├─ ContinuousImprovement.capture(state, result)
  └─ emit("run_end")
```

## 各子组件职责

| 组件 | 职责 | 决策时机 |
|------|------|----------|
| **AgentBudget** | 限制 max_steps / max_tool_calls / max_duration_seconds | before_step / after_think / after_step |
| **ConstraintSet** | 声明式规则检查（匹配 phase + 条件 → Violation） | before_step / before_act / after_think / after_step |
| **WorkflowController** | 聚合 Budget + Constraints + is_cancelled，统一返回 WorkflowDecision | 4 个决策点 |
| **FeedbackLoop** | 步骤间注入系统提示（如步骤计数警告） | 每步 After Observe |
| **ContinuousImprovement** | 记录运行统计数据到 store | 运行结束后 |

## 技术栈

- Python dataclass + `asyncio` 协程
- `time.monotonic()` 做时间预算检查（不受系统时间调整影响）
- `HarnessEvent` + `HarnessHook` 实现发布/订阅风格的事件系统
- `inspect.isawaitable()` 兼容同步和异步 hook 函数

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| 主循环逻辑偏长（~180 行 `run()` 方法） | 将决策点提取为 `_step_decision()` 等子方法 |
| 事件发射是同步的（`asyncio.gather` 而非 fire-and-forget） | 对非关键 hook 使用 `asyncio.create_task` 异步发射 |
| `ContinuousImprovement` 默认不存储（store=None 则跳过） | 默认使用 `InMemoryImprovementStore`，方便开发调试 |
| 决策点虽然多但都是顺序检查 | 允许并行检查 budget + constraints（当前没有互相依赖） |
| 缺少 metric 暴露 | 在决策点增加 counter 指标，方便监控 |

## 使用案例

### 自定义预算

```python
from src.core.agents.runtime.harness import AgentBudget

budget = AgentBudget(
    max_steps=3,
    max_tool_calls=6,
    max_duration_seconds=45.0,
)

runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    budget=budget,
)
```

### 添加约束规则

```python
from src.core.agents.runtime.harness import ConstraintSet, ConstraintViolation

constraints = ConstraintSet()

# 禁止在 step > 5 后执行写操作
def block_write_after_step5(phase, state, payload):
    if phase == "before_act" and state.step > 5:
        msg = payload.get("assistant_message", {})
        tool_calls = msg.get("tool_calls", [])
        for tc in tool_calls:
            if "execute" in tc.get("function", {}).get("name", ""):
                return ConstraintViolation(
                    stop_reason=StopReason.CONSTRAINT_VIOLATION,
                    message="Step > 5, write operations blocked"
                )
    return None

constraints.add_rule("before_act", block_write_after_step5)

runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    constraints=constraints,
)
```

### 自定义反馈注入

```python
from src.core.agents.runtime.harness import FeedbackLoop

def step_warning(state, payload):
    if state.step >= 5:
        return {
            "role": "system",
            "content": f"已经第 {state.step} 步了，请尽快给出最终答案，不要再调用工具。"
        }
    return None

feedback = FeedbackLoop(providers=[step_warning])

runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    feedback_loop=feedback,
)
```

### 监听所有 Harness 事件

```python
async def log_all_events(event):
    print(f"[{event.name}] trace={event.trace_id} step={event.state.step}")

runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    hooks=[log_all_events],
)
```

Harness 发出的事件类型：`run_start`, `step_start`, `think_start`, `think_end`, `act_start`, `act_end`, `feedback_collected`, `step_end`, `run_end`, `run_error`, `run_stopped`, `budget_max_steps`, `budget_max_duration`, `budget_max_tool_calls`, `constraint_violation`, `improvement_recorded`。
