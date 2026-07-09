# Agent Guide

> 深入理解 TaskPilot 的 Agent 子系统。使用示例见 [Agent Usage Guide](agent-usage-guide.md)，项目总览见 [README](../README.md)。

TaskPilot Agent 的核心命题是：**让模型决定下一步，但让工程系统决定边界在哪里。**

它采用双层结构：内层是 Think → Act → Observe 的 Agent Loop，负责智能决策；外层是 Harness、Budget、Constraint、Lifecycle、Snapshot 和 Trace，负责治理、恢复和观测。

## 设计总览

<p align="center"><img src="../assets/agent-overview.png" alt="Agent 双层架构：智能层与治理层" width="85%" style="border-radius: 8px;"/></p>

这不是"模型外面包一层 retry"。治理层在每个 step 前后都参与裁决：是否超预算、是否被取消、是否需要反思、是否已经完成、是否需要持久化可恢复状态。

## 六层结构

`src/core/agents/` 内部按能力边界拆成六层：

```text
src/core/agents/
├── engine/          # Agent 对外 API、Loop、Runner、Lifecycle、Prompting、Planning
├── capabilities/    # LLM Provider、Tools、Skills、MCP、权限与序列化
├── state/           # AgentLoopState、Result、Snapshot、Context、Memory、Protocol、MessageTree
├── execution/       # Dispatcher 和执行结果模型
├── runtime/         # Harness、Budget、Constraint、Workflow、Feedback、Replay、Evaluator
└── multi_agents/    # MessageBus、Coordinator、SubAgent、Handoff 协议
```

层间关系可以理解为：

- `engine` 决定 Agent 怎样被创建、怎样进入循环。
- `capabilities` 提供模型、工具和 Skill。
- `state` 保存对话、步骤、计划、记忆、快照、消息树和协议对象。
- `runtime` 管理运行边界和步间治理。
- `execution` 为更高层编排提供统一结果门面。
- `multi_agents` 处理多个 Agent 之间的协作与隔离。

## 主执行链路（统一 ReAct）

所有执行路径——agent 任务、chat 对话——都走同一条 ReAct Loop。不再有独立的简单循环。

<p align="center"><img src="../assets/agent-execution-sequence.png" alt="Agent 主执行链路时序" width="85%" style="border-radius: 8px;"/></p>

### 入口统一

```
POST /api/agent/run  → TaskScheduler → agent.run handler  (mode="agent")
POST /api/chat/...   → run_chat_turn()                     (纯文本)
```

两个入口最终都委托给 `AgentLoopRunner` → `AgentLoopHarness`，差异只在于 tools 数量（agent 模式加载 tools，chat 模式传空列表）。

`ChatTurnRunner`（原来的"生产路径"，for-range 极简循环）已被弃用。原来两条互不重叠的执行循环合并为一条。

### 关键分工

- `AgentLoopRunner` 负责装配（Think、Act、Observe、Budget、Strategy），不负责主循环治理。
- `AgentLoopHarness` 负责运行时治理（循环控制、事件边界、Budget/Constraint/Cancel 裁决），不关心具体 provider 或 skill 实现。
- `DecisionStrategy` 决定每一步怎样执行 Think/Act/Observe。
- `Think`、`Act`、`Observe` 是可独立测试和替换的阶段对象。

### 流式事件

Harness 在关键节点通过共享 `TraceEventBus` 发布前端兼容的 `chat.*` 事件：

| 节点 | 事件 | 发布者 |
|------|------|--------|
| LLM 产出 token | `chat.token_delta` | Think（stream_callback 包装） |
| 开始执行 tool | `chat.tool_call_start` | Act |
| tool 执行完毕 | `chat.tool_call_end` | Act |
| 循环正常结束 | `chat.turn_end` | AgentLoopHarness（run_end 之后） |
| 异常 | `chat.turn_error` | AgentLoopHarness |

前端无需改动，事件协议保持不变。

## DecisionStrategy

策略接口位于 `engine/planning/strategy.py`：

```python
class DecisionStrategy(Protocol):
    name: str
    async def on_run_start(state, ctx) -> None: ...
    async def run_step(state, ctx) -> StepOutput: ...
    async def on_step_end(state, ctx, output) -> None: ...
```

内置三种策略：

- `react`：默认策略。每步执行 Think → Act → Observe，延迟低，适合大多数任务。
- `plan_execute`：运行开始时生成结构化计划，再围绕当前计划步骤执行，适合长任务和多步骤目标。
- `reflexion`：在 ReAct 基础上把连续失败转化为语言化反馈，再注入下一轮上下文。

这里选择 `Protocol` 而不是继承式基类，是为了保持策略替换的轻量性：只要实现相同形状即可接入，不需要把所有策略绑死在一个继承树里。

## Prompt、Memory 与 Context

Think 阶段不是简单把 goal 发给模型。它会经过：

```text
MemoryManager.retrieve()
  → KnowledgeSelector.select()
  → PromptAssembler.assemble()
  → ContextWindowManager.compact()
  → collapse_old_tool_results()
  → LLMProvider.complete() / stream_chat()
```

`MemoryManager` 由短期记忆、长期记忆和可插拔检索器组成。默认关键词检索零依赖；需要语义检索时，可以切换到 embedding 后端。

`ContextWindowManager` 负责在 token 预算内压缩上下文。Agent 任务越长，越不能依赖模型"自然记住一切"；必须把上下文窗口当作有限资源来管理。当启用 LLM 摘要压缩时（`enable_summary_compaction=True`），经由 `compactor.py` 调用 Provider 将早期历史压缩为摘要文本，失败时自动回退到中段截断。

### 双层 ToolResult

长工具返回（如几百行 JSON）每轮原样塞进历史是 token 浪费的主要来源。`tool_result_memory.py` 实现双层策略：

- `annotate_tool_message`：超长结果（>1500 字符）同时保存完整版和摘要版。
- `collapse_old_tool_results`：送 LLM 前把旧轮次的长结果替换为摘要，最近 2 条保留完整。

关键区分：真实历史 `messages` 不丢（持久化用），送给 LLM 的是折叠副本。

## Skill / Tool 体系

TaskPilot 把所有可执行能力统一进 SkillRegistry：

<p align="center"><img src="../assets/agent-skill-system.png" alt="Skill / Tool 注册与执行体系" width="85%" style="border-radius: 8px;"/></p>

执行前会经过 `PermissionGuard`。每个 Skill 带有风险级别：`READ`、`WRITE`、`DESTRUCTIVE`。MCP 工具默认按更保守的 `WRITE` 处理，避免未知外部能力被低估风险。

**工具分组白名单**：每个 Skill 通过 `domain` 字段标记所属组（`database` / `http` / `task` / `utils` / `chat_ops` / `plan` / `artifact` / `handoff` / `mcp`）。`group_filter.py` 提供 `filter_tools_by_groups`，调用方通过 `allowed_tool_groups` 和 `exclude_tools` 在运行时按场景做最小权限过滤。不传参数则放行全部，默认行为不变。

## Runtime Harness

`runtime/harness/` 是 Agent 自主性的边界层：

```text
harness.py       # AgentLoopHarness，主循环和事件边界
budget.py        # AgentBudget，步数/工具/耗时预算
constraints.py   # ConstraintSet，策略门禁
workflow.py      # WorkflowController，继续/终止裁决
feedback.py      # FeedbackLoop，步间反馈插件
reflection.py    # ReflectionProvider，连续失败后的反思
improvement.py   # ContinuousImprovement，改进记录
replay.py        # ReplayRecorder / ReplayProvider
evaluator.py     # Evaluator
logging.py       # HarnessEventLogger
```

一个重要原则：**反思、评测、回放、改进记录都是运行时能力，不应该硬编码进 ReAct。** 这样未来新增 guardrail、外部评审或成本控制信号时，可以作为 FeedbackProvider 或 Hook 接入，而不是改主循环。

## 状态、暂停与恢复

Agent 生命周期独立于任务状态机：

<p align="center"><img src="../assets/agent-lifecycle.png" alt="Agent 生命周期状态机" width="85%" style="border-radius: 8px;"/></p>

- `pause()`：请求暂停，循环在 step 边界挂起。
- `resume()`：从暂停点继续。
- `stop()`：请求停止，当前 step 完成后返回 `USER_CANCELLED`。
- `save_snapshot()`：保存 messages、steps、plan、tool calls 等状态。
- `run_from_snapshot()`：从快照恢复执行。

这条设计的核心约束是：不能在任意协程切换点强杀 Agent。工具调用、数据库连接和事件写入都需要清理机会，所以取消要协作式传播。

## 跨 Run 记忆与反思

Agent 的默认行为是每次 run 独立执行，不携带过往经验。`memory_store.py` 打通了一条"写回 + 注入"闭环：

```text
run 成功/失败
  → generate_reflection()    # LLM 复盘，生成 2-4 条经验要点
  → save_reflection()        # 写入 agent_memory 表 (account_id + scope_key)
  → 下次同 goal 启动时
  → fetch_reflections()      # 按 scope_key 检索最近 3 条
  → format_memory_injection() # 拼入 system prompt
```

整个链路受 `enable_memory` 开关控制，默认 `False`（保持旧行为）。

## 消息树

`chat_messages` 从线性列表升级为有向无环图（`seq` → `parent_seq`），支撑非破坏式压缩和回溯：

```
线性（旧）:  [user] → [asst] → [tool] → [asst] → [tool] → ... 50+ 条
                                              ↑ 上下文爆炸

消息树（新）:
  [user] → [asst.tc1] → [tool1] → [asst.tc2] → [tool2]
                ↘ [asst.side]                         ↓
                                          [system:summary] → [asst:final]
  head_seq 始终指向主路径最新节点
```

核心操作：

- **非破坏式压缩**：`compact_main_path()` 插入一条 summary 节点，head 指针越过被压区间。旧消息仍在表中可回溯、可审计。
- **回溯**：`backtrack_head()` 把 head 指回历史 seq，从那里 fork 新分支。
- **双写**：`ChatRepository.append_message()` 自动分配 seq/parent_seq 并推进 trace_head。不传 trace_id 时行为不变（向后兼容）。

详见 `src/core/agents/state/message_tree.py`。

## 多智能体协作

`multi_agents/` 提供两类协作语义：

- **Coordinator**：把任务拆给多个 Agent，支持 `parallel`、`sequential`、`dynamic`、`dag` 编排。
- **SubAgent / Handoff**：前者强调上下文隔离和结果回传，后者强调控制权移交和同一任务续跑。

两种范式取舍：

- `Spawn` 适合独立研究、并行分析、避免主上下文被污染。
- `Handoff` 适合专家切换、连续执行、需要保留完整上下文的任务。

TaskPilot 当前更偏向"隔离优先"。原因是 Agent 系统最容易失控的不是能力不足，而是上下文互相污染后无法解释错误来源。

## 评测与回放

Agent 的行为不能只靠日志排查。`Evaluator` 和 `Replay` 提供两条闭环：

- `Evaluator`：批量跑测试用例，采集成功率、步数、耗时、工具调用和可选 LLM-as-judge 分数。
- `Replay`：录制 assistant message 和 tool result，回放时不调用真实 LLM 或真实工具，用于确定性复现。

这让 Prompt、策略和 Skill 的修改可以被回归测试覆盖，而不是每次靠人工观察"感觉更好了"。

## 关键权衡

| 决策 | 当前选择 | 替代方案 | 取舍 |
|---|---|---|---|
| 执行路径 | 统一 ReAct Loop（`AgentLoopRunner`） | 双循环（ChatTurnRunner + AgentLoopHarness） | 治理一致，不重复实现，但纯文本对话也走完整 harness |
| 对外 API | 单一 `agent.run` handler + `run_chat_turn()` | 多个 @register 入口 | 两条入口覆盖所有场景，但最终都委托给同一 Runnable |
| 策略扩展 | `DecisionStrategy` Protocol | 继承式基类 | 接入轻量，但需要靠类型检查和测试守住协议 |
| 反思机制 | `FeedbackLoop` 插件 | 写进 Reflexion 策略 | 可跨策略复用，但链路理解成本更高 |
| 记忆检索 | 默认关键词，可选 embedding | 默认向量数据库 | 零依赖启动，后续可替换检索后端 |
| 上下文卸载 | 文件 Artifact + 按需回读 | Redis / 向量库 | 更贴合"大块内容回读"，不提前引入检索语义 |
| 消息存储 | 消息树（seq/parent_seq）双写 | 纯线性 id 排序 | 支撑非破坏式压缩和回溯，当前读路径仍走线性 id |
| 多智能体 | Coordinator + SubAgent 隔离 | 共享大上下文 | 可观测性更好，但跨 Agent 状态共享更克制 |

## 演进方向

当前架构已完成 Agent Loop、策略可插拔、Skill/Tool、Memory、Runtime Harness、Replay/Evaluator 和 Multi-Agent 基础。**最近完成的演进（2026-07）：**

- ✅ 统一执行路径：`ChatTurnRunner` 弃用，全部走 `AgentLoopRunner` / `AgentLoopHarness`（ReAct）。
- ✅ 流式事件贯通：`Think`/`Act`/`Harness` 通过共享 `event_bus` 发布 `chat.token_delta`、`chat.tool_call_start/end`、`chat.turn_end/error`。
- ✅ 真实上下文压缩（`compactor.py`）：LLM 摘要 + 截断回退，两条执行循环均已接入。
- ✅ 双层 ToolResult（`tool_result_memory.py`）：长工具结果历史自动折叠，从源头省 token。
- ✅ 工具分组白名单（`group_filter.py`）：按 `domain` 做运行时权限最小化。
- ✅ 跨 run 记忆（`memory_store.py` + `agent_memory` 表）：反思生成 → 持久化 → 下次注入，打通闭环。
- ✅ 消息树（`message_tree.py` + `trace_head` 表）：chat_messages 双写 seq/parent_seq/branch_type，支撑非破坏式压缩和回溯。

下一阶段最可能变化的位置：

- 树读路径切换：将 `build_llm_messages` 从线性 `ORDER BY id` 切到 `get_main_path`（seq/parent_seq 回溯），真正启用压缩和分支。
- Tool calling 兼容性：不同 provider 的结构化输出、并行工具调用、错误修复提示。
- Runtime 治理：成本预算、token 预算、危险工具确认、用户中断恢复。
- Multi-Agent 协议：任务分解、结果聚合、共享状态和上下文隔离的平衡。
- Prompt 评测：把策略、Prompt、Skill 描述纳入可重复评测，而不是靠一次运行判断质量。
