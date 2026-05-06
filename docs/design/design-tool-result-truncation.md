# Tool Result Truncation

> Prevent oversized tool outputs from consuming excessive context window tokens.

## 背景 (Background)

Agent 在执行工具时（如数据库查询、HTTP 请求），工具可能返回大量数据（几千行查询结果、完整 HTML 页面等）。这些数据直接塞入消息历史会：

1. 浪费 LLM context window 的宝贵空间
2. 增加 API 调用成本（按 token 计费）
3. 可能导致超出模型 context limit 而报错
4. LLM 通常只需要前几百字符就能理解工具执行结果

参考 Claude Code 的做法：对 tool result 设置最大长度，超出部分截断并告知 LLM 结果被截断。

## 设计 (Design)

### 核心逻辑

在 `Act` 阶段，工具执行成功后、构建 tool result message 之前，对输出内容做长度检查和截断。

```python
def _truncate_output(self, content: str) -> str:
    """Truncate tool output if it exceeds max length."""
    if not content or len(content) <= self.max_tool_result_length:
        return content
    truncated = content[: self.max_tool_result_length]
    return (
        f"{truncated}\n\n"
        f"[...truncated, showing first {self.max_tool_result_length} chars "
        f"of {len(content)} total]"
    )
```

截断发生在 `_execute_one` 的成功路径中，对序列化后的 output 字符串做处理。

### 配置项

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `max_tool_result_length` | `int` | `2000` | 单个工具返回结果的最大字符数，超出部分被截断 |

### 影响范围

| 文件 | 改动 |
|------|------|
| `src/core/agents/loop/act/__init__.py` | 新增 `max_tool_result_length` 字段和 `_truncate_output` 方法 |
| `src/core/agents/loop/runner.py` | 暴露 `max_tool_result_length` 参数并传递给 `Act` |

### 截断策略

- 只截断成功的 tool result，错误信息保持完整（错误信息通常很短）
- 截断后追加提示文本，让 LLM 知道数据不完整
- 截断基于字符数而非 token 数（简单高效，避免引入 tokenizer 依赖）
- `ToolCallRecord` 中的 `result` 字段保存完整结果（用于调试/审计），截断只影响传给 LLM 的消息

## 向后兼容 (Backward Compatibility)

- 默认值 2000 字符对绝大多数场景足够
- 设置 `max_tool_result_length=0` 或极大值可禁用截断
- 现有调用方无需修改任何代码

## 测试策略 (Testing)

1. 工具返回短内容（< 2000 chars）→ 不截断
2. 工具返回长内容（> 2000 chars）→ 截断并包含提示文本
3. 工具返回空内容 → 不截断
4. 自定义 `max_tool_result_length` 生效
5. 错误结果不被截断
