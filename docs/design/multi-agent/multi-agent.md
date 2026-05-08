# Multi-Agent — 多 Agent 协作系统

> `src/core/agents/multi_agent/protocol.py` — `Message`, `MessageType`, `MessagePriority`
> `src/core/agents/multi_agent/bus.py` — `MessageBus`
> `src/core/agents/multi_agent/coordinator.py` — `MultiAgentCoordinator`, `TaskAssignment`

---

## 为什么存在这个功能？

单个 Agent 可以处理大部分任务，但有些场景需要多 Agent 协作：

1. **任务并行化** — 一个复杂分析任务拆成多个子任务，分配给不同 Agent 并行执行
2. **专业化分工** — 不同 Agent 具有不同的工具和知识（数据库 Agent、HTTP Agent、代码分析 Agent）
3. **结果聚合** — 多个 Agent 各自产出部分结果，需要一个协调器汇总

## 为什么选这个设计？

**消息总线 + 协调器 + 消息协议**：

- `Message` — 统一的消息格式，包含 7 种类型（REQUEST/RESPONSE/BROADCAST/NOTIFICATION/TASK/RESULT/HEARTBEAT）和 4 级优先级
- `MessageBus` — 异步 pub/sub 总线，每个 Agent 有独立的 `asyncio.Queue`，支持 TTL、历史记录、统计
- `MultiAgentCoordinator` — 负责任务分解、Agent 分配、并行/串行/动态执行、结果聚合

Agent 之间不直接调用方法，而是通过消息总线通信——这是与单 Agent 最大的架构差异。

对比可选方案：
- Agent 直接引用调用方法：紧耦合，无法跨进程，Agent 故障会级联
- 共享数据库做状态同步：增加 DB 负载，延迟高
- 用 Ray/Actor 模型：引入重依赖，当前阶段不必要

## 解决什么问题？

1. **任务并行化** — 协调器可以将子目标分配给多个 Agent 并行执行
2. **Agent 解耦** — Agent 之间通过消息通信，不依赖彼此的实现细节
3. **执行策略灵活** — sequential（顺序）/ parallel（并行）/ dynamic（动态依赖图）
4. **可观测** — MessageBus 提供历史记录和统计，可追踪整个协作过程

## 在 Agent 流程中承担什么责任？

```
用户调用 MultiAgentCoordinator.coordinate(task)
  │
  ├─ decompose(task) → sub_tasks
  │    └─ 按任务类型拆解（当前：简单 LLM 拆解）
  │
  ├─ 创建 TaskAssignment（每个 sub_task 一个）
  │
  ├─ execute(strategy, assignments):
  │    ├─ "sequential": 顺序执行每个 assignment，上一个结果作为下一个的 context
  │    ├─ "parallel":   asyncio.gather 并行执行所有
  │    └─ "dynamic":    依赖图调度（stub，当前退化为 parallel）
  │
  ├─ aggregate(results) → 合并所有 Agent 的输出
  │
  └─ 返回汇总结果

每个 Agent 通过 MessageBus 通信：
  ├─ bus.register_agent(agent_id)
  ├─ bus.send(Message(type=TASK, ...))
  ├─ bus.receive(agent_id)
  └─ bus.subscribe(RESULT, handler)
```

## 核心数据模型

### MessageType（7 种）

| 类型 | 用途 |
|------|------|
| `REQUEST` | 请求另一个 Agent 执行操作 |
| `RESPONSE` | 对 REQUEST 的回复 |
| `BROADCAST` | 广播给所有 Agent |
| `NOTIFICATION` | 单向通知（无需回复） |
| `TASK` | Coordinator 分发的任务 |
| `RESULT` | 任务执行结果 |
| `HEARTBEAT` | Agent 存活检测 |

### MessagePriority（4 级）

| 级别 | 数值 | 用途 |
|------|------|------|
| `LOW` | 0 | 普通通知 |
| `NORMAL` | 1 | 常规任务 |
| `HIGH` | 2 | 重要结果 |
| `URGENT` | 3 | 紧急消息（如取消、错误） |

### Message

```python
@dataclass
class Message:
    msg_id: str
    msg_type: MessageType
    sender: str
    receiver: str               # broadcast 为空
    content: Any
    priority: MessagePriority
    ttl_seconds: float = 300
    correlation_id: Optional[str] = None  # 关联的原始消息
    parent_trace_id: Optional[str] = None # 父任务 trace_id
    metadata: dict = {}
```

## 技术栈

- Python asyncio（Queue、gather）
- `asyncio.Queue` 做 Agent 消息队列
- TTL 过期检测
- JSON 序列化（`to_dict()` / `from_dict()`）

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| `_handle_heartbeat` 只打 log，无超时检测 | 实现心跳超时 → 自动重分配任务 |
| `_handle_result` 只打 log，无异步回调 | 实现 Promise 风格的回调机制 |
| `_execute_dynamic` 退化为 parallel | 实现基于拓扑排序的 DAG 调度 |
| 无 Agent 健康检查 | 心跳丢失 N 次后标记 Agent 为不可用 |
| 无跨进程消息总线 | 抽象 MessageBus 接口，支持 Redis/RabbitMQ 实现 |
| `decompose()` 用 LLM 拆解，消耗 token | 小任务用规则匹配，大任务用 LLM |

## 使用案例

### 基础多 Agent 协作

```python
from src.core.agents import Agent, MultiAgentCoordinator

# 创建专业化 Agent
db_agent = Agent.create(
    llm_api_key="sk-xxx",
    tool_areas=["database"],
)

http_agent = Agent.create(
    llm_api_key="sk-xxx",
    tool_areas=["http"],
)

# 创建协调器
coordinator = MultiAgentCoordinator()
coordinator.register_agent("db_expert", db_agent)
coordinator.register_agent("http_expert", http_agent)

# 分配任务
result = await coordinator.coordinate(
    task="查询用户数据库中的活跃用户，并检查他们的 API 访问权限",
    strategy="sequential",  # 先查 DB，再查 API
    context={"db_table": "users", "api_endpoint": "https://api.example.com/verify"},
)

print(f"协调结果: {result}")
```

### 并行执行

```python
result = await coordinator.coordinate(
    task="同时查询订单数据和用户数据",
    strategy="parallel",  # 两个 Agent 同时执行
    context={},
)
```

### 使用 MessageBus 直接通信

```python
from src.core.agents.multi_agent import MessageBus, Message, MessageType, MessagePriority

bus = MessageBus()
bus.register_agent("agent_a")
bus.register_agent("agent_b")

# 发送消息
await bus.send(Message(
    msg_id="msg-001",
    msg_type=MessageType.REQUEST,
    sender="agent_a",
    receiver="agent_b",
    content={"action": "fetch_data", "params": {"table": "orders"}},
    priority=MessagePriority.HIGH,
))

# 接收消息
msg = await bus.receive("agent_b", timeout=5.0)
if msg:
    print(f"收到: {msg.msg_type} from {msg.sender}: {msg.content}")
    reply = msg.reply(content={"data": [1, 2, 3]})
    await bus.send(reply)

# 查看消息历史
history = bus.get_history("agent_a", message_type=MessageType.RESPONSE, limit=10)

# 查看总线统计
stats = bus.get_stats()
print(f"已发送: {stats['messages_sent']}, 活跃 Agent: {stats['active_agents']}")
```

### 订阅消息类型

```python
async def handle_task(message: Message):
    print(f"收到任务: {message.content}")
    # 执行任务...
    result_msg = Message(
        msg_id="result-001",
        msg_type=MessageType.RESULT,
        sender="agent_b",
        receiver=message.sender,
        content={"status": "done"},
        priority=MessagePriority.NORMAL,
        correlation_id=message.msg_id,
    )
    await bus.send(result_msg)

bus.subscribe(MessageType.TASK, handle_task)
```
