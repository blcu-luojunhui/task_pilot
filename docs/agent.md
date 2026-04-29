# Agent Guide

## Agent 在 TaskPilot 里的角色

在 TaskPilot 中，Agent 不是“外挂脚本”，而是任务执行链路中的一等公民。  
它运行在任务调度框架内，接受同样的并发控制、超时控制和取消机制。

---

## Agent Loop

Agent 通过一个循环完成任务推进：

1. **Think**：分析目标与上下文，决定下一步行动
2. **Act**：调用可执行技能（Executable Skills）
3. **Observe**：评估结果，决定继续、重试、切换策略或结束

这种模式使任务执行从“固定流程”升级为“可调整策略”。

---

## Skills 双轨体系

### 1) Executable Skills（可执行技能）

通过 `@skill` 注册，Agent 在 Act 阶段调用。  
常见技能包括：数据库查询、HTTP 调用、任务状态操作、通用工具函数等。

### 2) Knowledge Skills（知识型技能）

从 Markdown 文件加载，用于给 Agent 提供领域规则和最佳实践。  
它们不直接执行代码，而是影响 Think 阶段的决策质量。

---

## Tool Spec 适配

TaskPilot 支持将技能自动序列化为不同 LLM 的工具描述格式（如 OpenAI、Claude）。  
这样可以在不重写技能定义的前提下切换模型或多模型并存。

---

## 扩展方式

你可以从这几个方向扩展 Agent 能力：

- 新增可执行技能（如第三方系统操作能力）
- 新增知识技能（如业务规则、安全约束）
- 新增工具格式适配器（支持更多模型接口）
- 自定义依赖解析器（测试环境、多租户环境）

---

## 与项目其它层的关系

- Agent 的执行入口受 `jobs` 层调度
- Agent 依赖 `core/agents/skills` 完成工具治理
- Agent 通过 `infra` 获取数据库、日志、HTTP、MCP 等能力

这种关系保证：智能行为可以持续增强，同时不破坏底层工程稳定性。
