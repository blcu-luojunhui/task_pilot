# Memory 系统 — 短期与长期记忆

> `src/core/agents/state/memory/short_term.py` — `ShortTermMemory`
> `src/core/agents/state/memory/long_term.py` — `LongTermMemory`, `MemoryEntry`

---

## 为什么存在这个功能？

Agent 在单次 run 中通过 `state.messages` 维护会话上下文，但这有两个局限：

1. **跨会话记忆** — 一个 Agent 这次查询了"张三的订单"，下次再问"他的最近订单"时不知道该用哪些表、哪些字段。长期记忆可以记住：数据库 schema、常用查询模式、用户偏好等
2. **运行内结构化记忆** — `state.messages` 是混杂的，短期记忆提供结构化的工具结果缓存、关键事实提取

如果没有记忆系统，每次 Agent 执行都是"失忆的"——即使之前的执行发现了一些重要信息，也无法在后续执行中复用。

## 为什么选这个设计？

**ShortTermMemory + LongTermMemory 两层架构**：

- `ShortTermMemory`：会话级，内存字典存储消息列表、tool results 缓存、提取的事实。随 run 结束而销毁
- `LongTermMemory`：跨会话，JSON 文件持久化 `MemoryEntry` 列表，支持 CRUD、按 key 查询、按时间排序

对比可选方案：
- 向量数据库（Chroma/Pinecone）：可以做语义检索但增加外部依赖，当前阶段先做简单键值存储
- 全放 state.messages：格式不统一，难以检索
- Redis：增加运维负担，JSON 文件对单进程足够

## 解决什么问题？

1. **跨会话知识复用** — Agent 可以记住上次发现的 schema、规则、最佳实践
2. **结构化缓存** — Tool results 可以按 target 缓存，同一 run 内避免重复查询
3. **事实提取** — 从对话中提取关键事实单独存储，后续参考

## 在 Agent 流程中承担什么责任？

```
Think 阶段（当前未集成，设计预留）：
  └─ PromptAssembler 可以调用 memory.recall(goal) 注入相关记忆

Act 阶段（当前未集成，设计预留）：
  └─ tool 执行后可以调用 memory.save(key, result) 缓存结果

Agent 运行结束后（设计预留）：
  └─ 从 AgentLoopResult 提取关键信息存入 LongTermMemory
```

当前 Memory 系统已实现但**未接入主 Think/Act/Observe 链路**。它们被设计为可选组件，由调用方在自定义场景中使用。

## 核心数据模型

### ShortTermMemory

```python
class ShortTermMemory:
    def add_message(self, role: str, content: str) -> None
    def add_tool_result(self, tool_name: str, result: Any) -> None
    def get_tool_results(self, tool_name: str) -> List[Any]
    def extract_facts(self, pattern: str) -> List[str]
    def clear(self) -> None
```

### LongTermMemory

```python
class LongTermMemory:
    def __init__(self, storage_dir: str)
    def save(self, key: str, content: Any, metadata: dict) -> MemoryEntry
    def load(self, key: str) -> Optional[MemoryEntry]
    def search(self, query: str) -> List[MemoryEntry]  # 关键词匹配
    def list_recent(self, limit: int = 10) -> List[MemoryEntry]
    def delete(self, key: str) -> bool
```

### MemoryEntry

```python
@dataclass
class MemoryEntry:
    key: str
    content: Any
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    importance: float = 0.0   # 重要性评分
    access_count: int = 0     # 访问次数
```

## 技术栈

- Python dataclass + JSON 文件存储
- `datetime` 时间戳
- 关键词匹配搜索

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| 未接入主链路 | 在 PromptAssembler.assemble() 中集成 memory.recall() |
| long_term 是 flat key-value JSON，无语义检索 | 接入 embedding + 向量相似度搜索 |
| 记忆召回无排序策略 | 按重要性 + 时间衰减 + 访问频率排序 |
| 无记忆淘汰/TTL | 增加 max_entries + LRU 淘汰 |
| JSON 文件不适合高并发写入 | 小数据量 OK，大数据量改 SQLite |

## 使用案例

### ShortTermMemory — 会话内缓存

```python
from src.core.agents.state.memory import ShortTermMemory

memory = ShortTermMemory()

# 缓存工具结果
memory.add_tool_result(
    tool_name="db_query",
    result={"table": "orders", "row_count": 1500}
)

# 后续查询直接读缓存
cached = memory.get_tool_results("db_query")

# 添加消息
memory.add_message("user", "帮我查一下订单数据")
memory.add_message("assistant", "好的，我来查询")

# 从对话中提取关键事实
facts = memory.extract_facts(r"订单.*?(\d+)")
```

### LongTermMemory — 跨会话持久化

```python
from src.core.agents.state.memory import LongTermMemory

memory = LongTermMemory("./data/memory/")

# 保存记忆
memory.save(
    key="db_schema_orders",
    content={"table": "orders", "columns": ["id", "user_id", "amount", "status"]},
    metadata={"domain": "database", "importance": 0.8},
)

# 读取记忆
entry = memory.load("db_schema_orders")
if entry:
    print(f"上次更新: {entry.updated_at}")
    print(f"访问次数: {entry.access_count}")

# 搜索记忆（关键词匹配）
results = memory.search("orders database")
for r in results:
    print(f"  {r.key}: {r.content}")

# 列出最近记忆
recent = memory.list_recent(limit=5)
```

### 自定义集成（在 hook 中保存分析结果）

```python
from src.core.agents.state.memory import LongTermMemory

long_term = LongTermMemory("./data/memory/")

async def save_analysis_to_memory(event):
    if event.name == "run_end":
        result = event.payload.get("result")
        if result and result.success:
            # 将分析结果持久化到长期记忆
            long_term.save(
                key=f"analysis_{result.trace_id}",
                content={
                    "goal": event.state.goal,
                    "final_answer": result.final_answer,
                    "tool_calls_count": result.tool_calls_count,
                },
                metadata={"success": True, "steps": result.total_steps},
            )

runner = AgentLoopRunner(..., hooks=[save_analysis_to_memory])
```

### 记忆召回策略示例（设计参考）

```python
# 未来接入后的预期行为
def recall_memories(query: str, memory: LongTermMemory) -> str:
    """召回最相关的记忆用作 prompt 补充"""
    entries = memory.search(query)
    # 按 importance * time_decay * access_frequency 排序
    entries.sort(
        key=lambda e: e.importance * (0.9 ** e.days_since_update()) * e.access_count,
        reverse=True,
    )
    # 返回前 3 条，控制在 500 tokens 内
    return "\n".join(str(e.content)[:150] for e in entries[:3])
```
