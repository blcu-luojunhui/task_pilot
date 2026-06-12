# TaskPilot

在工程底座上运行 Agentic Workflow。确定性兜底，Agent 驱动上限。

---

## 为什么

定时任务不问"下一步该做什么"——它在正确的时间触发正确的函数，然后等待结果。

但当任务需要理解上下文、在失败中调整策略、跨越多轮判断收敛时，`cron` 和 `Celery` 不够用。你需要 Agent，而 Agent 需要状态机、超时控制、优雅关闭——这些生产级基础设施不能妥协。

TaskPilot 把 **Think → Act → Observe** 循环接入工程底座。确定性外壳框住不确定性，智能内核驱动任务上限。

## 架构

```
api (HTTP 接入，轻薄透传)
 └─> jobs (任务引擎，确定性边界)
      └─> core ── agents/       (Agent 六层引擎)
                ├─ chat/         (对话编排 / 流式 / 风险分级)
                ├─ auth/         (JWT 鉴权 / 账户管理)
                ├─ agent_task/   (Goal 驱动任务执行)
                ├─ skills/       (知识库 Skill 仓库)
                ├─ config/       (pydantic-settings)
                ├─ dependency/   (DI 容器)
                └─ bootstrap/    (启动 / 优雅关闭)
           └─> infra ── database/       (MySQL · aiomysql 连接池)
                       ├─ observability/ (日志 / 告警 / Prometheus)
                       ├─ streaming/     (TraceEventBus / 事件持久化)
                       └─ shared/        (HTTP 客户端 / 错误码)
```

四层单向依赖。**api** 做参数校验与透传，**jobs** 收敛状态机与并发控制，**core** 是 Agent 能力中心，**infra** 不感知业务。反向依赖视为设计缺陷。

### api — HTTP 接入

Quart web 层 + 中间件栈：Trace → ErrorHandler → Logger → RateLimit → Auth。10 个端点分组：task / chat / agent / auth / skill / run / replay / health / metrics / system。

### jobs — 确定性边界

MySQL 状态机 `INIT → PROCESSING → SUCCESS / FAILED / CANCEL_REQUESTED → CANCELLED`。多进程围绕同一张 task_manager 表协作，通过轮询 CANCEL_REQUESTED 实现跨进程协作式取消。TaskScheduler 定时调度。

### core — Agent 能力中心

**agents/** 六层引擎：

| 层 | 职责 | 关键组件 |
|---|---|---|
| engine | Loop 编排 + 决策 | AgentLoopRunner / LifecycleManager / Think-Act-Observe / 3 种策略 |
| capabilities | LLM + Tool + Skill | Provider ×3 / Skill 体系 / 9 个 Tool 区域 / MCP |
| state | 状态 + 记忆 + 协议 | 双层记忆 / ContextWindowManager / 协议消息 / StateSnapshot |
| execution | 执行调度 | Dispatcher / ExecutionResult |
| runtime | 治理 + 可观测 | Budget / ConstraintSet / Debugger / Evaluator / Replay |
| multi_agents | 多智能体协作 | MessageBus / MultiAgentCoordinator / SubAgent |

**三种决策策略**：ReAct（默认，Think→Act→Observe 循环）/ Plan-Execute（先规划后逐步执行）/ Reflexion（失败后自我反思修正）。

**三种 LLM Provider**：OpenAI / Claude / DeepSeek，统一 `LLMProvider` 抽象，Tool Spec 序列化随 provider 自适应。

**chat/** — ChatTurnRunner 对话编排、SSE 流式输出、工具风险分级（READ / WRITE / DESTRUCTIVE）、高危操作需用户确认。

**auth/** — JWT + API Token 双模鉴权，账户仓库，装饰器 `@require_user`。

### infra — 基础设施

aiomysql 连接池（原生 SQL，无 ORM）、TraceIdFilter 注入日志上下文（`format: [%(trace_id)s]`）、LogService 异步缓冲写、Prometheus 指标、TraceEventBus 事件总线。

### 前端

React 18 + TypeScript + Vite + Ant Design。节点图（@xyflow/react）、流式实时更新、React Query 数据管理、Zustand 状态管理、recharts 图表、i18next 国际化。页面：Dashboard / Chat / Skills / Tasks / Runs / RunTask / Evals / Account / Login / Register。

## 关键设计

- **确定性边界框住 Agent**：Budget（max_steps / max_tool_calls / max_duration）+ ConstraintSet + 跨进程取消。Agent 不确定性不溢出 jobs 层
- **状态外置**：所有可恢复状态走 MySQL，进程内只持有运行时缓存。便于跨进程协作、重启恢复、灰度切换
- **trace_id 贯穿**：`Agent-YYYYmmddHHMMSS-xxxxxxxxxxxxxxxx`，从 HTTP 请求到 LLM 调用全链路
- **暂停/恢复/快照**：Agent 执行中可 pause() 暂停，save_snapshot() 保存，run_from_snapshot() 恢复
- **流式输出**：token 级流式回调，支持 Chat 模式下 SSE 推送
- **优雅关闭**：停止接收新任务 → 运行中任务收敛 → 刷新日志/告警/指标缓冲 → 释放连接池

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY 和数据库连接信息
python scripts/init_db.py
```

```bash
hypercorn app:app -c app_config.toml        # → localhost:6060
cd frontend && npm install && npm run dev   # → localhost:5173
```

生产模式前端内建托管：
```bash
cd frontend && npm run build
FRONTEND_DIST=frontend/dist hypercorn app:app -c app_config.toml
```

## 使用

**创建 Agent**

```python
from src.core.agents import Agent

agent = Agent.create(
    llm_api_key="<your-key>",
    llm_provider="deepseek",      # openai | claude | deepseek
    strategy="react",             # react | plan_execute | reflexion
    tool_areas=["http", "database", "utils"],
    verbose=True,
)

result = await agent.run("分析最近一周的天气趋势")
print(result.final_answer)
```

**注册 Skill**

```python
from src.core.agents import skill, SkillContext

@skill(
    name="fetch_weather",
    description="获取指定城市的天气信息",
    risk_level="read",
    parameters={"city": {"type": "string", "description": "城市名称", "required": True}},
)
async def fetch_weather(ctx: SkillContext, city: str) -> dict:
    return {"city": city, "temperature": 22, "condition": "晴"}
```

**暂停/恢复**

```python
agent.pause()
agent.save_snapshot(metadata={"reason": "manual check"})
# ... 任意时间后 ...
await agent.run_from_snapshot(snapshot_id)
```

## 了解更多

- [Agent Guide](docs/agent.md) — 六层架构详解、Loop 机制、决策策略、Memory、Multi-Agent、Runtime Harness
- [Quickstart](docs/quickstart.md) — 环境变量、数据库初始化、启动配置
- [API Guide](docs/api.md) — 端点参考
- [项目总览](docs/project.md) — 模块全景
- [设计文档](docs/design/) — 架构决策记录

---

MIT
