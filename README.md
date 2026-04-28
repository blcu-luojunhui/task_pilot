# TaskPilot

> Agentic Task Orchestration Engine

智能任务编排引擎，融合 Agent Loop 与异步任务调度，构建可观测、可取消、可扩展的自主任务执行系统。

---

## Overview

TaskPilot 不只是一个任务队列。它是一个面向 Agentic Workflow 设计的任务编排引擎：

- Agent 驱动的任务决策与执行（Think → Act → Observe 循环）
- 声明式技能注册（`@skill` 装饰器 + Markdown 知识注入）
- 多 LLM 适配（OpenAI / Claude tool spec 格式自动转换）
- 通过 MCP (Model Context Protocol) 接入外部工具和数据源
- 基于 MySQL 的分布式状态机，支持跨进程协调
- 完整的任务生命周期管理：并发控制、超时熔断、优雅取消、4 阶段关闭

```
┌──────────────────────────────────────────────────────────────┐
│                         TaskPilot                            │
│                                                              │
│  ┌───────────┐    ┌───────────┐    ┌───────────────────┐    │
│  │  HTTP API │───▶│ Scheduler │───▶│    Agent Loop      │    │
│  └───────────┘    └───────────┘    │                    │    │
│                                     │  Think → Act       │    │
│  ┌───────────┐    ┌───────────┐    │    → Observe       │    │
│  │    MCP    │◀──▶│  Skills   │◀──▶│                    │    │
│  │  Servers  │    │  Registry │    └───────────────────┘    │
│  └───────────┘    └─────┬─────┘                              │
│                         │                                    │
│              ┌──────────┴──────────┐                         │
│              │   Agentic Tools     │                         │
│              │ db │ http │ task    │                         │
│              └──────────┬──────────┘                         │
│                         │                                    │
│  ┌──────────────────────┴───────────────────────────────┐   │
│  │              Infrastructure Layer                     │   │
│  │  AsyncMySQLPool │ LogService │ AlertService │ HTTP    │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## Architecture

### 分层设计

```
src/
├── api/                            # HTTP 接入层
│   └── v1/
│       ├── endpoints/              # RESTful 端点（tasks、health）
│       ├── routes/                 # Blueprint 路由注册
│       └── utils/                  # 请求模型、校验、依赖注入
│
├── core/                           # 框架内核
│   ├── agents/
│   │   ├── skills/                 # Skills 框架
│   │   │   ├── model.py            #   Skill 数据模型（EXECUTABLE / KNOWLEDGE）
│   │   │   ├── types.py            #   协议定义（DependencyResolver / ToolSpecAdapter / MarkdownParser）
│   │   │   ├── registry.py         #   SkillRegistry + @skill 装饰器
│   │   │   ├── executor.py         #   SkillExecutor（超时、重试、错误包装）
│   │   │   ├── validator.py        #   ParameterValidator（参数验证）
│   │   │   ├── serializer.py       #   OpenAIAdapter / ClaudeAdapter（LLM 格式适配）
│   │   │   ├── context.py          #   SkillContext + ContainerResolver（按需注入）
│   │   │   └── loader.py           #   SkillLoader + 插件式 Markdown 解析器
│   │   ├── agentic_tools/          # Agent 专用工具（@skill 注册的可执行技能）
│   │   │   ├── database.py         #   db_query / db_query_one / db_execute
│   │   │   ├── http.py             #   http_get / http_post
│   │   │   ├── task.py             #   task_query_status / task_list_processing / task_cancel
│   │   │   └── utils.py            #   util_md5 / util_timestamp_to_str / ...
│   │   └── loop/                   # Agent Loop（Think / Act / Observe）
│   ├── bootstrap/                  # 应用生命周期编排
│   ├── config/                     # 配置体系（pydantic-settings）
│   └── dependency/                 # DI 容器（dependency-injector）
│
├── infra/                          # 基础设施
│   ├── database/mysql/             # 异步连接池（aiomysql）
│   ├── mcp/                        # MCP Server 集成
│   ├── observability/              # 日志 & 告警（异步队列 + 可插拔后端）
│   └── shared/                     # HTTP 客户端、工具函数、响应封装
│
├── jobs/                           # 任务引擎
│   ├── task_handler.py             # 处理器基类 + @register 装饰器
│   ├── task_scheduler.py           # 调度器（并发控制、状态机、超时熔断）
│   ├── task_lifecycle.py           # 生命周期管理（注册表、取消轮询）
│   ├── task_config.py              # 状态常量、任务配置
│   └── task_utils.py               # 异常体系、校验工具
│
├── skills/                         # 知识型 Skill Markdown 文件
│   └── knowledge/
│       ├── task-scheduling-principles.md
│       ├── database-query-patterns.md
│       ├── http-client-usage.md
│       └── observability-best-practices.md
│
└── tests/                          # 测试
```

### 依赖方向

```
api → jobs → core ← infra
               ↑
     agents/agentic_tools
         ↓ uses
     agents/skills (框架)
         ↓ uses
        infra (基础设施)
```

| 层 | 职责 | 原则 |
|---|---|---|
| `api` | HTTP 协议适配，请求解析与响应封装 | 薄层，不含业务逻辑 |
| `jobs` | 任务调度、状态机、生命周期管理 | 核心编排，可独立于 HTTP 运行 |
| `core/agents/skills` | Skills 框架（模型、注册、执行、序列化） | 可扩展协议，面向接口 |
| `core/agents/agentic_tools` | Agent 专用工具（@skill 注册的可执行技能） | 应用层，封装 infra 能力 |
| `core/agents/loop` | Agent Loop（Think / Act / Observe） | 决策引擎 |
| `infra` | 数据库、MCP、日志、告警、HTTP 客户端 | 可替换实现 |

---

## Skills System

TaskPilot 的 Skills 系统支持两种技能类型：

### 可执行技能（Executable Skills）

通过 `@skill` 装饰器注册，Agent 在 Act 阶段调用：

```python
from src.core.agents.skills import skill, SkillContext

@skill(
    name="db_query",
    description="从 MySQL 数据库查询数据",
    dependencies=["db", "log"],
    parameters={
        "query": {"type": "string", "description": "SQL 查询语句", "required": True},
        "params": {"type": "array", "description": "查询参数", "required": False},
    },
)
async def db_query(ctx: SkillContext, query: str, params=None):
    return await ctx.db.async_fetch(query=query, params=params)
```

### 知识型技能（Knowledge Skills）

从 Markdown 文件加载，注入到 Agent prompt 中指导决策：

```markdown
---
name: database-query-patterns
description: 数据库查询的最佳实践
category: database
scope: agent:*
---

## Guidelines
- 使用参数化查询防止 SQL 注入
- 批量操作使用 batch=True 提升性能
- 查询单条记录用 async_fetch_one()
```

### 内置 Agentic Tools（13 个）

| 工具 | 说明 | 依赖 |
|------|------|------|
| `db_query` | 查询多行数据 | db, log |
| `db_query_one` | 查询单条数据 | db, log |
| `db_execute` | 执行写操作 | db, log |
| `http_get` | HTTP GET 请求 | log |
| `http_post` | HTTP POST 请求 | log |
| `task_query_status` | 查询任务状态 | db, log |
| `task_list_processing` | 列出执行中任务 | db, log |
| `task_cancel` | 请求取消任务 | db, log |
| `util_md5` | 计算 MD5 哈希 | - |
| `util_timestamp_to_str` | 时间戳转字符串 | - |
| `util_generate_trace_id` | 生成追踪 ID | - |
| `util_batch_split` | 分批处理数据 | - |
| `util_current_time` | 获取当前时间 | - |

### LLM Tool Spec 适配

自动生成不同 LLM 的工具描述格式：

```python
from src.core.agents.skills import get_global_registry, ClaudeAdapter, ToolSpecSerializer

registry = get_global_registry()

# OpenAI 格式（默认）
specs = registry.to_tool_specs()

# Claude 格式
claude_serializer = ToolSpecSerializer(ClaudeAdapter())
specs = claude_serializer.serialize_many(registry.list_executable())
```

```json
// Claude tool use 格式
{
  "name": "db_query",
  "description": "从 MySQL 数据库查询数据",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "SQL 查询语句"},
      "params": {"type": "array", "description": "查询参数"}
    },
    "required": ["query"]
  }
}
```

### 执行器（SkillExecutor）

支持超时控制、重试机制、参数验证：

```python
from src.core.agents.skills import SkillExecutor, SkillContext

executor = SkillExecutor(
    timeout=30.0,       # 执行超时（秒）
    retry=2,            # 重试次数
    retry_delay=1.0,    # 重试延迟（秒）
    validate_params=True # 参数验证
)

skill = registry.get("db_query")
ctx = SkillContext.build(skill, server_container)
result = await executor.execute(skill, ctx, query="SELECT * FROM articles LIMIT 10")
```

### 可扩展协议

通过 Protocol 接口支持自定义扩展：

| 协议 | 用途 | 示例 |
|------|------|------|
| `DependencyResolver` | 自定义依赖注入 | 测试 mock、多环境切换 |
| `ToolSpecAdapter` | 自定义工具描述格式 | 适配新的 LLM API |
| `MarkdownParser` | 自定义 Markdown 解析 | 支持新的元数据格式 |

---

## Core Concepts

### Task State Machine

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

| 状态 | 值 | 触发条件 |
|------|---|---------|
| `INIT` | 0 | `INSERT` 任务记录 |
| `PROCESSING` | 1 | 乐观锁 `UPDATE WHERE status=0` |
| `SUCCESS` | 2 | 处理器返回 `TaskStatus.SUCCESS` |
| `CANCELLED` | 3 | 捕获 `CancelledError` |
| `CANCEL_REQUESTED` | 4 | 调用 `/cancel_task` API |
| `FAILED` | 99 | 异常抛出或超时强制释放 |

### Async Task Cancellation

跨进程协作式取消机制：

```
Client          MySQL              LifecycleManager       asyncio.Task
  │                │                      │                     │
  │ POST /cancel   │                      │                     │
  │───────────────▶│                      │                     │
  │                │                      │                     │
  │  status → 4    │                      │                     │
  │◀───────────────│                      │                     │
  │                │   poll every 5s      │                     │
  │                │◀─────────────────────│                     │
  │                │  rows with status=4  │                     │
  │                │─────────────────────▶│                     │
  │                │                      │  task.cancel()      │
  │                │                      │────────────────────▶│
  │                │                      │  CancelledError     │
  │                │                      │◀────────────────────│
  │                │  status → 3          │                     │
  │                │◀─────────────────────│                     │
```

### Graceful Shutdown

```
Phase 1: Stop Accepting       → app.config["ACCEPTING_TASKS"] = False
Phase 2: Drain Running Tasks  → TaskLifecycleManager.shutdown(timeout=30s)
Phase 3: Flush Observability   → AlertService.stop() + LogService.stop()
Phase 4: Release Resources     → AsyncMySQLPool.close_pools()
```

---

## Agentic Workflow

TaskPilot 的终极形态是由 Agent 驱动整个任务系统的运转：

```
┌─────────────────────────────────────────────────┐
│                  Agent Loop                      │
│                                                  │
│   ┌─────────┐                                    │
│   │  Think  │  分析任务目标，规划执行策略           │
│   └────┬────┘                                    │
│        ▼                                         │
│   ┌─────────┐  ┌──────────────────────────────┐  │
│   │   Act   │─▶│ SkillRegistry.get("db_query") │  │
│   └────┬────┘  │ SkillExecutor.execute(...)    │  │
│        │       └──────────────────────────────┘  │
│        ▼                                         │
│   ┌─────────┐                                    │
│   │ Observe │  评估结果，决定继续/重试/终止         │
│   └────┬────┘                                    │
│        └──────▶ 循环直到任务完成或达到终止条件      │
└─────────────────────────────────────────────────┘
```

设计原则：

- Agent 是任务的执行者 — Agent Loop 运行在 `asyncio.Task` 内，受同一套并发控制和取消机制管理
- Skills 是 Agent 的手和脚 — `@skill` 注册可执行技能，Markdown 注入领域知识
- Agentic Tools 封装基础设施 — 数据库、HTTP、任务管理等能力通过 `SkillContext` 按需注入
- MCP 是 Agent 的眼睛 — 通过 MCP Server 获取外部上下文
- 可观测性贯穿全程 — 每一步 Think/Act/Observe 都通过 LogService 记录

---

## Quick Start

### Requirements

- Python 3.11+
- MySQL 5.7+

### Install & Run

```bash
pip install -r requirements.txt
cp .env.example .env  # 编辑 .env，填入数据库连接信息

# 本地开发
hypercorn app:app -c app_config.toml

# Docker
docker-compose up -d
```

服务监听 `0.0.0.0:6060`，Hypercorn 4 workers。

### Environment Variables

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

---

## API Reference

### Health Check

```http
GET /api/health
```

### Run Task

```http
POST /api/run_task
Content-Type: application/json

{"task_name": "my_task", "date_string": "2025-04-28"}
```

### Cancel Task

```http
POST /api/cancel_task
Content-Type: application/json

{"trace_id": "Task-20250428143022-a1b2c3d4e5f6g7h8"}
```

---

## Extending TaskPilot

### Register a Task Handler

```python
from src.jobs.task_handler import register
from src.jobs.task_config import TaskStatus

@register("crawl_articles")
async def crawl_articles(self) -> int:
    target_date = self.data.get("date_string")
    articles = await fetch_articles(target_date)
    await self.db_client.async_save(
        "INSERT INTO articles (title, content) VALUES (%s, %s)",
        [(a["title"], a["content"]) for a in articles],
        batch=True,
    )
    return TaskStatus.SUCCESS
```

### Register an Agentic Tool

```python
from src.core.agents.skills import skill, SkillContext

@skill(
    name="search_articles",
    description="搜索文章",
    dependencies=["db"],
    parameters={
        "keyword": {"type": "string", "description": "搜索关键词", "required": True},
        "limit": {"type": "integer", "description": "返回数量", "default": 10},
    },
)
async def search_articles(ctx: SkillContext, keyword: str, limit: int = 10):
    return await ctx.db.async_fetch(
        "SELECT * FROM articles WHERE title LIKE %s LIMIT %s",
        params=(f"%{keyword}%", limit),
    )
```

### Custom LLM Adapter

```python
from src.core.agents.skills import ToolSpecAdapter, ToolSpecSerializer

class MyLLMAdapter:
    def to_spec(self, skill):
        return {"tool_name": skill.name, "tool_desc": skill.description, ...}

serializer = ToolSpecSerializer(MyLLMAdapter())
specs = serializer.serialize_many(registry.list_executable())
```

### Custom Dependency Resolver

```python
from src.core.agents.skills import DependencyResolver, SkillContext

class TestResolver:
    def resolve(self, dep_name):
        if dep_name == "db":
            return MockDatabase()
        raise ValueError(f"Unknown: {dep_name}")

ctx = SkillContext.from_resolver(TestResolver())
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Web Framework | Quart 0.19 | Async Flask-compatible ASGI framework |
| ASGI Server | Hypercorn | HTTP/2 + WebSocket, multi-worker |
| Database | MySQL + aiomysql 0.2 | Async connection pooling, distributed state |
| Config | pydantic-settings 2.12 | Type-safe configuration with env/file sources |
| DI Container | dependency-injector 4.48 | Declarative singleton/factory providers |
| HTTP Client | aiohttp 3.10 | Async HTTP for external API calls |
| Retry | tenacity 9.0 | Exponential backoff with configurable policies |
| Validation | Pydantic 2.10 | Request/response schema validation |

---

## License

MIT
