# Project Guide

> The engineering map behind TaskPilot.

TaskPilot 的核心不是“跑一个函数”，而是把任务从接入、调度、执行、观察到关闭组织成一条可靠链路。  
Agent 能力被放进这条链路里，但底层仍然由清晰的状态机和基础设施边界托住。

[Back to README](../README.md)

---

## Mental Model

```text
HTTP API
   |
   v
Task Scheduler
   |
   v
Task Lifecycle + State Machine
   |
   v
Handlers / Agent Loop / Skills
   |
   v
MySQL + Observability + External Tools
```

TaskPilot 的设计重点是：**让任务执行更智能，但不牺牲工程上的可控性。**

---

## Layers

### `api`

HTTP 接入层。它负责请求解析、参数校验、响应封装和路由注册。  
这一层应该保持轻薄，不放复杂编排逻辑。

### `jobs`

任务引擎层。它负责调度、抢占、并发控制、状态流转、取消和关闭时的任务收敛。  
这是 TaskPilot 最核心的确定性边界。

### `core`

应用核心层。它放置 Agent Loop、Skills 框架、配置系统和依赖注入容器。  
Agent 的智能行为在这里被组织成可注册、可执行、可替换的能力。

### `infra`

基础设施层。它封装 MySQL、日志、告警、HTTP 客户端、MCP 等外部依赖。  
业务层不直接关心底层实现，只通过明确的依赖访问能力。

---

## Dependency Direction

```text
api -> jobs -> core
              ^
              |
            infra
```

原则很简单：

- `api` 只适配协议
- `jobs` 负责流程编排
- `core` 提供可复用能力
- `infra` 封装外部世界

---

## Task State Machine

| Status | Value | Meaning |
|---|---:|---|
| `INIT` | 0 | 任务已创建，等待调度 |
| `PROCESSING` | 1 | 任务已被调度器占用并执行 |
| `SUCCESS` | 2 | 任务执行成功 |
| `CANCELLED` | 3 | 任务已协作式取消 |
| `CANCEL_REQUESTED` | 4 | 已收到取消请求，等待运行中任务响应 |
| `FAILED` | 99 | 任务异常、超时或被强制释放 |

这套状态机让多个进程可以围绕同一张 MySQL 表协作：抢占任务、观察进度、请求取消，并在异常场景下留下可追踪记录。

---

## Shutdown Path

TaskPilot 的关闭过程分为四步：

1. 停止接收新任务
2. 等待运行中的任务收敛
3. 刷新日志、告警和指标
4. 释放数据库连接等基础资源

这样做的目的不是“优雅”本身，而是尽量避免任务半途丢失、日志未落盘、连接未释放。

---

## Design Principles

- Keep the API thin.
- Keep orchestration inside `jobs`.
- Keep infrastructure replaceable.
- Let Agent intelligence enhance execution without bypassing the task lifecycle.
