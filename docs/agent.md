# TaskPilot Agent 子系统架构设计

> 版本: v2.0 | 日期: 2026-06-11 | 基线代码: `../src/core/agents`

## 1. 设计总览

### 1.1 一句话定位

TaskPilot Agent 是一个**工程治理 + Agentic 灵活性**双层架构：底层是确定性工程边界（状态机、Budget、约束、快照），上层是可插拔的决策智能（策略、记忆、反思、多代理协作）。

### 1.2 核心设计理念

| 原则 | 含义 | 实现位置 |
|------|------|----------|
| **确定性外壳** | Agent 的不确定性不溢出到任务引擎层；状态机、Budget、超时、取消都在 harness 收敛 | `harness/` + `workflow.py` + `budget.py` |
| **策略可插拔** | 决策循环算法（ReAct/PlanExecute/Reflexion）与 Harness 解耦，通过 Protocol 注入 | `engine/planning/` |
| **状态外置** | 所有可恢复状态进 MySQL/JSON 快照，进程内只持有运行时缓存 | `state/snapshot.py` |
| **渐进增强** | 每个能力都能单独开关、单独灰度、单独回滚 | `AgentConfig` 的 30+ 配置项 |
| **可观测优先** | trace_id 贯穿全链路，每个阶段发 harness 事件 | `HarnessEventLogger` |
| **失败显式** | 错误不静默吞掉，tool call 失败回到 transcript 让 LLM 可见并自行修正 | `Observe` 错误计数 + `ReflectionProvider` |

### 1.3 六层架构

```
api (HTTP 接入)
 └─ jobs (任务引擎，确定性边界)
     └─ core/agents/
         ├─ engine/         Layer 1: 控制层 — Agent 大脑
         ├─ capabilities/   Layer 2: 能力层 — LLM/Skill/Tool
         ├─ state/          Layer 3: 状态层 — State/Context/Memory/Snapshot
         ├─ execution/      Layer 4: 执行层 — Dispatcher 统一门面
         ├─ runtime/        Layer 5: 运行时 — Harness/Budget/Feedback/Evaluator
         └─ multi_agents/   Layer 6: 多代理 — Coordinator/SubAgent/Handoff
```

跨层调用方向单向（api → jobs → core → infra），反向依赖视为设计缺陷。

---

## 2. 主执行链路

### 2.1 单 Agent 完整链路

```
Agent.create(config)
  │
  ├─ load_agentic_tools()          → 全局 SkillRegistry
  ├─ _build_provider()             → LLMProvider (OpenAI/Claude/DeepSeek)
  ├─ _build_planner()              → AssistantPlanner (闭包，封装 tool 序列化/调用)
  ├─ _build_runner()               → AgentLoopRunner
  │     ├─ Think(planner, prompt_assembler, memory_manager, context_manager)
  │     ├─ Act(registry, executor, artifact_store)
  │     ├─ Observe(abort_on_tool_error, memory_manager)
  │     ├─ MemoryManager           → 短期 + 长期 + 可插拔检索后端
  │     ├─ ContextWindowManager   → token 预算感知的上下文压缩
  │     ├─ AgentBudget             → max_steps / max_tool_calls / max_duration
  │     ├─ ConstraintSet           → 策略门禁
  │     ├─ FeedbackLoop            → ReflectionProvider 注入反思
  │     ├─ DecisionStrategy        → ReAct / PlanExecute / Reflexion
  │     └─ AgentLoopHarness        → 聚合上述所有组件
  │
Agent.run(goal)
  └─ AgentLoopHarness.run()
       │
       ├─ strategy.on_run_start()        ← PlanExecute: 生成计划
       │
       └─ while not terminated:
            ├─ lifecycle.wait_if_paused()
            ├─ workflow.before_step()     ← Budget + Constraints 检查
            ├─ strategy.run_step()
            │    ├─ Think.run()
            │    │    ├─ MemoryManager.retrieve()  → 相关记忆注入
            │    │    ├─ PromptAssembler.assemble() → system prompt 组装
            │    │    ├─ ContextWindowManager.compact() → 上下文压缩
            │    │    └─ planner(messages, step)  → LLM 调用
            │    ├─ Act.run()
            │    │    ├─ SkillRegistry.get()   → 查找 tool
            │    │    ├─ SkillExecutor.execute() → 执行 tool
            │    │    └─ ArtifactStore.put()   → 超长结果卸载
            │    └─ Observe.run()
            │         ├─ 检测 final answer  → MODEL_FINAL
            │         ├─ 追踪 consecutive_tool_errors
            │         └─ MemoryManager.add()  → 写入短期记忆
            ├─ feedback_loop.run()          ← ReflectionProvider: 错误反思
            ├─ workflow.after_step()
            ├─ 构建 Step 记录
            └─ strategy.on_step_end()
```

### 2.2 策略驱动 vs Harness 控制

两个维度的分工：

| 职责 | 归属 | 说明 |
|------|------|------|
| Think → Act → Observe 决策 | `DecisionStrategy` | 策略决定每一"步"内部如何执行 |
| 生命周期 / Budget / 事件 / 反馈 | `AgentLoopHarness` | Harness 控制循环何时进入/退出 |

策略是"心脏"（每次搏动做什么），Harness 是"大脑皮层"（何时搏动、何时停止、如何响应环境信号）。

---

## 3. 核心抽象设计

### 3.1 DecisionStrategy — 决策循环的可插拔抽象

```python
class DecisionStrategy(Protocol):
    name: str
    async def on_run_start(state, ctx) -> None   # 初始化钩子
    async def run_step(state, ctx) -> StepOutput  # 单步执行
    async def on_step_end(state, ctx, output) -> None  # 步后钩子
```

三种实现：

| 策略 | name | 行为差异 |
|------|------|----------|
| `ReActStrategy` | `react` | 等价原有 Think→Act→Observe，零回归 |
| `PlanExecuteStrategy` | `plan_execute` | 先调 LLM 生成 `state.plan`，每步针对当前 plan step 执行 |
| `ReflexionStrategy` | `reflexion` | ReAct + 连续失败触发 LLM 反思（通过 FeedbackLoop 注入） |

选择策略的设计理由：

- **ReAct** 是 2023 年已被充分验证的 baseline，推理和行动交替，适合简单任务
- **Plan-Execute** 来自 Anthropic 2024 推荐——先外化计划再逐步执行，减少长任务中的"漂移"现象
- **Reflexion** 来自 Shinn et al. 2023——把语言化的自我反馈作为"梯度信号"注入下一轮，比简单的静态 error_hint 有效得多

**为什么用 Protocol 而非 ABC？** Agent 的调用路径在热循环里，ABC 的 `isinstance` 检查和抽象方法查找有微小但可累积的开销。Protocol 是纯 structural typing，运行时零成本。

### 3.2 PlanStep — 计划作为"一等公民"

```python
class PlanStepStatus(Enum):
    PENDING / IN_PROGRESS / DONE / FAILED / SKIPPED

@dataclass
class PlanStep:
    id: str
    goal: str
    status: PlanStepStatus
    result: Optional[str]
```

设计动因：

- Claude Code / Cursor 等产品的 "todo list" 证明——把计划外化到结构化状态中，模型每轮都能看见进度、勾选、修订，是降低长任务漂移的最简单而有效的手段
- **不再依赖 LLM 在自然语言里"记住"进度**——进度是结构化状态，前端可渲染、快照可恢复、模型可工具化修订（`update_plan` tool）
- `PromptAssembler` 自动将 plan 渲染为 `## Plan` 段，注入每轮 system prompt

### 3.3 MemoryManager — 三层记忆架构

```
MemoryManager
  ├─ ShortTermMemory      ← 会话内：最近 tool results，关键词打分检索
  ├─ LongTermMemory       ← 跨会话：JSON 文件持久化，importance × 时间衰减排序
  └─ MemoryRetriever      ← 可插拔检索后端
       ├─ KeywordRetriever    — 默认：词重叠打分，零依赖
       └─ EmbeddingRetriever  — 可选：余弦相似度 + importance + 时间衰减
```

检索 query 改进：原来的 `query=state.goal`（单一），现在 `build_memory_query()` 拼接 `goal + 最近 observation 摘要`，让检索更聚焦当前上下文。

**为什么不用向量数据库（Chroma/Pinecone）？** 当前阶段的目标是建立正确的检索抽象，而非过早绑定外部依赖。`EmbeddingRetriever` 的 `embed_fn` 可以是任何兼容函数（OpenAI embedding / 本地 sentence-transformers / mock），后续切换为向量数据库只需替换 `MemoryRetriever` 实现。

### 3.4 ArtifactStore — 上下文卸载

超长工具结果（> `offload_threshold_chars`）落盘为 artifact，对话中保留引用指针 + 摘要。需要完整内容时用 `read_artifact` 工具按需回读。

这是 Anthropic 2025 "Context Engineering" 中 **compaction** 策略的工程落地：上下文是有限预算，不是什么东西都往里塞。

### 3.5 ReflectionProvider — 语言化的自我反馈

当 `consecutive_tool_errors >= trigger_errors` 时，调用 LLM 生成一段分析（"为什么失败 + 下一步换什么策略"），以 `role=user, name=reflection` 注入下一轮 Think。

设计决策：
- **不额外消耗 step**：反思发生在 `after_step` 阶段（FeedbackLoop），不计入主循环步数
- **通过 FeedbackLoop 注入**：复用现有机制，不新增特殊路径
- **反思的 token 算入 budget**：避免反思无限消耗

---

## 4. 运行时治理

### 4.1 双层安全网

```
外层: AgentBudget + ConstraintSet + WorkflowController
       → 确定性的资源限制（步数 / 工具调用次数 / 耗时 / 策略门禁）

内层: Agent 自主决策（Think/Act/Observe + Strategy）
       → 灵活的智能行为（何时停 / 换什么工具 / 怎样修正错误）
```

如果策略让 Agent 走入死循环，外层会在 N 步后强制终止。这是 **"让 Agent 自主，但不放任"** 的工程原则。

### 4.2 生命周期闭环

```
IDLE → RUNNING ⇄ PAUSED → STOPPED → IDLE
                  ↘ ERROR ↗
```

- `pause()` → `wait_if_paused()` 阻塞主循环但不返回 → `resume()` 继续
- `stop()` → `is_stop_requested()` 返回 True → 当前 step 完成后返回 `USER_CANCELLED`
- `StateSnapshot` 可在 PAUSED 状态下保存全部状态（messages / steps / plan / tool_calls），从快照恢复时继续执行

### 4.3 可观测事件

Harness 发 10+ 种事件：`run_start → step_start → think_start/end → act_start/end → step_end → feedback_collected → run_end`

所有事件经 `HarnessEventLogger` 输出（compact/verbose 双模式），前端 PromptInspector / Trace 可见。

---

## 5. 多代理协作

### 5.1 四种编排策略

| 策略 | 适用场景 | 实现 |
|------|----------|------|
| **parallel** | 子任务独立可并行 | `asyncio.gather` 并发执行 |
| **sequential** | 子任务有弱依赖 | 串行，早失败终止 |
| **dynamic** | 前步结果影响后步 | 流水线，上游结果注入下游 context |
| **dag** | 显式依赖声明 | 拓扑排序 + 层并行 + 环检测 |

### 5.2 能力路由 (OPT-8)

注册 agent 时声明 `capabilities: list[str]`，分配任务时 `_score_agent(task, agent_id)` 按关键词匹配打分，最高分匹配，无匹配回退轮询。

### 5.3 子代理隔离 (OPT-9)

`SubAgentSpawner` 创建独立 Agent 实例（独立 registry / state / 上下文窗口），只回传最终结论。这是 Anthropic 多智能体研究系统中"subagent context isolation"的直接落地——主上下文不被子任务细节污染。

与 Handoff 的区别：
- **Spawn**：隔离并行，独立上下文 → 回传结论（适合：委派子任务）
- **Handoff**：单线程续跑，共享上下文 → 控制权移交（适合：专长切换）

### 5.4 防递归/防环

- Spawn: `max_depth=2`（可配置）
- Handoff: `max_depth=3` + `handoff_chain` 元数据追踪
- DAG: `_has_cycle()` DFS 环检测 + 自动降级 sequential

---

## 6. Skill / Tool 体系

### 6.1 注册路径

```
1. 系统内置 tools     → load_agentic_tools(["database","http","task","utils","plan","artifact","handoff"])
2. 用户自定义 skill    → @agent.skill(name=..., description=...)
3. MCP 服务器 tools    → MCPToolLoader.load_from_server(server_name, transport="stdio", command=[...])
4. Markdown 知识 skills → registry.load_from_directory(path)
```

### 6.2 Tool 区域一览

| 区域 | 包含 | 说明 |
|------|------|------|
| `database` | SQL 查询 | 参数化查询 + SQL 注入过滤 |
| `http` | HTTP 请求 | REST API 调用 |
| `task` | 任务管理 | 启动/取消/查询任务 |
| `utils` | 通用工具 | MD5、时间戳、随机数 |
| `plan` | 计划管理 | `update_plan` |
| `artifact` | 回读大结果 | `read_artifact` |
| `handoff` | 控制权移交 | `handoff_to` |
| `chat_ops` | 聊天操作 | — |

### 6.3 执行隔离

每个 tool 声明 `risk_level: READ | WRITE | DESTRUCTIVE`，`PermissionGuard` 在 executor 执行前检查。MCP 工具默认 `WRITE`（保守），可按声明覆盖。

---

## 7. 配置体系 (AgentConfig)

### 7.1 完整配置项

| 类别 | 配置项 | 默认值 | 说明 |
|------|--------|--------|------|
| **LLM** | `llm_provider` | `deepseek` | openai / claude / deepseek |
| | `llm_api_key` | — | 必填 |
| | `llm_model` | None | None→provider 默认 |
| | `llm_base_url` | None | None→provider 默认 |
| | `llm_temperature` | 0.2 | [0, 2] |
| **执行** | `max_steps` | 8 | 最大步数 |
| | `max_context_tokens` | 60000 | 上下文窗口上限 |
| | `max_tool_result_length` | 2000 | 工具结果截断阈值 |
| | `abort_on_tool_error` | False | 首错即中止 |
| | `max_consecutive_errors` | 3 | 连续错误中止阈值 |
| **工具** | `tool_areas` | None | 加载的工具区域 |
| | `tool_dependencies` | None | 依赖注入 |
| **策略** | `strategy` | `react` | react / plan_execute / reflexion |
| | `enable_reflection` | False | 启用反思 |
| | `reflection_trigger_errors` | 2 | 反思触发阈值 |
| **记忆** | `memory_backend` | `keyword` | keyword / embedding |
| | `long_term_memory_path` | None | 长期记忆文件路径 |
| | `embedding_provider` | None | embedding 后端 |
| **知识** | `knowledge_backend` | `keyword` | keyword / embedding |
| **上下文** | `enable_context_offload` | False | 超长结果落盘 |
| | `offload_threshold_chars` | 4000 | 卸载触发阈值 |
| **模型** | `enable_prompt_cache` | False | Prompt 缓存 |
| | `thinking_budget` | 0 | Thinking token 配额 |
| **MCP** | `mcp_servers` | None | MCP 服务器列表 |
| **其他** | `enable_routing` | False | 任务路由分解 |
| | `verbose` | False | 详细日志 |
| | `show_prompt` | False | 打印完整 prompt |

### 7.2 开关设计原则

- 所有新能力默认**关闭**：`enable_reflection=False`, `memory_backend="keyword"`, `knowledge_backend="keyword"`, `enable_context_offload=False`, `enable_prompt_cache=False`, `thinking_budget=0`
- 策略默认 `react`（等价旧行为），非法值在 `__post_init__` 抛 `AgentConfigError`
- 每个能力独立开关、独立灰度、独立回滚

---

## 8. 评测与回放闭环

### 8.1 Evaluator

```
evaluate(agent, test_cases, metrics) → List[EvaluationResult]
  ├─ 逐用例跑 agent.run(goal)
  ├─ 采集: success / steps / latency / tool_calls / token_usage / expected_match
  ├─ LLM-as-judge (可选): judge_score → 0.0~1.0
  ├─ summarize() → 文本汇总表
  └─ to_json(filepath) → 持久化报告
```

### 8.2 Replay

```
ReplayRecorder: 录制 step_end → assistant_message + tool_results
ReplayProvider: 按录制顺序吐出 assistant_message (不调真实 LLM)
ReplayActor:    按录制返回 tool_results (不执行真实工具)
```

用于失败链路分析和 CI 回归。回放过程不调用真实 provider/工具，确定性可重复。

---

## 9. 设计决策记录

### 9.1 为什么 Think/Act/Observe 是独立 dataclass 而非三个方法？

它们各自有独立的依赖（Think 需要 prompt/memory/context、Act 需要 registry/executor/artifact、Observe 需要 error/memory），作为独立 dataclass 可以独立构造、独立测试、独立注入。如果合并为一个类，构造函数会膨胀到 15+ 参数。

### 9.2 为什么 AgentLoopRunner 和 AgentLoopHarness 分开？

Runner 负责**装配**（创建组件、注入依赖、解析策略），Harness 负责**运行**（事件循环、生命周期、工作流决策）。装配逻辑和运行逻辑的复杂度各自很高，分开可以独立演进。

### 9.3 为什么 feedback 走 FeedbackLoop 而不是硬编码在 Harness 里？

反思、guardrail、环境信号等"步间反馈"是开放集合。FeedbackLoop + FeedbackProvider 的插件机制允许在不改动 Harness 核心逻辑的前提下增删反馈来源。

### 9.4 为什么 MemoryRetriever 用 Protocol 而非 ABC？

同 DecisionStrategy——检索在每次 Think 时调用，热路径上不应有抽象开销。Protocol 是编译时的类型检查 + 运行时的零成本鸭子类型。

### 9.5 为什么 Artifact 走文件系统而非向量数据库？

Artifact 的语义是"大块内容按需回读"，不是语义搜索。文件系统天然适合这个场景——顺序读写、低延迟、无需额外依赖。后续如有语义搜索需求，跟 Memory/KB 走同一条检索路径。

---

## 10. 架构演进路线

```
v1: 基础 Agent Loop (Think/Act/Observe)         ← 已完成
v2: 治理层 (Budget/Workflow/Events/Snapshot)     ← 已完成
v3: Multi-Agent (Coordinator/Bus/Protocol)        ← 已完成
v4: 策略可插拔 + 计划 + 反思 + 记忆语义化        ← 当前版本
v5 (规划中): 能力路由验证 + 子代理生产级 + MCP 生态集成
```

---

## 11. 目录结构

```
src/core/agents/
├── __init__.py                  # 公共 API 总出口
├── exceptions.py                # AgentConfigError, ToolNotFoundError, etc.
│
├── engine/                      # Layer 1: 控制层
│   ├── agent.py                 #   Agent + AgentConfig (30+ 配置项)
│   ├── lifecycle.py             #   LifecycleManager (状态机)
│   ├── loop.py                  #   Think / Act / Observe
│   ├── runner.py                #   AgentLoopRunner (装配点)
│   ├── types.py                 #   Thought/Action/Observation/Step/PlanStep
│   ├── planning/                #   决策策略 (可插拔)
│   │   ├── strategy.py          #     DecisionStrategy Protocol
│   │   ├── react.py             #     ReActStrategy
│   │   ├── plan_execute.py      #     PlanExecuteStrategy
│   │   └── reflexion.py         #     ReflexionStrategy
│   └── prompting/               #   Prompt 工程
│       ├── assembler.py         #     PromptAssembler (动态组装)
│       ├── knowledge_selector.py#     KnowledgeSelector (领域/语义)
│       └── router.py            #     TaskRouter (目标分解)
│
├── capabilities/                # Layer 2: 能力层
│   ├── llm/                     #   LLM Provider
│   │   ├── base.py              #     LLMProvider(ABC) + LLMConfig
│   │   ├── deepseek.py          #     DeepSeekPlanner (deprecated)
│   │   └── providers/           #     OpenAI/Claude/DeepSeek
│   ├── skills/                  #   Skill 框架
│   │   ├── model.py             #     Skill/SkillType/RiskLevel
│   │   ├── registry.py          #     SkillRegistry + @skill 装饰器
│   │   ├── executor.py          #     SkillExecutor
│   │   ├── context.py           #     SkillContext (依赖注入)
│   │   ├── guard.py             #     PermissionGuard
│   │   └── serializer.py        #     ToolSpecSerializer (OpenAI/Claude)
│   └── tools/                   #   Tool 集合
│       ├── loader.py            #     load_agentic_tools + TOOL_AREAS
│       ├── database.py          #     SQL 工具
│       ├── http.py              #     HTTP 工具
│       ├── task.py              #     任务管理工具
│       ├── utils.py             #     通用工具
│       ├── plan.py              #     update_plan (OPT-2)
│       ├── artifact.py          #     read_artifact (OPT-5)
│       ├── handoff.py           #     handoff_to (OPT-10)
│       ├── chat_ops.py          #     聊天操作
│       └── mcp_loader.py        #     MCPToolLoader (OPT-15)
│
├── state/                       # Layer 3: 状态层
│   ├── models.py                #   AgentState/StopReason/AgentLoopState/AgentLoopResult
│   ├── snapshot.py              #   StateSnapshot (JSON 持久化)
│   ├── artifacts.py             #   ArtifactStore (上下文卸载)
│   ├── utils.py                 #   generate_agent_trace_id
│   ├── context/                 #   上下文管理
│   │   ├── manager.py           #     ContextWindowManager
│   │   └── tokenizer.py         #     TokenCounter
│   ├── memory/                  #   记忆系统
│   │   ├── manager.py           #     MemoryManager (统一入口)
│   │   ├── short_term.py        #     ShortTermMemory
│   │   ├── long_term.py         #     LongTermMemory + MemoryEntry
│   │   └── backends.py          #     KeywordRetriever + EmbeddingRetriever
│   └── protocol/                #   通信协议
│       ├── messages.py          #     assistant_message/tool_result_message
│       └── models.py            #     ToolCall
│
├── execution/                   # Layer 4: 执行层
│   ├── dispatcher.py            #   Dispatcher (run_single / run_multi 门面)
│   └── result.py                #   ExecutionResult / ExecutionStatus
│
├── runtime/                     # Layer 5: 运行时
│   ├── hooks.py                 #   Hook / LoggingHook / TracingHook
│   └── harness/
│       ├── harness.py           #     AgentLoopHarness (主循环)
│       ├── budget.py            #     AgentBudget
│       ├── constraints.py       #     ConstraintSet
│       ├── workflow.py          #     WorkflowController
│       ├── feedback.py          #     FeedbackLoop
│       ├── reflection.py        #     ReflectionProvider (OPT-3)
│       ├── improvement.py       #     ContinuousImprovement
│       ├── evaluator.py         #     Evaluator (OPT-11)
│       ├── replay.py            #     ReplayRecorder/ReplayProvider (OPT-12)
│       ├── debugger.py          #     Debugger
│       ├── logging.py           #     HarnessEventLogger
│       └── fixtures.py          #     FixtureManager
│
└── multi_agents/                # Layer 6: 多代理
    ├── protocol.py              #   Message / MessageType / SubTask
    ├── bus.py                   #   MessageBus (pub/sub)
    ├── coordinator.py           #   MultiAgentCoordinator (4 种策略)
    └── subagent.py              #   SubAgentSpawner (OPT-9)
```

---

## 12. 关键设计权衡

| 决策 | 选择 | 替代方案 | 理由 |
|------|------|----------|------|
| Agent 对外 API | 单一 `Agent` 对象 + `AgentConfig` 开关 | AgentBuilder / AgentFactory | 用户心智模型最简单：一个对象，30+ 开关 |
| 策略注入 | Protocol 在 `__post_init__` 默认 ReActStrategy | 注册表/DI 容器 | 热路径零开销，默认行为零破坏 |
| 计划存储 | `AgentLoopState.plan: list[PlanStep]` | 独立 PlanManager | 状态已在 state 中，多一层抽象无增益 |
| 反思注入 | FeedbackLoop Provider | 策略内置 | 反思是横切关注点（跨策略），不是策略专属 |
| 多代理调度 | coordinator 内部 4 种策略 | 独立 Scheduler 类 | 当前规模下单一协调器的复杂度可控 |
| 上下文卸载 | 文件系统 + 按需回读 | 向量数据库 / Redis | Artifact 不是语义搜索，文件系统是正确抽象 |
| MCP 接入 | 映射为 Skill + 注册进 Registry | 独立 ToolProvider 层 | 复用现有 Skill 体系的权限/执行/序列化 |
