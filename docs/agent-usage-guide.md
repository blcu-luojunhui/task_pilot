# Agent Usage Guide

> 这是一份面向使用者的手册。架构细节见 [Agent Guide](agent.md)，项目入口见 [README](../README.md)。

TaskPilot Agent 的最小使用方式是：创建 Agent，声明模型和工具区域，提交一个 goal，拿到 `AgentLoopResult`。

## 最小示例

```python
from src.core.agents import Agent

agent = Agent.create(
    llm_api_key="your-api-key",
    llm_provider="deepseek",      # deepseek | openai | claude
    tool_areas=["utils"],
)

result = await agent.run("帮我分析系统状态")

print(result.success)
print(result.final_answer)
print(result.total_steps)
print(result.tool_calls_count)
print(result.trace_id)
```

默认 provider 是 `deepseek`，默认策略是 `react`，默认最大步数是 `8`。

## 选择模型 Provider

```python
agent = Agent.create(
    llm_api_key="sk-xxx",
    llm_provider="openai",
    llm_model="gpt-4o",
    llm_base_url="https://api.openai.com/v1",
    llm_temperature=0.2,
)
```

支持的 provider：

- `deepseek`：默认模型 `deepseek-chat`。
- `openai`：默认模型 `gpt-4o`。
- `claude`：默认模型 `claude-sonnet-4-6`。

`Agent.create()` 会按 provider 自动选择 Tool Spec 序列化格式。OpenAI 与 DeepSeek 使用 function wrapper，Claude 使用 Claude tool schema。

## 加载工具区域

内置工具按区域加载，避免把不需要的工具暴露给模型：

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    tool_areas=["utils", "http"],
)
```

常用区域：

| 区域 | 能力 | 是否通常需要依赖 |
|---|---|---|
| `utils` | 时间、哈希、批处理等通用能力 | 否 |
| `http` | HTTP 请求 | 是，注入 `http_client` 更适合生产 |
| `database` | SQL 查询与写入 | 是，注入 `db_client` |
| `task` | 任务查询、提交、取消 | 是，依赖任务服务 |
| `plan` | 更新结构化计划 | 否 |
| `artifact` | 回读上下文卸载结果 | 否 |
| `handoff` | Agent 控制权移交 | 视场景而定 |
| `chat_ops` | 聊天相关操作 | 是，依赖聊天服务 |

依赖注入示例：

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    tool_areas=["database", "http"],
    tool_dependencies={
        "db_client": db_client,
        "http_client": http_client,
    },
)
```

不要在 Skill 内部直接创建数据库连接或 HTTP client。TaskPilot 的约定是：基础设施由外部注入，Skill 只表达领域动作。

## 注册自定义 Skill

装饰器方式适合大多数场景：

```python
from src.core.agents import SkillContext

@agent.skill(
    name="fetch_weather",
    description="获取指定城市的天气信息",
    risk_level="read",
    parameters={
        "city": {"type": "string", "description": "城市名称"},
    },
)
async def fetch_weather(ctx: SkillContext, city: str) -> dict:
    return {"city": city, "temp": 25}
```

也可以直接注册 `Skill` 对象：

```python
from src.core.agents import Skill, SkillType, RiskLevel

skill = Skill(
    skill_id="my_tool_001",
    name="my_tool",
    description="My custom tool",
    skill_type=SkillType.EXECUTABLE,
    handler=my_function,
    risk_level=RiskLevel.READ,
    parameters={"param": {"type": "string", "description": "Input"}},
)

agent.register_skill(skill)
```

Skill 描述会进入模型上下文。好的描述应该说明“什么时候用”和“输入输出是什么”，不要只写函数名的中文翻译。

## 选择执行策略

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    strategy="plan_execute",
)
```

策略选择建议：

- `react`：默认。适合工具调用少、目标清晰、希望低延迟的任务。
- `plan_execute`：适合“分析日志 → 总结问题 → 生成报告”这类多步骤目标。
- `reflexion`：适合工具容易失败、需要模型从错误中调整策略的探索性任务。

启用反思反馈：

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    strategy="reflexion",
    enable_reflection=True,
    reflection_trigger_errors=2,
)
```

反思不是免费能力。它会额外消耗 token，但能把连续失败转换为下一轮可见的修正信号。

## 控制运行边界

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    max_steps=8,
    max_context_tokens=60000,
    max_tool_result_length=2000,
    abort_on_tool_error=False,
    max_consecutive_errors=3,
)
```

常用规则：

- 简单查询任务：`max_steps=3` 到 `4`。
- 多工具分析任务：`max_steps=8` 到 `12`。
- 外部工具不稳定时：保留 `abort_on_tool_error=False`，让错误写回 transcript 给模型修正。
- 高风险写操作：缩小工具区域，并用 `risk_level` 配合 `PermissionGuard`。

## 生命周期与快照

Agent 生命周期独立于 MySQL 任务状态机：

```python
agent.pause()      # 当前 step 完成后挂起
agent.resume()     # 从暂停点继续
agent.stop()       # 当前 step 完成后以 USER_CANCELLED 返回
```

状态查询：

```python
agent.lifecycle_state   # IDLE / RUNNING / PAUSED / STOPPED / ERROR
agent.is_paused
agent.is_running
```

保存和恢复快照：

```python
agent.set_snapshot_dir("./snapshots")

agent.pause()
snapshot_id = agent.save_snapshot(metadata={"task_id": "task-001"})

result = await agent.run_from_snapshot(snapshot_id)
```

快照适合长任务、人工审核点和失败恢复。不要把它当成任意时刻强制中断，Agent 仍然在 step 边界协作式暂停。

## 上下文、记忆与 Artifact

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    memory_backend="keyword",
    long_term_memory_path="./memory/agent.json",
    enable_context_offload=True,
    offload_threshold_chars=4000,
)
```

说明：

- `memory_backend="keyword"` 是默认零依赖检索。
- `memory_backend="embedding"` 需要提供 embedding backend。
- `enable_context_offload=True` 会把超长工具结果保存为 artifact，prompt 中保留摘要和引用。

上下文窗口是 Agent 的稀缺资源。对大结果做 offload，通常比把完整 JSON、HTML 或日志塞进 prompt 更稳定。

## 任务路由

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    enable_routing=True,
)

result = await agent.run("分析日志，生成报告，提出修复建议")
```

任务路由适合目标天然可拆分的场景。它不会替代 Multi-Agent，只是在单 Agent 内先做目标分解，再按子目标推进。

## run() 返回值

```python
result = await agent.run(goal="...")

result.success
result.final_answer
result.stop_reason
result.total_steps
result.tool_calls_count
result.duration_seconds
result.trace_id
```

常见 `stop_reason`：

| 值 | 含义 |
|---|---|
| `MODEL_FINAL` | 模型判断任务完成 |
| `MAX_STEPS` | 达到最大 step 上限 |
| `BUDGET_EXHAUSTED` | 时间或工具调用预算耗尽 |
| `USER_CANCELLED` | 用户请求停止 |
| `CONSTRAINT_VIOLATION` | 违反约束 |
| `ERROR` | 执行异常 |

## 调试建议

- 开发期使用 `verbose=True` 观察每步执行。
- 使用 `show_prompt=True` 检查最终发给模型的 prompt，但不要在生产日志中打开。
- 通过 `trace_id` 串联 HTTP 请求、任务日志、Agent step 和工具调用。
- 修改 Skill 描述、Prompt 或策略后，用 Replay/Evaluator 做回归，而不是只看一次人工运行结果。
