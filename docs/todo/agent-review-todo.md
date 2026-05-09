---
title: Agent 模块待优化清单
module: src/core/agents
status: draft
created: 2026-05-09
owner: luojunhui
---

# Agent 模块待优化清单

本文档汇总对 `src/core/agents/` 模块的 review 结论，按"正确性 Bug → 架构设计 → 边界/性能 → 结构可维护性 → 安全/运维"分层列出，供后续迭代时按 ROI 排期。

每条包含：
- **位置**：文件:行
- **问题**：现状描述
- **影响**：实际会发生什么
- **建议**：可落地的修复方向

---

## P0 · 正确性 Bug（先修）

### 1. `util_timestamp_to_str` 参数名不匹配，调用必崩
- **位置**：`capabilities/tools/utils.py:48,56`
- **问题**：schema 声明参数是 `format`，但 handler 签名是 `date_format`。
- **影响**：LLM 按 schema 传 `format` → 通过 `ParameterValidator` → `handler(ctx, **params)` 抛 `TypeError: got unexpected keyword 'format'`。
- **建议**：把 schema 的 `format` 改为 `date_format`（注意 `format` 是内置名，尽量避免）。

### 2. `CapabilityRegistry.list_skills` 调用不存在的方法
- **位置**：`capabilities/registry.py:50`
- **问题**：`self._skill_registry.list(**filters)` 而 `SkillRegistry` 只有 `filter / list_executable / list_knowledge / list_by_tags`。
- **影响**：任何使用 `CapabilityRegistry.list_skills` 的路径直接 `AttributeError`。
- **建议**：统一调用 `filter(predicate)` 或补齐 `SkillRegistry.list(**filters)`。

### 3. Claude Provider 丢 `tool_calls` / `tool_call_id`
- **位置**：`capabilities/llm/providers/claude.py:160-165`
- **问题**：`_convert_message` 仅保留 `role` 与 `content`，直接丢弃 `tool_calls` 和 `tool_call_id`。
- **影响**：进入多轮工具调用后 Claude 收不到 `tool_use`/`tool_result` 内容块，对话链路断裂。
- **建议**：把 OpenAI 风格的 tool 消息翻译成 Claude 的 `tool_use` / `tool_result` 内容块（`content: [{type: "tool_use", id, name, input}, ...]`）。

### 4. `ContextWindowManager` 压缩会产生孤儿 tool 消息
- **位置**：`state/context/manager.py:_truncate_middle`
- **问题**：按顺序从尾部保留消息，不感知 `assistant(tool_calls)` 与 `tool(tool_call_id)` 的配对关系。
- **影响**：压缩后若只留 tool 结果没有 assistant，OpenAI/DeepSeek 返回 400；Claude 拒绝。
- **建议**：以「tool-call 对」为原子单位整组保留或丢弃；或在压缩后做一次孤儿检测并清理。

### 5. `Observe.run` 在 content 为 None 时仍视为成功
- **位置**：`engine/loop.py:215-218`
- **问题**：无 tool_calls 直接赋值 `final_answer=content` + `MODEL_FINAL`，空/None 也当成功。
- **影响**：LLM "放弃"输出时被标记为成功，`AgentLoopResult.success=True` 但 `final_answer=None`。
- **建议**：判"无工具调用且内容为空"为 `LLM_ERROR_ABORT` 或新增 `EMPTY_RESPONSE` StopReason。

### 6. `SkillExecutor.retry` 不区分错误种类
- **位置**：`capabilities/skills/executor.py:101-108`
- **问题**：所有异常都重试（包括 `ValueError`、权限拒绝、SQL 过滤拒绝）。
- **影响**：参数错/权限错浪费 N 次调用。
- **建议**：引入 `retryable_exceptions=(asyncio.TimeoutError, aiohttp.ClientError, ...)` 白名单；非白名单直接抛。

### 7. HTTP SSRF 防护 naive，易绕过
- **位置**：`capabilities/tools/http.py:_validate_url`
- **问题**：字符串前缀判断，不挡 DNS rebinding / IPv6 私网 / 数字 host / URL 编码绕过。
- **影响**：攻击者可诱使 Agent 访问内网服务（metadata、数据库、Redis）。
- **建议**：
  - 解析域名 → `socket.gethostbyname` → `ipaddress.ip_address(...).is_private | is_loopback | is_link_local` 全量判断
  - IPv6 加上 `fc00::/7` / `fe80::/10` / `::1`
  - aiohttp 层用自定义 `AsyncResolver` 拒绝解析到内网的请求

### 8. SQL 过滤仅黑名单正则
- **位置**：`capabilities/skills/sql_filter.py`
- **问题**：`CREATE TEMPORARY TABLE` / `LOAD DATA INFILE` 等未覆盖；注释剥离非完备。
- **影响**：潜在数据泄漏、库外 IO。
- **建议**：
  - 短期补全黑名单
  - 长期靠 DB 账号权限做白名单（只读账号跑 `db_query`）
  - 使用 `sqlparse` 做 AST 级别校验

### 9. `write_file` 路径校验存在绕过
- **位置**：`capabilities/tools/utils.py:130-159`
- **问题**：
  - 字符串 `startswith` 不抗符号链接
  - 用户 home 下敏感路径未覆盖（`.bash_history / .kube / .docker / .npmrc`）
  - 没有"只允许项目根目录下写入"的 policy
- **建议**：
  - 改为「允许根目录白名单」+ `Path.resolve()` 保证在白名单内
  - `os.path.realpath` 后对比 `commonpath`

---

## P1 · 架构 / 设计

### 10. "Agent 隔离"是假的 —— 全局 skill registry 造成跨实例污染
- **位置**：`engine/agent.py:create`（`get_global_registry()`）
- **问题**：多 Agent 共用全局 registry，A 注册的业务 skill 会被 B 看见；`permission_guard` 类似。
- **影响**：多租户/多 Agent 编排下隔离失效。
- **建议**：`Agent` 持有本地 registry；global 仅作 bootstrap 源；`load_agentic_tools` 支持注入目标 registry。

### 11. 已 deprecated 类仍顶层导出
- **位置**：`agents/__init__.py:73,78,150,156`
- **问题**：`HarnessRunner`、`RunnerConfig`、`Dispatcher` 已标注 deprecated，但仍在 `__all__`。
- **建议**：从 `__init__.py` 删除；保留源文件一段时间以便下游迁移。

### 12. 权限检查两处重复
- **位置**：`engine/loop.py:163` 与 `capabilities/skills/executor.py:72-78`
- **问题**：职责混乱；`Agent.create` 构造的 `SkillExecutor` 从不传 guard，后者是死路径。
- **建议**：只保留在 `SkillExecutor` 一层；`Act` 不再检查。

### 13. `stream_sink` 定义但未接线
- **位置**：`engine/loop.py:36`
- **问题**：Think 有字段，Agent → Runner → Harness → Think 链路从未传递。
- **建议**：沿链路贯通到 Provider 层；或删除假接口。

### 14. `run_with_routing` 独立主循环外，不受总预算约束
- **位置**：`engine/runner.py:148`
- **问题**：每个子目标独立 `self.run()`，重置 `max_steps` / `max_tool_calls` / `max_duration_seconds`。
- **影响**：总预算被 ×N 放大。
- **建议**：子调用间共享 `AgentBudget`（把 remaining 往下传），或文档上明确 routing 会叠加预算。

### 15. 全局单例并发不安全
- **位置**：`skills/registry.py:98` / `capabilities/registry.py:63`
- **问题**：懒加载无锁。
- **建议**：`threading.Lock`，或在框架 bootstrap 阶段一次性完成注册。

### 16. 双层 Registry 冗余
- **位置**：`capabilities/registry.py:CapabilityRegistry` vs `skills/registry.py:SkillRegistry`
- **问题**：`CapabilityRegistry` 把 tool 变成 Skill 再注册，仓库内无真实使用方。
- **建议**：二选一保留；删除未被使用的抽象层。

### 17. `Agent.create` 方法体近 200 行
- **位置**：`engine/agent.py:142-339`
- **问题**：classmethod 内联了 provider/planner 工厂/schema 转换/runner/lifecycle。
- **建议**：
  - `planner_factory` 里的 schema 转换（259-292 行）复用现有 `ToolSpecSerializer`
  - 拆分：`_build_provider()` / `_build_planner()` / `_build_runner()`

### 18. `exceptions.py` 异常体系未贯彻
- **位置**：`exceptions.py` + `engine/loop.py:_record_error`
- **问题**：定义了 `ToolExecutionError / ToolNotFoundError / LLMTimeoutError / LLMResponseError` 但几乎没被 raise；`Act` 用字符串，`SkillExecutor` 抛自定义异常。
- **建议**：统一 raise 路径；让所有 tool/LLM 错误继承自 `AgentError` 层级。

### 19. `Lifecycle` 和 `Harness` 的 loop_state 双向同步
- **位置**：`engine/agent.py:run` 与 `harness/harness.py:run`
- **问题**：两处都会 `transition_to(RUNNING)`，harness 注释明确暴露耦合。
- **建议**：单一事实源（推荐 harness），`Agent.run` 只传参。

---

## P1 · 边界与性能

### 20. `Act.run` 并发执行无上限
- **位置**：`engine/loop.py:145-146`
- **问题**：`asyncio.gather(*tasks)` 无 Semaphore，一次返回 10 个 db_query 直接打爆 DB 池。
- **建议**：配置 `max_concurrency`，`asyncio.Semaphore` 控制。

### 21. Provider 层每次新开 `aiohttp.ClientSession`
- **位置**：`openai.py:48` / `deepseek.py:47` / `claude.py:58`
- **问题**：连接池无沉淀，每次 TCP/TLS 握手。
- **建议**：Provider 构造时持有 session（生命周期随 Agent），或全局 shared connector + `async_close()`。

### 22. 暂停/停止检查粒度太粗
- **位置**：`runtime/harness/harness.py:137-148`
- **问题**：只在 step 起点检查；Think（几十秒 LLM）和 Act（长 tool）中不检查。
- **影响**：用户按下暂停至少要等到下个 step。
- **建议**：把 `is_cancelled` / `wait_if_paused` 传入 Actor，在 tool 执行前后都检查；Think 里也支持 cancel。

### 23. TokenCounter 不跟随 Agent 配置
- **位置**：`engine/runner.py:80-82`
- **问题**：`ContextWindowManager` 默认 `model="gpt-4o"`，无论实际用 DeepSeek/Claude。
- **建议**：构造时把 `config.llm_model` 传下来。

### 24. `PromptAssembler` 按字符截断
- **位置**：`engine/prompting/assembler.py:39-41`
- **问题**：`4 chars/token` 估算 + 字符截断，中文误差大；截断的是结尾（关键 knowledge）。
- **建议**：用 `TokenCounter` 精确截断；按 section 优先级丢弃（先丢 error hint / knowledge，保留 goal/budget）。

### 25. `MessageBus.send` 中 `asyncio.create_task` 未保活
- **位置**：`multi_agents/bus.py:121-125`
- **问题**：任务丢进 loop 无强引用，可能被 GC。
- **建议**：内部持有一个 `Set[Task]`，`task.add_done_callback(self._tasks.discard)`。

### 26. `LongTermMemory._save` 同步阻塞事件循环
- **位置**：`state/memory/long_term.py:102-123`
- **问题**：`store / delete / clear` 内直接同步 `json.dump`。
- **建议**：`aiofiles` 或 `asyncio.to_thread`。

### 27. `StateSnapshot.save` 不限制尺寸
- **位置**：`state/snapshot.py`
- **问题**：整个 messages 和 tool_outputs 原样落地，大 tool 输出可达 MB 级。
- **建议**：
  - tool_output 截断（复用 `max_tool_result_length`）
  - 大字段分片或独立文件
  - 提供 GC 策略（保留最近 N 个 snapshot）

### 28. `consecutive_tool_errors` 不适配并行调用
- **位置**：`engine/loop.py:222-228`
- **问题**：并行执行时只要有一条成功就清零，容易掩盖持续失败。
- **建议**：按 per-tool 统计；或"本步全部失败才 ++"。

### 29. `Act._execute_one` 的宽泛 except
- **位置**：`engine/loop.py:188-190`
- **问题**：`except Exception` 吞掉所有异常（含 `asyncio.CancelledError` 在 Py≤3.7 是 Exception 子类）。
- **建议**：
  ```python
  except asyncio.CancelledError:
      raise
  except Exception as e:
      ...
  ```
  保留 traceback 到日志，tool_result 返回 `error_class` + 简短 msg。

---

## P2 · 结构可维护性

### 30. `OpenAIAdapter` 与 `ClaudeAdapter` 重复率 >90%
- **位置**：`capabilities/skills/serializer.py:29-106`
- **建议**：抽 `_build_json_schema(skill) -> dict` 共享，两个 adapter 只管字段名差异。

### 31. `StateSnapshot.save` 手写 dict 化
- **位置**：`state/snapshot.py:51-100`
- **问题**：dataclass 序列化与模型演进脱钩；schema_version=2 无版本路由逻辑。
- **建议**：
  - 为 `AgentLoopState / Step / ToolCallRecord` 加 `to_dict/from_dict`
  - 或 `dataclasses.asdict()` + 自定义 encoder（枚举、datetime）
  - 补齐 schema 版本迁移框架

### 32. KnowledgeSelector 纯关键词匹配
- **位置**：`engine/prompting/knowledge_selector.py:14-37`
- **问题**：硬编码 `_DOMAIN_KEYWORDS`；扩展新 domain 要改源码。
- **建议**：
  - 短期：外挂配置文件 / 自动从 skill.tags 汇总
  - 长期：embedding 向量检索 Top-K

### 33. `MultiAgentCoordinator._decompose_task` 任选第一个 Agent
- **位置**：`multi_agents/coordinator.py:139`
- **问题**：`list(self.agents.values())[0]`，若首个 Agent 不具备分解能力直接崩。
- **建议**：显式指定 `planner_agent_id`，或按 capability tag 匹配。

### 34. `FeedbackLoop._normalize` 默认 `role=system`
- **位置**：`runtime/harness/feedback.py:46`
- **问题**：多 system 消息在 OpenAI 上行为未定义。
- **建议**：默认 `role: user, name: "feedback"`。

### 35. `ContinuousImprovement` 形同空壳
- **位置**：`runtime/harness/improvement.py`
- **问题**：默认 `store=None` → `capture` 直接返回 None。
- **建议**：要么默认 `InMemoryImprovementStore`，要么不在 harness 里调用。

### 36. `AgentLoopState.messages / tool_calls / steps` 三份数据冗余
- **位置**：`state/models.py:AgentLoopState`
- **问题**：wire state 和 trace state 混在一起，同步易错。
- **建议**：
  - `messages`：仅当前发给 LLM 的窗口（压缩后）
  - `tool_calls + steps`：不可变历史
  - 显式区分两者

---

## P2 · 安全/运维

### 37. Token usage 从不聚合
- **位置**：`LLMResponse.usage` 存在，但 `AgentLoopResult` 里无累计字段
- **问题**：无法做 billing、配额、成本观察
- **建议**：`AgentLoopResult` 新增 `token_usage: {prompt, completion, total}`，每步 accumulate。

### 38. 日志泄漏风险
- **位置**：`runtime/harness/logging.py` verbose 模式
- **问题**：tool result、assistant content 原样落日志；API key / PII 可能被打印。
- **建议**：
  - 提供 sanitizer hook
  - 对 `risk_level != READ` 的工具结果做掩码

### 39. 缺 OpenTelemetry / tracer 接入
- **位置**：全局
- **问题**：`Debugger` 仅内存 trace；`trace_id` 未挂任何 tracer。
- **建议**：接入 `opentelemetry-api`，把 HarnessEvent 当 span event。

---

## 落地顺序建议

| 优先级 | 条目 | 理由 |
| --- | --- | --- |
| P0 | 1, 2, 3, 4, 5 | 运行时崩溃或 silent corruption |
| P0 | 6, 7, 8, 9 | 安全/稳定性 |
| P1 | 10, 11, 12, 17 | 架构清晰度，影响后续扩展 |
| P1 | 20, 21, 22 | 性能/并发 |
| P1 | 23, 24, 27 | 内存/预算正确性 |
| P2 | 其余 | 可维护性、观察性 |

---

## 备注

- 本清单是 review 结论，非最终 backlog；具体修复可拆成独立 PR / task，每条完成后勾掉或移走。
- 动手前建议补齐最小用例覆盖：`engine/loop.py`、`harness/harness.py`、`capabilities/skills/executor.py`、`providers/claude.py` 当前几乎没有单元测试兜底。
