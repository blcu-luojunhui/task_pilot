# Agent Run 架构设计文档

> 基于 `src/core/agent_task/run_goal.py`，追踪 `agent.run` 的完整执行链路。

## 目录

1. [整体架构](#1-整体架构)
2. [核心组件](#2-核心组件)
3. [执行链路](#3-执行链路)
4. [Agent Loop 内部流程](#4-agent-loop-内部流程)
5. [终止条件](#5-终止条件)
6. [策略与扩展](#6-策略与扩展)
7. [SSE 事件体系](#7-sse-事件体系)
8. [文件索引](#8-文件索引)

---

## 1. 整体架构

```
POST /api/agent/run          (HTTP 入口，验证参数)
  └─> run_agent(scheduler)   (任务 handler，外部协调)
        └─> Runner.run()     (组装 Think/Act/Observe)
              └─> Harness.run()  (Loop 驱动器)
                    └─> while not terminated:    (核心循环)
                          Strategy.run_step()
                            ├─ Think  → LLM 调用
                            ├─ Act    → 工具执行
                            └─ Observe → 终止判断
```

### 两层设计

| 层 | 文件 | 职责 | 依赖 |
|---|------|------|------|
| **外层**（协调层） | `run_goal.py` | 任务入口、工具加载、Planner 构造、记忆注入、结果持久化 | TaskScheduler、MySQL、LLM 配置 |
| **内层**（Loop 层） | `runner.py` + `harness.py` + `loop.py` | 纯粹的 Think→Act→Observe 循环，不感知基础设施 | 仅 LLM Provider + SkillRegistry |

**设计意图**：外层关心"从哪来、到哪去"，内层是纯粹的 Agent Loop 抽象，可以脱离 TaskScheduler/MySQL 独立运行和测试。

---

## 2. 核心组件

### 2.1 AgentLoopRunner（组装器）

`src/core/agents/engine/runner.py`

Runner 本身不包含循环逻辑，它的 `__post_init__` 负责**按依赖顺序组装**所有组件：

```
Runner.__post_init__():
  ├─ budget = AgentBudget(max_steps=10)
  ├─ constraints = ConstraintSet()
  ├─ feedback_loop = FeedbackLoop()
  ├─ continuous_improvement = ContinuousImprovement()
  ├─ memory_manager = MemoryManager()
  ├─ thinker = Think(planner, context_manager, prompt_assembler, memory, ...)
  ├─ actor = Act(registry, executor, tool_deps, ...)
  ├─ observer = Observe(abort_on_tool_error, max_consecutive_errors, ...)
  └─ harness = AgentLoopHarness(thinker, actor, observer, budget, strategy, ...)
```

Runner 对外暴露两个执行入口：

| 方法 | 用途 |
|------|------|
| `run(goal, messages)` | 标准执行，走 Harness |
| `run_with_routing(goal, messages)` | 先 TaskRouter 分解 goal 为子目标，再依次执行 |

### 2.2 AgentLoopHarness（驱动器）

`src/core/agents/runtime/harness/harness.py`

Harness 负责**生命周期管理**：while 循环、步骤边界、事件发射、Hook 调用、最终结果构建。

它的 `run()` 方法不直接调用 Think/Act/Observe，而是委托给 `Strategy.run_step()`，实现决策逻辑与执行逻辑的解耦。

### 2.3 WorkflowController（围栏）

`src/core/agents/runtime/harness/workflow.py`

在每步前后各设一道围栏：

```
before_step(): 检查 budget（max_steps/超时）、constraints、is_cancelled
after_step():  检查 budget（超时）、constraints
```

任何围栏返回 `WorkflowDecision` → Harness 立即设置 `state.stop_reason` → while 退出。

### 2.4 Think / Act / Observe（三阶段）

都实现在 `src/core/agents/engine/loop.py`。

| 组件 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **Think** | LLM 调用前的上下文准备 + 调用 | `state.messages` | `{role, content, tool_calls?, _usage?}` |
| **Act** | 工具调用执行（并行） | `state` + `ToolCall[]` | `[{role: tool, content, tool_call_id}]` |
| **Observe** | 结果写入历史 + 终止判断 | `assistant_message` + `tool_results` | 副作用：更新 `state.messages`, `state.stop_reason` |

### 2.5 Planner（LLM 适配闭包）

`Planner` 不是类，是一个**闭包函数**，由 `run_goal.py:_build_planner()` 构造：

```python
async def _planner(messages, step, **kwargs) -> Dict:
    # 闭包捕获了 provider 和序列化好的 openai_tools
    ...
    return {"role": "assistant", "content": "...", "tool_calls": [...], "_usage": {...}}
```

**闭包内的两个关键决策**：

1. 有 `openai_tools` → 强制走非流式 `provider.chat()`，防止流式路径丢失 `tool_calls`
2. 无工具（纯 chat 模式）→ 可走流式 `provider.stream_chat()`，逐 token 推送前端

### 2.6 AgentLoopState（状态容器）

`src/core/agents/state/models.py`

```python
@dataclass
class AgentLoopState:
    goal: str                               # 目标（不变）
    messages: List[Dict] = []               # 对话历史（动态增长）
    max_steps: int = 8
    trace_id: str

    step: int = 0                           # 当前步数
    stop_reason: Optional[StopReason] = None  # is_terminated() 的依据
    final_answer: Optional[str] = None
    consecutive_tool_errors: int = 0        # 连续工具失败计数

    tool_calls: List[ToolCallRecord] = []   # 结构化工具调用记录
    steps: List[Step] = []                  # 结构化步骤记录
    token_usage: Dict[str, int] = {}        # 累计 token

    def is_terminated(self) -> bool:
        return self.stop_reason is not None
```

---

## 3. 执行链路

### 3.1 入口：`POST /api/agent/run`

```
api/v1/endpoints/agent.py:124  →  参数校验  →  scheduler.schedule("agent.run")
  → 写入 task_manager (INIT)  →  返回 trace_id  →  asyncio.create_task(_task_wrapper)
    → handler(scheduler)  →  run_goal.run_agent()
```

### 3.2 外部协调：`run_agent()`

1. 自动推断 mode（agent / chat）
2. 启动 `_start_cancel_poller()`：后台每 2s 轮询 MySQL `task_status=4`
3. 构建 `_cancel_checker()`：**同步**闭包，读 dict flag
4. 构建 `_build_llm_provider()`：按 base_url 推断 provider 类型（deepseek/openai/claude）
5. 分发到 `_run_agent_mode()` 或 `_run_chat_mode()`

### 3.3 Agent 模式完整路径

```
_run_agent_mode()
  ├─ ① 加载工具
  │     load_agentic_tools(["chat_ops", "task", "http", "utils"])
  │     → 触发各 area 下 @skill 装饰器注册到全局 registry
  │     → tools = registry.filter(executable)
  │
  ├─ ② 构造 Planner（闭包）
  │     openai_tools = serializer.serialize_many(tools)  → [{"type": "function", "function": {...}}]
  │     _planner = async fn(messages, step) → provider.chat(messages, tools=openai_tools)
  │
  ├─ ③ 构造工具依赖
  │     tool_deps = {db, log, config, task_invoker, account_id}
  │
  ├─ ④ 构造 AgentLoopRunner
  │     runner = AgentLoopRunner(planner, registry, executor, max_steps=10, is_cancelled, ...)
  │     → __post_init__ 自动组装 Think/Act/Observe/Harness
  │
  ├─ ⑤ 记忆注入（可选）
  │     reflections = fetch_reflections(db, account_id, scope_key)
  │     → 拼接到 system prompt 尾部
  │
  ├─ ⑥ 执行
  │     result: AgentLoopResult = await runner.run(goal, messages, trace_id)
  │
  ├─ ⑦ 记忆写回（可选）
  │     reflection = generate_reflection(provider, goal, final_answer, success)
  │     → save_reflection(db, account_id, scope_key, ...)
  │
  └─ ⑧ 持久化
        UPDATE task_manager.data = {goal, status: "completed"/"failed", content, token_usage}
        → scheduler._release_task(status) 更新 task_status + finish_timestamp
```

---

## 4. Agent Loop 内部流程

### 4.1 while 循环每轮要做的事

```
while not state.is_terminated():

  ① lifecycle 检查
       lifecycle.wait_if_paused()       # 暂停 → 等待 resume
       lifecycle.is_stop_requested()?   # 停止 → USER_CANCELLED，break

  ② workflow.before_step()
       budget.check_before_step()       # step >= max_steps? 超时?
       is_cancelled?                    # cancel_flag["requested"]?
       constraint.check("before_step")  # 可扩展

  ③ state.step += 1
     emit("step_start")

  ④ strategy.run_step()
       Think:  thinker.run(state)
         → prompt_assembler.assemble()         # 组装 system prompt
         → memory_manager.aretrieve(query)     # 注入相关记忆
         → context_manager.compact_if_needed() # token 超限截断
         → collapse_old_tool_results()         # 折叠旧工具结果
         → is_cancelled? → return None
         → await planner(messages, step)       # 调 LLM
         → 返回 {role, content, tool_calls?, _usage?}

       Act:    actor.run(state, tool_calls)
         → 单 tool_call → 直接执行
         → 多 tool_calls → asyncio.gather 并行执行（Semaphore 限流 5）
         → 依次：check cancel → publish "tool_call_start" → executor.execute()
                → publish "tool_call_end"

       Observe: observer.run(state, msg, results)
         → state.add_assistant_message(msg)
         → 无 tool_calls → state.final_answer = content, stop_reason = MODEL_FINAL
         → 有 tool_calls → state.add_tool_results(results), 继续下一轮

  ⑤ feedback_loop.run()                  # 反馈收集 hook
  ⑥ workflow.after_step()                # 步骤后预算检查
  ⑦ strategy.on_step_end()               # 策略后钩子（如 Reflexion）
  ⑧ emit("step_end")
```

### 4.2 messages 如何增长

```
Step 1 前:
  [system: "你是助手...", user: "查询世界杯最佳射手"]

Step 1 Think → LLM 返回:
  {content: "好的我来搜索", tool_calls: [{name: "web_search", args: {...}}]}

Step 1 Observe → messages 变为:
  [system, user,
   assistant: {content: "好的我来搜索", tool_calls: [...]},
   tool: {tool_call_id: "call_1", content: "搜索结果是..."}]

Step 2 Think → LLM 看到上一步的完整上下文 → 继续推理或给出最终答案
```

### 4.3 工具执行上下文

```
Skill 函数声明:
  async def web_search(query: str, config: ProjectConfigSettings, account_id: int):

Act 执行时:
  resolver = MappingResolver({db, log, config, task_invoker, account_id})
  context = SkillContext(_resolver=resolver)
  executor.execute(skill, context, **{"query": "世界杯"})
    → resolver.resolve("config") → 注入 ProjectConfigSettings
    → resolver.resolve("account_id") → 注入 account_id
```

工具不需要感知 HTTP / CLI / 测试环境差异，Resolver 按名匹配注入。

---

## 5. 终止条件

| 触发位置 | stop_reason | 触发条件 |
|----------|------------|----------|
| **Observe** | `model_final` | LLM 返回纯 text，无 tool_calls |
| **budget.before_step** | `max_steps` | 步数 >= max_steps（默认 8，agent.run 设为 10） |
| **budget.before_step** | `budget_exhausted` | 超时（如果配置了 max_duration_seconds） |
| **workflow.before_step** | `user_cancelled` | `cancel_flag["requested"]` = True（MySQL task_status=4） |
| **workflow.before_step** | `constraint_violation` | 自定义约束检查失败 |
| **Think** | `llm_error_abort` | LLM 请求抛出异常 |
| **Observe** | `tool_error_abort` | 连续 3 步工具全部失败 |
| **Harness** | `error` | Loop 内其他未捕获异常 |

**`success` 判定**：仅当 `stop_reason == model_final` 时 `result.success = True`。

---

## 6. 策略与扩展

### 6.1 策略模式

Harness 不直接调 Think/Act/Observe，而是委托给 `Strategy.run_step()`：

```python
# 当前默认策略：ReAct
# src/core/agents/engine/planning/react.py

class ReActStrategy:
    async def run_step(state, ctx) -> StepOutput:
        # Think
        assistant_message = await ctx.thinker.run(state)
        # Act
        tool_calls = get_tool_calls(assistant_message)
        tool_results = await ctx.actor.run(state, tool_calls) if tool_calls else []
        # Observe
        ctx.observer.run(state, assistant_message, tool_results)
        return StepOutput(assistant_message, tool_results)
```

**可替换策略**：

| 策略 | 文件 | 差异 |
|------|------|------|
| `react` | `react.py` | 标准 Think→Act→Observe |
| `plan_execute` | `plan_execute.py` | on_run_start 时先生成执行计划，然后逐步推进 |
| `reflexion` | `reflexion.py` | 步后自省，从失败中修正策略 |

### 6.2 可扩展点

| 扩展点 | 注入方式 | 示例 |
|--------|---------|------|
| **新策略** | `AgentLoopRunner(strategy="plan_execute")` | 替换 ReAct 为 PlanExecute |
| **新增约束** | `ConstraintSet.add(check_fn, hook="before_step")` | 禁止访问特定域名 |
| **Hook** | `AgentLoopHarness(hooks=[my_hook])` | 每步发 Discord 通知 |
| **新工具区域** | `@skill("my_area")` + `load_agentic_tools(["my_area"])` | 添加自定义工具集 |
| **新 Provider** | 实现 `LLMProvider` 基类 + 注册到 `_PROVIDER_MAP` | 接入新模型 |
| **反馈提供者** | `feedback_loop.providers.append(ReflectionProvider(...))` | 反思式自我修正 |

---

## 7. SSE 事件体系

### 7.1 事件生命周期

```
run_start
  → step_start
    → think_start
      → [token_delta × N]          (persist=False, 不写 DB)
    → think_end
    → [tool_call_start → tool_call_end] × N
  → step_end
  → ...（循环）
→ turn_end 或 turn_error
```

### 7.2 事件分类

| persist | 事件举例 | 说明 |
|---------|---------|------|
| **True** | `think_start`, `think_end`, `tool_call_start`, `tool_call_end`, `turn_end`, `turn_error` | 写 `agent_events` 表，前端 SSE 订阅和历史回放都可读取 |
| **False** | `token_delta` | 仅实时推送，不写 DB（每秒几十条，全写太重） |

### 7.3 Harness 层事件（观察者可见）

| 事件 | 含义 | 携带数据 |
|------|------|---------|
| `run_start` | Loop 开始 | goal, metadata |
| `step_start` | 新步骤开始 | step 序号 |
| `think_start` | LLM 调用开始 | - |
| `think_end` | LLM 调用结束 | assistant_message（含 content + tool_calls） |
| `act_start` | 工具执行开始 | tool_calls 列表 |
| `act_end` | 工具执行结束 | tool_results |
| `step_end` | 步骤结束 | 汇总 assistant_message + tool_results |
| `run_end` | Loop 完成 | AgentLoopResult |
| `run_error` | Loop 异常 | error 信息 |
| `run_stopped` | 用户停止 | - |
| `feedback_collected` | 反馈收集 | 反馈消息 |
| `improvement_recorded` | 改进记录 | improvement 数据 |

### 7.4 前端消费路径

```
前端 GET /api/task_events/{trace_id} (SSE)
  → runTaskStore.handleLiveEvent()          — agent run 详情页
  → chat store reduceChatEvent()             — 纯 chat 页面
  → 根据 event_type switch-case 更新 UI: streamingText / toolCalls / finalResult / error
```

---

## 8. 文件索引

| 文件 | 职责 |
|------|------|
| `src/api/v1/endpoints/agent.py` | HTTP 入口：`POST /api/agent/run` |
| `src/api/v1/endpoints/tasks.py` | 任务详情/流式事件查询 |
| `src/core/agent_task/run_goal.py` | 任务 handler：`@register("agent.run")`，工具加载、Planner 构造、结果持久化 |
| `src/core/agents/engine/runner.py` | `AgentLoopRunner`：组装 Think/Act/Observe/Harness，暴露 `run()` |
| `src/core/agents/engine/loop.py` | `Think`、`Act`、`Observe` 三阶段实现 |
| `src/core/agents/runtime/harness/harness.py` | `AgentLoopHarness`：while 循环、事件发射、生命周期 |
| `src/core/agents/runtime/harness/workflow.py` | `WorkflowController`：步骤围栏（budget/cancel/constraints） |
| `src/core/agents/runtime/harness/budget.py` | `AgentBudget`：步骤数/工具调用数/超时控制 |
| `src/core/agents/runtime/harness/constraints.py` | `ConstraintSet`：可扩展的约束检查 |
| `src/core/agents/runtime/harness/feedback.py` | `FeedbackLoop`：反馈收集框架 |
| `src/core/agents/runtime/harness/improvement.py` | `ContinuousImprovement`：运行摘要 + 改进建议 |
| `src/core/agents/engine/planning/react.py` | `ReActStrategy`：默认 Think→Act→Observe 策略 |
| `src/core/agents/state/models.py` | `AgentLoopState`、`AgentLoopResult`、`StopReason` |
| `src/core/agents/capabilities/skills/__init__.py` | `SkillRegistry`、`SkillExecutor`、`SkillContext`、`MappingResolver` |
| `src/core/agents/capabilities/tools/loader.py` | `load_agentic_tools()`：按 area 加载工具集合 |
| `src/core/agents/capabilities/llm/providers/deepseek.py` | DeepSeek Provider 实现 |
| `src/core/chat/repository.py` | `ChatRepository`：chat_messages 表读写 |
| `src/core/chat/service.py` | Chat 服务层：发消息、提交 `chat.agent_turn` 任务 |
| `src/jobs/task_scheduler.py` | `TaskScheduler`：任务调度、状态机、Guard 函数 |
| `scripts/agent_run.py` | 测试脚本：跳过 MySQL/TaskScheduler，裸跑 Agent Loop |
