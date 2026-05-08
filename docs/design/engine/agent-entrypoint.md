# Agent 主入口与配置

> `src/core/agents/engine/agent.py` — `Agent`, `AgentConfig`

---

## 为什么存在这个功能？

Agent 系统的用户需要一个统一的、类型安全的入口来创建和配置 Agent。如果没有 `Agent.create()` 工厂方法和 `AgentConfig`，调用方需要手动组装 `AgentLoopRunner`、`SkillRegistry`、`SkillExecutor`、`LLMProvider` 等五六层组件，且每层的参数散落在各处，极易配置错误或遗漏。

## 为什么选这个设计？

**工厂方法 + dataclass 配置**：

- `AgentConfig` 用 dataclass 提供集中式配置，所有参数有类型注解和默认值，`__post_init__` 做集中校验（拒绝非法 provider、负值等）
- `Agent.create()` 类方法承担所有组装逻辑：解析 provider 默认值 → 创建 LLMProvider → 加载工具 → 创建 registry/executor → 组装 planner → 创建 runner + lifecycle
- `Agent` 实例对外暴露简洁 API：`run()` / `pause()` / `resume()` / `stop()` / `save_snapshot()` / `run_from_snapshot()`

对比可选方案：
- Builder 模式：需要维护 Builder 生命周期，对 Python 生态不够自然
- 构造函数直接传所有依赖：参数过多（10+），调用方认知负担重

## 解决什么问题？

1. **降低接入门槛** — 调用方三行代码即可创建可用的 Agent
2. **防止配置错误** — `__post_init__` 在构造时即校验，fail fast
3. **Provider 透明切换** — 只需要改 `llm_provider="openai"` 一个参数，其余自动适配
4. **可选功能按需开启** — `enable_routing`、`verbose`、`show_prompt` 等通过配置控制

## 在 Agent 流程中承担什么责任？

```
Agent.create()              → 组装所有组件（仅一次）
Agent.run(goal)             → 入口，管理 lifecycle 状态转换
Agent.pause() / resume()    → 运行时控制（外部线程安全调用）
Agent.stop()                → 优雅终止
Agent.save_snapshot()       → 暂停时持久化状态
Agent.run_from_snapshot()   → 从持久化状态恢复执行
```

`Agent` 类是用户与 Agent 系统的**唯一交互界面**，所有内部组件（Runner、Harness、Think、Act、Observe）对调用方透明。

## 技术栈

- Python dataclass + `__post_init__` 校验
- `_PROVIDER_MAP` 字典做 provider 路由
- `_PROVIDER_DEFAULTS` 字典存各 provider 的 model/base_url 默认值
- `asyncio.Event` 支撑 pause/resume 机制
- `Path.mkdir(parents=True, exist_ok=True)` 管理快照目录

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| `Agent.create()` 参数列表偏长（15+ 参数） | 拆分 `AgentConfig` 为 `LLMConfig` + `ExecutionConfig` + `ToolConfig` 三个子配置 |
| `planner_factory` 闭包定义在 `create()` 内部，逻辑较重（~60 行） | 提取为独立的 `PlannerFactory` 类，便于单独测试 |
| 没有配置的热更新能力 | Agent 创建后 `config` 不可变——对于长时运行 Agent 可能需要动态调整 budget |

## 使用案例

### 基础使用

```python
from src.core.agents import Agent

agent = Agent.create(
    llm_api_key="sk-xxx",
    llm_provider="deepseek",
    max_steps=10,
)

result = await agent.run("查询今天的订单总数")
print(result.final_answer)
```

### 切换 Provider

```python
# 同样的代码，只改一个参数
agent = Agent.create(
    llm_api_key="sk-xxx",
    llm_provider="claude",       # deepseek → claude
    llm_model="claude-sonnet-4-6",
)
```

### 加载特定工具域并调试

```python
agent = Agent.create(
    llm_api_key="sk-xxx",
    tool_areas=["database", "http"],
    verbose=True,               # 打印每步执行日志
    show_prompt=True,           # 打印发给 LLM 的完整 prompt
)
```

### 带生命周期控制

```python
agent = Agent.create(llm_api_key="sk-xxx")

# 异步执行
import asyncio
task = asyncio.create_task(agent.run("长时间分析任务"))

# 外部控制
await asyncio.sleep(5)
agent.pause()                         # 暂停
agent.set_snapshot_dir("./snapshots")
agent.save_snapshot({"reason": "维护窗口"})
agent.resume()                        # 恢复

# 或者直接停止
agent.stop()
```
