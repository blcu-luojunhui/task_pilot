# Project Guide

> TaskPilot 的工程地图。Agent 细节见 [Agent Guide](agent.md)，启动方式见 [Quickstart](quickstart.md)。

[Back to README](../README.md)

TaskPilot 的核心不是“跑一个函数”，而是把任务从接入、调度、执行、观察到关闭组织成一条可靠链路。Agent 能力被放进这条链路里，但底层仍然由状态机、取消、超时和可观测性托住。

## Mental Model

![TaskPilot 心智模型](images/project-mental-model.png)

目标是：**让任务执行更智能，但不牺牲工程上的可控性。**

## Layers

### `api`

HTTP 接入层。负责请求解析、参数校验、响应封装、路由注册和中间件接入。这里不放业务编排逻辑。

中间件顺序：

```text
Trace → ErrorHandler → RequestLogger → RateLimit → Auth
```

### `jobs`

任务引擎层。负责调度、抢占、并发控制、状态流转、取消和关闭时的任务收敛。这里是 TaskPilot 最核心的确定性边界。

Agent 可以增强任务执行，但不能绕开 `TaskLifecycleManager`。

### `core`

能力中心。这里放 Agent Loop、Skills、LLM Provider、Multi-Agent、Chat、Auth、配置、DI 容器和启动关闭协调。

```text
src/core/
├── agents/       # Agent Loop / Skills / Tools / Memory / Runtime / Multi-Agent
├── chat/         # 会话编排、SSE、风险分级、消息仓库
├── auth/         # JWT、API Token、账户与权限
├── skills/       # 系统/个人 Skill 仓库
├── config/       # pydantic-settings
├── dependency/   # ServerContainer
└── bootstrap/    # AppContext 与资源生命周期
```

### `infra`

基础设施层。封装 MySQL、日志、告警、HTTP 客户端、事件总线和持久化。它不感知业务领域，只提供稳定能力。

## Dependency Direction

```text
api → jobs → core → infra
       │       │
       └───────┘
```

允许上层调用下层，禁止下层反向依赖上层。实际代码中 `jobs` 和 `core` 都会使用 `infra` 能力，但 `infra` 不应该知道任务或 Agent 的业务语义。

## Task State Machine

| Status | Value | Meaning |
|---|---:|---|
| `INIT` | 0 | 任务已创建，等待调度 |
| `PROCESSING` | 1 | 任务已被调度器占用并执行 |
| `SUCCESS` | 2 | 任务执行成功 |
| `CANCELLED` | 3 | 任务已协作式取消 |
| `CANCEL_REQUESTED` | 4 | 已收到取消请求，等待运行中任务响应 |
| `FAILED` | 99 | 任务异常、超时或被强制释放 |

![任务状态机](images/project-task-state-machine.png)

多进程围绕同一张 MySQL 表协作：抢占任务、观察进度、请求取消，并在异常场景下留下可追踪记录。

## Agent Lifecycle

Agent 自身的生命周期由 `LifecycleManager` 管理，独立于任务状态机：

![Agent 生命周期状态机](images/agent-lifecycle.png)

- `pause()` / `resume()`：暂停和恢复，支持快照持久化。
- `stop()`：请求停止，当前 step 完成后返回。
- `save_snapshot()` / `run_from_snapshot()`：保存并恢复 Agent 运行状态。

任务状态机回答“任务在平台里是什么状态”；Agent 生命周期回答“模型循环现在能否继续执行”。两者不要混成一个概念。

## Shutdown Path

1. 停止接收新任务。
2. 等待运行中的任务收敛。
3. 刷新日志、告警、指标和事件缓冲。
4. 释放数据库连接池、HTTP 客户端等基础资源。

优雅关闭的目标不是“看起来干净”，而是避免任务半途丢失、日志未落盘、连接未释放。

## Design Principles

- `api` 保持轻薄，只做协议适配。
- `jobs` 收敛任务生命周期，不把 Agent 不确定性泄漏到调度层。
- `core` 提供可复用能力，围绕 Loop / Skill / Prompt / Provider 演进。
- `infra` 封装外部依赖，不反向感知业务。
- 状态优先外置，进程内只保留运行态缓存。
- trace_id 必须贯穿请求、任务、Agent step、工具调用和日志。
