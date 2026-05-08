# Act 阶段 — 工具执行

> `src/core/agents/engine/loop.py` — `Act`

---

## 为什么存在这个功能？

LLM 在 Think 阶段决定了要调用哪些工具、传什么参数后，Act 阶段负责实际执行这些工具调用，并将结果格式化后返回给 Observe 阶段。

核心挑战：

1. **并行执行** — LLM 可能同时返回多个 tool call，串行执行会增加延迟
2. **结果截断** — 工具（如数据库查询）可能返回几万行数据，全部塞入 LLM context 会浪费 token
3. **依赖注入** — 每个工具可能需要不同的外部依赖（数据库连接池、HTTP 客户端等）
4. **权限检查** — 在工具执行前需要校验 LLM 请求的操作是否被允许

## 为什么选这个设计？

**单工具串行路径 + 多工具 asyncio.gather 并行路径 + 统一的 _execute_one 内部流程**：

- `run()` 检测 tool_calls 数量，1 个直接 await，多个用 `asyncio.gather` 并发
- `_execute_one()` 内部流程：lookup skill → check permission → build context → execute → truncate output → build result
- 截断只在传给 LLM 的结果上做，`ToolCallRecord` 保留完整结果
- 权限检查通过 `PermissionGuard` 完成（不配置则跳过）

对比可选方案：
- 总是串行执行：简单但浪费 latency（3 个 I/O 工具串行耗时是并行的 3 倍）
- 用 `asyncio.wait` 而非 `asyncio.gather`：gather 保证结果顺序与输入一致，逻辑更简单
- 用线程池并行：asyncio 事件循环单线程，线程池反而增加上下文切换开销

## 解决什么问题？

1. **I/O 延迟优化** — 多个独立工具调用并发执行，总耗时 ≈ max(各工具耗时)
2. **上下文空间保护** — 长结果截断并告知 LLM，防止 context overflow
3. **安全的依赖注入** — `SkillContext` 惰性解析依赖，工具只拿到它声明的依赖
4. **权限门控** — 在执行前校验风险等级，阻止越权操作

## 在 Agent 流程中承担什么责任？

```
Harness 主循环
  │
  ├─ get_tool_calls(assistant_message)
  │    └─ 从 LLM 响应中提取 tool_calls → List[ToolCall]
  │
  ├─ workflow.before_act(state, assistant_message)
  │    └─ 约束检查（如禁止在此 phase 执行写操作）
  │
  ├─ Act.run(state, tool_calls)
  │    │
  │    ├─ if len(tool_calls) == 1:
  │    │     result = await _execute_one(state, tool_calls[0])
  │    │
  │    ├─ else:
  │    │     tasks = [_execute_one(state, tc) for tc in tool_calls]
  │    │     results = await asyncio.gather(*tasks)
  │    │
  │    └─ 每个 _execute_one():
  │         ├─ 在 registry 中查找 skill
  │         ├─ PermissionGuard.check(skill) → 拒绝则返回 permission_denied 错误
  │         ├─ SkillContext 构造（注入依赖）
  │         ├─ SkillExecutor.execute(skill, context, params)
  │         │    ├─ ParameterValidator 校验参数
  │         │    ├─ PermissionGuard 风险管理
  │         │    └─ handler(**params) 执行
  │         ├─ 序列化 + 截断输出
  │         ├─ 构造 ToolCallRecord 记录到 state
  │         └─ 返回 tool_result_message
  │
  └─ 返回 tool_results → Harness 继续到 Observe
```

## 截断策略

- 成功结果：`content[:max_tool_result_length] + "[...truncated, showing first N chars of M total]"`
- 错误结果：不截断（错误信息通常很短）
- `ToolCallRecord.tool_output` 保留完整结果，截断只影响传给 LLM 的消息
- 默认 `max_tool_result_length=2000`

## 并行执行安全性

| 关注点 | 处理方式 |
|--------|----------|
| 单个工具抛异常 | `_execute_one` 内部 catch 所有异常，返回 error dict，不影响其他工具 |
| asyncio 数据竞争 | 单线程事件循环，不存在竞争 |
| 结果顺序 | `asyncio.gather` 保证结果顺序与 tasks 顺序一致 |

## 技术栈

- `asyncio.gather` 并发执行
- `SkillRegistry` 查 skill → `SkillExecutor` 执行
- `PermissionGuard` 权限门控
- `SkillContext` 惰性依赖注入

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| 并行执行没有并发限制 | 增加 `max_parallel_tools` 参数，超过则分批执行 |
| 工具超时默认 30s，对所有工具统一 | 按 skill 声明 timeout（轻量工具 5s，重量工具 120s） |
| 截断基于字符数而非 token | 可选接入 tiktoken 做精确 token 截断 |
| 截断只保留前 N 字符 | 智能截断：保留开头摘要 + 末尾关键数据 |

## 使用案例

### 调整工具执行参数

```python
from src.core.agents.engine.loop import Act
from src.core.agents.capabilities import SkillExecutor

executor = SkillExecutor(timeout=15.0, retry=2)  # 15s 超时，最多 2 次重试
actor = Act(
    registry=registry,
    executor=executor,
    max_tool_result_length=4000,  # 增加到 4000 字符
)

runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    actor=actor,
)
```

### 并行执行效果

```python
# LLM 在单轮中决定调用 3 个工具：
#   http_get("https://api.example.com/users")     → 耗时 1.2s
#   db_query("SELECT COUNT(*) FROM orders")         → 耗时 0.8s
#   http_get("https://api.example.com/products")    → 耗时 1.5s

# 串行总耗时：1.2 + 0.8 + 1.5 = 3.5s
# 并行总耗时：max(1.2, 0.8, 1.5) = 1.5s
# 节省约 57%
```

### 注入外部依赖到工具

```python
from src.core.agents.capabilities import SkillContext, ContainerResolver

# 准备依赖容器
deps = {
    "db_pool": AsyncMySQLPool(...),
    "http_client": AsyncHttpClient(...),
    "config": ProjectConfigSettings(...),
}

context_builder = lambda state: SkillContext(
    trace_id=state.trace_id,
    resolver=ContainerResolver(deps),
)

runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    context_builder=context_builder,
    tool_dependencies=deps,  # 兼容旧参数
)
```
