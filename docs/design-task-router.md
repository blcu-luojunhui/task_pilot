# Task Router

> Assess task complexity before the main loop and decompose complex goals into sequential sub-goals.

## 背景 (Background)

当前 agent loop 对所有任务一视同仁：用户 goal 直接进入 Think→Act→Observe。对于复杂任务，这会让 LLM：
- 在单轮中同时规划和执行，容易迷失
- 不擅长维护长链路目标
- 把复杂任务拆解责任压在每一步临场发挥上

TaskRouter 提前做一次复杂度评估，把复杂任务拆成顺序子目标。

## 设计 (Design)

### 核心组件

```python
@dataclass
class TaskRouter:
    planner: AssistantPlanner
    enabled: bool = True

    async def route(self, goal: str) -> List[str]:
        ...
```

### 路由协议

Router 使用同一个 planner 发一次轻量请求，要求仅返回 JSON：

- 简单任务：`{"type": "simple"}`
- 复杂任务：`{"type": "complex", "sub_goals": ["...", "..."]}`

### 执行方式

`AgentLoopRunner.run_with_routing()`：
1. 调 `router.route(goal)`
2. simple → 直接 `run(goal)`
3. complex → 顺序执行每个 sub_goal
4. 前一个子目标结果通过 system message 传给后一个子目标
5. 最终将所有 sub-goal 的 `final_answer` 拼接为总答案

### 影响范围

| 文件 | 改动 |
|------|------|
| `src/core/agents/loop/router.py` | 新建 TaskRouter |
| `src/core/agents/loop/runner.py` | 新增 router 字段和 `run_with_routing()` |
| `src/core/agents/loop/__init__.py` | 导出 TaskRouter |

## 向后兼容 (Backward Compatibility)

- 原有 `run()` 完全不变
- 新增 `run_with_routing()` 作为可选入口
- `router=None` 时退化为普通 run
- Router 解析失败时直接回退到 `[goal]`

## 测试策略 (Testing)

1. Router 返回 simple → run_with_routing() 行为与 run() 一致
2. Router 返回 complex → 顺序执行多个 sub_goal
3. Router 返回非法 JSON → 回退到原 goal
4. 任一 sub_goal 失败 → 立即返回失败结果
