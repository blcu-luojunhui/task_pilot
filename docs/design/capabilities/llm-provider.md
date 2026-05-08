# LLM Provider 抽象层

> `src/core/agents/capabilities/llm/base.py` — `LLMProvider`, `LLMMessage`, `LLMResponse`, `LLMConfig`, `FinishReason`
> `src/core/agents/capabilities/llm/providers/openai.py` — `OpenAIProvider`
> `src/core/agents/capabilities/llm/providers/claude.py` — `ClaudeProvider`
> `src/core/agents/capabilities/llm/providers/deepseek.py` — `DeepSeekProvider`

---

## 为什么存在这个功能？

Agent 系统需要调用 LLM 来做推理和决策。但不同的 LLM Provider（OpenAI、Claude、DeepSeek）有不同的：
- API 端点和认证方式
- 消息格式（system/user/assistant 的排列规则）
- tool call 格式（OpenAI `function` vs Claude `tool_use` content block）
- 流式响应格式

如果每个 Provider 的实现散落在业务代码中，切换 LLM 就需要改动大量逻辑。抽象层的目标是：**业务代码只依赖 `LLMProvider.chat()` 接口，具体实现可插拔**。

## 为什么选这个设计？

**统一接口 + Provider 实现 + Agent.create() 的 `_PROVIDER_MAP` 路由**：

- `LLMProvider` 是抽象基类，定义 `chat()` 和 `stream_chat()` 两个核心方法
- `LLMMessage` 统一消息格式（role + content + tool_calls + tool_call_id）
- `LLMResponse` 统一响应格式（content + tool_calls + finish_reason + usage）
- `_PROVIDER_MAP = {"openai": OpenAIProvider, "claude": ClaudeProvider, "deepseek": DeepSeekProvider}`
- `Agent.create(llm_provider="openai")` → 一行切换

对比可选方案：
- LangChain 的 LLM 抽象：功能丰富但耦合重，引入大量不需要的依赖
- 直接使用 openai/anthropic SDK：业务代码与具体 SDK 耦合，切换成本高
- 每个 Agent 子类实现自己的 LLM 调用：重复代码多，维护成本高

## 解决什么问题？

1. **Provider 透明切换** — `llm_provider="claude"` 一行切换，其余代码零改动
2. **统一消息格式** — 内部使用 `LLMMessage` / `LLMResponse`，`normalize_tool_calls()` 做格式转换
3. **默认配置管理** — `_PROVIDER_DEFAULTS` 存储各 provider 的 model/base_url 默认值
4. **扩展性** — 新增 Provider 只需实现 `LLMProvider` 接口并注册到 `_PROVIDER_MAP`

## 在 Agent 流程中承担什么责任？

```
Agent.create(llm_provider="deepseek")
  │
  ├─ _PROVIDER_MAP["deepseek"] → DeepSeekProvider
  ├─ LLMConfig(api_key, model, base_url, temperature)
  └─ provider = DeepSeekProvider(config)

planner_factory(messages, step) 闭包：
  │
  ├─ 转换消息格式 → List[LLMMessage]
  ├─ 构建工具列表（从 registry）
  ├─ response = await provider.chat(messages, tools, temperature)
  │    └─ LLMResponse(content, tool_calls, finish_reason)
  ├─ normalize_tool_calls(response.tool_calls)
  │    └─ 自动识别 OpenAI/Claude 格式
  └─ 返回标准化 dict → Think 阶段继续

Think.run(state) → planner(messages, step) 闭包调用
```

## LLMProvider 接口

```python
class LLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> LLMResponse: ...

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
        **kwargs,
    ) -> AsyncIterator[LLMResponse]: ...
```

## Provider 默认配置

| Provider | 默认 Model | 默认 Base URL |
|----------|-----------|---------------|
| `openai` | `gpt-4` | `https://api.openai.com/v1` |
| `claude` | `claude-3-opus-20240229` | `https://api.anthropic.com/v1` |
| `deepseek` | `deepseek-chat` | `https://api.deepseek.com` |

## 技术栈

- Python ABC + dataclass
- `openai` SDK（OpenAIProvider）
- `anthropic` SDK（ClaudeProvider）
- `httpx` / `aiohttp`（DeepSeekProvider 兼容 OpenAI 格式）
- `normalize_tool_calls()` 自动格式识别

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| `DeepSeekPlanner` legacy 类仍存在 | 标记 deprecated，迁移所有调用方后移除 |
| `stream_chat` 未在主链路中使用 | Harness 增加 streaming mode |
| Provider 不支持 fallback（A 挂了切 B） | 增加 `FallbackProvider` 包装器 |
| 每个 Provider 的 `chat()` 各自处理 retry | 统一 retry 逻辑到基类 |
| 不支持模型能力查询（context window 大小等） | 增加 `LLMProvider.capabilities` 属性 |

## 使用案例

### 基础使用（切换 Provider）

```python
# DeepSeek
agent = Agent.create(llm_api_key="sk-xxx", llm_provider="deepseek")

# OpenAI
agent = Agent.create(llm_api_key="sk-xxx", llm_provider="openai")

# Claude
agent = Agent.create(llm_api_key="sk-xxx", llm_provider="claude")
```

### 自定义模型和 API 地址

```python
agent = Agent.create(
    llm_api_key="sk-xxx",
    llm_provider="openai",
    llm_model="gpt-4o",
    llm_base_url="https://my-proxy.example.com/v1",  # 代理
)
```

### 直接使用 Provider（不通过 Agent）

```python
from src.core.agents.capabilities.llm import LLMConfig, DeepSeekProvider, LLMMessage

config = LLMConfig(
    api_key="sk-xxx",
    model="deepseek-chat",
    temperature=0.1,
)
provider = DeepSeekProvider(config)

messages = [
    LLMMessage(role="system", content="You are a helpful assistant."),
    LLMMessage(role="user", content="解释什么是 SQL 注入"),
]

response = await provider.chat(messages)
print(response.content)
print(f"tokens: {response.usage}")

# 流式
async for chunk in provider.stream_chat(messages):
    print(chunk.content, end="", flush=True)
```

### 新增自定义 Provider

```python
from src.core.agents.capabilities.llm import LLMProvider, LLMConfig, LLMMessage, LLMResponse

class MyCustomProvider(LLMProvider):
    def __init__(self, config: LLMConfig):
        self.config = config

    async def chat(self, messages, tools=None, temperature=0.2, **kwargs):
        # 调用自定义 LLM API
        response = await my_api_call(messages, tools, temperature)
        return LLMResponse(
            content=response.content,
            tool_calls=response.tool_calls,
            finish_reason=response.finish_reason,
        )

    async def stream_chat(self, messages, tools=None, temperature=0.2, **kwargs):
        # 流式版本
        ...
```
