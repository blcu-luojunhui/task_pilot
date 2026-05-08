# Think 阶段 — LLM 推理

> `src/core/agents/engine/loop.py` — `Think`
> `src/core/agents/engine/prompting/assembler.py` — `PromptAssembler`
> `src/core/agents/engine/prompting/knowledge_selector.py` — `KnowledgeSelector`

---

## 为什么存在这个功能？

Agent 的每一步都需要让 LLM 基于当前上下文（goal + 历史消息 + 已执行的 tool 结果）做出下一步决策——调用哪个工具、传什么参数、还是直接给出最终答案。

如果只是把 `state.messages` 原样发给 LLM，缺少以下关键信息：

1. **动态预算提示** — LLM 不知道还剩几步、用了多少时间
2. **错误恢复提示** — LLM 不知道刚才连续失败了几次
3. **领域知识** — LLM 不知道该任务相关的专业知识/规范
4. **上下文过载** — messages 可能超过 token 限制

Think 阶段负责**在调用 LLM 之前，构建一个高质量的、信息完整的 prompt，管理上下文窗口**。

## 为什么选这个设计？

**三段式处理链：PromptAssembler → KnowledgeSelector → ContextWindowManager → LLM**：

- `PromptAssembler` 构建 system message（base instructions + goal + budget + recovery hints + knowledge）
- `KnowledgeSelector` 按 goal/tool_call_history 关键词匹配相关领域知识
- `ContextWindowManager` 在 token 超限时压缩历史消息
- `Think.run()` 把 system message 插入到消息头部，压缩后的消息传给 LLM

对比可选方案：
- 把 prompt 拼装逻辑放在 planner 里：planner 变成上帝对象，且无法复用（换个 provider 要重写）
- 不做上下文压缩：超限直接报错 → 任务失败

## 解决什么问题？

1. **LLM 有完整的任务上下文** — 知道目标、预算、历史、错误状态
2. **动态注入领域知识** — 不把所有知识塞进 system prompt，按需选择
3. **防止上下文溢出** — 超限前自动压缩，而非报错
4. **Provider 无关** — 拼装逻辑与具体 LLM 实现解耦

## 在 Agent 流程中承担什么责任？

```
AgentLoopHarness.run() 主循环
  │
  ├─ Think.run(state)
  │    │
  │    ├─ PromptAssembler.assemble(state)
  │    │    ├─ base_instructions (角色定义)
  │    │    ├─ goal (当前目标)
  │    │    ├─ budget (剩余步数)
  │    │    ├─ recovery_hint (连续错误时)
  │    │    └─ KnowledgeSelector.select(state) 知识注入
  │    │
  │    ├─ context_manager.compact_if_needed(messages)
  │    │    └─ 保留 system + first user + last N, 中间替换为摘要
  │    │
  │    ├─ planner(messages, step) → LLM API 调用
  │    │
  │    └─ 错误处理 → LLMError
  │
  └─ 返回 assistant_message → Harness 继续到 Act
```

## PromptAssembler 输出结构

```
[system] Base Instructions (角色定义 + 工具使用规范)
[system] Goal: <用户目标>
[system] Budget: Step 3/8, 2 tool calls used
[system] ⚠️ 你已经连续 2 次工具调用失败，请检查参数格式并重试，或直接给出当前可得的最佳答案。
[system] ## Reference Knowledge
  <匹配到的领域知识>
-----
[user]  原始 user message
[assistant] 第1轮响应
[tool]  第1轮结果
...
```

## KnowledgeSelector 选择策略

1. 从 `state.goal` 关键词匹配 domain（database / http / task-management / observability）
2. 从 `state.tool_call_history` 中已调用工具反推 domain
3. Skill 声明了非 `general` domain 的优先匹配
4. 通过 `max_knowledge_tokens` 限制知识总长度

## 技术栈

- Python dataclass
- LLM Provider 抽象层（`LLMProvider.chat()`）
- 字符数 token 估算（`chars / 4.0 ≈ tokens`）
- 消息列表拼接（`[system_msg] + compacted_history`）

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| KnowledgeSelector 用简单关键词匹配 | 用 embedding 做语义相似度匹配 |
| PromptAssembler 输出结构固定 | 支持自定义 section 模板 |
| 每步都重新 assemble，system message 大部分重复 | 缓存 system message，只在 goal/errors/budget 变化时重建 |
| token 估算是近似的（chars/4） | 可选接入 tiktoken 做精确计数 |
| 压缩策略只保留最近 N 条，中间知识全部丢失 | 让 LLM 生成中间摘要而非丢弃 |

## 使用案例

### 查看 Think 阶段组装后的完整 prompt

```python
agent = Agent.create(
    llm_api_key="sk-xxx",
    show_prompt=True,  # 打印发给 LLM 的完整 prompt
    verbose=True,       # 同时打印执行日志
)

result = await agent.run("查询今天的订单数据")
# 日志输出：
# [Think] Step 1 - 组装 prompt:
# [system] You are an AI assistant...
# [system] Goal: 查询今天的订单数据
# [system] Budget: Step 1/8
# [user] 查询今天的订单数据
```

### 自定义 PromptAssembler 的 base instructions

```python
from src.core.agents.engine.prompting import PromptAssembler

assembler = PromptAssembler(
    base_instructions="你是一个数据库管理专家，只允许执行 SELECT 语句。",
    knowledge_selector=my_knowledge_selector,
)

# 通过 runner 注入
runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    thinker=Think(planner=my_planner, prompt_assembler=assembler),
)
```

### 注入特定领域的 knowledge skill

```python
from src.core.agents.capabilities import Skill, SkillType, RiskLevel
from src.core.agents.capabilities import get_global_registry

# 注册一条知识类 skill
knowledge_skill = Skill(
    skill_id="db_schema_v1",
    name="db_schema",
    description="当前数据库表结构和字段说明",
    skill_type=SkillType.KNOWLEDGE,
    handler=lambda: None,  # 知识类无 handler
    body="## 数据库表结构\n- orders: id, user_id, amount, status, created_at\n- users: id, name, email",
    domain="database",
    format="markdown",
)

registry = get_global_registry()
registry.register(knowledge_skill)

# 当 goal 中包含 "数据库"/"SQL"/"订单" 等关键词时，
# KnowledgeSelector 会自动把这条知识注入到 system prompt
```
