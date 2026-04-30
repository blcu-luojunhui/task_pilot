# Agent Guide

> How TaskPilot turns task execution into an agentic workflow.

在 TaskPilot 中，Agent 不是绕过任务系统的“外挂脚本”。  
它运行在调度器和生命周期管理之内，接受同样的并发控制、超时控制、取消机制和可观测约束。

[Back to README](../README.md)

---

## The Loop

Agent 的核心循环是：

```text
Think -> Act -> Observe -> Think ...
```

- **Think**：理解任务目标、上下文和当前状态，决定下一步策略
- **Act**：调用 Skills 或外部工具执行动作
- **Observe**：读取执行结果，判断继续、重试、切换策略或结束

当前代码中，这三个阶段分别位于：

- `src/core/agents/loop/think/`
- `src/core/agents/loop/act/`
- `src/core/agents/loop/observe/`

`AgentLoopRunner` 负责装配阶段，真正驱动生命周期的是 `AgentLoopHarness`。

---

## Runtime Architecture

TaskPilot 的 Agent Runtime 分成几层：

```text
AgentLoopRunner
  -> AgentLoopHarness
      -> WorkflowController
          -> AgentBudget
          -> ConstraintSet
      -> Think
      -> Act
      -> Observe
      -> FeedbackLoop
      -> ContinuousImprovement
      -> HarnessEventLogger
```

### Runner

`AgentLoopRunner` 是面向调用方的入口，负责组装默认组件：

- `Think`
- `Act`
- `Observe`
- `AgentBudget`
- `ConstraintSet`
- `FeedbackLoop`
- `ContinuousImprovement`
- `AgentLoopHarness`

调用示例：

```python
runner = AgentLoopRunner(
    planner=planner,
    registry=registry,
    executor=SkillExecutor(),
    budget=AgentBudget(max_steps=4, max_tool_calls=1),
)

result = await runner.run(
    goal="帮我解释一下：三重积分的理解和应用",
    messages=[{"role": "user", "content": goal}],
)
```

### Harness

`AgentLoopHarness` 负责运行时生命周期：

- 创建 `AgentLoopState`
- 生成或接收 `trace_id`
- 触发 run / step / think / act / feedback / end 事件
- 调用 workflow 进行预算、取消和约束判断
- 构建 `AgentLoopResult`

Harness 不直接关心具体模型，也不直接关心具体业务工具。

---

## Trace ID

每次 Agent 执行都会有一个 `trace_id`。

如果调用方没有传入，系统会自动生成：

```text
Agent-YYYYmmddHHMMSS-xxxxxxxxxxxxxxxx
```

`trace_id` 会贯穿：

- `AgentLoopState.trace_id`
- `AgentLoopResult.trace_id`
- `HarnessEvent.trace_id`
- `metadata["trace_id"]`
- 每一条 agent loop 日志

日志示例：

```text
agent_loop trace_id=Agent-... event=run_start step=0 stop_reason=None
agent_loop trace_id=Agent-... event=think_start step=1 stop_reason=None
agent_loop trace_id=Agent-... event=act_start step=1 stop_reason=None
agent_loop trace_id=Agent-... event=run_end step=2 stop_reason=model_final
```

这让一次 Agent 执行中的模型调用、工具调用、反馈、约束和最终结果都能被同一个 trace 串起来。

---

## Harness Controls

Harness 不是简单的 while loop，它包含几类控制能力。

### Budget

`AgentBudget` 控制资源上限：

- `max_steps`
- `max_tool_calls`
- `max_duration_seconds`

如果预算耗尽，Agent 会以 `StopReason.BUDGET_EXHAUSTED` 或 `StopReason.MAX_STEPS` 停止。

### Constraints

`ConstraintSet` 是约束机制，可在不同阶段拦截流程：

- `before_step`
- `after_think`
- `before_act`
- `after_step`

适合做工具白名单、危险操作拦截、上下文策略检查等。

### Workflow

`WorkflowController` 统一做流程决策：

- 是否取消
- 是否超预算
- 是否违反约束
- 是否允许进入下一阶段

### Feedback

`FeedbackLoop` 可以在每一步结束后向 transcript 注入反馈消息。  
这些反馈会被下一轮 `Think` 看到，用来形成持续修正的回路。

### Continuous Improvement

`ContinuousImprovement` 在 run 结束后记录运行摘要：

- goal
- success
- stop reason
- total steps
- tool call count
- metadata

默认可以使用 `InMemoryImprovementStore`，后续也可以接数据库或评测系统。

---

## Skills

Skills 是 Agent 的能力边界。TaskPilot 将它拆成两类：

### Executable Skills

Executable Skills 是可被 Agent 调用的函数能力，通过 `@skill` 注册。  
它们适合封装数据库查询、HTTP 请求、任务管理、通用工具函数等动作。

### Knowledge Skills

Knowledge Skills 是 Markdown 文档中的知识片段。  
它们不会直接执行代码，而是注入到 Agent 的上下文中，用来约束策略、补充领域规则和沉淀最佳实践。

---

## Built-in Tool Areas

TaskPilot 内置的 Agentic Tools 主要覆盖四类能力：

- Database：查询、读取单条记录、执行写操作
- HTTP：调用外部接口
- Task：查询任务状态、列出执行中任务、请求取消任务
- Utils：时间、哈希、批处理、trace id 等通用能力

这些工具都通过 Skills 框架暴露给 Agent，而不是直接散落在业务流程中。

工具区域通过 `load_agentic_tools()` 显式加载：

```python
from src.core.agents.agentic_tools import load_agentic_tools

load_agentic_tools(["utils"])
load_agentic_tools(["database", "http", "task"])
```

默认只加载不依赖 infra 的 `utils`。  
Database、HTTP、Task 这类 infra 能力需要调用方按需启用，并通过 `tool_dependencies` 配置依赖。

---

## Model Adapters

不同 LLM 对工具描述格式的要求不同。  
TaskPilot 将技能定义和模型格式拆开，通过 Tool Spec Adapter 将同一组 Skills 序列化为不同模型可理解的工具描述。

这意味着：

- 技能只需要定义一次
- 模型接入可以独立演进
- OpenAI、Claude 或其它格式可以共存

当前已经提供 DeepSeek planner：

- `src/core/agents/llm/deepseek.py`
- `DeepSeekPlanner`
- `DeepSeekSettings`

DeepSeek 使用 OpenAI 兼容的 tool calling 格式。  
`DeepSeekPlanner` 会把 `SkillRegistry` 中的 Skills 序列化为 tools，并把模型返回的 tool calls 转换为内部消息格式。

`.env` 示例：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com/chat/completions
```

运行示例：

```bash
python examples/deepseek_goal_agent.py
```

默认目标：

```text
帮我解释一下：三重积分的理解和应用
```

---

## Transcript And Tool Calls

Agent loop 内部使用统一的消息工具：

- `ToolCall`
- `assistant_message()`
- `tool_result_message()`
- `get_tool_calls()`
- `normalize_tool_calls()`

这些定义位于：

```text
src/core/agents/loop/messages.py
```

外部仍可以传普通 `dict` 消息，但 loop 内部会统一规范化，避免不同模块重复解析 `role`、`tool_calls`、`arguments`。

---

## Minimal Demo

不依赖真实模型的最小目标驱动 demo：

```bash
python examples/minimal_goal_agent.py
```

这个 demo 会：

1. 接收目标：`帮我解释一下：三重积分的理解和应用`
2. 进入 Agent loop
3. Think 阶段决定调用 `explain_math_concept`
4. Act 阶段执行本地 Skill
5. Observe 阶段写回工具结果
6. 第二轮 Think 输出最终回答

真实 DeepSeek API demo：

```bash
python examples/deepseek_goal_agent.py
```

需要先在 `.env` 中配置：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key
```

---

## Extension Points

你可以从这些位置扩展 Agent 系统：

- 新增 Executable Skill，接入新的系统能力
- 新增 Knowledge Skill，沉淀业务规则和操作经验
- 新增 Tool Spec Adapter，支持新的模型接口
- 新增 Planner，接入新的 LLM
- 新增 Dependency Resolver，适配测试、多环境或多租户场景
- 新增 Constraint，约束工具和策略边界
- 新增 FeedbackProvider，为下一轮 Think 注入反馈
- 新增 ImprovementStore，保存运行摘要用于评测和优化

---

## Boundary

Agent 可以让任务执行更灵活，但它不应该绕开任务系统本身。

在 TaskPilot 中：

- 任务是否开始，由 `jobs` 调度
- 任务是否取消，由生命周期管理器协调
- 工具能做什么，由 Skills 注册表治理
- 外部系统如何访问，由 `infra` 封装
- 运行过程如何追踪，由 `trace_id` 和 harness event log 串联

这条边界让智能行为可以增长，同时仍然保留可测试、可审计、可回收的工程结构。
