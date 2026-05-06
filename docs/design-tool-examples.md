# Tool Examples & Structured Output

> Improve LLM tool calling accuracy with usage examples and standardized output format.

## 背景 (Background)

LLM 在调用工具时经常猜错参数格式，尤其是：
- 不确定参数应该是字符串还是数组
- 不知道日期格式要求
- 不清楚返回值的结构

提供 examples 是最直接的解决方案——比长篇描述更有效。同时，统一的输出格式让 LLM 更容易解析结果并做出下一步决策。

## 设计 (Design)

### Examples 机制

#### 定义

在 `@skill` 装饰器中声明 examples：

```python
@skill(
    name="task_query_status",
    examples=[
        {
            "input": {"trace_id": "Agent-20260430-abc123"},
            "output": "返回任务完整信息（状态、时间、数据等）"
        },
    ],
    ...
)
```

#### 序列化

Examples 追加到 tool spec 的 description 字段中：

```
从 MySQL 数据库查询数据，返回多行结果。仅支持 SELECT 语句。

Examples:
  Input: {"query": "SELECT * FROM task_manager WHERE trace_id = %s", "params": ["Agent-20260430-abc"]}
  Output: 返回匹配的任务记录列表
```

这样 LLM 在看到工具描述时就能理解正确的调用方式。

### ToolOutput 结构化输出

#### 定义

```python
@dataclass
class ToolOutput:
    success: bool
    data: Any = None
    message: str = ""
    row_count: Optional[int] = None

    def serialize(self) -> str: ...

    @classmethod
    def ok(cls, data, message="", row_count=None) -> "ToolOutput": ...

    @classmethod
    def error(cls, message: str) -> "ToolOutput": ...
```

#### 使用方式

工具可以返回 ToolOutput（推荐）或原始类型（向后兼容）：

```python
# 推荐
return ToolOutput.ok(data=rows, row_count=len(rows))

# 仍然支持
return rows
```

#### 序列化集成

`serialize_content()` 通过 duck typing 识别 ToolOutput：

```python
def serialize_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if hasattr(value, "serialize") and callable(value.serialize):
        return value.serialize()
    return json.dumps(value, ensure_ascii=False, default=str)
```

### 配置项

| 参数 | 位置 | 说明 |
|------|------|------|
| `examples` | `@skill()` 装饰器 | 工具调用示例列表 |
| `examples` | `Skill` model | `List[Dict[str, Any]]` 字段 |

### 影响范围

| 文件 | 改动 |
|------|------|
| `src/core/agents/skills/model.py` | 新增 `examples` 字段 |
| `src/core/agents/skills/registry.py` | `@skill` 支持 `examples` 参数 |
| `src/core/agents/skills/serializer.py` | 序列化时注入 examples 到 description |
| `src/core/agents/skills/output.py` | 新建，ToolOutput 实现 |
| `src/core/agents/loop/messages.py` | `serialize_content` 识别 ToolOutput |
| 所有 agentic_tools | 添加 examples 声明 |

## 向后兼容 (Backward Compatibility)

- `examples` 默认为空列表，不传则 description 不变
- 工具仍可返回 str/dict/list，ToolOutput 是可选的增强
- `serialize_content` 对非 ToolOutput 类型保持原有行为

## 测试策略 (Testing)

1. 有 examples 的工具 → tool spec description 包含 Examples 段
2. 无 examples 的工具 → description 不变
3. ToolOutput.ok() → serialize 输出包含 data
4. ToolOutput.error() → serialize 输出包含 [ERROR] 前缀
5. serialize_content 正确处理 ToolOutput 对象
6. serialize_content 对 str/dict/list 行为不变
