# Chat 模块重构 TODO（0518）

## 背景

`src/core/chat/` 已经有 70% 实现：会话/消息表 + Repository + chat_ops 工具 + agent_task 派发 + 前端 ChatPage。但当前 `chat.agent_turn` 直接复用 `Agent.create + AgentLoopRunner`，背了完整 harness（budget/feedback_loop/improvement/context_window），不符合"轻量聊天"诉求；同时高风险工具（`run_task`）一旦被 LLM 选中就直接执行，缺少"先 propose 再 confirm"的人机协作环节。

本次重构目标是替换执行内核 + 引入工具风险分级 + 落地结构化意图确认，前端补齐流式渲染与确认卡片。

## 目标

- 新建 `ChatTurnRunner`，绕开 harness，仅复用 `LLMProvider` / `ToolSpecSerializer` / chat_ops，单文件 ~150 行
- 工具按风险（low/high）分级：low 直接执行，high 走 propose-confirm
- 消息表新增 `status` 字段，承载 `completed` / `pending_confirmation` / `rejected` / `cancelled` 状态
- 流式输出复用 `trace_event_bus`，扩展 `chat.*` 事件命名空间
- 前端识别 pending 消息渲染 PlanCard，新增 `/confirm` 调用，工具调用结果块独立渲染

## 设计核心

**ChatTurnRunner**：极简 while 循环，每轮 = LLM stream → 累积 tokens → 解析 tool_calls。无 tool_calls 落 assistant 消息收尾；有 high-risk 落 `pending_confirmation` 消息暂停；全 low-risk 直接执行后下一轮。

**风险分级**：在 `src/core/chat/risk.py` 维护 `TOOL_RISK_REGISTRY` 字典，不侵入 `@skill` 装饰器。`run_task=high`，`list_recent_tasks=low`，`plan_tasks=low`。

**Propose-Confirm**：高风险工具被选中时，runner 不执行，把 `tool_calls` 写入消息的 `tool_calls` 列 + `status=pending_confirmation` + 发 `chat.tool_call_proposed` 和 `chat.turn_paused` 事件，turn 结束。前端 PlanCard 渲染按钮，用户点确认后调 `/confirm`，后端派发新 turn 携带 `confirmed_tool_calls` 跳过 LLM 直接执行。

## 总览

| 阶段 | 编号 | 任务 | 依赖 | 预估改动 |
|------|------|------|------|---------|
| P0 | P0-1 | 数据库 schema 增量 | - | init.sql + 1 ALTER |
| P0 | P0-2 | 工具风险分级注册 | - | 新建 risk.py |
| P0 | P0-3 | ChatTurnRunner 核心 | P0-2 | 新建 runner.py |
| P0 | P0-4 | chat 事件命名空间 | - | 新建 events.py |
| P0 | P0-5 | ChatService + 改造 agent_task | P0-3,P0-4 | service.py + agent_task.py |
| P0 | P0-6 | 待确认消息落库 + 历史拼装 | P0-3 | repository.py 扩展 |
| P0 | P0-7 | /confirm API 端点 | P0-5,P0-6 | endpoints/chat.py |
| P1 | P1-1 | 前端 chat 事件订阅扩展 | P0-4 | useChatTurnStream + chatStore |
| P1 | P1-2 | PlanCard 组件 + confirm 调用 | P0-7 | 新建组件 + chat.ts |
| P1 | P1-3 | ToolCallBlock 渲染 | P1-1 | 新建组件 |
| P1 | P1-4 | 流式 token 实时拼接渲染 | P1-1 | MessageList 改造 |
| P2 | P2-1 | ChatTurnRunner 单元测试 | P0-3 | tests/ 新建 |
| P2 | P2-2 | API 端到端集成测试 | P0-7 | tests/ 新建 |
| P2 | P2-3 | 文档与 CHANGELOG | 全部 | 更新文档 |

## 全局约定

- **trace_id 格式**：沿用 `Chat-YYYYmmddHHMMSS-<16hex>`，便于和 Agent 任务区分；如 chat 沿用 `Agent-` 前缀也可以，需在 P0-3 实现里显式指定
- **事件命名**：所有 chat 事件统一 `chat.` 前缀，避免和 `agent.*` / `task.*` 混淆
- **工具失败**：tool_call 异常 → 写 role=tool 消息 `{ok: false, error}` → 进入下一轮让 LLM 自修正，不直接抛
- **取消**：`CANCEL_REQUESTED` 仍走 task_lifecycle_manager 现有机制，runner 在 LLM stream 之间检查
- **错误信息回写**：runner 顶层 except 落一条 role=assistant content=错误摘要 status=cancelled 的消息，再 publish `chat.turn_error`

---

## P0：后端核心（必须按顺序执行）

### P0-1：数据库 schema 增量

**目标**：`chat_messages` 表新增 `status` 列，支撑 pending_confirmation / rejected 状态。

**文件**：`init.sql`

**操作**：

1. 在 `chat_messages` 表定义中，`created_at` 之前新增列：
   ```sql
   status TINYINT NOT NULL DEFAULT 0 COMMENT '0=completed, 1=pending_confirmation, 2=rejected, 3=cancelled',
   ```
2. 在文件末尾追加 ALTER（兼容已有数据库）：
   ```sql
   ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS status TINYINT NOT NULL DEFAULT 0 COMMENT '0=completed, 1=pending_confirmation, 2=rejected, 3=cancelled' AFTER token_usage;
   ```

**验证**：`grep -n 'status' init.sql` 能看到新列定义。

---

### P0-2：工具风险分级注册

**目标**：新建 `src/core/chat/risk.py`，维护工具名 → 风险等级映射，不侵入 `@skill` 装饰器。

**文件**：新建 `src/core/chat/risk.py`

**内容**：

```python
from enum import IntEnum
from typing import Dict


class ToolRisk(IntEnum):
    LOW = 0
    HIGH = 1


TOOL_RISK_REGISTRY: Dict[str, ToolRisk] = {
    "plan_tasks": ToolRisk.LOW,
    "list_recent_tasks": ToolRisk.LOW,
    "run_task": ToolRisk.HIGH,
}

DEFAULT_RISK = ToolRisk.HIGH


def get_tool_risk(tool_name: str) -> ToolRisk:
    return TOOL_RISK_REGISTRY.get(tool_name, DEFAULT_RISK)


def is_high_risk(tool_name: str) -> bool:
    return get_tool_risk(tool_name) == ToolRisk.HIGH
```

**设计说明**：
- `DEFAULT_RISK = HIGH`：未注册的工具默认高风险，安全优先
- 后续新增工具只需在 `TOOL_RISK_REGISTRY` 加一行
- 不用装饰器参数是因为 chat_ops 工具可能被多个场景复用，风险等级是 chat 模块的策略而非工具本身的属性

**验证**：`python -c "from src.core.chat.risk import is_high_risk; assert is_high_risk('run_task'); assert not is_high_risk('list_recent_tasks')"`

---

### P0-3：ChatTurnRunner 核心

**目标**：新建 `src/core/chat/runner.py`，实现极简 while 循环，替代 harness。

**文件**：新建 `src/core/chat/runner.py`

**类签名**：

```python
class ChatTurnRunner:
    def __init__(
        self,
        llm_provider: LLMProvider,
        tools: List[Skill],
        trace_id: str,
        event_bus: TraceEventBus,
        cancel_checker: Callable[[], Awaitable[bool]],
    ):
        ...

    async def run(
        self,
        messages: List[Dict],
        system_prompt: str,
        *,
        confirmed_tool_calls: Optional[List[Dict]] = None,
    ) -> ChatTurnResult:
        ...
```

**核心逻辑（伪代码）**：

```python
async def run(self, messages, system_prompt, *, confirmed_tool_calls=None):
    # 如果是 confirm 续跑，跳过 LLM，直接执行已确认的 tool_calls
    if confirmed_tool_calls:
        tool_results = await self._execute_tools(confirmed_tool_calls)
        messages = messages + [tool_call_msg, *tool_result_msgs]
        # 继续进入正常循环让 LLM 看到结果

    max_iterations = 10  # 防无限循环
    for _ in range(max_iterations):
        # 1. 检查取消
        if await self.cancel_checker():
            return ChatTurnResult(status="cancelled", content="")

        # 2. 调 LLM（流式）
        full_content, tool_calls = await self._stream_llm(messages, system_prompt)

        # 3. 无 tool_calls → 结束
        if not tool_calls:
            await self._publish("chat.turn_end", {"content": full_content})
            return ChatTurnResult(status="completed", content=full_content)

        # 4. 有 tool_calls → 分级
        high_risk = [tc for tc in tool_calls if is_high_risk(tc["function"]["name"])]
        low_risk = [tc for tc in tool_calls if not is_high_risk(tc["function"]["name"])]

        if high_risk:
            # 暂停，等用户确认
            await self._publish("chat.tool_call_proposed", {"tool_calls": tool_calls})
            await self._publish("chat.turn_paused", {})
            return ChatTurnResult(
                status="pending_confirmation",
                content=full_content,
                proposed_tool_calls=tool_calls,
            )

        # 5. 全 low-risk → 直接执行
        tool_results = await self._execute_tools(tool_calls)
        messages = messages + [
            {"role": "assistant", "content": full_content, "tool_calls": tool_calls},
            *tool_results,
        ]
        # 继续循环

    return ChatTurnResult(status="completed", content="达到最大迭代次数")
```

**内部方法**：

- `_stream_llm(messages, system_prompt)` → 调 `self.llm_provider.stream_chat()`，逐 chunk 发 `chat.token_delta` 事件，累积 content + tool_calls
- `_execute_tools(tool_calls)` → 遍历 tool_calls，查找对应 Skill 执行，发 `chat.tool_call_start` / `chat.tool_call_end` 事件，返回 role=tool 消息列表
- `_publish(event_type, data)` → `self.event_bus.publish(self.trace_id, event_type, data, source="chat")`

**ChatTurnResult 数据类**：

```python
@dataclass
class ChatTurnResult:
    status: str  # "completed" | "pending_confirmation" | "cancelled"
    content: str
    proposed_tool_calls: Optional[List[Dict]] = None
    tool_call_results: Optional[List[Dict]] = None
    token_usage: Optional[Dict] = None
```

**关键设计决策**：
- `max_iterations=10`：防止 LLM 反复调低风险工具死循环
- 高风险工具出现时**整批暂停**（不拆分执行 low-risk 部分），因为 LLM 的 tool_calls 可能有逻辑依赖
- `confirmed_tool_calls` 入参让 confirm 续跑不需要重新调 LLM
- 不做 budget 计费，但 `token_usage` 累积返回，由上层决定是否记录

**验证**：写完后 `ruff check src/core/chat/runner.py` 无报错。

---

### P0-4：chat 事件命名空间

**目标**：新建 `src/core/chat/events.py`，定义 chat 专用事件类型常量 + 辅助发布函数。

**文件**：新建 `src/core/chat/events.py`

**内容**：

```python
class ChatEventType:
    TOKEN_DELTA = "chat.token_delta"
    TOOL_CALL_START = "chat.tool_call_start"
    TOOL_CALL_END = "chat.tool_call_end"
    TOOL_CALL_PROPOSED = "chat.tool_call_proposed"
    TURN_PAUSED = "chat.turn_paused"
    TURN_END = "chat.turn_end"
    TURN_ERROR = "chat.turn_error"
```

**事件 payload 规范**：

| 事件 | data 字段 |
|------|-----------|
| `chat.token_delta` | `{"delta": "增量文本", "accumulated": "已累积全文"}` |
| `chat.tool_call_start` | `{"tool_name": "xxx", "arguments": {...}, "call_id": "xxx"}` |
| `chat.tool_call_end` | `{"tool_name": "xxx", "call_id": "xxx", "result": {...}, "ok": true/false}` |
| `chat.tool_call_proposed` | `{"tool_calls": [...], "reason": "LLM 给出的理由"}` |
| `chat.turn_paused` | `{}` |
| `chat.turn_end` | `{"content": "最终回复", "token_usage": {...}}` |
| `chat.turn_error` | `{"error": "错误摘要"}` |

**验证**：`python -c "from src.core.chat.events import ChatEventType; print(ChatEventType.TOKEN_DELTA)"`

---

### P0-5：ChatService + 改造 agent_task

**目标**：新建 `src/core/chat/service.py` 作为 chat 模块的门面，改造 `agent_task.py` 使用 `ChatTurnRunner`。

**文件**：
- 新建 `src/core/chat/service.py`
- 修改 `src/core/chat/agent_task.py`

#### service.py

```python
class ChatService:
    def __init__(self, db, log, config, event_bus, task_invoker):
        self.repo = ChatRepository(db)
        self.log = log
        self.config = config
        self.event_bus = event_bus
        self.task_invoker = task_invoker

    async def start_turn(self, conversation_id: str, user_message: str) -> str:
        """发消息，派发 chat.agent_turn 任务，返回 trace_id"""
        ...

    async def confirm_plan(self, conversation_id: str, message_id: int, action: str) -> Optional[str]:
        """
        action = "confirm" | "reject"
        confirm: 取出 pending 消息的 tool_calls，派发新 turn 携带 confirmed_tool_calls
        reject: 更新消息 status=rejected，落一条 assistant 消息说"好的，已取消"
        返回新 trace_id（confirm 时）或 None（reject 时）
        """
        ...

    async def cancel_turn(self, conversation_id: str, trace_id: str):
        """取消正在运行的 turn"""
        ...
```

#### agent_task.py 改造

**核心变更**：
1. 删除 `Agent.create()` + `agent.run()` 调用
2. 替换为：
   ```python
   from src.core.chat.runner import ChatTurnRunner, ChatTurnResult
   from src.core.agents.capabilities.llm.base import LLMProvider
   from src.core.agents.capabilities.tools.loader import load_agentic_tools

   # 构建 runner
   provider = create_llm_provider(config)  # 复用现有 provider 工厂
   tools = load_agentic_tools(["chat_ops", "task"])
   runner = ChatTurnRunner(
       llm_provider=provider,
       tools=tools,
       trace_id=trace_id,
       event_bus=event_bus,
       cancel_checker=cancel_checker,
   )

   # 运行
   result = await runner.run(messages, system_prompt, confirmed_tool_calls=confirmed)
   ```
3. 根据 `result.status` 落不同状态的消息：
   - `completed` → `status=0` 正常消息
   - `pending_confirmation` → `status=1` + `tool_calls=result.proposed_tool_calls`
   - `cancelled` → `status=3`

**系统 prompt 设计**（写在 agent_task.py 或独立 `src/core/chat/prompts.py`）：

```python
CHAT_SYSTEM_PROMPT = """你是 TaskPilot 助手。你的职责是：
1. 理解用户意图，用自然语言回答问题
2. 当用户需要执行操作时，使用可用工具完成
3. 对于查询类操作（list_recent_tasks），直接执行并汇报结果
4. 对于执行类操作（run_task），说明你打算做什么、为什么，然后调用工具

可用工具会自动提供。你不需要解释工具的存在，只需在合适时机使用它们。
保持回复简洁、有帮助。用中文回复。"""
```

**验证**：
- `ruff check src/core/chat/service.py src/core/chat/agent_task.py`
- 确认 `agent_task.py` 不再 import `Agent` / `AgentLoopRunner` / `AgentLoopHarness`

---

### P0-6：待确认消息落库 + 历史拼装

**目标**：扩展 `ChatRepository`，支持 status 字段读写 + 历史消息拼装时正确处理 pending 消息。

**文件**：修改 `src/core/chat/repository.py`

**变更**：

1. `append_message()` 新增 `status: int = 0` 参数，INSERT 时写入
2. `update_message_status(message_id: int, status: int)` — 新方法，用于 confirm/reject 时更新
3. `get_pending_message(conversation_id: str) -> Optional[Dict]` — 查最新 status=1 的消息
4. `build_llm_messages(conversation_id: str) -> List[Dict]` — 新方法，从 chat_messages 拼装 LLM 格式消息列表：
   - role=user → `{"role": "user", "content": ...}`
   - role=assistant + tool_calls → `{"role": "assistant", "content": ..., "tool_calls": [...]}`
   - role=tool → `{"role": "tool", "tool_call_id": ..., "content": ...}`
   - status=pending_confirmation 的消息**不**包含在历史中（因为还没执行）
   - status=rejected 的消息包含，但 tool_calls 不传（让 LLM 知道用户拒绝了）

**验证**：
- `ruff check src/core/chat/repository.py`
- 确认 `build_llm_messages` 返回的列表格式符合 OpenAI messages 规范

---

### P0-7：/confirm API 端点

**目标**：在 `src/api/v1/endpoints/chat.py` 新增 confirm 端点。

**文件**：修改 `src/api/v1/endpoints/chat.py`

**新增路由**：

```python
@bp.route("/conversations/<conversation_id>/confirm", methods=["POST"])
async def confirm_plan(conversation_id: str):
    """
    Body: {"message_id": int, "action": "confirm" | "reject"}
    Response:
      - confirm: {"code": 0, "trace_id": "xxx"}
      - reject: {"code": 0}
      - 无 pending 消息: {"code": 404, "message": "no pending plan"}
    """
    ...
```

**逻辑**：
1. 校验 body 参数
2. 调 `chat_service.confirm_plan(conversation_id, message_id, action)`
3. confirm 时返回新 trace_id（前端用来订阅 SSE）
4. reject 时返回 code=0，前端可选择性展示"已取消"

**验证**：
- `ruff check src/api/v1/endpoints/chat.py`
- 手动 curl 测试（需要先有 pending 消息）

---

### P0-8：更新 `__init__.py` 导出 + DI 注册

**目标**：把新增的类注册到模块导出和 DI 容器。

**文件**：
- 修改 `src/core/chat/__init__.py` — 新增导出 `ChatService`, `ChatTurnRunner`, `ChatTurnResult`, `ToolRisk`, `ChatEventType`
- 修改 `src/core/dependency/container.py` — 新增 `chat_service` 单例

**DI 注册**：

```python
chat_service = providers.Singleton(
    ChatService,
    db=async_mysql_pool,
    log=log_service,
    config=config,
    event_bus=trace_event_bus,
    task_invoker=...,  # 需要看 TaskInvoker 的依赖
)
```

**验证**：`python -c "from src.core.chat import ChatService, ChatTurnRunner"`

---

## P1：前端改造

### P1-1：chat 事件订阅扩展

**目标**：扩展 `useChatTurnStream` hook 和 `chatStore`，识别新的 `chat.*` 事件类型。

**文件**：
- 修改 `frontend/src/hooks/useChatTurnStream.ts`
- 修改 `frontend/src/stores/chatStore.ts`

**useChatTurnStream 变更**：

当前 hook 已经监听 `/api/task_events/<trace_id>` 并回调 `onEvent`。需要确保以下事件类型被正确分发：

```typescript
// 新增事件类型常量
export const CHAT_EVENTS = {
  TOKEN_DELTA: 'chat.token_delta',
  TOOL_CALL_START: 'chat.tool_call_start',
  TOOL_CALL_END: 'chat.tool_call_end',
  TOOL_CALL_PROPOSED: 'chat.tool_call_proposed',
  TURN_PAUSED: 'chat.turn_paused',
  TURN_END: 'chat.turn_end',
  TURN_ERROR: 'chat.turn_error',
} as const;
```

**chatStore 变更**：

1. 新增状态字段：
   ```typescript
   interface ChatState {
     // 已有
     liveSegment: string;        // 流式累积文本
     inFlight: boolean;          // 是否有 turn 在跑
     activeTraceId: string | null;

     // 新增
     pendingPlan: PendingPlan | null;  // 当前待确认的 plan
     liveToolCalls: ToolCallStatus[];  // 正在执行的工具调用
   }

   interface PendingPlan {
     messageId: number;
     toolCalls: ToolCall[];
     reason: string;
   }

   interface ToolCallStatus {
     callId: string;
     toolName: string;
     arguments: Record<string, unknown>;
     status: 'running' | 'completed' | 'failed';
     result?: unknown;
   }
   ```

2. `handleLiveEvent(event)` 扩展分支：
   ```typescript
   switch (event.type) {
     case 'chat.token_delta':
       set({ liveSegment: get().liveSegment + event.data.delta });
       break;
     case 'chat.tool_call_start':
       set({ liveToolCalls: [...get().liveToolCalls, { ...event.data, status: 'running' }] });
       break;
     case 'chat.tool_call_end':
       // 更新对应 callId 的状态
       break;
     case 'chat.tool_call_proposed':
       set({ pendingPlan: { toolCalls: event.data.tool_calls, ... } });
       break;
     case 'chat.turn_paused':
       set({ inFlight: false });
       break;
     case 'chat.turn_end':
       // 落消息到 activeMessages，清空 liveSegment
       break;
     case 'chat.turn_error':
       // 落错误消息，清空状态
       break;
   }
   ```

3. 新增 action：
   ```typescript
   confirmPlan: async (action: 'confirm' | 'reject') => { ... }
   ```

**验证**：`cd frontend && npx tsc --noEmit` 无类型错误。

---

### P1-2：PlanCard 组件 + confirm 调用

**目标**：新建 `frontend/src/components/chat/PlanCard.tsx`，渲染待确认的工具调用计划，提供确认/拒绝按钮。

**文件**：新建 `frontend/src/components/chat/PlanCard.tsx`

**组件设计**：

```tsx
interface PlanCardProps {
  plan: PendingPlan;
  onConfirm: () => void;
  onReject: () => void;
  loading: boolean;
}

// 渲染内容：
// 1. 标题："我打算执行以下操作"
// 2. 工具调用列表（每个 tool_call 一行）：
//    - 工具名（Tag 样式）
//    - 参数摘要（JSON 折叠展示）
// 3. 底部按钮组：[确认执行] [取消]
// 4. loading 状态：确认后按钮 disabled + spinner
```

**样式**：
- 使用 Ant Design `Card` + `Tag` + `Button` + `Collapse`
- 卡片背景色区分于普通消息（浅黄或浅蓝）
- 按钮：确认用 `type="primary"`，取消用 `default`

**API 调用**：新增 `frontend/src/api/chat.ts`：

```typescript
export async function confirmChatPlan(
  conversationId: string,
  messageId: number,
  action: 'confirm' | 'reject'
): Promise<{ code: number; trace_id?: string }> {
  const res = await client.post(
    `/chat/conversations/${conversationId}/confirm`,
    { message_id: messageId, action }
  );
  return res.data;
}
```

**验证**：
- `npx tsc --noEmit`
- 手动在 ChatPage 中触发 pending 状态，确认 PlanCard 渲染正确

---

### P1-3：ToolCallBlock 渲染组件

**目标**：新建 `frontend/src/components/chat/ToolCallBlock.tsx`，在消息流中渲染工具调用的执行过程和结果。

**文件**：新建 `frontend/src/components/chat/ToolCallBlock.tsx`

**组件设计**：

```tsx
interface ToolCallBlockProps {
  toolCall: ToolCallStatus;
}

// 渲染内容：
// 1. 工具名 Tag + 状态指示器（running=spinner, completed=✓, failed=✗）
// 2. 参数区域（可折叠 JSON）
// 3. 结果区域（completed 时展示，可折叠）
// 4. 错误区域（failed 时展示，红色文本）
```

**集成位置**：在 `MessageList` 组件中，当消息有 `tool_calls` 字段时，在消息文本下方渲染 `ToolCallBlock` 列表。

**验证**：`npx tsc --noEmit`

---

### P1-4：流式 token 实时拼接渲染

**目标**：改造 `MessageList` 组件，在 turn 进行中实时渲染 `liveSegment`。

**文件**：修改 `frontend/src/components/chat/MessageList.tsx`（或对应文件名）

**变更**：

1. 在消息列表末尾，当 `inFlight && liveSegment` 时，渲染一个"正在输入"的 assistant 消息气泡：
   ```tsx
   {inFlight && liveSegment && (
     <MessageBubble role="assistant" content={liveSegment} streaming />
   )}
   ```

2. `streaming` prop 控制：
   - 显示闪烁光标（CSS animation）
   - 不显示时间戳
   - 不显示操作按钮（复制等）

3. 当 `liveToolCalls` 非空时，在流式消息下方渲染 `ToolCallBlock` 列表

4. 当 `pendingPlan` 非空时，在消息列表末尾渲染 `PlanCard`

5. 自动滚动到底部：每次 `liveSegment` 更新时 scrollToBottom

**验证**：
- `npx tsc --noEmit`
- 启动 dev server，发送消息，确认流式文本实时出现
- 触发工具调用，确认 ToolCallBlock 渲染
- 触发高风险工具，确认 PlanCard 出现

---

### P1-5：前端类型定义更新

**目标**：更新 `frontend/src/api/types.ts`，新增 chat 相关类型。

**文件**：修改 `frontend/src/api/types.ts`

**新增类型**：

```typescript
export interface ChatMessage {
  // 已有字段...
  status: 0 | 1 | 2 | 3;  // 新增：0=completed, 1=pending_confirmation, 2=rejected, 3=cancelled
}

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string;  // JSON string
  };
}

export interface ConfirmPlanRequest {
  message_id: number;
  action: 'confirm' | 'reject';
}

export interface ConfirmPlanResponse {
  code: number;
  message?: string;
  trace_id?: string;
}
```

**验证**：`npx tsc --noEmit`

---

## P2：测试与文档

### P2-1：ChatTurnRunner 单元测试

**目标**：测试 runner 的核心分支逻辑。

**文件**：新建 `tests/core/chat/test_runner.py`

**测试用例**：

1. `test_simple_reply_no_tools` — LLM 返回纯文本，无 tool_calls → status=completed
2. `test_low_risk_tool_execution` — LLM 返回 `list_recent_tasks` → 直接执行 → 下一轮 LLM 返回文本 → completed
3. `test_high_risk_tool_pauses` — LLM 返回 `run_task` → status=pending_confirmation + proposed_tool_calls
4. `test_confirmed_tool_calls_skip_llm` — 传入 `confirmed_tool_calls` → 直接执行 → 继续循环
5. `test_cancel_during_stream` — cancel_checker 返回 True → status=cancelled
6. `test_tool_execution_error` — 工具抛异常 → 写 error 结果 → 下一轮 LLM 自修正
7. `test_max_iterations_guard` — 连续 10 轮都有 low-risk tool_calls → 到达上限退出

**Mock 策略**：
- `LLMProvider` → mock `stream_chat()` 返回预设 chunks
- `TraceEventBus` → mock `publish()` 记录调用
- `cancel_checker` → mock callable
- 工具执行 → mock Skill 对象

**验证**：`pytest tests/core/chat/test_runner.py -v` 全绿。

---

### P2-2：API 端到端集成测试

**目标**：测试 chat 端点的完整流程。

**文件**：新建 `tests/api/test_chat_endpoints.py`

**测试用例**：

1. `test_send_message_triggers_turn` — POST /messages → 返回 trace_id → 任务被派发
2. `test_confirm_plan_triggers_execution` — 先制造 pending 消息 → POST /confirm action=confirm → 返回新 trace_id
3. `test_reject_plan_updates_status` — POST /confirm action=reject → 消息 status 变为 2
4. `test_confirm_nonexistent_returns_404` — 无 pending 消息时 confirm → 404
5. `test_cancel_turn` — POST /cancel → 任务被取消

**验证**：`pytest tests/api/test_chat_endpoints.py -v` 全绿。

---

### P2-3：文档更新

**目标**：更新项目文档反映 chat 模块新架构。

**文件**：
- 修改 `CLAUDE.md` — 在"Agent Loop 结构"后新增"Chat Loop 结构"小节
- 修改 `src/core/chat/__init__.py` 的模块 docstring

**CLAUDE.md 新增内容**：

```markdown
### Chat Loop 结构（轻量对话）

```
ChatService.start_turn → chat.agent_turn task → ChatTurnRunner
  → Stream LLM → 解析 tool_calls
  → 无 tool → 落消息 → END
  → low-risk tool → 执行 → 下一轮
  → high-risk tool → 落 pending_confirmation → PAUSE
  → /confirm → 续跑 confirmed_tool_calls → 执行 → 下一轮
```

与 Agent Loop 的区别：
- 不走 harness（无 budget/feedback_loop/improvement/context_window）
- 工具风险分级 + propose-confirm 人机协作
- 直接复用 LLMProvider / ToolSpecSerializer / TraceEventBus
```

**验证**：文档内容与实际实现一致。

---

## 执行顺序与依赖图

```
P0-1 (schema) ─────────────────────────────────────────┐
P0-2 (risk.py) ──────────┐                             │
P0-4 (events.py) ────────┤                             │
                          ├─→ P0-3 (runner.py) ────────┤
                          │                             ├─→ P0-5 (service + agent_task)
P0-6 (repository 扩展) ──┘─────────────────────────────┘         │
                                                                   ├─→ P0-7 (/confirm)
                                                                   └─→ P0-8 (__init__ + DI)
                                                                              │
P1-5 (types.ts) ──────────────────────────────────────────────────────────────┤
                                                                              │
P1-1 (事件订阅) ──→ P1-4 (流式渲染) ──→ P1-2 (PlanCard) ──→ P1-3 (ToolCallBlock)
                                                                              │
P2-1 (runner 测试) ──→ P2-2 (API 测试) ──→ P2-3 (文档)
```

**可并行的任务**：
- P0-1 / P0-2 / P0-4 三者无依赖，可并行
- P1-5 可与 P0 阶段并行
- P2-1 可在 P0-3 完成后立即开始

---

## 注意事项（给执行 agent 的提醒）

1. **不要改 `src/core/agents/` 下的任何文件**——chat 模块是独立路径，不侵入 agent 引擎
2. **LLMProvider 的 `stream_chat` 方法**——先读 `src/core/agents/capabilities/llm/base.py` 确认方法签名和返回类型，runner 要适配
3. **ToolSpecSerializer**——先读 `src/core/agents/engine/prompting/assembler.py` 看工具如何序列化为 LLM 格式，runner 需要复用同样的序列化逻辑
4. **chat_ops 工具的执行方式**——先读 `src/core/agents/capabilities/tools/chat_ops.py` 看 Skill 对象的 `execute()` 方法签名
5. **trace_event_bus.publish 的参数**——先读 `src/infra/streaming/trace_event_bus.py` 确认 publish 签名
6. **前端 SSE 端点路径**——当前是 `/api/task_events/<trace_id>`，chat 复用同一端点，不需要新建
7. **消息 role 值**——数据库存的是字符串 `"user"` / `"assistant"` / `"tool"`，和 OpenAI 格式一致
8. **confirmed_tool_calls 的传递**——通过 task payload 传入 agent_task，再传给 runner。需要在 task_utils 或 agent_task 的 payload 解析中支持这个字段
