# TaskPilot

> From scheduled tasks to agentic execution.

任务系统最初都长一个样：接请求，入队列，改状态，写日志。

然后任务变长了。它开始依赖外部系统，需要在执行中途做判断、做重试、感知上下文变化。普通的调度器走到这里就碰到了天花板。

TaskPilot 在这个拐点上选择了两件事同时做——

**向下扎根**：并发控制、状态机、超时/取消、可观测、优雅关闭——这些是工程确定性不该妥协的部分。

**向上生长**：把 Agent Loop（Think → Act → Observe）、Skills 框架和多智能体协作接入执行链路，让任务不是被"运行"，而是在上下文里持续判断下一步。

确定性兜底，灵活性在上。

**TaskPilot 的目标，是在可控的后端工程边界内，让任务系统拥有 Agentic Workflow 的能力。**

---

## Architecture

```
api (Quart, 轻薄接入层)
  └─ jobs (任务引擎, 确定性边界)
       └─ core (Agent 引擎, 能力中心)
            └─ infra (MySQL / 日志 / 告警 / 事件总线)
```

四层单向依赖，反向依赖视为设计缺陷。每一层的职责和边界见 [Project Guide](docs/project.md)。

Agent 引擎内部结构：

```
AgentLoopRunner                    # 驱动 Think → Act → Observe 循环
  ├─ Planner                       # 将 Skills 序列化为 LLM tool calling 格式
  ├─ SkillExecutor                 # 执行工具，结果写回 transcript
  ├─ WorkflowController            # Budget / ConstraintSet / 取消 判断
  ├─ FeedbackLoop                  # 结果评估与反馈
  ├─ ContinuousImprovement         # 从反馈中学习改进
  └─ MultiAgentCoordinator         # 多智能体协作编排
```

![TaskPilot Strategy](assets/strategy.png)

---

## What It Gives You

**任务引擎**
- MySQL 状态机：`INIT → PROCESSING → SUCCESS / FAILED / CANCELLED`
- 并发控制、超时处理、跨进程协作式取消
- 优雅关闭：停止接新 → 等待收敛 → 刷新缓冲 → 释放连接池

**Agentic 执行**
- Think → Act → Observe 循环，LLM 在每步根据 transcript 动态决策
- Budget 控制（max_steps / max_tool_calls / max_duration_seconds）框住不确定性
- trace_id 贯穿全链路（格式 `Agent-YYYYmmddHHMMSS-xxxxxxxxxxxxxxxx`）

**Skills 体系**
- `@skill` 装饰器注册可执行工具，自动发现
- Markdown 知识文档注入 Agent 上下文
- Tool 区域按需启用：database / http / task / utils

**Multi-Agent 协作**
- Coordinator 编排多智能体通信与结果聚合
- MessageBus 解耦智能体间消息传递

**LLM 多提供商**
- OpenAI 兼容接口，已适配 DeepSeek / OpenAI / Claude
- Provider 抽象层，切换模型不影响上层逻辑

**可观测**
- 异步缓冲日志、prometheus 指标、TraceEventBus 事件流
- 告警服务、请求限流、全链路 trace

---

## Quick Start

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量（复制模板修改）
cp .env.example .env

# 初始化数据库
python scripts/init_db.py

# 启动服务（默认 0.0.0.0:6060）
hypercorn app:app -c app_config.toml
```

完整运行说明见 [Quickstart](docs/quickstart.md)。

---

## Define a Skill

```python
from src.core.agents.capabilities.skills import skill

@skill(
    name="fetch_weather",
    description="获取指定城市的天气信息",
    category="http",
)
async def fetch_weather(city: str) -> dict:
    """Agent 可以调用这个 Skill 获取天气数据。"""
    ...
```

Skill 注册后会被 Planner 自动发现并序列化为 LLM function call 的 tool spec，Agent 在 Loop 中按需调用。

---

## Project Structure

```
src/
├── api/          # Quart web 层：中间件、路由、校验
├── jobs/         # 任务引擎：调度器、状态机、生命周期
├── core/         # 核心能力：Agent 引擎、Skills、LLM、配置、DI
│   └── agents/
│       ├── engine/         # Agent Loop / Runner / Planner
│       ├── capabilities/   # LLM / Tools / Skills
│       ├── runtime/        # 运行时 Hook / Harness
│       ├── state/          # 状态管理 / 快照 / 上下文 / 记忆
│       ├── multi_agents/   # 多智能体协作
│       └── execution/      # 执行调度
├── infra/        # 基础设施：MySQL、日志、告警、事件总线
skills/
├── execute/      # 可执行 Skills（@skill 注册）
└── knowledge/    # 知识 Skills（Markdown 注入上下文）
docs/             # 项目文档、设计文档、开发指南
tests/            # 测试
```

---

## Read Next

- [Project Guide](docs/project.md) — 架构分层、模块职责、任务状态机
- [Agent Guide](docs/agent.md) — Agent Loop、Skills、工具适配与扩展
- [Agent Usage Guide](docs/agent-usage-guide.md) — Agent 使用指南
- [Quickstart](docs/quickstart.md) — 安装、启动、环境变量、数据库初始化
- [API Guide](docs/api.md) — 健康检查、运行任务、取消任务

---

## For Whom

- 想把传统异步任务系统升级为 Agentic Workflow
- 需要跨进程状态协同、任务取消和故障可追踪
- 希望把执行能力、领域知识与基础设施能力分层治理
- 需要在 Agent 自主性和工程可控性之间找到平衡点
- 想快速搭建 Agentic App 服务——Skill 注册即用，Loop 开箱即跑，基础设施已就绪

---

## License

MIT
