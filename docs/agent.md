# Agent Guide

> How TaskPilot turns task execution into an agentic workflow.

在 TaskPilot 中，Agent 不是绕过任务系统的"外挂脚本"。它运行在调度器和生命周期管理之内，接受同样的并发控制、超时控制、取消机制和可观测约束。

[Back to README](../README.md)

---

## The Loop

Agent 的核心循环：

```text
Think → Act → Observe → Think ...
```

- **Think**：理解任务目标、上下文和当前状态，决定下一步策略
- **Act**：调用 Skills 或外部工具执行动作
- **Observe**：读取执行结果，判断继续、重试、切换策略或结束

三段式循环的实现在 `src/core/agents/engine/loop.py`（`Think` / `Act` / `Observe` 类），`AgentLoopRunner` 负责装配阶段，`AgentLoopHarness` 驱动完整生命周期。

---

## Runtime Architecture

```text
AgentLoopRunner           # 入口：组装组件，委托给 Harness
  └─ AgentLoopHarness     # 运行时生命周期：驱动 Think/Act/Observe 循环
       ├─ Think           #   调用 Planner → LLM，管理上下文窗口
       │    ├─ ContextWindowManager    # token 预算与截断
       │    ├─ KnowledgeSelector       # 从 Knowledge Skills 选择相关知识
       │    └─ PromptAssembler         # 组装 system prompt + 工具描述 + 消息
       ├─ Act             #   执行 tool calls，写回 transcript
       ├─ Observe         #   判断结果：继续 / 错误处理 / 结束
       ├─ WorkflowController   #   流程决策：取消、预算、约束
       │    ├─ AgentBudget          # max_steps / max_tool_calls / max_duration
       │    └─ ConstraintSet        # before_step / after_think / before_act 拦截
       ├─ FeedbackLoop          #   每步注入反馈到 transcript
       └─ ContinuousImprovement #   运行结束记录摘要
```

### Runner

`AgentLoopRunner` 是面向调用方的入口，组装默认组件。调用示例：

```python
from src.core.agents import Agent

agent = Agent.create(
    llm_api_key="your-api-key",
    llm_provider="deepseek",
)

result = await agent.run(goal="帮我分析系统状态")
print(result.final_answer)
```

### Harness

`AgentLoopHarness` 负责运行时生命周期：创建 `AgentLoopState`、生成 trace_id、触发各阶段事件、调用 WorkflowController 做流程控制、构建 `AgentLoopResult`。Harness 不直接关心具体模型或业务工具。

---

## Trace ID

每次 Agent 执行都有一个 `trace_id`，格式：

```text
Agent-YYYYmmddHHMMSS-xxxxxxxxxxxxxxxx
```

`trace_id` 贯穿 `AgentLoopState`、`AgentLoopResult`、`HarnessEvent`、metadata 和每一条 agent loop 日志：

```text
agent_loop trace_id=Agent-... event=run_start step=0 stop_reason=None
agent_loop trace_id=Agent-... event=think_start step=1 stop_reason=None
agent_loop trace_id=Agent-... event=act_start step=1 stop_reason=None
agent_loop trace_id=Agent-... event=run_end step=2 stop_reason=model_final
```

---

## Harness Controls

### Budget

`AgentBudget` 控制资源上限：`max_steps`、`max_tool_calls`、`max_duration_seconds`。预算耗尽时以 `StopReason.BUDGET_EXHAUSTED` 或 `StopReason.MAX_STEPS` 停止。

### Constraints

`ConstraintSet` 在不同阶段拦截流程：`before_step`、`after_think`、`before_act`、`after_step`。适合做工具白名单、危险操作拦截、上下文策略检查。

### Workflow

`WorkflowController` 统一做流程决策：是否取消、是否超预算、是否违反约束、是否允许进入下一阶段。

### Feedback

`FeedbackLoop` 在每一步结束后向 transcript 注入反馈消息。这些反馈被下一轮 Think 看到，形成持续修正回路。

### Continuous Improvement

`ContinuousImprovement` 在 run 结束后记录运行摘要：goal、success、stop_reason、total_steps、tool_call_count、metadata。默认使用 `InMemoryImprovementStore`，可接入数据库或评测系统。

---

## Skills

Skills 是 Agent 的能力边界，分为两类：

### Executable Skills

可被 Agent 调用的函数能力，通过 `@skill` 装饰器注册。封装数据库查询、HTTP 请求、任务管理、通用工具等动作。

### Knowledge Skills

Markdown 文档中的知识片段，存放在 `skills/knowledge/`。不直接执行代码，而是作为上下文注入，约束策略、补充领域规则和沉淀最佳实践。

---

## Built-in Tool Areas

四类内置工具，通过 `load_agentic_tools()` 按需启用：

| 区域 | 能力 | 依赖 |
|------|------|------|
| `database` | 查询、读取、写操作 | infra (MySQL) |
| `http` | 调用外部接口 | infra (HTTP client) |
| `task` | 任务状态查询、取消 | infra |
| `utils` | 时间、哈希、批处理、trace | 无 |

```python
from src.core.agents import load_agentic_tools

load_agentic_tools(["utils"])                        # 默认，无 infra 依赖
load_agentic_tools(["database", "http", "task"])     # 按需启用
```

---

## LLM Providers

Skill 定义与模型格式解耦。同一组 Skills 通过 Tool Spec Adapter 序列化为不同 LLM 的工具描述。

当前支持的 Provider：

| Provider | 默认模型 | 实现位置 |
|----------|----------|----------|
| DeepSeek | `deepseek-chat` | `capabilities/llm/providers/deepseek.py` |
| OpenAI | `gpt-4o` | `capabilities/llm/providers/openai.py` |
| Claude | `claude-sonnet-4-6` | `capabilities/llm/providers/claude.py` |

切换 Provider 只需改一行配置：

```python
agent = Agent.create(
    llm_api_key="your-key",
    llm_provider="claude",      # 切换到 Claude
)
```

---

## Multi-Agent

`MultiAgentCoordinator` 编排多智能体协作：

- **MessageBus** — 解耦智能体间消息传递，支持 MessageType / MessagePriority
- **Coordinator** — 任务分配（TaskAssignment）和结果聚合
- **Protocol** — 标准化 Agent 间通信格式

---

## Lifecycle & Snapshot

Agent 自身生命周期由 `LifecycleManager` 管理：

```python
agent.pause()                           # 暂停，当前 step 完成后挂起
agent.save_snapshot(metadata={...})     # 持久化当前状态
agent.resume()                          # 恢复执行
agent.stop()                            # 请求停止
```

快照支持断点续跑：

```python
agent.set_snapshot_dir("./snapshots")
snapshot_id = agent.save_snapshot()

# 后续从快照恢复
result = await agent.run_from_snapshot(snapshot_id)
```

---

## Evaluator & Debugger

- **Evaluator** (`runtime/harness/evaluator.py`) — 评估 Agent 执行质量，输出 `EvaluationResult` 和 `EvaluationMetric`
- **Debugger** (`runtime/harness/debugger.py`) — 记录 `TraceEvent`，提供 step 级别的执行轨迹
- **FixtureManager** (`runtime/harness/fixtures.py`) — 提供 `MockTool`，支持测试场景

---

## Transcript & Tool Calls

Agent loop 内部使用统一的消息类型，定义在 `src/core/agents/state/protocol.py`：

- `ToolCall` — 标准化 tool call 结构
- `assistant_message()` — 构建 assistant 消息
- `tool_result_message()` — 构建 tool 结果消息
- `get_tool_calls()` / `normalize_tool_calls()` — 提取和规范化

外部可传普通 `dict`，loop 内部统一规范化。

---

## Extension Points

- 新增 **Executable Skill** — 接入新系统能力
- 新增 **Knowledge Skill** — 沉淀业务规则和操作经验
- 新增 **LLM Provider** — 实现 `LLMProvider` 接口
- 新增 **Constraint** — 约束工具和策略边界
- 新增 **FeedbackProvider** — 为下一轮 Think 注入反馈
- 新增 **ImprovementStore** — 保存运行摘要用于评测优化
- 新增 **Hook** — 在 run/step/think/act 事件点插入自定义逻辑

---

## Boundary

Agent 可以让任务执行更灵活，但它不应该绕开任务系统本身。

在 TaskPilot 中：

- 任务是否开始，由 `jobs` 调度
- 任务是否取消，由生命周期管理器协调
- 工具能做什么，由 Skills 注册表治理
- 外部系统如何访问，由 `infra` 封装
- 运行过程如何追踪，由 `trace_id` 和 harness event log 串联

这条边界让智能行为可以增长，同时保留可测试、可审计、可回收的工程结构。
