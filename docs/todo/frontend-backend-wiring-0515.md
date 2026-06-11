# 前后端联调对齐 TODO（2026-05-15）

## 背景

`frontend/` 已经实现了 7 个页面（Dashboard / Tasks / TaskDetail / Traces / Skills / Runs / System），目前通过 `VITE_USE_MOCKS=true` 走 MSW 跑通了 UI。本轮目标：**关掉 mock，把前端打到后端真实接口**，并补齐契约不一致或后端缺失的能力。

不动前端 UI，只对齐后端契约（少量改 harness 事件 payload）。前端唯一的改动是新建 `.env.local` 关闭 MSW。

## 整体执行顺序

```
P0 (阻塞 happy path):  #1 → #2 → #3      # 提交任务 / Dashboard 主体
P1 (显示完整性):        #4 → #5 → #6      # JSON 反序列化先修，goal/skill 计数才显示对
P2 (端到端验证):        #7 → #8           # 联调 + 构建校验
```

P0 三条互不依赖可以并行；#5（agent_metadata.goal）改了 harness 会刷一次 trace 数据；#6（skill 计数）独立。

## 契约真相对照表

| 字段/能力 | 前端期望 (`frontend/src/api/types.ts`) | 后端现状 | 任务 |
|---|---|---|---|
| `system/stats.health.mysql` | `'ok' \| 'degraded' \| 'failed' \| 'stopped'` | bool | #1 |
| `system/stats.recent_failures[].error` | 字符串摘要 | 不返回 | #2 |
| `run_task` 顶层 | `{code, message, trace_id, data?}` | `{code, status, message, data: {code, message, trace_id}}` | #3 |
| `task.data` / `run.token_usage` 等 JSON 列 | object | 可能是 string（aiomysql 默认） | #4 |
| `agent_metadata.goal` | string | 不存在（run_start payload 不发 goal） | #5 |
| `SkillInfo.call_count_24h` | number | 不返回 | #6 |

---

# Task #1 [P0]：system/stats 健康字段改 HealthFlag 字符串

## 上下文

`DashboardPage.tsx` 顶部有 MySQL / LogService 两个状态徽章，颜色靠枚举字符串决定：

```ts
// frontend/src/pages/DashboardPage.tsx:158-167
const color = flag === 'ok' ? 'green'
  : flag === 'degraded' ? 'orange'
  : flag === 'failed' ? 'red' : 'default';
// ...
<Tag color={color}>{flag.toUpperCase()}</Tag>
```

后端目前返回 bool，前端 `flag.toUpperCase()` 会运行时报错（bool 没有 toUpperCase）或渲染 `TRUE`。

## 定位

- **文件**：`src/api/v1/endpoints/system.py`
- **行**：62-79（`system_stats` 函数 health 字段构造）
- **函数**：`_ping_mysql`（已有）；`log_running` 当前是写死的 `True`

## 修法

```python
# system.py 顶部 import
from typing import Literal

HealthFlag = Literal["ok", "degraded", "failed", "stopped"]


async def _check_mysql(deps: ApiDependencies) -> HealthFlag:
    try:
        row = await deps.mysql.async_fetch_one("SELECT 1 AS ok")
        return "ok" if row else "degraded"
    except Exception:
        return "failed"


def _check_log_service(deps: ApiDependencies) -> HealthFlag:
    try:
        metrics = deps.log.get_metrics()  # 已有这个方法，参考 health.py:46
        return "ok" if metrics.get("is_running") else "stopped"
    except Exception:
        return "failed"
```

`system_stats` 内：

```python
mysql_flag = await _check_mysql(deps)
log_flag = _check_log_service(deps)
return jsonify({
    "code": 0,
    "data": {
        "health": {"mysql": mysql_flag, "log_service": log_flag},
        # ...其余不变
    },
})
```

## 验收

```bash
curl -s http://127.0.0.1:6060/api/system/stats | jq '.data.health'
# 期望: {"mysql": "ok", "log_service": "ok"}（字符串而非 true/false）
```

前端 Dashboard 顶部两个 Badge 颜色为绿色，文字为 `OK`。

---

# Task #2 [P0]：system/stats recent_failures 补 error 摘要字段

## 上下文

Dashboard 底部"近期失败"表格有"错误摘要"列：

```tsx
// frontend/src/pages/DashboardPage.tsx:149
{ title: '错误摘要', dataIndex: 'error', ellipsis: true },
```

后端 `_recent_failures` 直接 `SELECT *` 返回，没有 `error` 字段，这一列永远空白。

## 定位

- **文件**：`src/api/v1/endpoints/system.py`
- **行**：28-33（`_recent_failures` 函数）
- **数据来源**：`task_manager.data` JSON 字段；约定可能含 `error` / `error_message` / `failure_reason` 任一键（实际看历史失败任务）

## 修法

```python
import json

_ERROR_KEYS = ("error", "error_message", "failure_reason", "reason")


def _extract_error(data_field) -> str | None:
    if data_field is None:
        return None
    if isinstance(data_field, str):
        try:
            data_field = json.loads(data_field)
        except json.JSONDecodeError:
            return data_field[:200]
    if not isinstance(data_field, dict):
        return None
    for key in _ERROR_KEYS:
        v = data_field.get(key)
        if v:
            return str(v)[:200]
    return None


async def _recent_failures(deps: ApiDependencies, limit: int = 10) -> list:
    rows = await deps.mysql.async_fetch(
        "SELECT * FROM task_manager WHERE task_status = 99 "
        "ORDER BY finish_timestamp DESC LIMIT %s",
        params=(limit,),
    )
    for row in rows:
        row["error"] = _extract_error(row.get("data"))
    return rows
```

⚠️ 注意：和 #4 有耦合。如果 #4 已经把所有 endpoint 的 `data` 列做了归一化（dict），这里 `_extract_error` 的 string 分支可省。但为防御性，保留 string 分支不影响正确性。

## 验收

```bash
curl -s http://127.0.0.1:6060/api/system/stats | jq '.data.recent_failures[0]'
# 期望返回有 error 字段（值或 null）
```

前端 Dashboard 失败任务的"错误摘要"列：失败任务 `data.error` 存在时展示前 200 字；不存在时空白但不报错。

---

# Task #3 [P0]：run_task 返回结构改扁平

## 上下文

前端 `tasks.ts:39` 直接拿 `response.data` 作为 `RunTaskResponse`：

```ts
// frontend/src/api/tasks.ts:38-41
export async function runTask(payload: RunTaskRequest): Promise<RunTaskResponse> {
  const response = await apiClient.post<RunTaskResponse>('/run_task', payload);
  return response.data;  // 这里就是 axios 的 response.data，等于 HTTP body
}

// frontend/src/api/types.ts:84-89
export interface RunTaskResponse {
  code: number;
  message: string;
  trace_id: string;       // ← 顶层
  data?: Record<string, unknown>;
}
```

`TaskSubmitForm` 拿 `result.trace_id` 跳详情页。

后端目前返回（`TaskScheduleResponse.success_response` → `ApiResponse.success`）：

```json
{
  "code": 0,
  "status": "success",
  "message": "success",
  "data": {
    "code": 0,
    "message": "Task started successfully",
    "trace_id": "Agent-xxx"
  }
}
```

`trace_id` 嵌在 `data` 里，前端拿不到。

## 定位

- **后端文件**：`src/api/v1/endpoints/tasks.py`
- **行**：59-77（`run_task` 端点）
- **scheduler**：`src/jobs/task_scheduler.py:351-358`（`deal()` 成功分支）
- **shared**：`src/infra/shared/response.py:43-50`（`TaskScheduleResponse.success_response`）

## 修法（推荐方案 A：在 endpoint 层适配，不污染 shared）

```python
# src/api/v1/endpoints/tasks.py run_task 函数末尾

scheduler = TaskScheduler(body, trace_id, deps)
result = await scheduler.deal()

# 兼容 shared 层的嵌套返回，把 trace_id 提到顶层
if isinstance(result, dict) and result.get("code") == 0:
    inner = result.get("data") or {}
    flat = {
        "code": 0,
        "message": inner.get("message") or result.get("message", "Task started successfully"),
        "trace_id": inner.get("trace_id") or trace_id,
        "data": inner,  # 保留原 inner 给老调用方
    }
    return jsonify(flat)
return jsonify(result)
```

cancel_task 端点（`tasks.py:78-96`）已经是扁平结构，保持不动。

## 备选方案 B（改 shared，影响面更大）

`src/infra/shared/response.py:48-50`：

```python
@classmethod
def success_response(cls, task_name: str, data: dict):
    payload = {"code": ErrorCode.SUCCESS, "status": "success", "message": data.get("message", "success")}
    payload.update({"trace_id": data.get("trace_id"), "data": data})
    return payload
```

不推荐，因为 `TaskScheduleResponse.success_response` 是通用契约，可能被其他地方依赖。

## 验收

```bash
curl -s -X POST http://127.0.0.1:6060/api/run_task \
  -H 'Content-Type: application/json' \
  -d '{"task_name":"<已注册的任务名>"}' | jq
# 期望顶层有 trace_id 字段
```

前端 TaskSubmitForm 提交后能跳到 `/tasks/Agent-xxx`。

---

# Task #4 [P1]：list_tasks / list_runs / get_task JSON 列反序列化

## 上下文

aiomysql `DictCursor` 默认把 JSON 列原样返回为 **string**，不会自动反序列化。三处 endpoint 直接 `SELECT *` 后 `jsonify`，前端拿到字符串后再 `JSON.stringify` 会双重转义或运行时崩溃：

- `RunsPage.tsx:264`：`r.token_usage.total` —— `r.token_usage` 是字符串时直接 NaN
- `TaskDetailPage.tsx:142`：`JSON.stringify(detail.data, null, 2)` —— 双重转义后渲染出 `"\"key\":\"v\""`
- `RunsPage.tsx:298-303`：`detail.failed_tool_calls.length` —— 字符串没有 length 行为

## 定位

涉及三处端点：

| 端点 | 文件:行 | 需要解码的列 |
|---|---|---|
| `GET /api/tasks` | `endpoints/tasks.py:124-128` | `data` |
| `GET /api/tasks/<trace_id>` | `endpoints/tasks.py:144-158` | `data` |
| `GET /api/runs` | `endpoints/runs.py:54-58` | `token_usage`, `failed_tool_calls`, `metadata` |

## 修法

新建工具 `src/api/v1/utils/json_columns.py`：

```python
"""
JSON 列归一化工具

aiomysql DictCursor 不会自动反序列化 JSON 列，需要在 API 边界手动处理。
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping


def decode_json_columns(
    rows: Iterable[Mapping[str, Any]],
    columns: Iterable[str],
    *,
    default: Any = None,
) -> list[dict]:
    """对每行做指定列的 JSON 反序列化。dict 透传、字符串 json.loads、None/空字符串给 default。"""
    cols = tuple(columns)
    result: list[dict] = []
    for row in rows:
        item = dict(row)
        for col in cols:
            item[col] = _decode(item.get(col), default)
        result.append(item)
    return result


def decode_json_row(
    row: Mapping[str, Any] | None,
    columns: Iterable[str],
    *,
    default: Any = None,
) -> dict | None:
    if row is None:
        return None
    return decode_json_columns([row], columns, default=default)[0]


def _decode(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default
    return default


__all__ = ["decode_json_columns", "decode_json_row"]
```

加到 `src/api/v1/utils/__init__.py` 的 `__all__`：

```python
from .json_columns import decode_json_columns, decode_json_row
```

调用点改写：

**`endpoints/tasks.py` list_tasks (124-140)**：

```python
items = await deps.mysql.async_fetch(...)
items = decode_json_columns(items, ["data"], default={})
return jsonify({"code": 0, "data": {"total": total, "page": page, "page_size": page_size, "items": items}})
```

**`endpoints/tasks.py` get_task (144-158)**：

```python
task = await deps.mysql.async_fetch_one(...)
if not task:
    return jsonify({"code": 404, "message": "task not found"}), 404
task = decode_json_row(task, ["data"], default={})
agent_meta = await build_agent_metadata(deps.mysql, trace_id)
return jsonify({"code": 0, "data": {**task, "agent_metadata": agent_meta}})
```

**`endpoints/runs.py` list_runs (54-58)**：

```python
items = await deps.mysql.async_fetch(...)
items = decode_json_columns(
    items,
    ["token_usage", "failed_tool_calls", "metadata"],
    default=None,
)
```

⚠️ `failed_tool_calls` 默认建议 `None`（前端 `RunsPage.tsx:296` 用 `detail.failed_tool_calls && detail.failed_tool_calls.length > 0` 判空），`token_usage` 默认 `None`（前端有 `?? 0` 兜底），`metadata` 默认 `{}`。

⚠️ #2 的 `_recent_failures` 也命中此问题（读 `data` 字段），合并修：在 `_recent_failures` 里直接调 `decode_json_columns(rows, ["data"], default={})`，再调 `_extract_error`。

## 验收

```bash
# tasks
curl -s 'http://127.0.0.1:6060/api/tasks?page=1&page_size=1' \
  | jq '.data.items[0].data | type'   # → "object"

# runs
curl -s 'http://127.0.0.1:6060/api/runs?page=1&page_size=1' \
  | jq '.data.items[0].token_usage | type'  # → "object" 或 "null"

# task detail
curl -s 'http://127.0.0.1:6060/api/tasks/<某真实trace_id>' \
  | jq '.data.data | type'  # → "object"
```

前端 RunsPage 的 Tokens 列显示具体数字非 NaN；TaskDetailPage 的 data 区块 JSON 缩进正常。

---

# Task #5 [P1]：agent_metadata 补 goal 字段

## 上下文

前端 `TaskDetailPage.tsx:166-173` 依赖 `agent_metadata.goal`：

```tsx
{agent?.goal && (
  <Alert type="info" message="goal" description={agent.goal} />
)}
```

`TaskAgentMetadata.goal: string`（`types.ts:49`）

后端 `build_agent_metadata`（`agent_metadata.py`）从 `run_start.payload.metadata` + `run_end.payload.result` 拼装，但 harness 发 `run_start` 时 payload 只有 `{"metadata": context.metadata}`，**没有 goal**，前端 alert 永远不显示。

## 定位

- **harness**：`src/core/agents/runtime/harness/harness.py:130`
  ```python
  await self._emit("run_start", state, {"metadata": context.metadata})
  ```
- **重建器**：`src/api/v1/utils/agent_metadata.py:39-46`

## 修法（推荐方案 A：harness 把 goal 一并发出去）

```python
# harness.py:130
await self._emit(
    "run_start",
    state,
    {"metadata": context.metadata, "goal": goal},
)
```

`agent_metadata.py:39-46`：

```python
if run_start:
    start_meta = run_start.get("metadata", {})
    if isinstance(start_meta, str):
        import json
        start_meta = json.loads(start_meta)
    meta.update(start_meta)
    if run_start.get("goal"):
        meta["goal"] = run_start["goal"]
```

## 备选方案 B（不动 harness，从 agent_run_summaries 兜底）

`agent_run_summaries.goal` 列已经在 `improvement.py` 落库。新增兜底查询：

```python
# agent_metadata.py 末尾
if "goal" not in meta:
    row = await mysql.async_fetch_one(
        "SELECT goal FROM agent_run_summaries WHERE trace_id = %s",
        params=(trace_id,),
    )
    if row and row.get("goal"):
        meta["goal"] = row["goal"]
```

缺点：run 还没结束时 `agent_run_summaries` 没数据，PROCESSING 任务的 goal 仍然显示不出来。**推荐 A**。

## 备选方案 C（A + B 都做）

run_start 立刻有 goal（用于实时观察），run 结束后从 summary 兜底（用于历史 trace 复查）。最稳妥，代码改动最小。

## 验收

提交一个真实任务，进入详情页：

- PROCESSING 期间能看到 goal Alert
- 任务结束后刷新仍能看到 goal Alert

```bash
curl -s 'http://127.0.0.1:6060/api/tasks/<trace_id>' | jq '.data.agent_metadata.goal'
# 期望返回字符串，非 null
```

---

# Task #6 [P1]：/api/skills 补 call_count_24h

## 上下文

前端 `SkillsPage.tsx:53` 显示每个 skill 近 24h 调用数：

```tsx
<Statistic title="近 24h 调用" value={s.call_count_24h ?? 0} />
```

后端 `endpoints/skills.py:23-42` 不返回 `call_count_24h`，永远显示 0。

## 定位

- **文件**：`src/api/v1/endpoints/skills.py`
- **行**：23-42（`list_skills`）
- **数据源**：`agent_events` 表，`event_type='act_start'`，payload 形如 `{"tool_calls": [{"name": "skill_a", ...}, ...]}`

## 修法

要点：**一次查询 + 内存聚合**，避免 N+1（skill 数 × 一次 SQL）。

```python
# endpoints/skills.py
import json
from collections import Counter


async def _collect_24h_calls(deps) -> Counter:
    """聚合近 24h 内每个 skill 被调用次数（按 act_start.payload.tool_calls[].name）"""
    rows = await deps.mysql.async_fetch(
        "SELECT payload FROM agent_events "
        "WHERE event_type = 'act_start' "
        "AND created_at > NOW() - INTERVAL 1 DAY"
    )
    counter: Counter = Counter()
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        if not isinstance(payload, dict):
            continue
        for tc in payload.get("tool_calls", []) or []:
            name = tc.get("name") if isinstance(tc, dict) else None
            if name:
                counter[name] += 1
    return counter


# list_skills 内部
@bp.route("/skills", methods=["GET"])
async def list_skills():
    from src.core.agents.capabilities.skills import get_global_registry

    registry = get_global_registry()
    counts = await _collect_24h_calls(deps)
    skills = []
    for skill in registry.filter(lambda _: True):
        skills.append({
            "skill_id": skill.skill_id,
            "name": skill.name,
            # ...原有字段
            "call_count_24h": counts.get(skill.name, 0),
        })
    return jsonify({"code": 0, "data": skills})
```

性能预算：act_start 事件 24h 内通常 < 10000 行，单次扫描可接受；如未来量大再考虑加索引或建物化视图。

## 验收

```bash
curl -s http://127.0.0.1:6060/api/skills | jq '.data[] | {name, call_count_24h}'
# 期望每个 skill 都有 call_count_24h 字段
```

近期跑过 trace 的 skill `call_count_24h` > 0；前端 SkillsPage 卡片"近 24h 调用"数字正确。

---

# Task #7 [P2]：前端关闭 MSW 跑端到端联调

## 上下文

`frontend/.env.example` 默认 `VITE_USE_MOCKS=true`，`main.tsx:12-19` 会启动 MSW worker 拦截所有 `/api` 请求；后端真实接口完全没被打到。

需要本地起后端 + 前端做完整联调，验证 P0/P1 修改是否实际生效。

## 步骤

### 7.1 准备 .env.local（不入库）

```bash
cd frontend
cp .env.example .env.local
# 编辑 .env.local，把 VITE_USE_MOCKS 改成 false
```

或一行：

```bash
echo "VITE_USE_MOCKS=false" > frontend/.env.local
```

### 7.2 启动后端

```bash
# 项目根
hypercorn app:app -c app_config.toml
# 默认监听 127.0.0.1:6060
```

确认 `app_config.toml` 中 bind 端口与 `frontend/vite.config.ts:18` 的 proxy target 一致（127.0.0.1:6060）。

### 7.3 启动前端 dev server

```bash
cd frontend
npm install   # 如果 node_modules 没装
npm run dev
# 访问 http://localhost:5173
```

### 7.4 7 个页面逐项核对

| 页面 | 路径 | 验证点 |
|---|---|---|
| Dashboard | `/` | 顶部健康 Badge 颜色正确（#1）；24h 计数非空；近期失败表格"错误摘要"列有内容（#2） |
| Tasks | `/tasks` | 列表能筛选，任务名/状态/日期 work；提交任务跳详情页（#3） |
| TaskDetail | `/tasks/:traceId` | 左侧 data 区块 JSON 缩进正常（#4）；右侧 goal Alert 显示（#5）；状态为 PROCESSING 时上方 Badge 显示"实时同步中" |
| Traces | `/traces` | 直查入口能跳详情 |
| Skills | `/skills` | 每张卡有"近 24h 调用"数字（#6）；schema 折叠正常 |
| Runs | `/runs` | Tokens 列显示具体数字（#4）；点行抽屉里 token 分布完整 |
| System | `/system` | /api/health 内容渲染正常 |

### 7.5 SSE 流验证

新开一个真实任务，进任务详情页，观察：

- 状态徽章 `连接中... → 实时同步中`
- TraceView 的 Timeline 实时追加新事件（run_start → step_start → think_start → ...）
- 任务结束后状态变 `已结束`，没有重连尝试

### 7.6 取消任务验证

PROCESSING 任务点"取消"：

- 状态从 PROCESSING → CANCEL_REQUESTED → CANCELLED
- 取消事件出现在 trace 中

## 验收

7 个页面全部无 console 报错；SSE 流正常；提交+取消端到端 work。

发现的契约问题如不在 #1–#6 范围内，回写到本文档"附录：联调发现"段。

---

# Task #8 [P2]：frontend typecheck / lint / build

## 上下文

#1–#6 主要改后端，理论上不影响前端类型；但 #4 的 JSON 反序列化让前端拿到的是真正的 object 而非 string，可能暴露之前 mock 兼容的容忍代码。同时 build 是后端 `app.py:65-89` 静态托管的前置条件。

## 步骤

```bash
cd frontend
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
npm run build       # tsc -b && vite build → dist/
```

## 静态托管验证

```bash
# 项目根
FRONTEND_DIST_ENABLED=true hypercorn app:app -c app_config.toml
# 访问 http://127.0.0.1:6060/ 应渲染前端
```

## 验收

三条命令退出码 0；`frontend/dist/` 产出 `index.html` + `assets/`；后端单端口（6060）即可访问完整应用。

---

# 附录：联调发现（联调过程中如发现新问题在此追加）

> 这一段用来记录 #1–#6 之外、联调时新冒出来的契约 / UX 问题。每条按 `[发现日期] 文件:行 — 现象 — 修法` 写。

