# Agent Runtime 技术设计

> 本文描述 TaskPilot 当前代码已经实现的 Agent 运行时契约，覆盖 HTTP 任务入口、
> Agent Loop、工具权限、人工审批、副作用账本、人工对账、恢复和可观测性。
> 文档基线：2026-08-18。

## 1. 文档范围

本文回答以下问题：

- 一个 `agent.run` 请求如何进入任务系统并驱动 Agent Loop？
- 模型、上下文、工具和确定性任务状态机之间如何分工？
- 写操作如何经过能力授权、人工审批、执行账本和异常对账？
- 运行如何暂停、持久化和恢复？
- 不同策略、终止原因和事件分别具有什么可观察语义？

本文不描述前端交互细节，也不宣称通用 exactly-once。业务副作用若要获得
exactly-once 语义，仍需要目标系统支持幂等键，或让副作用与执行账本共享事务。

## 2. 设计目标与硬约束

### 2.1 设计目标

1. **限制不确定性扩散**：LLM 决定下一步动作，但不能绕开任务状态机、预算和权限。
2. **副作用默认保守**：写工具必须显式授权，默认还需要人工审批。
3. **恢复优先**：审批等待和执行结果不确定不是普通失败，而是可持久化、可恢复状态。
4. **执行可追溯**：同一个 `trace_id` 串联任务、模型步骤、工具调用、事件和账本。
5. **组件可替换**：Provider、Strategy、Skill、Memory、Constraint 和事件订阅者彼此解耦。

### 2.2 运行时不变量

- 模型只能看到本次运行被授权的 Tool Spec。
- Executor 必须再次校验模型返回的工具调用，不能信任模型遵守 Tool Spec。
- 同一批工具调用只要包含副作用工具，就按顺序执行，避免并发副作用产生不可控顺序。
- 写工具在账本不可用时 fail closed；只读路径不依赖副作用账本。
- 已进入 `execution_in_doubt` 的工具调用不得自动重试。
- 审批恢复使用冻结的原始工具调用，不能让模型重新生成参数。
- Tool 输出作为不可信数据进入上下文，不能覆盖 system 或 user 指令。

## 3. 分层与信任边界

```text
HTTP / API
  │  参数校验、身份、每次运行的 ToolPolicy / ApprovalPolicy
  ▼
TaskScheduler + task_manager
  │  确定性任务状态、取消、抢占、持久化、恢复调度
  ▼
run_goal.py
  │  Provider / Registry / Executor / Ledger / Runner 装配
  ▼
AgentLoopRunner
  │  组装 Strategy、Think、Act、Observe、Harness
  ▼
AgentLoopHarness
  │  生命周期、预算、约束、反馈、事件、结果构建
  ▼
DecisionStrategy
  ├─ Think   上下文组装与模型调用
  ├─ Act     权限校验、审批后工具执行、账本协议
  └─ Observe 消息写入、错误计数、终止判断
```

| 层 | 主要职责 | 不应承担的职责 |
|---|---|---|
| API | 解析不可信输入、绑定账户、创建运行策略 | 直接执行工具 |
| Jobs | 任务状态机、取消、调度、任务数据持久化 | 推理下一步动作 |
| Agent Task | 把基础设施依赖装配成一次运行 | 复制 Agent Loop |
| Runner / Harness | 驱动一次 Agent 运行 | 直接访问 HTTP request |
| Strategy | 决定单步 Think/Act/Observe 语义 | 绕过预算和权限 |
| Skill / Provider | 封装外部能力 | 修改任务状态机 |

## 4. 核心运行契约

### 4.1 `AgentLoopState`

`AgentLoopState` 是一次运行的唯一可恢复状态载体，主要包含：

| 字段 | 语义 |
|---|---|
| `goal` | 当前运行目标；Plan-Execute 执行子目标时只做临时替换 |
| `messages` | 传给模型的对话协议历史 |
| `step` / `max_steps` | 已执行步骤与步骤上限 |
| `stop_reason` | 是否终止的唯一判据；非空即终止或暂停 |
| `tool_calls` | 结构化工具审计记录 |
| `steps` | Thought / Action / Observation 结构化轨迹 |
| `pending_approval` | 冻结的审批请求和 assistant message |
| `pending_reconciliation` | 结果不确定的工具调用及批次恢复信息 |
| `token_usage` | 模型调用的累计 Token 用量 |
| `plan` | Plan-Execute 的结构化计划状态 |

状态快照通过 `StateSnapshot` 序列化，并使用 `schema_version` 标识协议版本。

### 4.2 `AgentLoopResult`

`AgentLoopResult` 是运行对调用方的稳定输出：

- `success` 仅在 `stop_reason == model_final` 时为 `True`。
- `pending_approval` 和 `pending_reconciliation` 表示运行可恢复暂停，而非成功。
- `metadata` 携带审批历史、对账历史和结构化计划等诊断信息。
- `total_steps`、`tool_calls_count`、`duration_seconds` 和 `token_usage` 用于预算与评估。

### 4.3 Runner 与 Harness

`AgentLoopRunner` 是组装器，负责创建或接收以下组件：

- `AgentBudget`
- `ConstraintSet`
- `FeedbackLoop`
- `ContinuousImprovement`
- `MemoryManager`
- `Think` / `Act` / `Observe`
- `DecisionStrategy`
- `AgentLoopHarness`

`AgentLoopHarness` 持有 while 循环和生命周期，不负责 Provider 或工具的具体实现。
它在每个步骤前后调用 `WorkflowController`，把预算、取消和约束统一转换成
`WorkflowDecision`。

## 5. 一次运行的完整链路

### 5.1 请求进入任务系统

```text
POST /api/agent/run
  → 校验 goal、tool_areas、max_steps
  → 解析 ToolPolicy 和 ApprovalPolicy
  → 生成 trace_id
  → 写入 task_manager
  → TaskScheduler 调度 agent.run
  → run_goal.run_agent()
```

HTTP 请求不会同步等待 Agent 完成。调用方先获得 `trace_id`，再通过事件流和任务查询
观察运行状态。

### 5.2 Agent Task 装配

`_run_agent_mode()` 按以下顺序装配一次运行：

1. 根据 `tool_areas` 加载系统工具。
2. 使用 `ToolPolicy` 过滤本次可用 Skill。
3. 用过滤结果构造 Provider Tool Spec。
4. 从同一结果构造 `PermissionGuard`，形成第二道执行校验。
5. 注入数据库、日志、配置、账户和 TaskInvoker 等工具依赖。
6. 创建 `DBToolExecutionLedger`。
7. 创建 `AgentLoopRunner`，注入事件总线、审批策略、取消检查和账本。
8. 如存在 checkpoint，则恢复 `AgentLoopState`。
9. 执行 Runner，并按结果更新 `task_manager`。

### 5.3 Harness 主循环

```text
while state.stop_reason is None:
  1. 检查 lifecycle pause / stop
  2. workflow.before_step(): budget / constraint / cancel
  3. state.step += 1
  4. strategy.run_step(state, context)
  5. 收集 feedback
  6. workflow.after_step()
  7. 记录结构化 Step
  8. strategy.on_step_end()
  9. 发布 step_end
```

异常由 Harness 收口为 `StopReason.ERROR`，同时发布 `run_error` 和前端错误事件。
等待审批或对账时发布 `run_paused`，不会错误地发布终态 `run_end`。

## 6. Think / Act / Observe

### 6.1 Think：上下文供给与模型调用

Think 的处理顺序是：

1. `PromptAssembler` 组装当前 goal、plan、预算和恢复提示。
2. `MemoryManager` 根据 goal 和近期 Observation 检索相关记忆。
3. `ContextWindowManager` 在超过 Token 预算时压缩或截断历史。
4. `collapse_old_tool_results()` 折叠较早的长工具结果。
5. 发布 `prompt_assembled`，供调试器和前端检查。
6. 再次检查取消信号。
7. 调用 Planner，并累计 Token 用量。

有工具时使用非流式模型调用，保证 Tool Call 参数完整；无工具的纯文本运行可使用流式调用。
流式调用只允许在首 Token 之前重试，避免客户端收到重复内容。

### 6.2 Act：工具执行

Act 对每个 Tool Call 执行以下协议：

1. 检查取消信号。
2. 发布 `tool_call_start`。
3. 从 Registry 解析 Skill。
4. 对副作用工具申请账本 claim。
5. 构造 `SkillContext`，写入 `trace_id`、`step`、`tool_call_id` 和 `tool_name`。
6. 执行 Skill，并记录耗时。
7. 对结果递归脱敏、截断并包裹为不可信 Tool 输出。
8. 对副作用工具完成或失败账本记录。
9. 发布 `tool_call_end`。

纯只读批次可以在 Semaphore 限制下并发执行；只要批次包含 `write` 或
`destructive` Skill，整个批次改为顺序执行。

### 6.3 Observe：状态推进

Observe 首先写入 assistant message。随后：

- 没有 Tool Call 且 content 非空：设置 `final_answer` 和 `model_final`。
- 没有 Tool Call 且 content 为空：设置 `llm_error_abort`。
- 存在 Tool Call：写入 Tool Results，供下一轮模型观察。
- 本轮所有工具都失败：增加 `consecutive_tool_errors`。
- 本轮所有工具都成功：清零连续失败计数。
- 达到错误阈值或启用立即中止：设置 `tool_error_abort`。

成功 Tool Result 同时进入短期记忆；Tool Result 中的 `Error:` 保持独立错误协议。

## 7. 工具安全模型

### 7.1 能力授权与执行校验

工具需要同时通过两道检查：

```text
ToolPolicy.filter_skills()
  → 只把获准 Tool Spec 发给模型

PermissionGuard.check()
  → Executor 再次验证实际 Tool Call
```

`ToolPolicy` 支持：

- `allowed_risk_levels`
- `allowed_tools`
- `blocked_tools`

HTTP Agent 默认仅开放 `read`。Agent SDK 仅复制调用方明确声明的 `tool_areas`；未声明时
不开放系统可执行工具，业务仍可通过 `agent.skill()` 显式注册实例级 Skill。

### 7.2 人工审批

`ApprovalPolicy` 默认拦截 `write` 和 `destructive` Tool Call，也可按工具名强制审批或豁免。

当一个批次中存在需要审批的调用时：

1. 模型生成的完整 assistant message 被冻结。
2. 对外审批请求中的参数先脱敏。
3. `stop_reason` 设为 `approval_required`。
4. Task 状态变为 `WAITING_APPROVAL(5)`。
5. checkpoint 和 `pending_approval` 写入 `task_manager.data`。

恢复时必须提交匹配的 `request_id`。批准后执行冻结参数；拒绝后向模型写入结构化 Tool
错误。客户端提交的 actor 不可信，HTTP API 使用已认证账户作为审计 actor。

### 7.3 副作用账本

账本主键为 `(trace_id, tool_call_id)`，同时保存工具名和参数摘要。

| 账本状态 | 运行时行为 |
|---|---|
| 首次 claim | 获得执行权并调用工具 |
| `completed` | 回放已存结果，不重复执行 |
| `failed` | 回放失败，不重复执行 |
| 已存在 `running` | 判定结果不确定，禁止自动执行 |
| 工具名或参数摘要不一致 | 拒绝复用同一 Tool Call ID |

该协议提供保守的 at-most-once 行为，不等价于 exactly-once。

### 7.4 人工对账

工具可能已产生副作用，但进程在结果写入账本前失败。此时状态进入
`execution_in_doubt`：

1. 冻结 assistant message、目标 Tool Call 和此前已完成的 Tool Results。
2. Task 状态变为 `WAITING_RECONCILIATION(6)`。
3. 操作员到下游系统核验真实结果。
4. 使用 `completed` 或 `failed` 裁决账本。
5. 从冻结批次继续，不重新执行结果不确定的调用。

审计历史只保存结果摘要，不保存人工提供的完整结果正文。

## 8. 策略语义

### 8.1 ReAct

默认策略。单步严格执行 Think → Approval Gate → Act → Observe。审批和对账协议在策略中
设置暂停状态，具体执行和恢复由 Harness 与 Act 完成。

### 8.2 Plan-Execute

运行开始时先生成结构化计划，解析 `-`、`*`、`+` 和编号列表。每个计划步骤按以下状态推进：

```text
pending → in_progress → done
                      ↘ failed
```

- 步骤只有在模型针对当前子目标返回最终文本时才进入 `done`。
- 工具调用结束后仍保持 `in_progress`，下一轮继续处理同一子目标。
- 当前子目标完成但仍有 pending 步骤时，清除本轮 `model_final` 并继续计划。
- 计划生成的 Token 纳入运行总量。
- 最终计划状态和每步结果进入 `AgentLoopResult.metadata.plan`。
- 计划生成失败时退化为 ReAct，并通过 `metadata.planning.status` 标记。

### 8.3 Reflexion

`strategy="reflexion"` 自动装配 `ReflectionProvider`。达到连续错误阈值后，Provider 根据
近期 Tool 错误生成语言化反馈，并通过 `FeedbackLoop` 注入下一轮消息。

当前实现属于**单次运行内的错误反思**，尚不是跨任务、带长期 episodic memory 的完整
Reflexion 学习系统。

### 8.4 Routing

`run_with_routing()` 先把目标拆成子目标，再顺序运行独立子 Runner。子 Runner 使用独立预算
和 Harness，但继承父 Runner 的：

- PermissionGuard 与 ApprovalPolicy
- ExecutionLedger
- Constraint、Hook 与 EventBus
- Strategy、Reflection 与 MemoryManager

这样可以避免路由入口绕过审批、安全策略或可观测性。

## 9. 暂停、快照与恢复

系统存在两类暂停：

| 类型 | 触发者 | 恢复输入 |
|---|---|---|
| 生命周期暂停 | SDK 调用方执行 `agent.pause()` | `agent.resume()` |
| 持久化运行暂停 | Approval / Reconciliation | 对应人工 Decision |

持久化 checkpoint 包含消息、步骤、工具记录、计划、Token、待审批或待对账信息。恢复时：

1. 校验 Decision 与 checkpoint 中的 ID 匹配。
2. 恢复相同 `trace_id` 和 step 序号。
3. 先处理冻结的审批或对账批次。
4. 再回到正常 Agent Loop。

## 10. 事件与日志

### 10.1 主要事件序列

```text
run_start / run_resumed
  → step_start
  → prompt_assembled
  → token_delta / llm_retry                    可选
  → approval_required                      可选
  → tool_call_start / tool_call_replayed / tool_call_end
  → reconciliation_required                可选
  → feedback_collected                     可选
  → step_end
  → improvement_recorded                   可选
  → run_paused | run_end | run_error
  → turn_paused | turn_end | turn_error
```

`token_delta` 只用于实时推送，不持久化。Harness 事件在写入 EventBus 前转换为 JSON-safe
数据并递归脱敏。Harness 中保留了 `_think()` / `_act()` 辅助方法，但当前 Strategy 主链路直接
调用 `Think.run()` / `Act.run()`，因此 `think_start`、`think_end`、`act_start` 和 `act_end`
不属于现行稳定事件契约。

### 10.2 日志契约

- compact 模式用于生产环境，不记录模型正文，只保留角色、长度、工具名和成功状态等度量。
- verbose 模式用于本地诊断，可以显示截断后的内容，但必须经过可配置 sanitizer。
- 模块不自行安装 Handler 或修改全局日志级别，日志路由由应用启动层负责。

## 11. 终止与任务状态映射

| `StopReason` | `success` | 任务结果 |
|---|---:|---|
| `model_final` | 是 | `SUCCESS(2)` |
| `approval_required` | 否 | `WAITING_APPROVAL(5)` |
| `execution_in_doubt` | 否 | `WAITING_RECONCILIATION(6)` |
| `user_cancelled` | 否 | `CANCELLED(3)` 或调用方取消语义 |
| `max_steps` / `budget_exhausted` | 否 | `FAILED(99)` |
| `llm_error_abort` / `tool_error_abort` | 否 | `FAILED(99)` |
| `constraint_violation` / `error` | 否 | `FAILED(99)` |

审批和对账属于非成功的可恢复暂停，因此不能只用 `success` 判断是否允许恢复。

## 12. 已知边界

以下内容是当前代码边界，不应在对外文档中宣称已经完成：

1. **Agent 实例并发**：Harness 和 Lifecycle 持有可变的当前状态，同一个 Agent 实例不支持并发 `run()`。
2. **高级配置贯通**：`enable_context_offload`、`knowledge_backend`、`enable_prompt_cache`、
   `thinking_budget` 和 `mcp_servers` 尚未全部从 `AgentConfig` 贯通到实际执行路径。
3. **内置运行时工具上下文**：`update_plan`、`read_artifact` 和 `handoff` 仍依赖私有运行时字段，
   尚未形成正式 `RunContext` 协议。
4. **Routing 恢复**：子目标等待审批后可以恢复冻结的 Agent 状态，但剩余路由编排尚未作为一等状态持久化。
5. **Plan 最终汇总**：Plan-Execute 保存所有步骤结果，但最终文本仍由最后完成的子目标决定，尚无独立 synthesis 阶段。
6. **评估闭环**：Evaluator 和 ContinuousImprovement 已存在，但尚未形成数据集版本、回归阈值和发布门禁。
7. **分布式 Artifact**：本地 ArtifactStore 不等价于跨进程、跨节点的持久化对象存储。

## 13. 验证与回归契约

当前关键测试覆盖：

- ToolPolicy 的模型侧过滤与 Executor 二次校验。
- WRITE / DESTRUCTIVE 工具审批与拒绝。
- checkpoint 后审批恢复。
- 执行账本的完成回放、参数漂移拒绝和 fail closed。
- execution-in-doubt 对账恢复。
- Provider Tool Spec 和 LLM 重试边界。
- Plan-Execute 多步骤推进和跨 Tool Round Trip。
- Reflexion Provider 自动装配。
- Routing 子 Runner 继承审批策略。
- Agent Registry 的 tool area 隔离。
- 日志 sanitizer 与 compact 内容保护。

修改运行时契约时，至少应执行：

```bash
python -m pytest -q
ruff check <changed-files>
git diff --check
```

## 14. 文件索引

| 文件 | 职责 |
|---|---|
| `src/api/v1/endpoints/agent.py` | Agent HTTP 入口、审批和对账 API |
| `src/core/agent_task/run_goal.py` | 任务装配、运行、checkpoint 和任务结果持久化 |
| `src/jobs/task_config.py` | 任务状态定义 |
| `src/core/agents/engine/agent.py` | Agent SDK 门面与 Tool Area 隔离 |
| `src/core/agents/engine/runner.py` | Runner 组装、Routing 与策略传播 |
| `src/core/agents/engine/loop.py` | Think、Act、Observe |
| `src/core/agents/engine/planning/` | ReAct、Plan-Execute、Reflexion |
| `src/core/agents/runtime/harness/harness.py` | Agent Loop 生命周期和结果构建 |
| `src/core/agents/runtime/harness/workflow.py` | 预算、取消和约束围栏 |
| `src/core/agents/runtime/harness/approval.py` | 人工审批协议 |
| `src/core/agents/runtime/harness/reconciliation.py` | 人工对账协议 |
| `src/core/agents/execution/ledger.py` | MySQL 副作用执行账本 |
| `src/core/agents/capabilities/skills/policy.py` | 每次运行的 ToolPolicy |
| `src/core/agents/state/snapshot.py` | 状态快照序列化与恢复 |
| `src/infra/streaming/trace_event_bus.py` | Trace 事件总线 |
| `tests/test_agent_strategy_contracts.py` | 策略、安全传播和日志契约测试 |
