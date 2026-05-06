# Agent 系统使用指南

## 概述

Agent 系统提供了一个完整的 AI Agent 框架，基于 Think-Act-Observe 循环，支持自定义技能和工具扩展。

## 架构分层

```
src/core/agents/
├── agent.py            # 统一的 Agent 接口
├── foundation/         # 基础层 - 核心抽象
│   ├── state/          状态管理
│   ├── protocol/       消息协议
│   └── context/        上下文管理
├── loop/               # 循环层 - 核心执行循环
│   ├── think/          思考阶段
│   ├── act/            执行阶段
│   └── observe/        观察阶段
├── capabilities/       # 能力层 - 技能和工具
│   ├── skills/         技能系统
│   ├── tools/          工具集合
│   └── llm/            LLM 集成
└── orchestration/      # 编排层 - 执行控制
    ├── executor/       执行器
    ├── runtime/        运行时控制
    └── routing/        任务路由
```

## 快速开始

### 1. 创建 Agent

```python
from src.core.agents import Agent

# 创建 Agent 实例
agent = Agent.create(
    llm_api_key="your-deepseek-api-key",
    max_steps=10,
)

# 运行任务
result = await agent.run("帮我分析系统状态")
print(result.final_answer)
```

### 2. 加载内置工具

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    tool_areas=["database", "http", "utils"],  # 加载工具区域
)
```

可用的工具区域：
- `database`: 数据库操作工具
- `http`: HTTP 请求工具
- `task`: 任务管理工具
- `utils`: 通用工具

### 3. 注册自定义 Skill

#### 方式 1: 使用装饰器

```python
@agent.skill(
    name="calculate_sum",
    description="计算两个数字的和",
    parameters={
        "a": {"type": "number", "description": "第一个数字"},
        "b": {"type": "number", "description": "第二个数字"},
    },
)
def calculate_sum(a: float, b: float) -> float:
    return a + b
```

#### 方式 2: 使用 Skill 对象

```python
from src.core.agents import Skill, SkillType

def my_function(param: str) -> str:
    return f"Processed: {param}"

skill = Skill(
    name="my_tool",
    description="My custom tool",
    skill_type=SkillType.PYTHON_FUNCTION,
    implementation=my_function,
    parameters={
        "param": {"type": "string", "description": "Input"}
    },
)

agent.register_skill(skill)
```

### 4. 注入依赖

```python
from src.infra.database import DatabaseClient

# 创建依赖
db_client = DatabaseClient(connection_string="...")

# 注入到 Agent
agent = Agent.create(
    llm_api_key="your-api-key",
    tool_areas=["database"],
    tool_dependencies={
        "db_client": db_client,
    },
)
```

## 高级功能

### 任务路由

启用任务路由可以自动将复杂任务拆分为多个子任务：

```python
agent = Agent.create(
    llm_api_key="your-api-key",
    enable_routing=True,  # 启用路由
)

result = await agent.run(
    "分析日志、生成报告、发送邮件"
)
```

### 完整配置

```python
agent = Agent.create(
    # LLM 配置
    llm_api_key="your-api-key",
    llm_model="deepseek-chat",
    llm_base_url="https://api.deepseek.com/chat/completions",
    llm_temperature=0.2,
    
    # 执行配置
    max_steps=10,
    max_context_tokens=60000,
    max_tool_result_length=2000,
    abort_on_tool_error=False,
    max_consecutive_errors=3,
    
    # 工具配置
    tool_areas=["database", "http"],
    tool_dependencies={...},
    
    # 其他
    enable_routing=True,
)
```

### 运行配置

```python
result = await agent.run(
    goal="Complete the task",
    messages=[...],           # 初始消息
    metadata={...},           # 元数据
    trace_id="custom-id",     # 追踪 ID
)

# 结果
print(result.success)         # 是否成功
print(result.final_answer)    # 最终答案
print(result.total_steps)     # 执行步数
print(result.tool_calls_count) # 工具调用次数
```

## API 参考

### Agent.create()

创建 Agent 实例。

**参数：**
- `llm_api_key` (str): LLM API 密钥
- `llm_model` (str): 模型名称，默认 "deepseek-chat"
- `llm_base_url` (str): API 地址
- `llm_temperature` (float): 温度参数，默认 0.2
- `max_steps` (int): 最大执行步数，默认 8
- `tool_areas` (List[str]): 要加载的工具区域
- `tool_dependencies` (Mapping): 工具依赖注入
- `enable_routing` (bool): 是否启用任务路由

**返回：**
- `Agent`: Agent 实例

### agent.skill()

装饰器，注册自定义 skill。

**参数：**
- `name` (str): Skill 名称
- `description` (str): Skill 描述
- `parameters` (Dict): 参数定义

### agent.run()

运行 Agent 执行任务。

**参数：**
- `goal` (str): 任务目标
- `messages` (List[Dict]): 初始消息列表
- `metadata` (Dict): 元数据
- `trace_id` (str): 追踪 ID

**返回：**
- `AgentLoopResult`: 执行结果

## 示例

完整示例请参考：
- `examples/agent_usage_examples.py` - 各种使用场景示例
- `examples/minimal_goal_agent.py` - 最小化示例
- `examples/deepseek_goal_agent.py` - DeepSeek 集成示例

## 扩展开发

### 创建自定义工具区域

1. 在 `src/core/agents/capabilities/tools/` 下创建新文件
2. 使用 `@skill` 装饰器定义工具
3. 在 `loader.py` 中注册工具区域

### 创建自定义 LLM 集成

1. 在 `src/core/agents/capabilities/llm/` 下创建新文件
2. 实现 `AssistantPlanner` 接口
3. 在创建 Agent 时使用自定义 planner

## 最佳实践

1. **合理设置 max_steps**：根据任务复杂度调整
2. **使用依赖注入**：避免在 skill 中硬编码依赖
3. **错误处理**：设置合适的 `max_consecutive_errors`
4. **工具选择**：只加载需要的工具区域
5. **任务拆分**：复杂任务启用 routing

## 故障排查

### 常见问题

1. **导入错误**：确保正确安装依赖
2. **API 密钥错误**：检查 LLM API 密钥配置
3. **工具未找到**：确认工具区域已加载
4. **依赖注入失败**：检查依赖名称是否匹配

## 贡献

欢迎贡献新的工具、技能和改进！
