# Skill 系统 — 工具能力的注册、发现与执行

> `src/core/agents/capabilities/skills/model.py` — `Skill`, `SkillType`, `RiskLevel`
> `src/core/agents/capabilities/skills/registry.py` — `SkillRegistry`
> `src/core/agents/capabilities/skills/executor.py` — `SkillExecutor`
> `src/core/agents/capabilities/skills/context.py` — `SkillContext`
> `src/core/agents/capabilities/skills/validator.py` — `ParameterValidator`
> `src/core/agents/capabilities/skills/serializer.py` — `ToolSpecSerializer`
> `src/core/agents/capabilities/skills/loader.py` — `SkillLoader`
> `src/core/agents/capabilities/skills/output.py` — `ToolOutput`
> `src/core/agents/capabilities/skills/types.py` — 协议类型

---

## 为什么存在这个功能？

Agent 需要调用外部工具（数据库查询、HTTP 请求、文件操作等）来完成用户任务。这些工具必须：

1. **被 LLM 感知** — LLM 要知道有哪些工具可用、每个工具的参数格式、功能描述
2. **被安全执行** — 参数校验 + 权限检查 + 超时控制 + 重试
3. **被统一管理** — 注册、发现、序列化（OpenAI/Claude 不同格式）
4. **被动态加载** — 支持 Markdown 格式的 knowledge skill 和 Python 函数的 executable skill

没有一个统一的 Skill 框架，每个工具就会变成独立实现，缺乏一致的参数校验、权限控制、错误处理和序列化逻辑。

## 为什么选这个设计？

**Skill 为中心的数据模型 + Registry 注册发现 + Executor 执行管道**：

- `Skill` 是一个 data class，包含 name / description / parameters / handler / risk_level / domain / examples 等所有元信息
- `SkillRegistry` 管理命名空间隔离的 skill 集合，支持全局单例
- `SkillExecutor.execute()` 是一个管道：validate → guard → build_context → handler → format_output，包含 timeout + retry
- `ToolSpecSerializer` 支持 OpenAI 和 Claude 两种 function/tool 格式

对比可选方案：
- 用装饰器注册 + 全局 dict：简单但不支持命名空间隔离、生命周期管理
- 用插件系统（如 pluggy）：引入外部依赖，对当前规模过重
- 用 LangChain 的 Tool 抽象：增加框架耦合，不够轻量

## 解决什么问题？

1. **统一的工具体验** — 所有工具（内置的 database/http/task、用户自定义的 @agent.skill()）走同一套执行管道
2. **LLM 格式适配** — OpenAI 的 `function` 格式和 Claude 的 `tool` 格式自动转换
3. **安全的依赖注入** — `SkillContext` 惰性解析依赖，工具声明 dependencies，调用方注入具体实现
4. **Knowledge 与 Executable 分离** — Knowledge skill（只读文档）和 Executable skill（函数调用）用 `SkillType` 区分

## 在 Agent 流程中承担什么责任？

```
Agent.create() 时：
  ├─ load_agentic_tools(["database", "http"])    → 注册内置工具到 registry
  ├─ @agent.skill(...) 装饰器                      → 注册自定义工具
  └─ registry = get_global_registry()              → 获取全局 registry

Act._execute_one() 执行时：
  ├─ registry.find(tool_name)                      → 查找 Skill 对象
  ├─ PermissionGuard.check(skill)                  → 权限门控
  ├─ SkillContext(resolver, trace_id)              → 构建上下文
  ├─ executor.execute(skill, context, params)
  │    ├─ ParameterValidator.validate(params)      → 参数校验
  │    ├─ guard.check(skill)                       → 风险管理
  │    └─ handler(**params)                        → 实际执行
  │         ├─ timeout 保护
  │         └─ retry 机制
  └─ serialize_content(result)                     → 格式化输出

Think 阶段（构建 LLM 请求）：
  └─ registry.list_executable()
       └─ ToolSpecSerializer.serialize(skill)      → OpenAI/Claude 格式
```

## Skill 数据模型

```python
class SkillType(str, Enum):
    EXECUTABLE = "executable"   # 可调用函数（db_query, http_get）
    KNOWLEDGE  = "knowledge"    # 只读知识（Markdown 文档）

class RiskLevel(str, Enum):
    READ        = "read"        # 只读（SELECT, GET）
    WRITE       = "write"       # 写操作（INSERT, POST, cancel）
    DESTRUCTIVE = "destructive" # 不可逆（DROP 等）

class Skill:
    skill_id: str               # 唯一标识
    name: str                   # 工具名（LLM 调用时使用）
    description: str            # 功能描述（注入 LLM prompt）
    skill_type: SkillType
    handler: Callable           # 执行函数（executable 类型）
    parameters: dict            # JSON Schema 参数定义
    dependencies: list[str]     # 依赖声明
    risk_level: RiskLevel
    scope: str                  # 命名空间
    domain: str                 # 领域（database/http/task/...）
    examples: list[dict]        # 使用示例（注入 LLM prompt）
    body: str                   # 知识内容（knowledge 类型）
```

## 技术栈

- Python dataclass + Enum
- `asyncio.wait_for` 超时控制
- `tenacity` 重试机制
- JSON Schema 参数校验
- OpenAI / Claude 双格式自适应

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| registry 是全局单例，多租户场景下 tool 集合冲突 | 引入 scoped registry（per-agent 而非 global） |
| ParameterValidator 只做基础校验 | 支持 JSON Schema 完整校验（oneOf/anyOf/dependencies） |
| SkillExecutor 重试对所有工具统一 | 按 skill 声明 retry_strategy（指数退避 vs 固定间隔） |
| ToolSpecSerializer 输出格式有限 | 支持 Anthropic computer_use、Google Gemini 等工具格式 |
| Markdown loader 的 frontmatter 解析对格式敏感 | 增加容错解析和格式校验 |

## 使用案例

### 注册自定义 tool

```python
from src.core.agents import Agent

agent = Agent.create(llm_api_key="sk-xxx")

@agent.skill(
    name="send_email",
    description="发送邮件通知",
    parameters={
        "to": {"type": "string", "description": "收件人"},
        "subject": {"type": "string", "description": "主题"},
        "body": {"type": "string", "description": "正文"},
    },
    risk_level="write",
    domain="notification",
    examples=[{
        "input": {"to": "admin@example.com", "subject": "任务完成", "body": "数据分析已完成"},
        "output": "邮件发送成功"
    }],
)
async def send_email(to: str, subject: str, body: str) -> str:
    # 实际发送邮件逻辑
    return f"已发送邮件到 {to}"
```

### 注册 knowledge skill（Markdown 格式）

```python
from src.core.agents.capabilities import Skill, SkillType, get_global_registry

knowledge = Skill(
    skill_id="api_docs_v1",
    name="api_documentation",
    description="内部 API 文档",
    skill_type=SkillType.KNOWLEDGE,
    handler=lambda: None,
    domain="http",
    body="""
## API 列表
- GET /api/users - 查询用户
- POST /api/orders - 创建订单
""",
)

get_global_registry().register(knowledge)
```

### 从目录加载 knowledge skills

```python
from src.core.agents.capabilities import load_skills_from_dir

# 从 ./knowledge/ 目录加载所有 .md 文件
# 每个 .md 文件通过 frontmatter 声明 name/description/domain
load_skills_from_dir("./knowledge")
```

### 使用 ToolOutput 结构化返回值

```python
from src.core.agents.capabilities import ToolOutput

@agent.skill(name="query_users", description="查询用户列表", ...)
async def query_users(status: str) -> ToolOutput:
    rows = await db.query("SELECT * FROM users WHERE status = %s", (status,))
    return ToolOutput.ok(
        data=rows,
        message=f"找到 {len(rows)} 个用户",
        row_count=len(rows),
    )
    # 或在错误时：
    # return ToolOutput.error("数据库连接失败")
```
