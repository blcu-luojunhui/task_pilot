# Dynamic Prompt Assembly

> Build a per-step system prompt from current agent state instead of relying on a static planner prompt.

## 背景 (Background)

当前 `DeepSeekPlanner.system_prompt` 是静态字符串，只能在初始化时设置一次。随着 agent loop 运行，LLM 看不到：
- 当前还剩多少步
- 最近是否连续工具失败
- 当前目标的动态上下文

因此需要在 Think 阶段按步构建 system message。

## 设计 (Design)

### 核心组件

新建 `PromptAssembler`：

```python
@dataclass
class PromptAssembler:
    base_instructions: str
    max_system_tokens: int
    knowledge_selector: Optional[KnowledgeSelector]

    def assemble(self, state: AgentLoopState) -> Dict[str, Any]:
        ...
```

### System Message 结构

- Base instructions
- Goal
- Budget
- Recovery hint（仅在有连续错误时出现）
- Reference knowledge（由 KnowledgeSelector 提供）

### 集成方式

在 `Think.run()` 中，将 assembler 生成的 system message 插入到 messages 头部，再交给 ContextWindowManager 和 planner。

```python
messages = list(state.messages)
if self.prompt_assembler:
    messages = [self.prompt_assembler.assemble(state)] + messages
```

### 影响范围

| 文件 | 改动 |
|------|------|
| `src/core/agents/loop/think/prompt_assembler.py` | 新建 PromptAssembler |
| `src/core/agents/loop/think/__init__.py` | Think 集成 PromptAssembler |
| `src/core/agents/loop/runner.py` | 默认组装 PromptAssembler |

## 向后兼容 (Backward Compatibility)

- `prompt_assembler=None` 时行为不变
- 不修改 `AssistantPlanner` 接口
- 不依赖特定 LLM provider

## 测试策略 (Testing)

1. PromptAssembler 输出包含 Goal/Budget 段
2. 连续错误时包含 Recovery Hint
3. 无 knowledge_selector 时不注入知识段
4. Think.run() 会将 system message 插到消息头部
