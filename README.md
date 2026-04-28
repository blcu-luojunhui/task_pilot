# TaskPilot

> Agentic Task Orchestration Engine

智能任务编排引擎，融合 Agent Loop 与异步任务调度，构建可观测、可取消、可扩展的自主任务执行系统。

---

## Overview

TaskPilot 不只是一个任务队列。它是一个面向 Agentic Workflow 设计的任务编排引擎：

- Agent 驱动的任务决策与执行（Think → Act → Observe 循环）
- 通过 MCP (Model Context Protocol) 接入外部工具和数据源
- 基于 MySQL 的分布式状态机，支持跨进程协调
- 完整的任务生命周期管理：并发控制、超时熔断、优雅取消、4 阶段关闭

```
┌─────────────────────────────────────────────────────────┐
│                      TaskPilot                          │
│                                                         │
│  ┌───────────┐    ┌───────────┐    ┌───────────────┐   │
│  │  HTTP API │───▶│ Scheduler │───▶│  Agent Loop   │   │
│  └───────────┘    └───────────┘    │               │   │
│                                     │ Think → Act   │   │
│  ┌───────────┐    ┌───────────┐    │   → Observe   │   │
│  │    MCP    │◀──▶│  Skills   │◀──▶│               │   │
│  │  Servers  │    │  Registry │    └───────────────┘   │
│  └───────────┘    └───────────┘                         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │           Infrastructure Layer                   │   │
│  │  MySQL Pool │ LogService │ AlertService │ HTTP   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## Architecture

### 分层设计

```
src/
├── api/                        # HTTP 接入层
│   └── v1/
│       ├── endpoints/          # RESTful 端点（tasks、health）
│       ├── routes/             # Blueprint 路由注册
│       └── utils/              # 请求模型、校验、依赖注入
│
├── core/                       # 框架内核
│   ├── agents/                 # Agent 系统
│   │   ├── loop/               # Agent Loop（Think / Act / Observe）
│   │   └── skills/             # 技能注册与调度
│   ├── bootstrap/              # 应用生命周期编排
│   ├── config/                 # 配置体系（pydantic-settings）
│   └── dependency/             # DI 容器（dependency-injector）
│
├── infra/                      # 基础设施
│   ├── database/mysql/         # 异步连接池（aiomysql）
│   ├── mcp/                    # MCP Server 集成
│   ├── observability/          # 日志 & 告警（异步队列 + 可插拔后端）
│   └── shared/                 # HTTP 客户端、工具函数、响应封装
│
└── jobs/                       # 任务引擎
    ├── task_handler.py         # 处理器基类 + @register 装饰器
    ├── task_scheduler.py       # 调度器（并发控制、状态机、超时熔断）
    ├── task_lifecycle.py       # 生命周期管理（注册表、取消轮询）
    ├── task_config.py          # 状态常量、任务配置
    └── task_utils.py           # 异常体系、校验工具
```

### 依赖方向

```
api → jobs → core ← infra
              ↑
           agents
```

| 层 | 职责 | 原则 |
|---|---|---|
| `api` | HTTP 协议适配，请求解析与响应封装 | 薄层，不含业务逻辑 |
| `jobs` | 任务调度、状态机、生命周期管理 | 核心编排，可独立于 HTTP 运行 |
| `core` | 配置、DI、Agent Loop、启动编排 | 稳定内核，极少变动 |
| `infra` | 数据库、MCP、日志、告警、HTTP 客户端 | 可替换实现，面向接口 |

---

## Core Concepts

### Task State Machine

任务在整个生命周期中经历以下状态流转：

```
                    ┌──────────────────────────────────┐
                    │          CANCEL_REQUESTED (4)     │
                    │         ┌──────────┐              │
                    ▼         │          │              │
  ┌──────┐    ┌────────────┐ │    ┌─────────────┐     │
  │ INIT │───▶│ PROCESSING │─┘    │  CANCELLED  │     │
  │ (0)  │    │    (1)     │─────▶│    (3)      │     │
  └──────┘    └────────────┘      └─────────────┘     │
                    │                                   │
                    ├──────────────────────────────────┘
                    │
              ┌─────┴─────┐
              ▼           ▼
        ┌─────────┐ ┌──────────┐
        │ SUCCESS │ │  FAILED  │
        │   (2)   │ │   (99)   │
        └─────────┘ └──────────┘
```

| 状态 | 值 | 含义 | 触发条件 |
|------|---|------|---------|
| `INIT` | 0 | 已创建，等待执行 | `INSERT` 任务记录 |
| `PROCESSING` | 1 | 执行中（已获取锁） | 乐观锁 `UPDATE WHERE status=0` |
| `SUCCESS` | 2 | 执行成功 | 处理器返回 `TaskStatus.SUCCESS` |
| `CANCELLED` | 3 | 已取消 | 捕获 `CancelledError` |
| `CANCEL_REQUESTED` | 4 | 取消请求中 | 调用 `/cancel_task` API |
| `FAILED` | 99 | 执行失败 | 异常抛出或超时强制释放 |

### Async Task Cancellation

TaskPilot 实现了跨进程的协作式任务取消机制：

```
┌──────────┐     ┌───────────┐     ┌──────────────────┐     ┌──────────────┐
│  Client  │     │  MySQL    │     │ LifecycleManager │     │ asyncio.Task │
│          │     │           │     │  (Poll Loop)     │     │              │
└────┬─────┘     └─────┬─────┘     └────────┬─────────┘     └──────┬───────┘
     │                 │                     │                      │
     │ POST /cancel    │                     │                      │
     │────────────────▶│                     │                      │
     │                 │                     │                      │
     │  status → 4     │                     │                      │
     │  (CANCEL_REQ)   │                     │                      │
     │◀────────────────│                     │                      │
     │                 │                     │                      │
     │                 │   poll every 5s     │                      │
     │                 │◀────────────────────│                      │
     │                 │                     │                      │
     │                 │  rows with status=4 │                      │
     │                 │────────────────────▶│                      │
     │                 │                     │                      │
     │                 │                     │  task.cancel()       │
     │                 │                     │─────────────────────▶│
     │                 │                     │                      │
     │                 │                     │  CancelledError      │
     │                 │                     │◀─────────────────────│
     │                 │                     │                      │
     │                 │  status → 3         │                      │
     │                 │◀────────────────────│                      │
     │                 │  (CANCELLED)        │                      │
```

设计要点：

- 信号传递：通过 MySQL 行状态而非进程信号，天然支持多实例部署
- 协作式取消：任务通过 `asyncio.CancelledError` 感知取消，可在 `finally` 中做清理
- 轮询间隔：默认 5 秒，可通过 `poll_interval` 参数调整
- 强制超时：取消信号发出后，等待 `force_kill_timeout`（默认 10s），超时则强制结束
- 幂等性：重复取消同一任务不会产生副作用

### Graceful Shutdown

4 阶段有序关闭，确保数据不丢失：

```
Phase 1: Stop Accepting
  └─ app.config["ACCEPTING_TASKS"] = False
  └─ 新请求返回 503

Phase 2: Drain Running Tasks
  └─ TaskLifecycleManager.shutdown(timeout=30s)
  └─ cancel 所有运行中任务，等待完成

Phase 3: Flush Observability
  └─ AlertService.stop(drain_timeout=5s)
  └─ LogService.stop(drain_timeout=10s)
  └─ 确保告警和日志队列排空

Phase 4: Release Resources
  └─ AsyncMySQLPool.close_pools()
  └─ 关闭所有数据库连接
```

### Concurrency Control & Timeout

```python
# 每个任务名可独立配置
TaskConfig(
    timeout=1800,          # 超时阈值（秒）
    max_concurrent=5,      # 最大并发数
    alert_on_failure=True, # 失败时触发告警
)
```

调度器在执行前自动检查：
1. 扫描该任务名下所有 `PROCESSING` 状态的记录
2. 超时任务 → 强制释放 + 触发告警
3. 活跃任务数 >= `max_concurrent` → 拒绝执行 + 触发告警

---

## Agentic Workflow (Roadmap)

TaskPilot 的终极形态是由 Agent 驱动整个任务系统的运转：

```
┌─────────────────────────────────────────────┐
│                Agent Loop                    │
│                                              │
│   ┌─────────┐                                │
│   │  Think  │  分析任务目标，规划执行策略       │
│   └────┬────┘                                │
│        ▼                                     │
│   ┌─────────┐                                │
│   │   Act   │  调用 Skills / MCP Tools 执行   │
│   └────┬────┘                                │
│        ▼                                     │
│   ┌─────────┐                                │
│   │ Observe │  评估结果，决定继续/重试/终止     │
│   └────┬────┘                                │
│        │                                     │
│        └──────▶ 循环直到任务完成或达到终止条件  │
└─────────────────────────────────────────────┘
```

#### Agent 与任务系统的集成点

| 集成点 | 说明 |
|--------|------|
| `core/agents/loop/` | Think-Act-Observe 循环引擎 |
| `core/agents/skills/` | 技能注册表，Agent 可调用的原子能力 |
| `infra/mcp/` | MCP Server 适配层，接入外部工具和数据源 |
| `jobs/task_handler.py` | Agent 作为一种特殊的 TaskHandler 注册 |
| `jobs/task_lifecycle.py` | Agent Loop 的中断与恢复由生命周期管理器协调 |

#### 设计原则

- Agent 是任务的执行者，不是任务本身 — Agent Loop 运行在 `asyncio.Task` 内，受同一套并发控制和取消机制管理
- Skills 是 Agent 的手和脚 — 每个 Skill 是一个可注册的异步函数，Agent 在 Act 阶段选择并调用
- MCP 是 Agent 的眼睛 — 通过 MCP Server 获取外部上下文（数据库查询、API 调用、文件读取等）
- 可观测性贯穿全程 — Agent 的每一步 Think/Act/Observe 都通过 LogService 记录，异常通过 AlertService 告警

---

## Quick Start

### Requirements

- Python 3.11+
- MySQL 5.7+

### Install

```bash
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# 编辑 .env，填入数据库连接信息
```

必填环境变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `TASK_PILOT_DB_HOST` | MySQL 地址 | `localhost` |
| `TASK_PILOT_DB_PORT` | MySQL 端口 | `3306` |
| `TASK_PILOT_DB_USER` | MySQL 用户 | `root` |
| `TASK_PILOT_DB_PASSWORD` | MySQL 密码 | (必填) |
| `TASK_PILOT_DB_DB` | 数据库名 | `task_pilot` |
| `TASK_TABLE` | 任务表名 | `task_manager` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

### Database Schema

```sql
CREATE TABLE task_manager (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    date_string      VARCHAR(64)    NULL,
    task_name        VARCHAR(256)   NULL,
    task_status      TINYINT        NOT NULL DEFAULT 0
        COMMENT '0:INIT 1:PROCESSING 2:SUCCESS 3:CANCELLED 4:CANCEL_REQUESTED 99:FAILED',
    start_timestamp  BIGINT         NULL,
    finish_timestamp BIGINT         NULL,
    trace_id         VARCHAR(128)   NULL,
    data             JSON           NULL,
    UNIQUE INDEX uk_trace_id (trace_id),
    INDEX idx_date_task (date_string, task_name),
    INDEX idx_status_task_name (task_status, task_name),
    INDEX idx_task_name (task_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Run

```bash
# 本地开发
hypercorn app:app -c app_config.toml

# Docker
docker-compose up -d
```

服务监听 `0.0.0.0:6060`，Hypercorn 4 workers。

---

## API Reference

### Health Check

```http
GET /api/health
```

```json
{"code": 0, "message": "success", "data": {"message": "TaskPilot is running"}}
```

### Run Task

```http
POST /api/run_task
Content-Type: application/json

{"task_name": "my_task", "date_string": "2025-04-28"}
```

```json
{
  "code": 0,
  "status": "task execute successfully",
  "task_name": "my_task",
  "data": {
    "code": 0,
    "message": "Task started successfully",
    "trace_id": "Task-20250428143022-a1b2c3d4e5f6g7h8"
  }
}
```

### Cancel Task

```http
POST /api/cancel_task
Content-Type: application/json

{"trace_id": "Task-20250428143022-a1b2c3d4e5f6g7h8"}
```

```json
{"code": 0, "message": "cancel requested", "trace_id": "Task-20250428143022-a1b2c3d4e5f6g7h8"}
```

---

## Extending TaskPilot

### Register a Task Handler

```python
from src.jobs.task_handler import register
from src.jobs.task_config import TaskStatus

@register("crawl_articles")
async def crawl_articles(self) -> int:
    """
    self.data       → 请求参数 dict
    self.db_client  → AsyncMySQLPool
    self.trace_id   → 追踪 ID
    self.log_client → LogService
    self.config     → ProjectConfigSettings
    """
    target_date = self.data.get("date_string")

    articles = await fetch_articles(target_date)
    await self.db_client.async_save(
        "INSERT INTO articles (title, content) VALUES (%s, %s)",
        [(a["title"], a["content"]) for a in articles],
        batch=True,
    )

    await self._log_task_event("crawl_completed", count=len(articles))
    return TaskStatus.SUCCESS
```

### Custom Log Backend

```python
class SLSLogService(LogService):
    @staticmethod
    def _put_log(contents: dict):
        # 接入阿里云 SLS
        sls_client.put_logs(contents)
```

### Custom Alert Backend

```python
async def feishu_alert(title, detail, **kwargs):
    # 接入飞书机器人
    await http_client.post(webhook_url, json={"title": title, "detail": detail})

AlertService.initialize(alert_backend=feishu_alert)
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Web Framework | Quart 0.19 | Async Flask-compatible ASGI framework |
| ASGI Server | Hypercorn | HTTP/2 + WebSocket support, multi-worker |
| Database | MySQL + aiomysql 0.2 | Async connection pooling, distributed state |
| Config | pydantic-settings 2.12 | Type-safe configuration with env/file sources |
| DI Container | dependency-injector 4.48 | Declarative singleton/factory providers |
| HTTP Client | aiohttp 3.10 | Async HTTP for external API calls |
| Retry | tenacity 9.0 | Exponential backoff with configurable policies |
| Validation | Pydantic 2.10 | Request/response schema validation |

---

## License

MIT