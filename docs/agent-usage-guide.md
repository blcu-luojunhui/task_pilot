# Agent 使用指南

## 概述

TaskPilot Agent 系统提供完整的 AI Agent 框架，基于 Think → Act → Observe 循环，支持多 LLM Provider、自定义 Skills、Multi-Agent 协作和状态快照。

## 架构

```
src/core/agents/
├── engine/           # Agent Loop / Runner / Planner / Lifecycle
│   └── prompting/    #   Prompt 组装、路由、知识选择
├── capabilities/     # 能力层
│   ├── llm/          #   LLM Provider 抽象 + DeepSeek/OpenAI/Claude
│   │   └── providers/
│   ├── tools/        #   内置工具：database / http / task / utils
│   └── skills/       #   Skill 注册、校验、执行、序列化、Guard
├── runtime/          # 运行时：Hook / Harness（Budget/Constraint/Feedback）
├── state/            # 状态管理 / 快照 / 上下文窗口 / 记忆
├── multi_agents/     # 多智能体协作
└── execution/        # 执行调度
```

## 快速开始

### 1. 创建 Agent

```python
from src.core.agents import Agent

agent = Agent.create(
    llm_api_key="your-api-key",
    llm_provider="deepseek",     # deepseek / openai / claude
)

result = await agent.run("帮我分析系统状态")
print(result.final_answer)       # 最终回答
print(result.success)            # 是否成功
print(result.total_steps)        # 执行步数
print(result.tool_calls_count)   # 工具调用次数
```

### 2. 加载内置工具

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    tool_areas=["utils"],                        # 默认，无 infra 依赖
    # tool_areas=["database", "http", "task"],   # 按需启用
)
```

| 工具区域 | 能力 | 需要依赖注入 |
|----------|------|------------|
| `utils` | 时间、哈希、批处理 | 否 |
| `database` | 数据库查询/写入 | 是 (`db_client`) |
| `http` | HTTP 请求 | 是 (`http_client`) |
| `task` | 任务状态/取消 | 是 |

### 3. 注入依赖

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

### 4. 注册自定义 Skill

**装饰器方式：**

```python
@agent.skill(
    name="fetch_weather",
    description="获取指定城市的天气信息",
    parameters={
        "city": {"type": "string", "description": "城市名称"},
    },
)
async def fetch_weather(city: str) -> dict:
    return {"city": city, "temp": 25}
```

**直接注册 Skill 对象：**

```python
from src.core.agents import Skill, SkillType

skill = Skill(
    skill_id="my_tool_001",
    name="my_tool",
    description="My custom tool",
    skill_type=SkillType.EXECUTABLE,
    handler=my_function,
    parameters={"param": {"type": "string", "description": "Input"}},
)
agent.register_skill(skill)
```

---

## LLM Provider 配置

### 切换 Provider

```python
# DeepSeek（默认）
agent = Agent.create(llm_api_key="sk-xxx", llm_provider="deepseek")

# OpenAI
agent = Agent.create(llm_api_key="sk-xxx", llm_provider="openai")

# Claude
agent = Agent.create(llm_api_key="sk-xxx", llm_provider="claude")
```

### 自定义参数

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    llm_provider="deepseek",
    llm_model="deepseek-chat",           # 模型名（None 用 provider 默认值）
    llm_base_url="https://api.deepseek.com",  # API 地址
    llm_temperature=0.2,                 # 温度 [0, 2]
)
```

---

## 完整配置

```python
agent = Agent.create(
    # LLM 配置
    llm_api_key="your-api-key",
    llm_provider="deepseek",
    llm_model=None,                # None = 使用 provider 默认值
    llm_base_url=None,             # None = 使用 provider 默认值
    llm_temperature=0.2,

    # 执行配置
    max_steps=8,
    max_context_tokens=60000,
    max_tool_result_length=2000,
    abort_on_tool_error=False,
    max_consecutive_errors=3,

    # 工具配置
    tool_areas=["utils"],
    tool_dependencies={},

    # 调试配置
    verbose=False,                 # 打印执行流程日志
    show_prompt=False,             # 打印发给 LLM 的完整 prompt
)
```

---

## 生命周期控制

Agent 有独立于任务状态机的生命周期：

```python
agent.pause()      # 暂停 — 当前 step 完成后挂起，run() 协程不返回
agent.resume()     # 恢复 — 从暂停点继续执行
agent.stop()       # 停止 — 当前 step 完成后以 USER_CANCELLED 返回
```

状态查询：

```python
agent.lifecycle_state   # AgentState: IDLE / RUNNING / PAUSED / STOPPED / ERROR
agent.is_paused         # bool
agent.is_running        # bool
```

---

## 状态快照

支持暂停后持久化，后续从快照恢复：

```python
# 设置快照目录
agent.set_snapshot_dir("./snapshots")

# 暂停并保存
agent.pause()
snapshot_id = agent.save_snapshot(metadata={"task_id": "xxx"})

# 从快照恢复执行
result = await agent.run_from_snapshot(snapshot_id)
```

---

## 任务路由

启用 `enable_routing=True`，复杂目标会被自动拆分为子任务按序执行：

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    enable_routing=True,
)

result = await agent.run("分析日志，生成报告，发送邮件")
# Agent 会将目标拆分为 3 个子任务依次执行
```

---

## run() 返回值

```python
result: AgentLoopResult = await agent.run(goal="...")

result.success            # bool — 是否成功
result.final_answer       # str | None — 最终回答
result.stop_reason        # StopReason — 停止原因
result.total_steps        # int — 总步数
result.tool_calls_count   # int — 工具调用次数
result.duration_seconds   # float — 执行耗时
result.trace_id           # str — 追踪 ID
```

StopReason 枚举：

| 值 | 含义 |
|---|------|
| `MODEL_FINAL` | LLM 判断任务完成 |
| `MAX_STEPS` | 达到 max_steps 上限 |
| `BUDGET_EXHAUSTED` | 时间或 tool call 预算耗尽 |
| `USER_CANCELLED` | 用户调用 stop() |
| `CONSTRAINT_VIOLATION` | 违反约束策略 |
| `ERROR` | 执行异常 |

---

## 最佳实践

1. **合理设置 max_steps**：简单任务 3-4 步，复杂分析 8-12 步
2. **按需加载工具**：只加载需要的 tool_areas，减少 token 消耗
3. **使用依赖注入**：避免在 Skill 中硬编码 infra 依赖
4. **设置风险级别**：为 Skill 指定 `RiskLevel.READ / WRITE / DESTRUCTIVE`，配合 PermissionGuard 做权限控制
5. **开启 verbose**：调试时设置 `verbose=True` 观察每一步的 think/act/observe 输出
6. **善用快照**：长时间运行的 Agent 任务定期保存快照，避免意外中断后从头开始
