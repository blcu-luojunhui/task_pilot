# TaskPilot 向 cyber-agent 学习：第一性原理分析

> 站在前沿 Agent 设计的视角，对 TaskPilot（本项目）与 cyber-agent（参考项目）的执行引擎做深度对比。
>
> 本文不是"功能清单"，而是**生成式原理**分析：cyber-agent 的优势不是来自 N 个并列功能，而是来自 4~5 个**本原决策**，那些功能只是这些决策的"推论"。看不到本原，照抄功能会很累且抄不全；看到本原，很多功能会"自己长出来"。
>
> 配套实现文档见 [`agent-engine-evolution-design.md`](agent-engine-evolution-design.md)。

---

## 元判断

两个项目处于不同的设计成熟度阶段，且优势区互补：

- **TaskPilot（本项目）**：工程底座扎实——分层架构、状态外置（MySQL）、优雅停机、跨进程协作式取消、多租户、DI 容器、SQL 安全过滤。这是一套**生产级的外环治理**。
- **cyber-agent（参考项目）**：Agent 执行引擎的**内核认知架构**出色——消息树、GoalTree、侧分支压缩、Memory/Knowledge 双线认知。

**核心结论先行**：TaskPilot 在"外环治理"上投入很重且已接近收益递减；在"内核认知"上投入很薄。**下一块钱该花在内核，而不是继续加固外环。** 长任务（50+ tool call）的可靠性，主要由内核的上下文/记忆/计划数据结构决定，外环护栏只是兜底。

---

## ⚠️ 一个必须先知道的事实：TaskPilot 有两条执行循环

分析与改造前必须认清——TaskPilot 实际存在**两套并行、能力不对等的 Agent 循环**：

| 循环 | 入口 | 治理能力 | 上下文管理 | 实际用途 |
|------|------|---------|-----------|---------|
| `ChatTurnRunner` | `../../src/core/chat/runner.py` | 无 budget / 无 feedback / 无 memory | **完全没有** | **生产定时任务**（`agent.run_goal`）+ Chat |
| `AgentLoopHarness` | `../../src/core/agents/runtime/harness/harness.py` | budget / constraint / feedback / improvement / memory | 有 `ContextWindowManager`（但见下） | `Agent.create()` / `Dispatcher` 路径 |

两个关键问题：

1. **生产路径反而最弱**。真正跑定时任务的是 `ChatTurnRunner`，它是一个 `for _ in range(10)` 的极简循环，**没有任何上下文窗口管理**——历史线性膨胀到模型上限直接 API 报错。
2. **富路径的"压缩"是假的**。`AgentLoopRunner.__post_init__`（`engine/runner.py:104`）构造 `ContextWindowManager` 时**没有传 `compactor`**，于是 `compact_if_needed` 永远走 `_truncate_middle`——即**有损中段截断**，不是 LLM 摘要。

所以任何"上下文/记忆/认知"的改造，都必须**同时考虑两条循环**，否则改了没用。这是后续实现文档里反复强调的约束。

---

## 本原一：一个 agent run 的最小数据本原是什么？

> 维度：设计 + 观念。**这是 cyber-agent 80% 优势的根，也是 TaskPilot 最该补的认知。**

第一性问题：*"一次 agent 执行，它的核心数据结构应该是什么？"*

- **TaskPilot 的答案**：`AgentLoopState.messages: List[Dict]`——一个**进程内、线性、可变**的列表，外面包一圈治理。状态快照进 MySQL，但循环的工作记忆是"一根线"。
- **cyber-agent 的答案**：`Message` 是一棵**持久化的树**节点，键为 `(sequence, parent_sequence)`；`Trace.head_sequence` 指针定义"当前现实"。"LLM 该看到什么"被还原成**一次遍历**：

```python
# 沿 parent_sequence 链从 head 回溯到根，再反转 —— 这就是"主路径"
path = []
seq = head_sequence
while seq is not None:
    msg = messages_by_seq.get(seq)
    path.append(msg)
    seq = msg.parent_sequence
path.reverse()
```

**为什么这是本原？** 因为下面 4 个"看似独立的功能"，其实是这**同一个决策的推论**：

| 看似独立的功能 | 在树模型里就是 | 在线性表里为什么难 |
|---|---|---|
| 回溯重跑 (rewind) | 新消息 `parent_sequence` 指向回溯点，旧尾巴自动变死支 | 必须取消重建，丢全部上下文 |
| 非破坏式压缩 | 摘要节点 `parent_sequence` 跳过被压区间，原消息仍在树上 | 只能截断，有损、不可逆 |
| 侧分支不污染主路径 | `head_sequence` 不前移到分支上，遍历自动过滤 | 得另开 trace_id 打补丁 |
| 多 Agent = 子 Trace | trace 里天然能挂 trace | trace_id 只是关联 ID，查不出树 |

**认知层的差距**：TaskPilot 把"消息历史"当**易耗品**（可变、可截断、用完即弃）；cyber-agent 把它当 **append-only 事件日志 + 一个可移动的"现在"指针**。后者是对自治系统更诚实的认识论——系统对自己的历史是诚实、可重放、可逆的。这不是"功能更多"，是**世界观不同**。

**对 TaskPilot 反而更容易**：你的状态本就外置在 MySQL，实现树模型只需 `chat_messages` 加 `sequence` / `parent_sequence` 两列、trace 级加 `head_sequence`。**你不需要 cyber-agent 那套"文件系统不污染主路径"的技巧——因为状态外置，树天然好做。** 这一步做完，rewind / 非破坏压缩 / 侧分支 / 子 trace 四件事同时获得地基。

---

## 本原二：循环是"带分支队列的状态机"，不是一条直线

> 维度：设计 + 功能。

第一性问题：*"agent 需不需要能'跳出任务去想任务本身，再无损地跳回来'？"*——长任务必然需要（压缩、反思、自检都是"元认知"）。

- **TaskPilot**：`AgentLoopHarness.run()` 是 `while not terminated: think→act→observe + 治理`；`FeedbackLoop` 把反馈消息**直接塞进同一根线性流**。它只能"在主线上加料"，**无法离开再回来**。
- **cyber-agent**：同样是循环，但多了 `force_side_branch` **队列** + `SideBranchContext`。压缩 / 反思 / 知识评估作为**共享主路径前缀（及 KV cache）的"绕道"**执行，跑完出队、`head_sequence` 复位、主路径毫发无损。

最精巧的是**队列顺序本身就是编排**：压缩前依次 `reflection`（趁还看得见，把知识抽出来）→ `knowledge_eval`（趁执行还在上下文里，判断注入的知识有没有用）→ `compression`（最后收缩）。因为压缩会**销毁 LLM 可见窗口**，所以一切"需要完整历史"的事必须先做。这是把"资源约束"翻译成"执行顺序"的典范。

**对 TaskPilot**：你有现成的 `LifecycleManager` PAUSE/RESUME 和 `WorkflowController`。一旦本原一（树）就位，侧分支几乎免费——开个临时 `parent_sequence` 挂在主路径上，跑完不前移 head 即可。

---

## 本原三：计划是"被持久化、可 rollup 的结构"，不是临时文本

> 维度：功能 + 设计。

- **TaskPilot** `PlanExecuteStrategy`：`state.plan: List[PlanStep]` 是**扁平文本步骤**，无依赖、无层级、无级联、无成本归集，跑完即弃。
- **cyber-agent** `GoalTree`：层级 + `agent_call` 节点链子 trace + **级联完成**（子全完→父自动完，无需 LLM 判断）+ `self_stats`/`cumulative_stats`（成本精确到子目标并向上 rollup）+ `rebuild_for_rewind`。

第一性差异：**计划本身是不是"值得被推理和持久化的状态"？** cyber-agent 认为是，所以计划能被回溯、被注入（每 5 轮把 GoalTree 重新注回上下文，防模型"忘了在干嘛"）、被算账。

关键洞察：**GoalTree 和消息树是同构的——都是带 `parent` 的树。** 统一这两棵树的建模方式，会省掉大量重复设计。TaskPilot 现有的 `update_plan` 工具方向对，缺的是"结构化 + 持久化 + rollup"。

---

## 本原四（认知/观念核心）：agent 与"自己经验"的关系

> 维度：认知 + 观念。这是整个"认知"维度的所在，也是 TaskPilot **连概念都还没建立**的地方。

cyber-agent 做了三个 TaskPilot 尚未区分的概念：

**1. Memory ≠ Knowledge —— 两条平行线，不是一条线的两段。**
- **Knowledge**（知识）：客观、共享，要走 `extract → review → commit` 审核才进全局库。
- **Memory**（记忆）：主观、私有、Markdown、**人类可随时手改纠错**，由 `dream` 跨 trace 演化。
- 二者都喂自同一个 `cognition_log` 事件流，但**谁也不会"升级"成谁**。

这是个很深的观念：**"我学到的事实"和"我形成的品味/策略"是两种东西，要分开存、分开治理。**

**2. "先保全，后发布"（preserve immediately, publish later）。**
知识必须在**压缩销毁上下文之前**就地抽取（immediate），但进全局库要人工 review（later）——这样错误知识不会污染所有 agent 的检索。这是对"自治系统会犯错"的正确工程回应。

**3. 知识评估闭环（`knowledge_eval`）——连很多前沿框架都没有。**
对注入给 agent 的知识，事后判定 `helpful / harmful / unused / irrelevant`，写回 `cognition_log`。**这是给"学习"装上反馈信号**：不只是"学了"，而是"学的到底有没有用"。

**对照 TaskPilot 的现实（冷酷版）**：
- `ContinuousImprovement.capture()` 写进的是默认的 `InMemoryImprovementStore`，进程结束即蒸发；
- `analyze()`（LLM 复盘）**从未被 harness 调用**；
- `MemoryManager.persist_to_long_term` **全代码库无任何调用**；
- Reflexion 的反思只注入**当前 run**，下一个 run 即遗忘。

**第一性结论**：TaskPilot 的 agent 在结构上是**失忆的**——每个 run 从零开始。而"学习"的本原要求两件事同时具备：**① 一条能活过单次 run 的 write-back 路径；② 一个判断"学到的东西有没有用"的反馈信号。** 你现在两者都缺，且接口都已存在、只差"通电"。

**对你"定时任务引擎"定位价值尤其高**：同一定时任务每天跑，"上次这个数据源超时了→这次调大 timeout"正是 cross-run memory 的杀手场景。

---

## 本原五：上下文经济是"架构"，不是"急救"

> 维度：设计 + 功能。

- **cyber-agent** 把上下文当**最稀缺资源**，从源头管控：
  - `ToolResult` **双层记忆**：`output`（可能巨大，只给 LLM 看一次）+ `long_term_memory`（短摘要，之后永久替代）。
  - **框架参数 vs 模型参数分离**：`hidden_params`（LLM 看不到但框架注入，如 `context`/`uid`）、`inject_params`（框架拥有、模型只能 append 不能覆盖）。
  - CJK 感知 token 估算、图片按 `w*h/750` 计价、每 5 轮重注入 GoalTree。
- **TaskPilot**：`_smart_truncate` 是**事后反应式**；`ArtifactStore`（大结果卸载）**默认关闭且默认 Act 没接线**；最致命的——`ContextWindowManager` 默认**没注入 compactor**，"压缩"退化成有损中段截断（见前文"两条循环"）。

第一性原理：**进入上下文的每个 token 都该被设计**（谁能进、进多久、怎么老化），而非等爆了再砍。**压缩是下游急救，源头管控（双层 ToolResult + 参数分离）才是上游治本。** 先把 compactor 接上线、把 ToolResult 改双层，比直接上三级压缩性价比更高。

---

## 观念层总纲：从"工程兜底不可靠 LLM" → "认知架构即产品"

TaskPilot 的 `../../CLAUDE.md` 写得很诚实：*"用工程手段框住 Agent 的不确定性……工程边界是兜底层。"* 这是**外环思维**——把可靠性寄托在 LLM **外面**的护栏。

cyber-agent 的隐含观念相反：**长任务的可靠性主要来自 LLM 内核的认知架构（树形记忆 / GoalTree / cognition），外环护栏是次要的。**

**边际收益已经转移**：你在外环（分层、状态外置、优雅停机、跨进程取消、多租户）做得很好，已到收益递减；内核（记忆/上下文/计划的数据结构）投入很薄。这是本文最重要的一句观念校正。

---

## 反向：别把 cyber-agent 当圣经

前沿专家的素养之一是知道**什么不该抄**。

**TaskPilot 真正领先 cyber-agent 的（要守住，甚至反哺）：**
- **确定性边界**：MySQL 状态机 + 跨进程**协作式取消**（轮询 `CANCEL_REQUESTED`）+ 原子锁 + 超时强制释放 + 多阶段优雅停机。cyber-agent 的取消只是进程内 `asyncio.Event`，跨进程/多租户远不如你。
- **DI 容器 + 生命周期编排**、`TraceEventBus` 异步事件流。
- **多 Agent DAG 调度**（`coordinator._execute_dag` 拓扑分层 + 环检测 + 失败下游 skip）——比 cyber-agent 的 `explore/delegate` 更接近真正的工作流编排。
- **SQL 安全过滤 / 风险分级 guard**——生产级安全姿态，cyber-agent 没有等价物。

**cyber-agent 自身的坑（抄时要跳过）：**
- `dream` 的反思/整合模型**硬编码** `gpt-4o`/`gpt-4o-mini`，没走统一的 utility LLM 通道，JSON plan 解析作者自己承认脆弱。
- 架构文档里 `RemoteTraceStore` / Context Hooks / A2A 有相当一部分是**"已写文档未实现"**。
- `per_trace_reflect` 无最小长度阈值（短 trace 也反思，浪费）；pending 知识无 TTL。

**正确姿势**：抄它的**本原**（树 / 侧分支 / 认知双线），不抄它的具体实现细节；同时把你的工程底座当资产守住。

---

## 落地优先级（按第一性原理重排）

> 与配套实现文档 [`agent-engine-evolution-design.md`](agent-engine-evolution-design.md) 的 Phase 对应。

| 优先级 | 学习项 | 对应本原 | 改动成本 | 收益 | 风险 |
|--------|--------|---------|---------|------|------|
| **P0** | 真实上下文压缩（接 compactor）+ 覆盖两条循环 | 本原五（下游） | 低 | 极高——防长任务直接 API 失败 | 低 |
| **P0** | 双层 ToolResult（output once + summary） | 本原五（上游） | 低 | 高——从源头抑制 token 膨胀 | 低 |
| **P1** | 工具分组白名单 | — | 低 | 中——安全 + 最小权限 | 极低 |
| **P1** | 跨 run 记忆 + 知识评估闭环 | 本原四 | 中 | 高——定时任务场景差异化价值 | 低 |
| **P1** | 消息树（`sequence`/`parent_sequence`/`head_sequence`） | 本原一 | 中 | 极高——压缩/回溯/侧分支/子 trace 的共同地基 | 中 |
| **P2** | GoalTree 层级目标（复用消息树同构建模） | 本原三 | 中 | 高——计划回退 + 成本 rollup | 中 |
| **P2** | 侧分支机制（树就位后近乎免费） | 本原二 | 低 | 中——非破坏式元认知 | 低 |
| **P2** | Markdown 可执行技能 / Human-in-the-Loop | — | 中 | 中 | 中 |

**排序说明**：与"先做 GoalTree / 三级压缩"的直觉不同，第一性排序把**「真实压缩 + 双层 ToolResult」**这种"低改动、立刻止血"的放最前（先别让长任务崩）；把**「消息树」**作为结构性地基紧随其后（它是压缩/回溯/侧分支/子 trace 的共同前提）；GoalTree 与侧分支作为消息树之上的推论后置。

---

## 核心判断（一句话）

TaskPilot 的工程外环已经很强，**下一阶段的投资应当全部压在 Agent 内核的认知架构上**：先用"真实压缩 + 双层 ToolResult"止住长任务失血，再用"消息树"奠定可回溯/可压缩/可分支的统一地基，最后用"跨 run 记忆 + 知识评估"让 agent 第一次真正"活过单次 run"。这三步做完，"生产级 Agentic Backend"的定位才算名副其实。

---

## 进阶探讨：Agent 认知差异的第一性原理与前沿演进（代码级映射）

> 作为前沿 Agent 设计者，我们不能只看文档中的哲学，必须看**代码是如何表达这些哲学的**。代码才是真实的设计。以下分析将哲学概念直接映射到两个项目的具体 Python 抽象上。

### 1. 造成 Agent 认知差异的第一性原因是什么？（代码级证据）

为什么 `cyber_agent` 的内核认知层会比 TaskPilot（现状）更高？第一性原因在于**数据结构所蕴含的认识论（Epistemology）不同**。

#### 1.1 时间的拓扑：列表（List） vs 树（Tree）
*   **TaskPilot 的代码现实（失忆与破坏）**：
    在 `../../src/core/agents/state/models.py` 中，上下文被定义为 `messages: List[Dict[str, Any]]`。这是一个线性的、可变的数组。
    当触发上下文管理时（`../../src/core/agents/state/context/manager.py`），调用的是 `_truncate_middle`。这个操作直接从 `List` 中**永久删除**了中间的元素。代码层面上，Agent 的过去被物理销毁了，它是一个**活在当下的失忆症患者**。
*   **cyber_agent 的代码现实（时间旅行与非破坏）**：
    在 `agent/trace/store.py` 中，消息不是一个数组，而是一个通过 `parent_sequence` 链接的链表/树。
    获取当前上下文的函数 `get_main_path_messages` 是一个 `while seq is not None: seq = msg.parent_sequence` 的回溯遍历。
    **认知差异的产生**：因为是树，`cyber_agent` 的压缩只是写一条摘要消息，并将其 `parent_sequence` 指向很久以前的节点。原来的详细消息依然在数据库中（只是不在主路径上）。这种数据结构赋予了 Agent **“反事实推理”和“无损回溯”**的物理基础。

#### 1.2 元认知的执行：内联注入（Inline） vs 状态机侧分支（Side-branch）
*   **TaskPilot 的代码现实（单线程思维）**：
    在 `../../src/core/agents/runtime/harness/feedback.py` 中，反思（Reflexion）的结果被直接 `append` 到主 `messages` 列表中。Agent 无法“停下手中的活去思考”，它的反思和执行混杂在同一条时间线上，容易导致上下文污染。
*   **cyber_agent 的代码现实（元认知空间）**：
    在 `agent/core/runner.py` 中，存在一个 `force_side_branch` 队列（如 `["reflection", "knowledge_eval", "compression"]`）。
    当触发侧分支时，Runner 会挂起主任务，切换 Prompt，执行一个子循环，然后**恢复主路径的 `head_sequence`**。
    **认知差异的产生**：代码层面的“侧分支”机制，在物理上隔离了“执行空间”和“思考空间”。Agent 可以“跳出任务去评估自己刚才学到的知识是否有用”，然后再回到任务中。

#### 1.3 经验的沉淀：用完即弃（Ephemeral） vs 主客观分离（Memory & Knowledge）
*   **TaskPilot 的代码现实（经验蒸发）**：
    在 `../../src/core/agents/runtime/harness/improvement.py` 中，`ContinuousImprovement.capture()` 生成了复盘记录，但默认写入的是 `InMemoryImprovementStore`。进程一结束，经验全部蒸发。
*   **cyber_agent 的代码现实（海马体与新皮层）**：
    它在代码中明确区分了两种持久化路径：
    1.  **客观知识（Knowledge）**：通过 `knowledge_eval` 侧分支，将提取的事实写入 `cognition_log.json`，最终经人类 Review 后进入 KnowHub（向量库）。
    2.  **主观记忆（Memory）**：通过 `agent/core/dream.py`（跨 Trace 整合），读取 `cognition_log`，让大模型（如 GPT-4o）去编辑本地的 Markdown 文件（如 `guidelines.md`）。
    **认知差异的产生**：代码强制分离了“我经历的原始日志（Log）”、“我提取的客观事实（Knowledge）”和“我总结的行事准则（Memory）”。

**结论**：认知差异的根源不在于 Prompt 怎么写，而在于**底层类和数据结构**是否为 Agent 提供了**时间方向感（树）**、**元认知空间（侧分支）**和**多模态记忆（双线认知）**。

### 2. 学习与提高认知的资料与网站

要保持对前沿 Agent 设计的敏锐度，不要只看框架的 API 文档，要看背后的**认知架构（Cognitive Architectures）**论文和顶级从业者的思考：

**必读论文（学术界的前沿探索）：**
*   **Generative Agents (Stanford/Google)**: 提出了基于记忆流（Memory Stream）、反思（Reflection）和计划（Planning）的 Agent 架构。
*   **ReAct (Yao et al.)**: 奠定了 Think-Act-Observe 的基础。
*   **Reflexion (Shinn et al.)**: 引入了基于语言反馈的强化学习（在 cyber_agent 的侧分支反思中可见其影子）。
*   **MemGPT**: 探讨了如何像操作系统管理内存（RAM/Disk）一样管理 Agent 的上下文窗口（Tiered Memory）。
*   **CoALA (Cognitive Architectures for Language Agents)**: 普林斯顿大学的这篇论文系统性地将 LLM Agent 映射到经典认知架构（如 SOAR、ACT-R）上，是理解 Agent 模块划分（工作记忆、长期记忆、决策模块）的圣经。

**优质网站与博客（工业界的最佳实践）：**
*   **Lilian Weng's Blog (OpenAI)**: 她的 [*LLM Powered Autonomous Agents*](https://lilianweng.github.io/posts/2023-06-23-agent/) 是一篇极佳的综述。
*   **Andrej Karpathy's Twitter/Talks**: 关注他关于 "Software 2.0/3.0" 以及把 LLM 视为操作系统的隐喻（LLM OS）。
*   **Harrison Chase (LangChain) / LangGraph Blog**: 关注他们为什么从线性的 LangChain 转向基于图状态机（Graph State Machine）的 LangGraph，这与 cyber_agent 的状态机理念不谋而合。
*   **arXiv (cs.AI / cs.CL)**: 定期搜索 "Language Agents", "Cognitive Architecture", "Multi-Agent Systems"。

**值得研究的开源代码库：**
*   **SWE-agent / OSWorld**: 研究它们是如何做环境 grounding（接地）和细粒度工具设计的。
*   **AutoGen / CrewAI**: 研究多智能体之间的对话模式（Conversation Patterns）和拓扑结构。

### 3. 超越 cyber_agent：下一代 Agent 的代码级前沿设计

在 `cyber_agent` 现有的认知之上，前沿科技正在向以下几个方向演进（这也是 TaskPilot 未来可以在代码层面探索的无人区）：

#### 3.1 从"上下文记忆"到"权重更新" (Continuous Learning via SFT/DPO)
目前 `cyber_agent` 的学习停留在 RAG（把经验写进数据库，下次塞进 Prompt 里）。
**代码级下一代设计**：在 `AgentLoopHarness` 结束时，不仅生成 `ImprovementRecord`，而是将整个 Trace 转化为 `(State, Chosen_Action, Rejected_Action)` 的数据集格式（如 JSONL）。积累到一定量后，触发一个后台 Job，调用大模型微调 API（如 OpenAI Fine-tuning），让经验沉淀到模型的**权重（Weights）**里，从而彻底释放上下文窗口。

#### 3.2 System 1 与 System 2 的动态算力路由 (Dynamic Compute Routing)
目前 Agent 对每个步骤都使用相同的模型（如全量调 GPT-4o）。
**代码级下一代设计**：在 `AgentLoopRunner` 中引入一个 `Router` 抽象。
*   **System 1（快思考）**：默认使用低成本模型（如 `gpt-4o-mini`）执行常规工具。
*   **System 2（慢思考）**：当 `state.consecutive_tool_errors > 1` 或 `Router` 判定当前步骤复杂度高时，动态将 `llm_provider` 切换为推理模型（如 `o1-preview`），甚至在代码中开启一个 **MCTS（蒙特卡洛树搜索）** 的循环，在内存中 `fork` 出多个 `AgentLoopState` 模拟多条执行路径，评估胜率后再将最优路径合并回主线。

#### 3.3 主动探索与世界模型 (Active Exploration & World Modeling)
`cyber_agent` 仍然是被动触发的（等待 `run_goal`）。
**代码级下一代设计**：编写一个驻留后台的 Daemon 进程。在没有用户任务时，它主动实例化 `subagent_type="explore"` 的 Agent，去调用 `read_schema`、`fetch_api_docs` 等工具。将其发现写入一个图数据库（GraphDB），构建系统的**世界模型（World Model）**。当真正的任务到来时，Agent 的 `KnowledgeSelector` 直接从这个预先构建的图谱中提取上下文。

#### 3.4 流体多智能体拓扑 (Fluid Multi-Agent Swarms)
目前的多智能体（包括 TaskPilot 的 DAG 和 cyber_agent 的 sub-trace）大多是静态定义的。
**代码级下一代设计**：在 `capabilities/tools` 中提供 `fork_agent` 和 `merge_agents` 工具。当 Agent 遇到需要多视角的问题时，它自己调用 `fork_agent(roles=["critic", "developer"])`，框架在内存中拉起两个共享当前 `head_sequence` 的子线程进行 Debate。辩论结束产生共识后，调用 `merge_agents` 将结果写回主路径。拓扑结构完全由 LLM 在运行时动态生成。

**总结**：`cyber_agent` 很好地在**数据结构层面**解决了 Agent "如何记住过去并反思" 的问题；而前沿的下一步，是解决 Agent **"如何更聪明地分配算力（System 1/2 路由）、如何主动理解世界（图谱构建）、以及如何自我进化（Trace-to-Dataset 权重更新）"** 的问题。TaskPilot 如果能在补齐基础树状认知后，向这些方向迈出代码级的一步，将具有极高的技术壁垒。
