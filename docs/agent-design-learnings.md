# agent_base（TaskPilot）向 agent_new（cyber-agent）可学习的设计思路

> 从高级 Agent 设计工程师视角，对两个项目的 Agent 执行引擎做深度对比分析。
> agent_new 在上下文管理、目标编排、Trace 抽象统一性三个维度有明显的架构领先。

---

## 总体评估

两个项目处于不同的设计成熟度阶段：

- **agent_new（cyber-agent）**：Agent 执行引擎设计深度出色，上下文管理、GoalTree、侧分支压缩是最大亮点
- **agent_base（TaskPilot）**：工程底座扎实（分层架构、状态外置、优雅停机、多租户），但执行引擎缺乏深度

agent_base 最需要补的不是工程模式，而是 **Agent 执行引擎的可靠性设计**。

---

## 1. GoalTree：层级化目标执行模型

### 问题

agent_base 的 `plan_execute` 策略生成的是线性步骤文本，没有结构化层级。多 Agent 协作通过 `MessageBus + Coordinator`，父子关系不可追踪。任务偏离后只能取消重建，无法回到中间节点重来。

### agent_new 的做法

每次 Agent 执行建模为一棵 GoalTree：

```
Mission
├── Goal A (normal)
│   ├── SubGoal A1 (agent_call, mode=explore) → 启动子 Agent
│   └── SubGoal A2 (normal)
├── Goal B (agent_call, mode=delegate) → 启动子 Agent
└── Goal C (normal)
```

核心机制：

| 机制 | 说明 |
|------|------|
| 级联完成 | 所有子目标完成 → 父目标自动完成，无需 LLM 显式判断 |
| 独立统计 | `self_stats`（自身）+ `cumulative_stats`（含后代），成本追踪精确到子目标粒度 |
| 回溯重跑 | `rebuild_for_rewind()` 基于时间戳截断，废弃后续目标，重置状态——可回到任意节点重来 |
| Goal 类型 | `normal`（常规执行）vs `agent_call`（启动子 Agent），通过 `sub_trace_ids` 链接父子 Trace |

### 建议方案

agent_base 的 `Strategy` 是 Protocol，天然支持插入新策略：

```python
class GoalTreeStrategy(DecisionStrategy):
    """用 GoalTree 替代线性 plan，支持级联完成和回溯重跑"""
```

数据库侧：在 `agent_run_summaries` 表增加 `goal_tree` JSON 列，存储完整 GoalTree 结构：

```sql
ALTER TABLE agent_run_summaries ADD COLUMN goal_tree JSON DEFAULT NULL;
ALTER TABLE agent_run_summaries ADD COLUMN parent_trace_id VARCHAR(64) DEFAULT NULL;
```

前端侧：`TraceGraph` 组件（基于 XYFlow dagre）可自然渲染树形执行图。

---

## 2. 上下文溢出管理：三级压缩策略

### 问题

agent_base 有 `AgentBudget`（max_steps / max_tool_calls / max_duration_seconds）做安全边界，但**没有上下文窗口溢出管理**。长任务执行 50+ 个 tool call 后，对话历史线性膨胀，最终 LLM API 调用直接失败，或模型丢失早期上下文后产生幻觉。

这是 agent_base **最迫切需要补充的能力**。

### agent_new 的做法

三级递进压缩：

| 级别 | 触发条件 | 策略 | 侵入性 |
|------|---------|------|--------|
| L0 | token > 阈值 | 大图降采样 / 替换为文字描述 | 低 |
| L1 | L0 不够 | 过滤已完成 Goal 的中间消息，用摘要替换 | 中 |
| L2 | L1 不够 | 暂停主任务，进入侧分支，LLM 生成压缩摘要后重建历史 | 高 |

**侧分支队列机制**（最精巧的设计）：

在 L2 压缩前，系统依次执行：`reflection`（知识反思）→ `knowledge_eval`（知识评估）→ `compression`（压缩）。每个侧分支有独立 `max_turns`，**退出侧分支后主路径历史完全不变**——侧分支不污染主对话。

### 建议方案

分三阶段引入：

**Phase 1（低风险）**：L0 图像优化

在 `Act` 阶段返回大图结果时自动降采样，不影响核心逻辑。

**Phase 2**：L1 目标过滤

利用 GoalTree（如已引入）或现有 plan 阶段标记，将已完成步骤的中间 tool call 结果替换为摘要。实现方式：在 `AgentLoopHarness.after_step` 中检查 token 计数，触发已完成的 tool 消息压缩。

**Phase 3**：L2 侧分支压缩

利用 agent_base 已有的 `LifecycleManager` 的 PAUSE/RESUME 能力：

```
主 Agent PAUSE → 新建 trace_id 做压缩子 Agent → 压缩结果写回 chat_messages → 主 Agent RESUME
```

`TraceEventBus` 在压缩期间 emit `context_overflow` 事件，让前端感知"Agent 正在整理记忆"。

**关键差异**：agent_base 的状态在 MySQL，侧分支不需要 agent_new 那种"不污染主路径"的文件系统技巧——直接开新 trace_id 做压缩，结果写回即可。

---

## 3. Trace 作为统一抽象

### 问题

agent_base 有 `trace_id` 贯穿全链路，但它是**关联 ID**而非**数据模型抽象**。四张表（task_manager / agent_events / agent_run_summaries / chat_messages）各自持有 trace_id，但之间没有树形层级关系。多 Agent 协作时，无法从根 trace_id 直接查所有子 Agent 执行情况。

### agent_new 的做法

"所有 Agent 都是 Trace"——主 Agent、子 Agent、ask_human 全部统一为 `Trace` 数据模型，通过 `parent_trace_id` 构建树：

- 统一查询——一次查询整棵执行树
- 统一成本统计——从根 Trace 向下 rollup
- 统一取消/暂停——从根 Trace 向下级联

### 建议方案

在 `agent_run_summaries` 增加 `parent_trace_id`：

```sql
ALTER TABLE agent_run_summaries ADD COLUMN parent_trace_id VARCHAR(64) DEFAULT NULL;
CREATE INDEX idx_parent_trace ON agent_run_summaries(parent_trace_id);
```

子 Agent 启动时写入 `parent_trace_id`，查询时用递归 CTE 获取整棵执行树。

---

## 4. 工具分组白名单

### 问题

agent_base 的工具通过 `SkillRegistry` 和全局注册管理，没有分组权限控制。不同任务场景（定时任务 vs 交互式 Chat）应该能访问不同范围的工具。

### agent_new 的做法

```python
@tool(groups=["core", "file"])
def read_file(path: str): ...

# 默认最小权限
RunConfig(tool_groups=["core"])

# 项目声明式扩展
RunConfig(tool_groups=["core", "file", "browser"])
```

分组语义逐级提升：`core` → `file` → `advanced` → `browser` → `content`

另有 `exclude_tools` 做细粒度排除。

### 建议方案

低成本、高收益的改进。利用 agent_base 已有的 `ConstraintSet`，新增一个 Constraint 实现：

```python
class ToolGroupConstraint(Constraint):
    allowed_groups: list[str] = ["core"]

    def check(self, tool: Tool) -> bool:
        return any(g in tool.groups for g in self.allowed_groups)
```

`Agent.create()` 时通过 `ConstraintSet` 注入，不改架构，只加一个约束。

---

## 5. 技能系统：Markdown 驱动

### 问题

agent_base 有两种技能存储，且存在结构问题：
1. **知识技能**：MySQL `system_skills` / `account_skills` 两张完全相同的表（违反 DRY）
2. **可执行技能**：`@skill` 装饰器写死在 Python 代码中，新增需要改代码 + 重新部署

### agent_new 的做法

技能是 Markdown 文件 + YAML 前置元数据：

```markdown
---
name: content-analyst
description: 分析内容并提供结构化摘要
tools: [web_fetch, knowledge_search]
version: "1.0"
---

# 内容分析师

## 触发条件
当用户需要分析网页内容时...

## 执行流程
1. 先用 web_fetch 获取内容
2. 用 knowledge_search 查找背景知识
3. 生成结构化摘要
```

`SkillLoader` 解析后注入系统提示。技能文件放任意目录，支持热加载。

### 建议方案

将可执行技能也改为 Markdown 驱动：

```
skills/
  executable/
    data_analysis.md    # YAML 头部声明 tool 依赖和执行逻辑
    report_gen.md
  knowledge/
    domain_expert.md    # 纯知识注入
```

收益：
- **零停机注册**：上传 Markdown 文件即生效，无需重新部署
- **消除双表冗余**：合并 `system_skills` / `account_skills`，加 `scope` 字段区分
- **与 agent_new 生态互通**：两者都用 Markdown 格式，可共享技能包

agent_base 的 `skills/` 目录已经是 Markdown 文件，说明团队有意识——需要做的是将 Python `@skill` 装饰器的逻辑也迁移到此范式。

---

## 6. Dream 记忆系统

### 问题

agent_base 有 `chat_messages` 和 `agent_run_summaries` 存储，但没有记忆反思机制。每次新任务 Agent 是"失忆"的——不记得之前做过类似任务及其经验教训。

### agent_new 的做法

两阶段 LLM 驱动的记忆反思：

```
Phase 1: Per-trace reflect
  对新消息的 Trace → 轻量模型生成反思摘要 → cognition_log

Phase 2: Cross-trace integrate
  汇总所有 Trace 反思 + 当前记忆文件 → 强模型更新记忆文件
```

记忆文件是人类可读的 Markdown，用户可随时编辑纠错——Agent 不会在错误记忆中越陷越深。

### 建议方案

对于 agent_base 的定时任务引擎定位，记忆系统价值尤其高——同一定时任务每次执行后的经验（"上次这个数据源超时了，下次调大 timeout"）应被后续执行利用：

1. `agent_run_summaries` 增加 `reflection_text` 列
2. 新增 `agent_memory` 表（或用文件系统，`skills/` 目录已是现成入口）
3. `AgentLoopHarness.after_step` 钩子中触发轻量反思
4. 任务完成后触发跨任务记忆整合

---

## 7. Human-in-the-Loop

### 问题

agent_base 的 `LifecycleManager` 支持 PAUSE/RESUME，但 PAUSE 是外部管理操作，Agent 不能主动请求"我需要人类确认这个操作"。

### agent_new 的做法

`ask_human` 是一等公民工具——Agent 暂停 Trace，等待人类输入后从 `parent_sequence` 链无缝恢复。

### 建议方案

agent_base 的实现路径：

1. Agent 调用 `ask_human(prompt)` → 工具处理器向 `LifecycleManager` 发 PAUSE 信号
2. `TraceEventBus` emit `human_input_required` 事件 → SSE 推送到前端
3. 用户在 Chat 界面输入 → 写入 `chat_messages`（role=user）→ RESUME Agent
4. Agent 的 `Observe` 阶段收到人类回复，继续执行

agent_base 的 Chat 前端已支持 SSE 实时推送，基础设施就绪。

---

## 8. 本地文件存储后端

### 问题

agent_base 必须有 MySQL 才能启动，开发体验重。

### agent_new 的做法

`TraceStore` 定义为 Protocol，文件系统实现（`FileSystemTraceStore`）支持零依赖启动：

```
.trace/{trace_id}/
  meta.json
  goal.json
  messages/{id}.json
  events.jsonl
```

用 `cat` / `jq` 就能调试。

### 建议方案

为 agent_base 增加 `LocalTraceStore`（Protocol 的另一实现），在 `ENV=development` 时自动切换。`dependency-injector` Container 天然支持按环境切换实现，改动成本极低。

---

## 9. 专用知识管理系统（KnowHub）

### agent_new 的做法

独立的 FastAPI 服务 + PostgreSQL + pgvector，语义搜索 + 去重管道 + 工具关联分析。本质是"Agent 版大众点评"——Agent 之间共享工具使用经验。

### 建议方案

短期优先级最低。如需语义搜索，对接外部向量数据库（Milvus / Qdrant）或用 pgvector（如果未来迁移到 PostgreSQL），无需自建完整 KnowHub 服务。

---

## 优先级总览

| 优先级 | 学习项 | 改动成本 | 收益 | 风险 |
|--------|--------|---------|------|------|
| **P0** | 上下文溢出管理 | 中 | 极高——防长任务失败 | 低 |
| **P0** | GoalTree 层级目标 | 中 | 高——计划回退 + 成本追踪 | 中 |
| **P1** | 工具分组白名单 | 低 | 中——安全提升 | 极低 |
| **P1** | Trace 树形抽象 | 中 | 高——多 Agent 编排可观测 | 中 |
| **P2** | Markdown 技能系统 | 中 | 中——零停机注册 | 中 |
| **P2** | Dream 记忆系统 | 中 | 中——跨任务知识积累 | 低 |
| **P2** | Human-in-the-Loop | 低 | 中——人机协作 | 低 |
| **P3** | 本地文件存储后端 | 低 | 低——开发体验 | 极低 |
| **P3** | KnowHub 知识管理 | 高 | 低（短期） | 高 |

---

## 核心判断

agent_base 的工程底座（分层架构、状态外置、优雅停机、多租户）已经很强。最需要从 agent_new 学的是 **Agent 执行引擎的深度设计**——上下文管理和目标编排直接影响 Agent 在长时间运行中的可靠性。P0 两项如果补上，agent_base 的"生产级 Agent 任务引擎"定位会更扎实。

反过来，agent_base 的部分工程实践（特别是依赖注入容器、优雅停机的多阶段拆卸、TraceEventBus 的异步事件流）也值得 agent_new 学习——但那需要另开一篇文档。
