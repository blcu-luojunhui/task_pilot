# Project Blueprint v3

> TaskPilot 项目总设计文档（基于 2026-05-07 代码状态更新）。  
> 作为后续开发的基线，统一回答四个问题：**要做什么、怎么组织、现在做到哪、接下来做什么**。
>
> **v3 变更说明：** 生命周期管理已完整闭环（v2 Phase 1 §8.2 已实现）。重新评估六层架构成熟度，调整命名策略（放弃 `engine/` → `core/` 以避免与顶层 `core/` 冲突），更新 TODO 优先级。

---

## 1. 目标 (Goals)

TaskPilot 要实现的不是一个单点 Agent，也不是一个普通任务队列，而是一个**面向后端场景的 Agentic Framework**。

它的核心目标有四类：

### 1.1 Agentic Framework

提供一套可复用的 Agent 框架，让任务执行从"固定函数调用"升级为"可感知上下文、可调用工具、可按状态持续决策"的执行系统。

关键能力：

- Think / Act / Observe 循环
- Skill / Tool 注册与执行
- 动态 Prompt 组装
- 领域知识注入
- 多步任务拆解与路由
- 后续支持多 Agent 协作

### 1.2 Async Backend

整个系统以异步后端为基础，支持高并发 I/O、长时任务、外部系统调用和流式事件输出。

关键能力：

- 异步 HTTP API
- 异步 MySQL 访问
- 异步日志 / 告警 / 指标
- 异步任务注册、取消与关闭
- SSE 事件流

### 1.3 Task Scheduling

任务调度是系统的工程底座。Agent 必须运行在调度和生命周期约束之内，而不是绕过它。

关键能力：

- 基于 MySQL 状态机的任务调度
- 并发控制
- 超时检测与回收
- 协作式取消
- 优雅关闭时任务收敛

### 1.4 Extensible Runtime Platform

不仅要"能跑"，还要支持后续演进为平台能力。

关键能力：

- 可替换 LLM
- 可扩展 Tool / Skill
- 可插拔约束与 Hook
- 可观察运行轨迹
- 支持评测、调试、回放

---

## 2. 非目标 (Non-Goals)

当前阶段 **不把以下内容作为第一优先级**：

- 通用工作流编排平台（如 Airflow / Temporal 替代品）
- 前端可视化编排器
- 全量分布式队列中间件
- 完整的多租户权限平台
- 面向公开互联网的通用 Agent 平台

TaskPilot 当前聚焦于：

**"在后端工程边界内，把任务系统升级成可控的 Agentic Execution Runtime。"**

---

## 3. 总体架构 (Overall Architecture)

### 3.1 顶层分层

```text
api   ->  jobs   ->  core
                  ^
                  |
                infra
```

#### `api/`

协议接入层。

职责：

- HTTP 请求接入
- 参数解析与校验
- 路由组织
- 响应封装
- 中间件（trace / rate limit / error handler / request logger）
- SSE 事件输出

原则：

- 保持薄
- 不承载复杂业务编排
- 不直接实现 Agent 推理逻辑

#### `jobs/`

任务引擎层。

职责：

- 任务创建
- 任务抢占
- 并发控制
- 超时检测
- 任务取消
- 生命周期轮询
- 执行包装与状态落库

这是系统最重要的**确定性边界**。

#### `core/`

应用核心层。

职责：

- Agent 框架
- Skills / Tools / LLM 接口
- 配置系统
- 依赖注入
- Prompting / Routing / Runtime Harness

这是系统的**智能执行层**。

#### `infra/`

基础设施层。

职责：

- MySQL
- HTTP Client
- Observability（日志 / 告警 / 指标）
- Streaming / Trace Event Bus
- Shared 工具

原则：

- 对外提供稳定接口
- 允许内部实现替换

---

### 3.2 Agent 子系统架构

当前 `src/core/agents/` 的实际结构（50 个源文件）：

```text
src/core/agents/
├── __init__.py              # 顶层统一导出（66 个公开符号）
├── exceptions.py            # 统一异常体系（AgentError 为根，15 个子类）
│
├── engine/                  # 控制层：Agent 主入口、Loop、Lifecycle、Prompting
│   ├── __init__.py
│   ├── agent.py             # Agent + AgentConfig（用户 API）+ pause/resume/stop/snapshot
│   ├── types.py             # ActionType / ThoughtType / Thought / Action / Observation / Step
│   ├── lifecycle.py         # LifecycleManager（状态机：IDLE→RUNNING→PAUSED/STOPPED/ERROR）
│   ├── loop.py              # Think / Act / Observe 三阶段实现
│   ├── runner.py            # AgentLoopRunner（主编排器，组装 Think/Act/Observe 到 Harness）
│   └── prompting/
│       ├── __init__.py
│       ├── assembler.py     # PromptAssembler（动态 prompt 组装）
│       └── knowledge_selector.py  # KnowledgeSelector（领域知识注入）
│
├── capabilities/            # 能力层：LLM / Skills / Tools / Registry
│   ├── __init__.py
│   ├── registry.py          # CapabilityRegistry（统一能力注册）
│   ├── skills/              # Skill 系统（10 个模块）
│   │   ├── __init__.py
│   │   ├── model.py         # Skill / SkillType / RiskLevel
│   │   ├── types.py         # DependencyResolver / ToolSpecAdapter / MarkdownParser 协议
│   │   ├── context.py       # SkillContext（惰性依赖注入）
│   │   ├── registry.py      # SkillRegistry（命名空间隔离 + 全局单例）
│   │   ├── loader.py        # SkillLoader（Markdown → Skill）
│   │   ├── executor.py      # SkillExecutor（validator → guard → handler + timeout + retry）
│   │   ├── validator.py     # ParameterValidator
│   │   ├── serializer.py    # OpenAIAdapter / ClaudeAdapter / ToolSpecSerializer
│   │   ├── guard.py         # PermissionGuard（基于 RiskLevel 的权限控制）
│   │   ├── output.py        # ToolOutput（结构化返回值）
│   │   └── sql_filter.py   # SQLFilter（数据库工具安全校验）
│   ├── tools/               # 内置工具实现（5 个模块）
│   │   ├── __init__.py
│   │   ├── loader.py        # TOOL_AREAS 映射 + load_agentic_tools()
│   │   ├── utils.py         # util_md5 / util_timestamp_to_str / write_file 等
│   │   ├── http.py          # http_get / http_post
│   │   ├── database.py      # db_query / db_query_one / db_execute（带 SQLFilter）
│   │   └── task.py          # task_query_status / task_create / task_update_status 等
│   └── llm/                 # LLM 抽象层
│       ├── __init__.py
│       ├── base.py          # LLMProvider / LLMMessage / LLMResponse / LLMConfig / FinishReason
│       ├── deepseek.py      # DeepSeekPlanner（legacy，标记待废弃）
│       └── providers/
│           ├── __init__.py
│           ├── openai.py    # OpenAIProvider
│           ├── claude.py    # ClaudeProvider
│           └── deepseek.py  # DeepSeekProvider
│
├── state/                   # 状态层：运行时状态 / 协议 / 上下文 / 记忆 / 快照
│   ├── __init__.py
│   ├── models.py            # AgentState / StopReason / ToolCallRecord / AgentLoopState / AgentLoopResult
│   ├── utils.py             # generate_agent_trace_id()
│   ├── snapshot.py          # StateSnapshot（快照保存与恢复）
│   ├── protocol/
│   │   ├── __init__.py
│   │   ├── models.py        # ToolCall（标准化工具调用表示）
│   │   └── messages.py      # assistant_message / tool_result_message / normalize_tool_calls
│   ├── context/
│   │   ├── __init__.py
│   │   └── manager.py       # ContextWindowManager（token 估算 + 中段截断）
│   └── memory/
│       ├── __init__.py
│       ├── short_term.py    # ShortTermMemory（会话级）
│       └── long_term.py     # LongTermMemory + MemoryEntry（跨会话，JSON file-backed）
│
├── execution/               # 执行层：路由 / 调度 / 结果
│   ├── __init__.py
│   ├── result.py            # ExecutionStatus / ExecutionResult / ToolExecutionResult / SkillExecutionResult
│   ├── dispatcher.py        # Dispatcher（轻量统一调度入口）
│   └── router.py            # TaskRouter（目标复杂度判断 + 子目标拆解）
│
├── runtime/                 # 运行时层：Harness / Hook / 可观测 / 测试设施
│   ├── __init__.py
│   ├── hooks.py             # Hook / LoggingHook / TracingHook / HookContext
│   └── harness/
│       ├── __init__.py
│       ├── harness.py       # AgentLoopHarness（主循环驱动 + 15 种事件类型 + lifecycle 集成）
│       ├── runner.py        # HarnessRunner（简化版备选 runner）
│       ├── budget.py        # AgentBudget（max_steps / max_tool_calls / max_duration）
│       ├── constraints.py   # ConstraintSet（基于 phase 的策略门）
│       ├── workflow.py      # WorkflowController（预算 + 约束 + 取消 统一决策）
│       ├── feedback.py      # FeedbackLoop（步骤间反馈注入）
│       ├── improvement.py   # ContinuousImprovement + ImprovementRecord
│       ├── logging.py       # HarnessEventLogger（Verbose / Compact 双模式）
│       ├── debugger.py      # Debugger + TraceEvent（录制 + JSON 持久化）
│       ├── evaluator.py     # Evaluator + EvaluationMetric（骨架）
│       └── fixtures.py      # FixtureManager + MockTool
│
└── multi_agent/             # 多 Agent 层（基础可用，高级特性待补）
    ├── __init__.py
    ├── protocol.py          # Message / MessageType(7种) / MessagePriority(4级)
    ├── bus.py               # MessageBus（异步 pub/sub + broadcast + TTL + 历史）
    └── coordinator.py       # MultiAgentCoordinator（拆解 / 分配 / 并行&串行执行 / 聚合）
```

**六层架构总结：**

| 层 | 目录 | 职责 | 成熟度 |
|---|---|---|---|
| 控制层 | `engine/` | Agent 主入口、Think-Act-Observe 循环、Lifecycle、Prompt 组装 | 主链路完整 + 生命周期闭环 |
| 能力层 | `capabilities/` | LLM Provider、Skill 系统、Tool 实现、统一注册 | 核心能力完整 |
| 状态层 | `state/` | Loop State、消息协议、Context 管理、Memory、Snapshot | 基础完整 |
| 执行层 | `execution/` | 路由、调度、执行结果模型 | 轻量，Dispatcher 与 Runner 关系待明确 |
| 运行时层 | `runtime/` | Harness、预算、约束、反馈、日志、评测/调试/测试设施 | Harness 完整，评测/调试/回放待补 |
| 多 Agent 层 | `multi_agent/` | 消息协议、消息总线、协调器 | 基础可用，高级特性待补 |

---

## 4. 关键执行链路 (Execution Flows)

### 4.1 HTTP 到任务执行

```text
POST /run_task
   ↓
parse_json + schema validate
   ↓
TaskScheduler.deal()
   ↓
并发与超时检查
   ↓
写入任务表 / 抢占任务
   ↓
注册本地 asyncio task
   ↓
执行业务 handler / agent
   ↓
更新状态 / 发布事件 / 写日志 / 指标
```

关键文件：

- `src/api/v1/endpoints/tasks.py`
- `src/jobs/task_scheduler.py`
- `src/jobs/task_handler.py`
- `src/jobs/task_lifecycle.py`

### 4.2 Agent Loop（含生命周期）

```text
Agent.create(provider="openai|claude|deepseek")
   ↓
Agent.run(goal)
   ├── lifecycle.transition_to(RUNNING)
   └── AgentLoopRunner
         ↓
       AgentLoopHarness.run()
         ├── 同步 lifecycle 初始状态 → state.lifecycle_state
         │
         └── while not state.is_terminated():
               ├── ★ lifecycle.wait_if_paused()    ← 暂停检查（v3 新增）
               ├── ★ lifecycle.is_stop_requested()  ← 停止检查（v3 新增）
               ├── WorkflowController.before_step()
               │
               ├── Think  → PromptAssembler + KnowledgeSelector → LLMProvider.chat()
               ├── Act    → SkillRegistry → PermissionGuard → SkillContext → SkillExecutor
               ├── Observe → StopReason 检测 + 错误计数
               ├── FeedbackLoop → 注入系统反馈
               │
               └── WorkflowController.after_step()
         ↓
       ContinuousImprovement.capture()
         ↓
       → AgentLoopResult (trace_id / success / final_answer / stop_reason)
```

关键文件：

- `src/core/agents/engine/agent.py` — Agent.create() 工厂 + pause/resume/stop + snapshot
- `src/core/agents/engine/runner.py` — AgentLoopRunner
- `src/core/agents/runtime/harness/harness.py` — AgentLoopHarness（含 lifecycle 检查）
- `src/core/agents/engine/loop.py` — Think / Act / Observe
- `src/core/agents/engine/lifecycle.py` — LifecycleManager

### 4.3 生命周期与快照闭环（v3 新增）

```text
Agent.run(goal)                        # 正常启动
   ↓
Agent.pause()                          # 外部暂停
   ├── lifecycle.transition_to(PAUSED)
   └── Harness 主循环在 wait_if_paused() 处阻塞
         ↓
Agent.save_snapshot(metadata)          # 保存快照
   └── StateSnapshot.save(trace_id, loop_state, lifecycle_state, metadata)
         ↓
Agent.resume()                         # 恢复执行
   ├── lifecycle.transition_to(RUNNING)
   └── Harness 主循环继续从暂停点执行

Agent.run_from_snapshot(snapshot_id)   # 从快照恢复
   ├── StateSnapshot.load(snapshot_id)
   ├── 恢复 loop_state（messages / step / goal / tool_calls）
   └── 继续执行

Agent.stop()                           # 外部停止
   ├── lifecycle.transition_to(STOPPED)
   └── Harness 主循环检测到 is_stop_requested() → stop_reason=USER_CANCELLED
```

### 4.4 LLM Provider 调用链路

```text
Agent.create(llm_provider="openai")
   ↓
_PROVIDER_MAP[provider] → ProviderClass
   ↓
LLMConfig(api_key, model, base_url, temperature)
   ↓
provider = ProviderClass(config)
   ↓
planner_factory(messages, step) → provider.chat(messages, tools, temperature)
   ↓
LLMResponse → normalize_tool_calls → 内部统一格式
```

支持的 Provider：`openai` / `claude` / `deepseek`，通过 `AgentConfig.llm_provider` 切换。

### 4.5 取消与优雅关闭

```text
cancel_task API
   ↓
DB task_status = CANCEL_REQUESTED
   ↓
TaskLifecycleManager polling
   ↓
发现本地 trace_id 命中
   ↓
cancel local asyncio.Task
   ↓
等待结束或超时回收
```

关闭流程：

```text
stop accepting tasks
   ↓
shutdown lifecycle manager
   ↓
drain alert / log
   ↓
close db / http client
```

关键文件：

- `src/jobs/task_lifecycle.py`
- `src/core/bootstrap/resource_manager.py`

---

## 5. 设计原则 (Design Principles)

后续开发统一遵循这些原则。

### 5.1 Agent 不绕过任务系统

Agent 是任务执行的一种高级形式，不是独立于调度器之外的系统。

意味着：

- Agent 执行必须带 trace_id
- Agent 执行必须能被取消
- Agent 执行必须服从预算、超时和并发控制
- Agent 结果必须能被观察和追踪

### 5.2 Async-first

所有外部 I/O 默认走异步接口：

- 数据库
- HTTP
- 流式事件
- 日志/告警

同步实现只允许作为适配或边缘场景，不应该成为主路径。

### 5.3 Deterministic orchestration, agentic execution

- `jobs/` 保持确定性
- `core/agents/` 提供智能性
- 智能行为不能破坏系统状态机边界

### 5.4 Infrastructure replaceable

基础设施不应散落在业务代码中。

- MySQL 可以替换实现
- LLM 可以替换 Provider
- Tools 可以替换依赖实现
- Observability 可以替换 sink

### 5.5 Trace-first observability

`trace_id` 是任务和 Agent 执行的第一标识。

它应贯穿：

- API 请求
- TaskScheduler
- AgentLoopState
- Harness 事件
- SSE 事件
- 日志 / 指标 / 告警

### 5.6 Lifecycle-first Agent control（v3 新增）

Agent 必须是可控的，不能只是"能跑"：

- 所有 Agent 必须暴露 pause / resume / stop
- Harness 主循环每步必须检查生命周期状态
- 快照保存与恢复必须是 pause-resume 的自然延伸
- 任务系统的取消与 Agent 的 stop 在语义上对齐

---

## 6. 当前现状 (Current State)

### 6.1 已经具备的能力

#### A. API 层

已具备：

- `run_task` 接口
- `cancel_task` 接口
- `task_events/<trace_id>` SSE 事件流
- trace middleware / error handler / rate limit 等中间件

#### B. Jobs / Scheduler 层

已具备：

- MySQL 状态机驱动的任务调度
- 任务抢占与状态落库
- 并发限制检测
- 超时任务检测与释放
- 本地运行任务注册表
- 基于轮询的跨进程取消
- 优雅关闭时集中取消

这是当前系统最稳定的一层。

#### C. Agent 核心链路

已具备：

- `Agent.create()` 统一入口（支持 `openai` / `claude` / `deepseek` 三种 Provider）
- Think / Act / Observe 循环
- `AgentLoopRunner` + `AgentLoopHarness` 双 runner 架构
- `TaskRouter` 的复杂任务拆解入口
- Dynamic Prompt Assembly（PromptAssembler + KnowledgeSelector）
- Context Window Management（token 估算 + 中段截断）
- Skill 执行与 Tool 调用（含参数校验 + 权限守卫 + 超时 + 重试）
- Budget / Constraint / Feedback / Improvement 运行时治理机制
- `StateSnapshot` 的状态快照保存与恢复
- ★ **生命周期管理完整闭环**：`Agent.pause()` / `resume()` / `stop()` + Harness 每步检查
- ★ **快照保存/恢复**：`save_snapshot()` / `run_from_snapshot()` 可用

说明：

- Agent 主链路已经成型，LLM Provider 抽象已完整接入
- **v3 重大更新：生命周期不再是"代码存在但未接入"的状态——pause/resume/stop 已暴露为 Agent 的公开 API，Harness 主循环中每步检查生命周期状态**

#### D. LLM Provider 抽象

已具备：

- `LLMProvider` 统一抽象接口（`chat()` / `stream_chat()`）
- `LLMMessage` / `LLMResponse` 统一消息格式
- `OpenAIProvider` / `ClaudeProvider` / `DeepSeekProvider` 三个完整实现
- `ToolCall` 协议层支持 OpenAI / Claude 格式自动识别
- `Agent.create()` 通过 `llm_provider` 参数切换 Provider

说明：

- Provider 抽象已完整接入主链路
- `DeepSeekPlanner`（legacy）仍存在于 `capabilities/llm/deepseek.py`，作为兼容层保留，待清理

#### E. Skills / Tools

已具备：

- Skill 注册器与执行器（含 `@skill()` 装饰器）
- Markdown knowledge 技能加载（FrontmatterParser + InlineMetadataParser）
- Database / HTTP / Task / Utils 四个工具域
- PermissionGuard（READ / WRITE / DESTRUCTIVE 三级）与 SQLFilter
- SkillContext 惰性依赖注入（ContainerResolver / MappingResolver）
- ToolSpecSerializer（OpenAI / Claude 双格式适配）

#### F. Runtime / Observability

已具备：

- Harness event logging（Verbose 开发模式 + Compact 生产模式）
- Streaming trace event bus
- 指标、日志、告警基础设施
- App startup / shutdown 资源编排
- `ContinuousImprovement` 运行记录采集
- `Debugger` 事件录制 + JSON 持久化
- `FixtureManager` + `MockTool` 测试设施

说明：

- 系统可观测性基础已经有了
- 但分析、评测、回放能力仍未完成

#### G. Multi-Agent 基础

已具备：

- 7 种 MessageType + 4 级 MessagePriority
- `MessageBus` 异步消息总线（pub/sub + broadcast + TTL + 历史 + 统计）
- `MultiAgentCoordinator` 任务分解、轮询分配、并行/串行执行、结果聚合

说明：

- 已有可用基础，但心跳处理、结果回调、依赖图调度仍为 stub，不能用于生产

---

### 6.2 尚未闭环的能力

#### A. LLM 抽象存在遗留代码

现状：

- `capabilities/llm/__init__.py` 同时导出 `DeepSeekProvider`（new）和 `DeepSeekPlanner`（legacy）
- 主路径已走 new Provider，但 legacy planner 仍可被外部直接引用

结论：

- **功能已迁移，导出未收敛。需要标记 legacy 为 deprecated 并最终移除。**

#### B. Runtime 高级能力未完成

以下模块还偏骨架：

- `runtime/harness/evaluator.py` — `evaluate()` body 是 `pass`
- `runtime/harness/debugger.py` — `replay()` 是 placeholder
- `runtime/harness/fixtures.py` — 已实现但未接入测试流程

#### C. Memory 能力偏弱

- `short_term.py` 已有基础结构（消息列表 + tool results buffer）
- `long_term.py` 是 flat key-value JSON 存储，无语义检索能力
- 缺少记忆召回策略，可能退化为 prompt 污染源

#### D. Multi-Agent 高级特性未实现

以下方法目前是 stub：

- `MultiAgentCoordinator._handle_result()` — 只打 log，TODO
- `MultiAgentCoordinator._handle_heartbeat()` — 只打 log，无超时检测
- `MultiAgentCoordinator._execute_dynamic()` — 退化为 parallel，无依赖图调度
- 缺少 Agent 健康检查和故障重分配

#### E. `execution/` 层与 Runner 的关系待明确

- `AgentLoopRunner` 当前在 `engine/runner.py`，但在语义上属于执行编排
- `execution/dispatcher.py` 是轻量转发器，与 Runner 的职责边界模糊
- `execution/` 目录目前只有 3 个文件（dispatcher / result / router），过于轻量

#### F. 命名分歧问题（v3 更新）

v2 中建议 `engine/` → `core/`，但这会与项目顶层 `src/core/` 冲突，产生 `src/core/agents/core/` 这种歧义路径。

当前命名分歧：

| 项目 | 当前代码 | v2 建议 | v3 建议 |
|---|---|---|---|
| 控制层目录 | `engine/` | `core/` | `engine/`（保持，避免与顶层 `core/` 冲突）|
| 多 Agent 目录 | `multi_agent/` | `multi_agents/` | `multi_agents/`（采纳，纯命名统一）|
| Runner 位置 | `engine/runner.py` | `execution/runner.py` | `execution/runner.py`（采纳，语义上属于执行层）|
| 控制层语义 | `engine` | `core` | `engine` — 语义清晰，不产生歧义 |

---

## 7. 后续开发基线决策 (Baseline Decisions)

从这份文档开始，后续开发默认遵循以下决策。

### 决策 1：保留当前四层主骨架

顶层骨架固定为：

- `api/`
- `jobs/`
- `core/`
- `infra/`

Agent 子系统固定为：

- `engine/` — 控制层（保持当前命名，不改为 `core/`）
- `capabilities/` — 能力层
- `state/` — 状态层
- `execution/` — 执行层
- `runtime/` — 运行时层
- `multi_agents/`（当前 `multi_agent/`）— 多 Agent 层

### 决策 2：任务系统优先级高于 Agent 花活

所有新增 Agent 功能都必须回答：

- 如何被调度？
- 如何取消？
- 如何追踪？
- 如何超时？
- 如何测试？

若回答不了，就不能进入主路径。

### 决策 3：LLM 能力统一走 Provider 抽象

当前 `Agent.create()` 已经通过 `_PROVIDER_MAP` 实现了统一的 Provider 切换。后续：

- 不再新增单独的模型专用 planner
- `DeepSeekPlanner` legacy 路径标记 deprecated，逐步移除
- 新模型接入只需实现 `LLMProvider` 接口

目标形态：

```text
Agent
  → planner_factory (闭包)
      → LLMProvider.chat()
```

### 决策 4：多 Agent 必须以消息协议为核心，而不是直接互调对象

后续 multi-agent 的扩展基于：

- Message
- MessageBus
- Coordinator

而不是 Agent 实例之间相互直接调用方法。

### 决策 5：运行时高级能力都挂到 harness 体系下

后续评测、回放、调试、mock、记录，都统一纳入 `runtime/harness/`。

### 决策 6：生命周期已闭环，后续功能必须尊重这一机制（v3 更新）

`LifecycleManager` 和 `StateSnapshot` 已完整接入 Harness 主循环。后续：

- 新增 Agent 功能必须考虑 pause/resume/stop 语义
- 长时间运行的操作必须检查 `wait_if_paused()` 和 `is_stop_requested()`
- 快照数据结构变更时必须保持向后兼容

---

## 8. TODO (Roadmap / To-Do)

以下 TODO 以"先固化主链路，再扩展高级能力"为顺序。

### Phase 1 — 收敛命名 + 清理遗留（最高优先级）

#### 8.1 统一命名与目录

- [ ] `multi_agent/` → `multi_agents/` 重命名
- [ ] `engine/runner.py` → `execution/runner.py` 迁移
- [ ] 更新所有 import 路径
- [ ] 校验 `src/core/agents/__init__.py` 导出与目录一致
- [ ] 清理旧文档中的过期路径引用

#### 8.2 收敛 LLM 导出

- [ ] `DeepSeekPlanner` 标记为 deprecated
- [ ] `capabilities/llm/__init__.py` 优先导出 Provider 层，legacy 放最后
- [ ] 确保所有示例和测试使用新的 Provider 路径

#### 8.3 建立最小开发示例

- [ ] `examples/basic_agent.py`
- [ ] `examples/agent_with_tools.py`
- [ ] `examples/agent_with_lifecycle.py`（pause/resume/snapshot 演示）
- [ ] `examples/agent_with_scheduler.py`
- [ ] `examples/stream_task_events.py`

---

### Phase 2 — 完成核心能力闭环

#### 8.4 Memory 方案落地

- [ ] 明确 short-term / long-term 的边界和使用场景
- [ ] 实现长期记忆的语义检索（embedding 或关键词索引）
- [ ] 设计记忆召回策略（按相关性 + 重要性 + 时间衰减排序）
- [ ] 避免把 memory 做成无约束的 prompt 污染源

#### 8.5 execution 层职责明确

- [ ] 明确 `AgentLoopRunner` / `Dispatcher` / `TaskRouter` 三者的职责边界
- [ ] `Dispatcher` 与 `AgentLoopHarness` 的关系梳理
- [ ] 补齐 `execution/` 层文档

---

### Phase 3 — 运行时增强

#### 8.6 Evaluator

- [ ] 测试集定义
- [ ] 评估指标（成功率 / token / latency / tool error rate）
- [ ] benchmark runner
- [ ] 结果持久化

#### 8.7 Debugger / Replay

- [ ] 实现 `Debugger.replay()` — 基于录制事件回放执行过程
- [ ] 保存可回放的完整 state / messages / tool results
- [ ] 支持 step-by-step replay
- [ ] 支持失败链路分析

#### 8.8 Fixtures / Mock Runtime

- [ ] mock tool 结果注入
- [ ] mock llm 响应注入
- [ ] mock scheduler / lifecycle
- [ ] 形成可重复测试环境

---

### Phase 4 — 多 Agent

#### 8.9 通信协议完善

- [ ] 明确 Message 结构的 trace_id / parent_trace_id / correlation_id 约定
- [ ] request / response / task / result / broadcast 的完整语义定义

#### 8.10 Message Bus 增强

- [ ] 可选跨进程消息总线接口
- [ ] 订阅过滤条件增强
- [ ] 消息持久化（可选）

#### 8.11 Coordinator 高级特性

- [ ] `_handle_heartbeat` 实现 Agent 超时检测
- [ ] `_handle_result` 实现异步结果回调
- [ ] `_execute_dynamic` 实现基于依赖图的调度
- [ ] 失败子任务重分配
- [ ] Agent 健康检查与故障转移

---

### Phase 5 — 平台化

#### 8.12 API 完善

- [ ] agent run API
- [ ] agent state query API
- [ ] agent pause / resume / stop API
- [ ] snapshot / resume API
- [ ] eval / replay API

#### 8.13 Observability 完善

- [ ] agent step metrics
- [ ] tool latency metrics
- [ ] planner latency metrics
- [ ] structured trace events
- [ ] dashboard 与告警策略

#### 8.14 文档和规范

- [ ] Skill 开发规范
- [ ] Tool 接入规范
- [ ] Provider 接入规范
- [ ] Multi-Agent 协议文档
- [ ] 测试基线文档

---

## 9. 近期待办建议 (Suggested Next Actions)

如果只做接下来一轮迭代，建议按这个顺序：

1. **统一命名** — `multi_agent/` → `multi_agents/`，runner 迁到 `execution/`
2. **清理 LLM 导出** — deprecate `DeepSeekPlanner`，收敛到 Provider 层
3. **补一组最小 examples** — 特别是 lifecycle 演示（pause/resume/snapshot）
4. **execution 层梳理** — 明确 Runner / Dispatcher / Router 的关系
5. **Runtime 增强** — Evaluator / Debugger replay / Fixtures
6. **最后再推进 multi-agent 高级特性**

原因：

- 生命周期已闭环（v2 Phase 1 最大目标达成）
- 命名不统一仍然是技术债，但比 v2 时期轻量（不需要 `engine/` → `core/` 的大重命名）
- LLM 导出不收敛，新接入方可能错误使用 legacy 路径
- 没有 examples，后续文档无法成为真正基线

---

## 10. v3 主要变更记录

| 变更 | 说明 |
|---|---|
| **生命周期状态更新** | §6.1-C 确认 pause/resume/stop 已暴露为 Agent API，Harness 每步检查 lifecycle 状态 |
| **新增生命周期流程图** | §4.3 新增 pause → snapshot → resume → run_from_snapshot 完整闭环链路 |
| **新增设计原则** | §5.6 Lifecycle-first Agent control |
| **命名策略修正** | §6.2-F 放弃 `engine/` → `core/`，改为保持 `engine/`，仅做 `multi_agent/` → `multi_agents/` 和 runner 迁移 |
| **成熟度评估更新** | §3.2 控制层成熟度从"主链路完整"升级为"主链路完整 + 生命周期闭环" |
| **TODO 重排** | §8 Phase 1 移除生命周期闭环（已完成），聚焦命名统一 + LLM 导出收敛 + examples |
| **基线决策更新** | §7 决策 6 从"生命周期接入 Harness 主循环"改为"生命周期已闭环，后续功能必须尊重这一机制" |
| **Agent 子系统结构更新** | §3.2 目录树更新，标注 lifecycle 集成点 |

---

## 11. 一句话总结

TaskPilot 当前已经具备：

- **稳定的任务调度底座**
- **成型的单 Agent 执行主链路**（含三种 LLM Provider 切换）
- **完整闭环的生命周期管理**（pause / resume / stop / snapshot / run_from_snapshot）
- **可扩展的 Skill / Tool / Prompting 基础**
- **基础可用的 Multi-Agent 协调能力**

v2 中最大的技术债——生命周期未接入主循环——已在 v3 中解决。当前剩下的工作重心是：

1. **收敛命名 + 清理 LLM 遗留代码**（小范围重命名，不破坏结构）
2. **补齐 Runtime 评测/调试/回放能力**
3. **把 Multi-Agent 从基础可用推进到生产就绪**

这份文档之后，后续开发应默认以这里的目标结构、现状判断和 TODO 顺序为准。
