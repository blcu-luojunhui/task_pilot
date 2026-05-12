# Project Guide

> The engineering map behind TaskPilot.

TaskPilot 的核心不是"跑一个函数"，而是把任务从接入、调度、执行、观察到关闭组织成一条可靠链路。Agent 能力被放进这条链路里，但底层仍然由清晰的状态机和基础设施边界托住。

[Back to README](../README.md)

---

## Mental Model

```text
HTTP API (Quart)
    │
    ▼
Task Scheduler
    │
    ▼
Task Lifecycle + State Machine (MySQL)
    │
    ▼
Agent Loop / Skills / Multi-Agent
    │
    ▼
MySQL + Observability + External Tools
```

**让任务执行更智能，但不牺牲工程上的可控性。**

---

## Layers

### `api`

HTTP 接入层。负责请求解析、参数校验、响应封装和路由注册。这一层保持轻薄，不放业务逻辑。

### `jobs`

任务引擎层。负责调度、抢占、并发控制、状态流转、取消和关闭时的任务收敛。**这是 TaskPilot 最核心的确定性边界。**

### `core`

Agent 能力中心。Agent Loop、Skills 框架、LLM Provider、Multi-Agent 协作、配置系统和 DI 容器都在这里。Agent 的智能行为被组织成可注册、可执行、可替换的能力。

```
src/core/agents/
├── engine/          # Agent Loop / Runner / Planner / Lifecycle
│   └── prompting/   # Prompt 组装 / 路由 / 知识选择
├── capabilities/    # LLM / Tools / Skills
│   ├── llm/         #   Provider 抽象 + DeepSeek/OpenAI/Claude 实现
│   ├── tools/       #   Database / HTTP / Task / Utils
│   └── skills/      #   注册 / 校验 / 执行 / 序列化 / Guard
├── runtime/         # Hook / Harness（Budget / Constraint / Feedback）
├── state/           # 状态管理 / 快照 / 上下文 / 记忆
├── multi_agents/    # 多智能体协作
└── execution/       # 执行调度 / 结果
```

### `infra`

基础设施层。封装 MySQL、日志、告警、HTTP 客户端等外部依赖。业务层不直接关心底层实现，只通过明确的接口访问能力。

---

## Dependency Direction

```text
api → jobs → core
               ↑
               │
             infra
```

- `api` 只适配协议
- `jobs` 负责流程编排
- `core` 提供可复用能力
- `infra` 封装外部世界

反向依赖视为设计缺陷。

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

多进程围绕同一张 MySQL 表协作：抢占任务、观察进度、请求取消，异常场景下留下可追踪记录。

---

## Agent Lifecycle

Agent 自身的生命周期由 `LifecycleManager` 管理，独立于任务状态机：

```text
IDLE → RUNNING → PAUSED / STOPPED / ERROR
                    │
                    ▼
                  RUNNING (恢复)
```

- `pause()` / `resume()` — 暂停和恢复，支持快照持久化
- `stop()` — 请求停止，当前 step 完成后返回
- `save_snapshot()` / `run_from_snapshot()` — 状态快照，支持断点续跑

---

## Shutdown Path

1. 停止接收新任务
2. 等待运行中的任务收敛
3. 刷新日志、告警、指标
4. 释放连接池等基础资源

目标不是"优雅"本身，而是避免任务半途丢失、日志未落盘、连接未释放。

---

## Design Principles

- API 层保持轻薄，不放编排逻辑
- 编排收敛在 `jobs` 层
- 基础设施可替换
- Agent 智能增强执行，但不绕开任务生命周期
