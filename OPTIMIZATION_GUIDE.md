# Agent 系统优化实现指南

本文档说明如何使用新实现的三大优化功能。

## 1️⃣ LLM 抽象层 - 支持多种 LLM

### 基本使用

```python
from src.core.agents import Agent

# 使用 OpenAI
agent = Agent.create(
    llm_provider="openai",
    llm_api_key="sk-...",
    llm_model="gpt-4",
    tool_areas=["database", "http"]
)

# 使用 Claude
agent = Agent.create(
    llm_provider="claude",
    llm_api_key="sk-ant-...",
    llm_model="claude-3-opus-20240229"
)

# 使用 DeepSeek（默认）
agent = Agent.create(
    llm_provider="deepseek",
    llm_api_key="your-key"
)
```

### 直接使用 Provider

```python
from src.core.agents.capabilities.llm.base import LLMConfig, LLMMessage
from src.core.agents.capabilities.llm.providers import OpenAIProvider

# 创建配置
config = LLMConfig(
    api_key="sk-...",
    model="gpt-4",
    temperature=0.7
)

# 创建 Provider
provider = OpenAIProvider(config)

# 发送请求
messages = [
    LLMMessage(role="system", content="You are a helpful assistant"),
    LLMMessage(role="user", content="Hello!")
]

response = await provider.chat(messages)
print(response.content)

# 流式响应
async for chunk in provider.stream_chat(messages):
    print(chunk, end="", flush=True)
```

### 自定义 Provider

```python
from src.core.agents.capabilities.llm.base import LLMProvider, LLMResponse

class CustomProvider(LLMProvider):
    async def chat(self, messages, tools=None, **kwargs) -> LLMResponse:
        # 实现你的 LLM 调用逻辑
        pass
    
    async def stream_chat(self, messages, tools=None, **kwargs):
        # 实现流式响应
        pass
    
    @property
    def name(self) -> str:
        return "custom"
    
    @property
    def supports_tools(self) -> bool:
        return True
    
    @property
    def supports_streaming(self) -> bool:
        return True
```

---

## 2️⃣ Agent 生命周期管理

### 基本控制

```python
from src.core.agents import Agent
import asyncio

# 创建 Agent
agent = Agent.create(llm_api_key="...")

# 在后台运行
task = asyncio.create_task(agent.run("复杂任务"))

# 暂停
await asyncio.sleep(5)
agent.pause()
print(f"Agent 状态: {agent.state}")  # PAUSED

# 恢复
await asyncio.sleep(2)
agent.resume()

# 停止
agent.stop()

# 等待完成
result = await task
```

### 状态监听

```python
def on_state_change(old_state, new_state):
    print(f"状态变化: {old_state} → {new_state}")

agent.lifecycle.on_state_change(on_state_change)
```

### 状态快照

```python
from pathlib import Path
from src.core.agents.state.snapshot import StateSnapshot

# 创建快照管理器
snapshot = StateSnapshot(Path(".snapshots"))

# 保存状态
snapshot_id = snapshot.save(
    agent_id="agent_001",
    loop_state=agent._runner.current_state,
    lifecycle_state=agent.state,
    metadata={"note": "checkpoint before critical operation"}
)

print(f"Snapshot saved: {snapshot_id}")

# 列出快照
snapshots = snapshot.list_snapshots(agent_id="agent_001")
for snap in snapshots:
    print(f"{snap['snapshot_id']}: {snap['goal']} (step {snap['step']})")

# 恢复状态
loop_state, lifecycle_state, metadata = snapshot.load(snapshot_id)
print(f"Restored to step {loop_state.step}")

# 删除快照
snapshot.delete(snapshot_id)
```

### 在执行循环中使用

```python
# 执行循环会自动检查生命周期状态
# 如果暂停，会等待恢复
# 如果停止，会立即退出

result = await agent.run("长时间任务")
```

---

## 3️⃣ Agent 间通信机制

### 基本通信

```python
from src.core.agents.multi_agent import MessageBus, Message, MessageType

# 创建消息总线
bus = MessageBus()

# 注册 Agent
queue_a = bus.register_agent("agent_a")
queue_b = bus.register_agent("agent_b")

# Agent A 发送消息给 Agent B
message = Message(
    type=MessageType.REQUEST,
    sender="agent_a",
    receiver="agent_b",
    content="请帮我查询数据库"
)
await bus.send(message)

# Agent B 接收消息
received = await bus.receive("agent_b")
print(f"收到消息: {received.content}")

# Agent B 回复
reply = received.reply(content="查询结果：...")
await bus.send(reply)

# Agent A 接收回复
response = await bus.receive("agent_a")
print(f"收到回复: {response.content}")
```

### 广播消息

```python
# 广播给所有 Agent
broadcast = Message(
    type=MessageType.BROADCAST,
    sender="agent_a",
    receiver="*",  # "*" 表示广播
    content="系统通知：任务已完成"
)
await bus.send(broadcast)
```

### 订阅消息类型

```python
async def handle_task(message: Message):
    print(f"收到任务: {message.content}")
    # 处理任务...

# 订阅 TASK 类型的消息
bus.subscribe(MessageType.TASK, handle_task)
```

### 多 Agent 协调

```python
from src.core.agents import Agent
from src.core.agents.multi_agent import MultiAgentCoordinator

# 创建协调器
coordinator = MultiAgentCoordinator()

# 创建并注册多个 Agent
agent1 = Agent.create(llm_api_key="...", tool_areas=["database"])
agent2 = Agent.create(llm_api_key="...", tool_areas=["http"])
agent3 = Agent.create(llm_api_key="...", tool_areas=["file"])

coordinator.register_agent("db_agent", agent1)
coordinator.register_agent("http_agent", agent2)
coordinator.register_agent("file_agent", agent3)

# 协调执行复杂任务
result = await coordinator.coordinate(
    task="分析用户数据并生成报告",
    strategy="parallel"  # parallel, sequential, dynamic
)

print(f"完成任务: {result['completed']}/{result['total_tasks']}")
print(f"成功率: {result['success_rate']:.2%}")

for task_result in result['results']:
    print(f"- {task_result['task']}: {task_result['status']}")
```

### 查看统计信息

```python
# 消息总线统计
stats = bus.get_stats()
print(f"总消息数: {stats['total_messages']}")
print(f"活跃 Agent: {stats['active_agents']}")

# 协调器状态
status = coordinator.get_status()
print(f"注册的 Agent: {status['agents']}")
print(f"活跃任务: {status['active_tasks']}")
print(f"完成任务: {status['completed_tasks']}")
```

---

## 完整示例

### 示例 1: 使用不同 LLM 的 Agent

```python
import asyncio
from src.core.agents import Agent

async def main():
    # 创建使用 OpenAI 的 Agent
    openai_agent = Agent.create(
        llm_provider="openai",
        llm_api_key="sk-...",
        llm_model="gpt-4"
    )
    
    # 创建使用 Claude 的 Agent
    claude_agent = Agent.create(
        llm_provider="claude",
        llm_api_key="sk-ant-...",
        llm_model="claude-3-opus-20240229"
    )
    
    # 同时运行
    results = await asyncio.gather(
        openai_agent.run("分析这段代码"),
        claude_agent.run("生成测试用例")
    )
    
    print("OpenAI 结果:", results[0].final_answer)
    print("Claude 结果:", results[1].final_answer)

asyncio.run(main())
```

### 示例 2: 可暂停的长时间任务

```python
import asyncio
from src.core.agents import Agent

async def main():
    agent = Agent.create(llm_api_key="...")
    
    # 启动任务
    task = asyncio.create_task(agent.run("处理大量数据"))
    
    # 5秒后暂停
    await asyncio.sleep(5)
    agent.pause()
    print("任务已暂停")
    
    # 保存快照
    from pathlib import Path
    from src.core.agents.state.snapshot import StateSnapshot
    
    snapshot = StateSnapshot(Path(".snapshots"))
    snapshot_id = snapshot.save(
        agent_id="agent_001",
        loop_state=agent._runner.current_state,
        lifecycle_state=agent.state
    )
    print(f"快照已保存: {snapshot_id}")
    
    # 2秒后恢复
    await asyncio.sleep(2)
    agent.resume()
    print("任务已恢复")
    
    # 等待完成
    result = await task
    print("任务完成:", result.final_answer)

asyncio.run(main())
```

### 示例 3: 多 Agent 协作

```python
import asyncio
from src.core.agents import Agent
from src.core.agents.multi_agent import MultiAgentCoordinator

async def main():
    # 创建协调器
    coordinator = MultiAgentCoordinator()
    
    # 创建专门的 Agent
    db_agent = Agent.create(
        llm_api_key="...",
        tool_areas=["database"]
    )
    
    api_agent = Agent.create(
        llm_api_key="...",
        tool_areas=["http"]
    )
    
    analysis_agent = Agent.create(
        llm_api_key="..."
    )
    
    # 注册 Agent
    coordinator.register_agent("database", db_agent)
    coordinator.register_agent("api", api_agent)
    coordinator.register_agent("analysis", analysis_agent)
    
    # 执行复杂任务
    result = await coordinator.coordinate(
        task="""
        1. 从数据库查询用户数据
        2. 调用 API 获取额外信息
        3. 分析数据并生成报告
        """,
        strategy="sequential"  # 顺序执行
    )
    
    # 查看结果
    print(f"任务完成率: {result['success_rate']:.2%}")
    
    for task_result in result['results']:
        print(f"\n任务: {task_result['task']}")
        print(f"Agent: {task_result['agent_id']}")
        print(f"状态: {task_result['status']}")
        print(f"结果: {task_result['result']}")

asyncio.run(main())
```

---

## 注意事项

1. **LLM Provider**
   - 确保 API Key 正确
   - 注意不同 Provider 的速率限制
   - Claude 需要设置 max_tokens

2. **生命周期管理**
   - pause/resume 只在任务运行时有效
   - 快照会保存完整状态，注意存储空间
   - 状态转换必须遵循规则

3. **多 Agent 通信**
   - 消息总线是内存中的，重启会丢失
   - 注意消息的 TTL 设置
   - 协调器会自动处理任务分配

---

## 下一步

1. 实现更多 LLM Provider（Gemini, Llama, etc.）
2. 增强任务分解算法
3. 实现基于依赖的动态调度
4. 添加消息持久化
5. 实现 Agent 发现机制
