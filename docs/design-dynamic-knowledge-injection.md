# Dynamic Knowledge Injection

> Inject only relevant knowledge skills into the system prompt instead of loading all knowledge statically.

## 背景 (Background)

项目里的 knowledge skills 已经存在，但当前没有被真正注入到 prompt 中。即使未来接入，也不能把所有 knowledge 全部塞进去，否则：
- system prompt 会迅速膨胀
- 无关知识会稀释当前任务的注意力
- token 成本上升

因此需要按任务上下文动态选择相关 knowledge。

## 设计 (Design)

### 核心组件

新建 `KnowledgeSelector`：

```python
@dataclass
class KnowledgeSelector:
    registry: SkillRegistry
    max_knowledge_tokens: int = 4000
    chars_per_token: float = 4.0

    def select(self, state: AgentLoopState) -> str:
        ...
```

### 选择策略

按照以下顺序推断相关 domain：
1. 从 `state.goal` 做关键词匹配（database/http/task-management/observability）
2. 从 `state.tool_call_history` 中已调用工具名推断 domain
3. 如果 skill 自身声明了非 `general` domain，则优先使用 skill.domain

### 预算控制

- 通过 `max_knowledge_tokens` 限制总知识长度
- 使用 `chars_per_token≈4` 粗略估算
- 超预算时按顺序截断，不做复杂摘要

### 集成方式

`PromptAssembler` 调用：

```python
knowledge = self.knowledge_selector.select(state)
if knowledge:
    sections.append(f"## Reference Knowledge\n{knowledge}")
```

### 影响范围

| 文件 | 改动 |
|------|------|
| `src/core/agents/loop/think/knowledge_selector.py` | 新建 KnowledgeSelector |
| `src/core/agents/loop/think/prompt_assembler.py` | 集成 knowledge_selector |
| `src/core/agents/loop/runner.py` | 默认组装 KnowledgeSelector |

## 向后兼容 (Backward Compatibility)

- `knowledge_selector=None` 时行为不变
- knowledge skills 本身不需要修改
- 不依赖具体 LLM provider

## 测试策略 (Testing)

1. goal 包含 SQL/数据库关键词时选中 database knowledge
2. goal 包含 API/http 关键词时选中 http knowledge
3. 已调用 task_* 工具后选中 task-management knowledge
4. 知识总长度超过预算时被截断
5. 无匹配 domain 时返回空字符串
