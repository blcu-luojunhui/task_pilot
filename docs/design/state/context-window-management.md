# Context Window Management — 上下文窗口管理

> `src/core/agents/state/context/manager.py` — `ContextWindowManager`

---

## 为什么存在这个功能？

Agent 每轮 Think-Act-Observe 都会向 `state.messages` 追加 assistant message 和 tool results。对于多步骤任务（8 步 × 每步可能多个工具调用），消息总量很容易超出 LLM 的 context window（DeepSeek 64K tokens，Claude 200K tokens）。超出后 API 直接报错，任务失败。

即使不超出，过长的上下文也会：
1. 增加 API 延迟和成本（按 token 计费）
2. 降低 LLM 对关键信息的注意力（"lost in the middle" 效应）

## 为什么选这个设计？

**估算 token → 超限时中段截断策略**：

- 用 `chars_per_token ≈ 4.0` 估算 token 数，不引入 tokenizer 依赖
- 压缩策略：保留 system messages + 第一条 user message（含 goal）+ 最近 N 条消息 + 中间替换为摘要占位消息
- 压缩只影响传给 LLM 的消息副本，`state.messages` 保持完整（用于审计和调试）

对比可选方案：
- 滑动窗口（只保留最近 N 条）：丢失 system prompt 和 goal
- LLM 自己总结历史：多一次 API 调用，增加成本
- 精确 tokenizer（tiktoken）：增加依赖，中英文混合场景下 chars/4 在 80-120% 精度范围内

## 解决什么问题？

1. **防止 context overflow** — 超限前自动压缩而非报错
2. **保留关键信息** — system messages + goal 不丢失
3. **零依赖** — 不需要 tokenizer，纯 Python
4. **调试友好** — 压缩不修改原始状态

## 在 Agent 流程中承担什么责任？

```
Think.run(state)
  │
  ├─ messages = list(state.messages)            ← 复制消息列表
  │
  ├─ if context_manager:
  │     messages = context_manager.compact_if_needed(messages)
  │     │
  │     ├─ estimate_tokens(messages)
  │     │    └─ 每个 message.content 和 tool_calls.arguments 的字符数 / 4
  │     │
  │     ├─ if total_tokens > max_context_tokens:
  │     │    ├─ 保留 system messages
  │     │    ├─ 保留 messages[system_count]（第一条 user，通常是 goal）
  │     │    ├─ 保留 messages[-preserve_recent:]
  │     │    ├─ 中间插入摘要占位消息
  │     │    └─ 返回压缩后的消息列表
  │     │
  │     └─ else: 返回原列表
  │
  └─ planner(messages, step)                   ← 传给 LLM 的是压缩后的副本
```

## 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `max_context_tokens` | `60000` | 触发压缩的 token 阈值 |
| `chars_per_token` | `4.0` | 字符到 token 的估算比率 |
| `preserve_recent_messages` | `6` | 压缩时保留的最近消息数 |

## 压缩示例

```
压缩前（10 条消息，~80K tokens）：
  [system]   Base instructions
  [system]   Goal: xxx
  [system]   Reference knowledge
  [user]     goal message
  [assistant] step 1 response
  [tool]     step 1 results
  [assistant] step 2 response
  [tool]     step 2 results
  [assistant] step 3 response
  [tool]     step 3 results

压缩后（~40K tokens）：
  [system]   Base instructions
  [system]   Goal: xxx
  [system]   Reference knowledge
  [user]     goal message
  [system]   [...previous conversation summarized, 2 steps omitted]
  [assistant] step 3 response
  [tool]     step 3 results
```

## 技术栈

- Python dataclass
- 字符数/4 token 估算

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| chars/4 对中文偏大（中文 ~2 chars/token） | 动态检测语言比例，调整 chars_per_token |
| 中段直接丢弃，不保留摘要 | 让 LLM 生成中间步骤摘要再压缩 |
| 阈值固定 60000 | 根据实际使用的模型动态调整（Claude 可以设 180000） |
| 保留的消息数 `preserve_recent_messages` 对所有场景统一 | 按任务类型调整（简单任务保留更少，复杂任务保留更多） |

## 使用案例

### 默认配置（推荐）

```python
# Agent.create() 默认启用，max_context_tokens=60000
agent = Agent.create(
    llm_api_key="sk-xxx",
    llm_provider="deepseek",
)
```

### 调整压缩策略

```python
runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    max_context_tokens=100000,  # 更大窗口（如用 Claude）
    # preserve_recent 通过 context_manager 设置
)
```

### 完全禁用（不推荐）

```python
runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    max_context_tokens=999999,  # 极大值 → 永不压缩
)
```

### 观察压缩触发

```python
# 在 Harness hook 中观察压缩
async def log_compaction(event):
    if event.name == "think_start":
        msgs = event.state.messages
        # 估算当前 token 使用量
        est_tokens = sum(
            len(str(m.get("content", ""))) / 4 for m in msgs
        )
        if est_tokens > 60000:
            print(f"⚠️ 步骤 {event.state.step}: 上下文已超限，触发压缩 ({est_tokens:.0f} tokens)")
```
