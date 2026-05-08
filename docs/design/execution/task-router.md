# Task Router — 任务复杂度评估与分解

> `src/core/agents/execution/router.py` — `TaskRouter`

---

## 为什么存在这个功能？

用户提交的 goal 可能很简单（"查今天的订单数"），也可能很复杂（"分析数据库性能问题，检查慢查询日志，生成优化报告"）。

复杂任务如果直接进入 Think-Act-Observe 循环：
- LLM 需要在第一步同时完成规划 + 执行，容易迷失方向
- 长链路目标难以维护——执行到第 5 步时可能忘了原始目标
- 错误传播——某个子目标失败会影响所有后续步骤

提前做一次复杂度评估，把复杂任务拆成顺序子目标逐个执行，可以显著提高成功率。

## 为什么选这个设计？

**LLM 单次路由 + 顺序子目标执行**：

- `TaskRouter.route(goal)` 用同一个 planner 发一次轻量请求，要求返回 `{"type": "simple"}` 或 `{"type": "complex", "sub_goals": [...]}`
- `run_with_routing()` 判断：simple → 直接 run(goal)；complex → 顺序执行每个 sub_goal
- 前一个子目标的结果通过 system message 传给后一个子目标
- 任一子目标失败则立即返回失败

对比可选方案：
- 预定义模板匹配：不够灵活，无法应对未预见的复杂任务类型
- 完全静态拆分：需要人工定义所有复杂任务的拆解规则，不可扩展
- 递归拆分：过度设计，子目标的子目标在当前阶段不需要

## 解决什么问题？

1. **复杂任务结构化拆解** — 一次规划，顺序执行
2. **子目标间上下文传递** — 后续子目标可以引用前面的结果
3. **失败快速返回** — 中间子目标失败不浪费后续步骤
4. **可选功能** — `enable_routing=True` 才启用，默认关闭（零开销）

## 在 Agent 流程中承担什么责任？

```
Agent.run(goal)
  │
  ├─ if config.enable_routing:
  │     return runner.run_with_routing(goal, ...)
  │
  └─ else:
        return runner.run(goal, ...)  ← 直接执行

run_with_routing(goal, messages, metadata, trace_id):
  │
  ├─ sub_goals = await router.route(goal)
  │
  ├─ if len(sub_goals) <= 1:
  │     return run(goal, ...)  ← 简单任务，直接执行
  │
  └─ for each sub_goal:
       ├─ 构造增强消息（前序结果 + 当前子目标）
       ├─ result = run(sub_goal, enhanced_messages, ...)
       ├─ 累积结果和消息
       └─ if not result.success: return result  ← 失败立即返回
  │
  └─ 拼接所有 final_answer → AgentLoopResult
```

## 路由协议

```json
// 简单任务
{"type": "simple"}

// 复杂任务
{
  "type": "complex",
  "sub_goals": [
    "检查数据库连接状态",
    "分析慢查询日志，找出耗时最长的 5 条",
    "针对慢查询生成优化方案"
  ]
}
```

## 技术栈

- Python dataclass
- 复用 Think 阶段的 `planner`（`AssistantPlanner`），无额外 LLM 依赖
- JSON 解析 + 容错（非法 JSON → 回退到 `[goal]`）

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| Router 自身消耗 token（一次 LLM 调用） | 简单任务用规则匹配（如 goal 长度 < 50 字符 → 直接 simple）替代 LLM |
| 只支持顺序子目标，不支持并行 | 增加 `strategy: "parallel"` 支持子目标并行执行 |
| 子目标间只传递文本结果 | 结构化传递（JSON 输出 → 下一个子目标的输入参数） |
| Router 的 planner 与主 LLM 是同一个 provider | 允许指定独立的轻量模型做路由（如 gpt-3.5 → gpt-4 执行） |

## 使用案例

### 启用路由

```python
agent = Agent.create(
    llm_api_key="sk-xxx",
    enable_routing=True,  # 启用任务路由
    max_steps=15,         # 复杂任务需要更多步骤
)

result = await agent.run("分析数据库性能问题并生成优化报告")
# Router 会将该复杂任务拆成子目标，逐个执行，最后拼接报告
```

### 运行结果示例

```python
# 复杂任务：
# goal: "检查数据库健康 + 分析慢查询 + 生成优化方案"
# Router 输出: ["检查数据库连接和基本健康状态",
#              "分析慢查询日志找出瓶颈",
#              "生成优化方案和配置建议"]

# 执行过程：
# Step 1-3: 子目标1 → 结果: "数据库连接正常，QPS 稳定"
# Step 4-8: 子目标2 → 结果: "发现 3 条慢查询 > 2s"
# Step 9-12: 子目标3 → 结果: "建议添加索引 idx_orders_status"

# 最终 result.final_answer 包含三个子目标的完整输出
```

### 回退机制

```python
# Router 返回 JSON 解析失败 → 回退到原始 goal
# 子目标数 <= 1 → 等价于直接 run(goal)
# 这些情况下行为完全等同于 enable_routing=False
```
