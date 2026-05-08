# AgentLoopRunner — 组件组装器

> `src/core/agents/engine/runner.py` — `AgentLoopRunner`

---

## 为什么存在这个功能？

Agent 系统由十几个独立组件组成：Think、Act、Observe、PromptAssembler、KnowledgeSelector、ContextWindowManager、SkillRegistry、SkillExecutor、PermissionGuard、AgentBudget、ConstraintSet、FeedbackLoop、ContinuousImprovement、WorkflowController、LifecycleManager。

如果没有一个统一的组装器，要么把所有组装逻辑塞进 `Agent.create()`（导致工厂方法臃肿），要么让调用方手动组装（认知负担极高）。

`AgentLoopRunner` 是中间层——**接收离散的组件参数，在 `__post_init__` 中按正确顺序和依赖关系将它们组装成可执行的 `AgentLoopHarness`**。

## 为什么选这个设计？

**Dataclass + `__post_init__` 组装**：

- 每个组件字段都有默认值（`None`），不传则自动创建默认实例
- `__post_init__` 按严格顺序组装：Budget → Constraints → FeedbackLoop → Improvement → Thinker → Actor → Observer → Harness → Router
- 调用方可以精准替换任意组件而不影响其他部分

对比可选方案：
- 直接在 `Agent.create()` 中组装：工厂方法过长（已有 ~200 行），难以维护
- 用 DI 容器（如 `dependency-injector`）：引入额外依赖，对当前规模过重
- Builder 模式：需要额外维护 Builder 类，且 asyncio 下 Builder 的生命周期管理麻烦

## 解决什么问题？

1. **组装复杂度封装** — 组件间的依赖关系（比如 Think 需要 ContextWindowManager + PromptAssembler + KnowledgeSelector）对调用方透明
2. **组件可替换** — 任意组件可以注入自定义实现，不传则默认
3. **配置参数传递** — `max_steps` → `AgentBudget`，`max_context_tokens` → `ContextWindowManager`，`max_tool_result_length` → `Act`，全部自动路由
4. **双入口** — `run()` 直接执行，`run_with_routing()` 先路由再执行

## 在 Agent 流程中承担什么责任？

```
Agent.create() 传入配置参数
       ↓
AgentLoopRunner.__init__()
       ├── Budget         ← AgentBudget(max_steps=...)
       ├── Constraints    ← ConstraintSet()
       ├── FeedbackLoop   ← FeedbackLoop()
       ├── Improvement    ← ContinuousImprovement()
       ├── Thinker        ← Think(planner, context_manager, prompt_assembler)
       ├── Actor          ← Act(registry, executor, permission_guard, ...)
       ├── Observer       ← Observe(abort_on_tool_error, max_consecutive_errors)
       ├── Harness        ← AgentLoopHarness(thinker, actor, observer, budget, ..., lifecycle)
       └── Router         ← TaskRouter(planner)
              ↓
Agent.run(goal) → runner.run(goal) → harness.run(goal)
```

`AgentLoopRunner` 只负责组装，不负责执行。真正的循环在 `AgentLoopHarness` 中。

## 技术栈

- Python dataclass + `__post_init__`
- `TYPE_CHECKING` 避免循环导入
- `Optional[...] = None` 实现可选组件注入

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| `__post_init__` 中的组装顺序是隐式约定，无显式校验 | 引入 `AssemblyPlan` 显式声明组装 DAG |
| runner 跑完一次后不能复用（组件状态已污染） | 增加 `reset()` 方法重置所有有状态组件 |
| `run_with_routing()` 中拼接子目标结果的逻辑较简陋 | 子目标间增加结构化 context 传递（非简单字符串拼接） |
| `router` 依赖 `planner` 做 LLM 调用，路由本身需要 token | 轻量 router：用规则匹配 + 关键词判断替代 LLM 调用 |

## 使用案例

### 方式 1：通过 Agent.create()（推荐）

```python
from src.core.agents import Agent

agent = Agent.create(
    llm_api_key="sk-xxx",
    llm_provider="deepseek",
    max_steps=10,
    tool_areas=["database", "http"],
    enable_routing=True,
)

result = await agent.run("分析最近一周的订单数据并生成报告")
```

### 方式 2：直接使用 Runner（高级自定义）

```python
from src.core.agents.engine.runner import AgentLoopRunner
from src.core.agents.capabilities import SkillRegistry, SkillExecutor

async def my_planner(messages, step):
    response = await call_my_custom_llm(messages)
    return {"role": "assistant", "content": response}

runner = AgentLoopRunner(
    planner=my_planner,
    registry=SkillRegistry(),
    executor=SkillExecutor(),
    max_steps=5,
    max_consecutive_errors=2,
)

result = await runner.run(goal="分析这段代码的性能瓶颈")
```

### 方式 3：替换特定组件（预算 + 钩子）

```python
from src.core.agents.runtime.harness import AgentBudget, HarnessHook

budget = AgentBudget(max_steps=5, max_tool_calls=10, max_duration_seconds=60.0)

async def metrics_hook(event):
    if event.name == "step_end":
        print(f"[METRICS] step={event.state.step} tools={len(event.state.tool_calls)}")

runner = AgentLoopRunner(
    planner=my_planner,
    registry=registry,
    executor=executor,
    budget=budget,
    hooks=[metrics_hook],
)
```

### 方式 4：带路由执行

```python
result = await runner.run_with_routing(
    goal="检查数据库健康状态，分析慢查询原因，生成优化方案",
)

# TaskRouter 会将复杂目标拆成子目标顺序执行，最终合并结果
print(result.final_answer)
```
