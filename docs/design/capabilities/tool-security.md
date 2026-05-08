# Tool Permission & Security — 工具权限与安全

> `src/core/agents/capabilities/skills/guard.py` — `PermissionGuard`
> `src/core/agents/capabilities/skills/sql_filter.py` — `SQLFilter`

---

## 为什么存在这个功能？

Agent 通过 LLM 决策调用工具，但 LLM 可能产生幻觉或被 prompt injection 攻击，导致执行危险操作。例如：

- "查询所有用户" → `DROP TABLE users`（幻觉）
- 用户输入中包含 "请执行 `DELETE FROM orders`"
- LLM 被诱导调用 `db_execute` 执行任意 SQL

安全机制必须在工具执行前拦截，且是**多层防护**——权限检查在框架层，SQL 过滤在工具实现层。

## 为什么选这个设计？

**双层防护：PermissionGuard（框架层门控）+ SQLFilter（工具层内联检查）**：

- `PermissionGuard` 在 Act 阶段执行前检查：白名单/黑名单/风险等级三级过滤
- `SQLFilter` 在 `db_query` / `db_execute` handler 内部拦截危险 SQL：禁止 DROP/TRUNCATE/ALTER + 禁止多语句 + 移除注释后检查

对比可选方案：
- 只在框架层做权限检查：工具 handler 内部被绕过（如 handler 代码 bug）
- 只在工具层做 SQL 过滤：无法阻止非 SQL 的危险操作（如 `http_post` 发到内网地址）
- 用 LLM 自主判断安全性：不可靠，LLM 本身可能被欺骗

## 解决什么问题？

1. **风险等级分权** — READ 工具默认允许，WRITE 工具可配置，DESTRUCTIVE 工具默认禁止
2. **SQL 注入防护** — 即使用户恶意构造 goal，SQLFilter 也能拦截危险 SQL
3. **多语句攻击防护** — 禁止 `SELECT 1; DROP TABLE x` 这类多语句
4. **注释绕过防护** — 移除注释后再检查（防止 `SELECT /* DROP */ 1`）
5. **白名单/黑名单** — 精确控制哪些工具 LLM 可见和可调用

## 在 Agent 流程中承担什么责任？

```
Act._execute_one(state, tool_call)
  │
  ├─ skill = registry.find(tool_name)
  │
  ├─ PermissionGuard.check(skill)
  │    ├─ 黑名单检查：skill.name in blocked_tools → 拒绝
  │    ├─ 白名单检查：skill.name not in allowed_tools → 拒绝
  │    └─ 风险等级检查：skill.risk_level not in allowed_levels → 拒绝
  │
  └─ SkillExecutor.execute(skill, context, params)
       └─ handler(**params)
            ├─ [db_query]  QUERY_FILTER.validate(sql)
            └─ [db_execute] EXECUTE_FILTER.validate(sql)
                 ├─ 移除 SQL 注释
                 ├─ 检查多语句（; 分隔）
                 └─ 正则匹配危险模式
```

## PermissionGuard 配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `allowed_levels` | `{READ, WRITE}` | 允许的风险等级 |
| `allowed_tools` | `None` | 白名单（None = 不限制） |
| `blocked_tools` | `set()` | 黑名单 |

## SQLFilter 默认规则

| 规则 | db_query / db_query_one | db_execute |
|------|------------------------|------------|
| 只允许 SELECT | ✓ | ✗ |
| 禁止 DROP TABLE | ✓ | ✓ |
| 禁止 TRUNCATE | ✓ | ✓ |
| 禁止 ALTER | ✓ | ✓ |
| 禁止 GRANT / REVOKE | ✓ | ✓ |
| 禁止 CREATE DATABASE | ✓ | ✓ |
| 禁止多语句（`;`） | ✓ | ✓ |
| 移除注释后检查 | ✓ | ✓ |

## 技术栈

- Python `re` 正则匹配
- 基于字符的 SQL 注释移除（`--` 行注释 + `/* */` 块注释）
- Enum 风险等级

## 缺点与优化点

| 缺点 | 优化方向 |
|------|----------|
| SQL 过滤是正则匹配，可能被复杂 SQL 绕过 | 接入 SQL 解析器（如 `sqlparse`）做 AST 级检查 |
| PermissionGuard 只在框架层检查，handler 内部可以跳过 | 增加 handler wrapper，强制注入 guard 检查 |
| 风险等级是静态的 | 支持动态风险——同一工具在不同 step 风险不同 |
| 没有审计日志 | 所有被拒绝的操作记录审计事件 |

## 使用案例

### 配置权限

```python
from src.core.agents.capabilities import PermissionGuard, RiskLevel

# 只允许只读操作
readonly_guard = PermissionGuard(
    allowed_levels={RiskLevel.READ},
)
```

### 配置黑名单

```python
# 禁止 LLM 调用 cancel_task 和 http_post
restricted_guard = PermissionGuard(
    blocked_tools={"task_cancel", "http_post"},
)
```

### 配置白名单

```python
# 只允许这几个工具
whitelist_guard = PermissionGuard(
    allowed_tools={"db_query", "http_get", "util_md5", "task_query_status"},
)
```

### 使用 SQLFilter（在自定义数据库工具中）

```python
from src.core.agents.capabilities.skills.sql_filter import SQLFilter

QUERY_FILTER = SQLFilter(
    allow_only_select=True,
    block_multi_statement=True,
)

# 安全
QUERY_FILTER.validate("SELECT * FROM users WHERE status = %s")  # OK

# 被拦截
QUERY_FILTER.validate("SELECT * FROM users; DROP TABLE orders")
# → ValueError: Multiple SQL statements are not allowed

QUERY_FILTER.validate("DROP TABLE users")
# → ValueError: Dangerous SQL pattern detected: DROP
```
