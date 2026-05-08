# Agent 生命周期管理

> `src/core/agents/engine/lifecycle.py` — `LifecycleManager`
> `src/core/agents/state/snapshot.py` — `StateSnapshot`

---

## 为什么存在这个功能？

Agent 执行可能持续数分钟、数十步。如果没有外部控制机制，调用方只能"等它跑完或报错"。实际生产场景需要：

1. **暂停/恢复** — 维护窗口、人工审核、资源紧张时暂停 Agent
2. **优雅停止** — 取消 Agent 时不丢状态，能在当前 step 结束后安全退出
3. **快照持久化** — 暂停后保存状态，进程重启后可恢复，不丢失已完成的工作
4. **状态可查询** — 外部系统需要知道 Agent 当前是 IDLE / RUNNING / PAUSED / STOPPED / ERROR

## 为什么选这个设计？

**状态机 + asyncio.Event + JSON 快照**：

- `LifecycleManager` 是一个有限状态机（IDLE → RUNNING → PAUSED → RUNNING / STOPPED / ERROR → IDLE），`can_transition()` 验证每次状态转换的合法性
- `asyncio.Event` 实现暂停/恢复——`wait_if_paused()` 在 `_pause_event` 上 await，`pause()` 时 clear，`resume()` 时 set，零 CPU 开销
- `StateSnapshot` 用 JSON 文件持久化 `AgentLoopState` + `lifecycle_state` + `metadata`，文件按 `trace_id` 命名

对比可选方案：
- 信号量/semaphore：只能限制并发，不能表达状态转换
- 数据库存储快照：对单进程场景过重，JSON 文件更简单直接
- threading.Event：asyncio 中会阻塞事件循环，必须用 `asyncio.Event`

## 解决什么问题？

1. **Agent 可控性** — 跑起来的 Agent 不再"失控"，外部可以暂停、恢复、停止
2. **优雅终止** — Harness 在每步开始时检查 `is_stop_requested()`，不会在工具执行中途强制中断
3. **状态持久化** — pause → snapshot → 进程重启 → run_from_snapshot 形成闭环
4. **状态审计** — `get_history()` 返回完整的状态转换记录（from → to + reason + timestamp）

## 在 Agent 流程中承担什么责任？

```
Agent.run(goal)
  └── lifecycle.transition_to(RUNNING)

AgentLoopHarness.run() 主循环，每步开始时：
  ├── await lifecycle.wait_if_paused()     ← 如果是 PAUSED 状态，在此阻塞
  ├── if lifecycle.is_stop_requested():    ← 如果请求了停止
  │       state.stop_reason = USER_CANCELLED
  │       break
  └── 继续 Think → Act → Observe

Agent.pause()
  └── lifecycle.transition_to(PAUSED)      ← 外部调用，线程安全

Agent.save_snapshot(metadata)
  └── StateSnapshot.save(loop_state, lifecycle_state, metadata)

Agent.run_from_snapshot(snapshot_id)
  └── StateSnapshot.load(snapshot_id) → 恢复 loop_state + lifecycle_state → 继续执行
```

## 技术栈

- Python `asyncio.Event` — 零开销的暂停/恢复等待
- 有限状态机 — `can_transition()` 字典验证
- JSON 文件持久化 — `StateSnapshot.save()` / `load()`
- `Path.mkdir(parents=True, exist_ok=True)` — 自动创建快照目录

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| 快照是完整 JSON 序列化，对于大型 message history 可能很大 | 增量快照：只存与上一快照的 diff |
| 快照恢复不支持从中间某个 tool call 内部恢复 | 增加 checkpoint 粒度到 tool call 级别 |
| 状态机转换规则硬编码在字典中 | 改为可配置的 transition table，允许自定义状态 |
| `_current_loop_state` 用 `Optional[Any]` 类型 | 引入 TYPE_CHECKING 下的 proper type hint |
| 快照没有版本号 | 增加 schema version，防止未来 AgentLoopState 结构变更后旧快照不可读 |

## 使用案例

### 暂停-快照-恢复完整流程

```python
import asyncio
from src.core.agents import Agent

agent = Agent.create(llm_api_key="sk-xxx")
agent.set_snapshot_dir("./snapshots")

# 在后台运行 Agent
async def run_agent():
    return await agent.run("分析过去一周的数据库慢查询")

task = asyncio.create_task(run_agent())

# 5 秒后暂停并保存快照
await asyncio.sleep(5)
agent.pause()
snapshot_id = agent.save_snapshot({"reason": "需要人工确认分析方向"})
print(f"快照已保存: {snapshot_id}")

# 确认后恢复
agent.resume()
result = await task
```

### 从快照恢复（进程重启后）

```python
agent = Agent.create(llm_api_key="sk-xxx")
agent.set_snapshot_dir("./snapshots")

# 从之前的快照继续执行
result = await agent.run_from_snapshot(
    snapshot_id="agent-a1b2c3d4-20260507-001",
)
print(f"从快照恢复后完成: {result.final_answer}")
```

### 监控 Agent 状态

```python
agent = Agent.create(llm_api_key="sk-xxx")

# 轮询状态（可从另一个协程/线程调用）
while agent.is_running:
    await asyncio.sleep(1)
    print(f"状态: {agent.lifecycle_state}")

if agent.is_paused:
    print("Agent 已暂停，等待外部决策...")
    agent.resume()
```

### 优雅停止

```python
agent = Agent.create(llm_api_key="sk-xxx")

async def run_with_timeout():
    task = asyncio.create_task(agent.run("长时间任务"))
    await asyncio.sleep(30)
    agent.stop()  # 在当前 step 完成后停止
    return await task

result = await run_with_timeout()
print(f"停止原因: {result.stop_reason}")  # USER_CANCELLED
```
