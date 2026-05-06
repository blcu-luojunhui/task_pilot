# Tool Permission Guard

> Multi-layer security for agent tool execution: risk level classification + SQL statement filtering.

## 背景 (Background)

Agent 通过 LLM 决策调用工具，但 LLM 可能产生幻觉或被 prompt injection 攻击，导致执行危险操作。当前系统缺乏任何执行前的安全检查，所有工具对 LLM 平等可见且无条件执行。

本设计实现双重防护：
1. **工具分级 (PermissionGuard)** — 按风险等级控制哪些工具可以执行
2. **SQL 过滤 (SQLFilter)** — 在数据库工具内部拦截危险 SQL 语句

## 设计 (Design)

### 工具风险等级

每个工具声明自己的 `risk_level`：

```python
class RiskLevel(str, Enum):
    READ = "read"              # 只读，无副作用（db_query, http_get, utils）
    WRITE = "write"            # 写操作，可逆（db_execute, http_post, task_cancel）
    DESTRUCTIVE = "destructive"  # 不可逆（DROP TABLE 等，当前无此类工具）
```

### PermissionGuard

在 `Act` 阶段执行工具前进行权限检查：

```python
@dataclass
class PermissionGuard:
    allowed_levels: Set[RiskLevel]    # 允许的风险等级
    allowed_tools: Optional[Set[str]] # 白名单（None=不限制）
    blocked_tools: Set[str]           # 黑名单

    def check(self, skill: Skill) -> Optional[str]:
        # 返回 None 表示允许，返回错误信息表示拒绝
```

检查顺序：黑名单 → 白名单 → 风险等级

### SQL 安全过滤

在 `db_query` / `db_execute` handler 内部调用：

```python
@dataclass
class SQLFilter:
    blocked_patterns: List[str]      # 禁止的 SQL 模式（正则）
    allow_only_select: bool          # 是否只允许 SELECT
    block_multi_statement: bool      # 是否禁止多语句
```

默认规则：
- `db_query` / `db_query_one`：只允许 SELECT
- `db_execute`：禁止 DROP, TRUNCATE, ALTER, GRANT, REVOKE, CREATE DATABASE
- 所有：禁止多语句（防止 `SELECT 1; DROP TABLE x`）
- 所有：移除注释后再检查（防止 `SELECT /* DROP TABLE x */ 1`）

### 配置项

| 组件 | 参数 | 默认值 |
|------|------|--------|
| PermissionGuard | `allowed_levels` | `{READ, WRITE}` |
| PermissionGuard | `allowed_tools` | `None`（不限制） |
| PermissionGuard | `blocked_tools` | `set()`（空） |
| SQLFilter | `blocked_patterns` | DROP/TRUNCATE/ALTER/GRANT/REVOKE/CREATE DATABASE |
| SQLFilter | `allow_only_select` | `True`（db_query）/ `False`（db_execute） |
| SQLFilter | `block_multi_statement` | `True` |

### 集成点

```
AgentLoopRunner
  → permission_guard: Optional[PermissionGuard]
    → Act._execute_one()
      → guard.check(skill) → 拒绝则返回 permission_denied 错误

db_query handler 内部:
  → QUERY_FILTER.validate(sql) → 拒绝则 raise ValueError

db_execute handler 内部:
  → EXECUTE_FILTER.validate(sql) → 拒绝则 raise ValueError
```

### 影响范围

| 文件 | 改动 |
|------|------|
| `src/core/agents/skills/model.py` | 新增 `RiskLevel` 枚举和 `risk_level` 字段 |
| `src/core/agents/skills/guard.py` | 新建，PermissionGuard 实现 |
| `src/core/agents/skills/sql_filter.py` | 新建，SQLFilter 实现 |
| `src/core/agents/loop/act/__init__.py` | 集成 PermissionGuard 检查 |
| `src/core/agents/loop/runner.py` | 暴露 `permission_guard` 参数 |
| `src/core/agents/agentic_tools/database.py` | 集成 SQL filter |
| 所有 agentic_tools | 声明 `risk_level` |

## 向后兼容 (Backward Compatibility)

- `risk_level` 默认为 `READ`，不传则为最安全等级
- `permission_guard` 默认为 `None`，不传则不做权限检查（行为与之前一致）
- SQL filter 集成在 handler 内部，对外部调用方透明

## 测试策略 (Testing)

1. PermissionGuard 拒绝 DESTRUCTIVE 工具
2. PermissionGuard 黑名单生效
3. SQLFilter 拦截 DROP TABLE
4. SQLFilter 允许正常 SELECT/INSERT
5. SQLFilter 拦截多语句
6. SQLFilter 移除注释后仍能检测危险语句
7. 不配置 guard 时行为不变
