# Project Blueprint

> TaskPilot 项目总设计文档。  
> 这份文档作为后续开发的基线，统一回答四个问题：**要做什么、怎么组织、现在做到哪、接下来做什么**。

---

## 1. 目标 (Goals)

TaskPilot 要实现的不是一个单点 Agent，也不是一个普通任务队列，而是一个**面向后端场景的 Agentic Framework**。

它的核心目标有四类：

### 1.1 Agentic Framework

提供一套可复用的 Agent 框架，让任务执行从“固定函数调用”升级为“可感知上下文、可调用工具、可按状态持续决策”的执行系统。

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

不仅要“能跑”，还要支持后续演进为平台能力。

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

**“在后端工程边界内，把任务系统升级成可控的 Agentic Execution Runtime。”**

---

## 3. 总体架构 (Overall Architecture)

## 3.1 顶层分层

```text
api   ->  jobs   ->  core
                  ^
                  |
                infra
```

### `api/`

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

### `jobs/`

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

### `core/`

应用核心层。

职责：

- Agent 框架
- Skills / Tools / LLM 接口
- 配置系统
- 依赖注入
- Prompting / Routing / Runtime Harness

这是系统的**智能执行层**。

### `infra/`

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

## 3.2 Agent 子系统架构

当前 `src/core/agents/` 的目标结构如下：

```text
src/core/agents/
├── core/           # 控制层：Agent 主入口、Loop、Prompting
├── capabilities/   # 能力层：llm / skills / tools / registry
├── state/          # 状态层：loop state / protocol / context / memory
├── execution/      # 执行层：runner / router / dispatcher / result
├── runtime/        # 运行时：hooks / harness / evaluator / debugger
└── multi_agents/   # 多 Agent（当前仍处于预留/过渡态）
```

### `core/`

控制层，负责 Agent 的主流程与上层 API。

核心文件：

- `src/core/agents/core/agent.py`
- `src/core/agents/core/loop.py`
- `src/core/agents/core/types.py`
- `src/core/agents/core/prompting/assembler.py`
- `src/core/agents/core/prompting/knowledge_selector.py`

### `capabilities/`

能力层，负责 Agent 可调用和可理解的内容。

核心目录：

- `skills/`：Skill 定义、注册、序列化、校验、执行
- `tools/`：数据库、HTTP、任务、工具方法
- `llm/`：当前主入口仍以 DeepSeek 为主
- `registry.py`：能力统一注册

### `state/`

状态层，负责运行时状态与协议抽象。

核心模块：

- `models.py`：AgentLoopState / AgentLoopResult / ToolCallRecord / StopReason
- `protocol/`：消息协议
- `context/`：上下文管理与压缩
- `memory/`：短期/长期记忆
- `snapshot.py`：状态快照（已开始补）

### `execution/`

执行层，负责把 loop、路由与执行结果组织起来。

核心模块：

- `runner.py`：AgentLoopRunner
- `router.py`：TaskRouter
- `dispatcher.py`：统一调度入口（当前偏轻量）
- `result.py`：执行结果结构

### `runtime/`

运行时层，负责生命周期与可观测。

核心模块：

- `harness/harness.py`：AgentLoopHarness
- `harness/budget.py`：预算控制
- `harness/constraints.py`：约束系统
- `harness/feedback.py`：反馈环
- `harness/improvement.py`：运行总结
- `hooks.py`：Hook 系统
- `harness/evaluator.py` / `debugger.py` / `fixtures.py`：预留能力

### `multi_agents/`

多 Agent 层，当前仍是**预留和过渡态**。

目标职责：

- Agent 间消息协议
- 消息总线
- 协调器
- 子任务分配与结果聚合

但当前代码尚未形成稳定实现，后文会单列为 TODO。

---

## 4. 关键执行链路 (Execution Flows)

## 4.1 HTTP 到任务执行

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

## 4.2 Agent Loop

```text
Agent.create()
   ↓
AgentLoopRunner
   ↓
AgentLoopHarness
   ↓
Think -> Act -> Observe
   ↓
Feedback / Constraints / Budget / Improvement
   ↓
AgentLoopResult
```

关键文件：

- `src/core/agents/core/agent.py`
- `src/core/agents/execution/runner.py`
- `src/core/agents/runtime/harness/harness.py`
- `src/core/agents/core/loop.py`

## 4.3 取消与优雅关闭

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

---

## 6. 当前现状 (Current State)

这里描述的是**当前代码的真实状态**，不是目标状态。

## 6.1 已经具备的能力

### A. API 层

已具备：

- `run_task` 接口
- `cancel_task` 接口
- `task_events/<trace_id>` SSE 事件流
- trace middleware / error handler / rate limit 等中间件

说明：

- 任务接入路径已成型
- 事件流已经可以作为前端或外部系统观察入口

### B. Jobs / Scheduler 层

已具备：

- MySQL 状态机驱动的任务调度
- 任务抢占与状态落库
- 并发限制检测
- 超时任务检测与释放
- 本地运行任务注册表
- 基于轮询的跨进程取消
- 优雅关闭时集中取消

这是当前系统最稳定的一层。

### C. Agent 核心链路

已具备：

- `Agent.create()` 统一入口
- Think / Act / Observe 循环
- `AgentLoopRunner` + `AgentLoopHarness`
- `TaskRouter` 的复杂任务拆解入口
- Dynamic Prompt Assembly
- Knowledge Injection
- Skill 执行与 Tool 调用
- Budget / Constraint / Feedback / Improvement 机制

说明：

- Agent 主链路已经成型
- 可以支撑单 Agent 的基本生产路径

### D. Skills / Tools

已具备：

- Skill 注册器与执行器
- Markdown knowledge 技能
- Database / HTTP / Task / Utils 工具域
- PermissionGuard 与风险级别控制

说明：

- “能力注册 + 模型调用 + 工具执行”这一闭环已经搭起来了

### E. Runtime / Observability

已具备：

- Harness event logging
- Streaming trace event bus
- 指标、日志、告警基础设施
- App startup / shutdown 资源编排

说明：

- 系统可观测性基础已经有了
- 但分析、评测、回放能力仍未完成

---

## 6.2 正在过渡中的部分

这些部分**有设计、有部分代码，但尚未形成稳定基线**。

### A. Planner 抽象层

现状：

- 已经出现了 `capabilities/llm/base.py` 和 provider 方向的代码设计
- 但当前实际主入口 `src/core/agents/capabilities/llm/__init__.py` 仍只导出 `DeepSeekPlanner`
- `Agent.create()` 当前仍直接绑定 DeepSeek

结论：

- **代码中有抽象尝试，但尚未真正接入主执行链路**
- 当前可视为“设计已启动，集成未完成”

### B. Agent 生命周期管理

现状：

- 已经引入 `core/lifecycle.py`、`state/snapshot.py` 方向的设计
- 但当前 `Agent.create()`、`AgentLoopRunner`、`AgentLoopHarness` 主链路尚未完整接入 pause / resume / stop / resume-from-snapshot

结论：

- **设计存在，主流程未闭环**

### C. Multi-Agent

现状：

- 代码中同时出现了 `multi_agents/` 预留实现
- 其中当前可见实现仍偏 placeholder
- 还没有稳定的消息协议、消息总线、任务分配、结果聚合主路径

结论：

- **Multi-Agent 目前不应视为已完成能力**

---

## 6.3 当前主要问题

### 1. 目标架构与当前代码仍有过渡态

例如：

- `multi_agent` / `multi_agents` 命名还不完全统一
- 一些设计文档仍引用旧路径
- 一些导出符号与当前目录结构不完全同步

### 2. LLM 抽象存在但未落到主入口

当前外部调用方仍主要面向 DeepSeek。

### 3. 生命周期管理未与主 Loop 闭环

pause / resume / stop 还没有成为正式运行接口。

### 4. Multi-Agent 仍属预留

没有达到可以依赖开发的程度。

### 5. Runtime 高级能力未完成

以下模块还偏骨架：

- `runtime/harness/evaluator.py`
- `runtime/harness/debugger.py`
- `runtime/harness/fixtures.py`

### 6. Memory 能力偏弱

- `short_term.py` 已有基础结构
- `long_term.py` 与真实持久化 / 召回策略仍未形成稳定方案

### 7. 示例与测试基线不足

当前适合开发者理解主链路，但还不足以作为完整产品级 SDK 示例体系。

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

- `core/`
- `capabilities/`
- `state/`
- `execution/`
- `runtime/`
- `multi_agents/`

### 决策 2：任务系统优先级高于 Agent 花活

所有新增 Agent 功能都必须回答：

- 如何被调度？
- 如何取消？
- 如何追踪？
- 如何超时？
- 如何测试？

若回答不了，就不能进入主路径。

### 决策 3：LLM 能力统一走 Provider / Planner 双层抽象

后续不再继续堆叠单独的模型专用 planner 作为长期方案。

目标形态：

```text
Agent
  -> Planner
      -> LLMProvider
```

### 决策 4：多 Agent 必须以消息协议为核心，而不是直接互调对象

后续 multi-agent 的扩展基于：

- Message
- MessageBus
- Coordinator

而不是 Agent 实例之间相互直接调用方法。

### 决策 5：运行时高级能力都挂到 harness 体系下

后续评测、回放、调试、mock、记录，都统一纳入 `runtime/harness/`。

---

## 8. TODO (Roadmap / To-Do)

以下 TODO 以“先固化主链路，再扩展高级能力”为顺序。

## Phase 1 - 收敛当前架构（最高优先级）

### 8.1 统一命名与目录

- [ ] 统一 `multi_agent` / `multi_agents` 命名
- [ ] 统一 `execution/` 下的 runner / router / dispatcher 导出
- [ ] 清理旧文档中的过期路径
- [ ] 校验 `src/core/agents/__init__.py` 对外导出与实际目录一致

### 8.2 固化 Agent 主入口

- [ ] 让 `Agent.create()` 不再只绑定 DeepSeek
- [ ] 明确 AgentConfig 中的 provider / planner 配置项
- [ ] 统一外部调用入口与默认构造逻辑

### 8.3 建立最小开发示例

- [ ] `examples/basic_agent.py`
- [ ] `examples/agent_with_tools.py`
- [ ] `examples/agent_with_scheduler.py`
- [ ] `examples/stream_task_events.py`

---

## Phase 2 - 完成核心能力闭环

### 8.4 Planner 抽象正式接入

- [ ] 引入 `LLMProvider` 统一接口
- [ ] 接入 OpenAI / Claude / DeepSeek provider
- [ ] 增加 Planner 抽象
- [ ] 把当前 DeepSeekPlanner 改为 provider 适配或兼容层
- [ ] 支持 tool calling 的统一消息格式

### 8.5 生命周期管理正式接入

- [ ] 让 `Agent` 暴露 `pause()` / `resume()` / `stop()`
- [ ] 在 `AgentLoopRunner` / `Harness` 中接入生命周期检查
- [ ] 让 snapshot 能恢复到可继续执行的状态
- [ ] 统一“任务取消”与“Agent 停止”的语义关系

### 8.6 Memory 方案落地

- [ ] 明确 short-term / long-term 的边界
- [ ] 实现长期记忆持久化
- [ ] 设计记忆召回策略
- [ ] 避免把 memory 做成无约束的 prompt 污染源

---

## Phase 3 - 运行时增强

### 8.7 Evaluator

- [ ] 测试集定义
- [ ] 评估指标（成功率 / token / latency / tool error rate）
- [ ] benchmark runner
- [ ] 结果持久化

### 8.8 Debugger / Replay

- [ ] 记录完整 harness 事件
- [ ] 保存可回放的 state / messages / tool results
- [ ] 支持 step-by-step replay
- [ ] 支持失败链路分析

### 8.9 Fixtures / Mock Runtime

- [ ] mock tool 结果
- [ ] mock llm 响应
- [ ] mock scheduler / lifecycle
- [ ] 形成可重复测试环境

---

## Phase 4 - 多 Agent

### 8.10 通信协议

- [ ] 明确 Message 结构
- [ ] request / response / task / result / broadcast 类型定义
- [ ] trace_id / parent_trace_id / correlation_id 约定

### 8.11 Message Bus

- [ ] 进程内消息总线
- [ ] 可选跨进程消息总线接口
- [ ] 订阅、过滤、历史记录、优先级支持

### 8.12 Coordinator

- [ ] 任务分解
- [ ] 任务分配
- [ ] 顺序 / 并行 / 动态调度策略
- [ ] 结果聚合
- [ ] 失败重分配

---

## Phase 5 - 平台化

### 8.13 API 完善

- [ ] agent run API
- [ ] agent state query API
- [ ] snapshot / resume API
- [ ] eval / replay API

### 8.14 Observability 完善

- [ ] agent step metrics
- [ ] tool latency metrics
- [ ] planner latency metrics
- [ ] structured trace events
- [ ] dashboard 与告警策略

### 8.15 文档和规范

- [ ] Skill 开发规范
- [ ] Tool 接入规范
- [ ] Provider 接入规范
- [ ] Multi-Agent 协议文档
- [ ] 测试基线文档

---

## 9. 近期待办建议 (Suggested Next Actions)

如果只做接下来一轮迭代，建议按这个顺序：

1. **统一 `src/core/agents/` 目录与导出**
2. **把 Planner 抽象真正接进 `Agent.create()`**
3. **让生命周期管理接入 Harness 主循环**
4. **补一组最小 examples + tests**
5. **最后再推进 multi-agent**

原因很简单：

- 目录和导出不稳定，后续越开发越乱
- Planner 不抽象，后面所有 LLM 扩展都会反复返工
- 生命周期不接入，Agent 只是“能跑”而不是“可控”
- 没有 examples / tests，后续文档无法成为真正基线

---

## 10. 一句话总结

TaskPilot 当前已经具备：

- **稳定的任务调度底座**
- **成型的单 Agent 执行主链路**
- **可扩展的 Skill / Tool / Prompting 基础**

但要成为后续长期开发依赖的 Agentic Framework，还需要继续完成三件事：

1. **把抽象层真正接入主路径**
2. **把生命周期和运行时闭环补齐**
3. **把多 Agent 从预留设计推进到稳定实现**

这份文档之后，后续开发应默认以这里的目标结构、现状判断和 TODO 顺序为准。
