# Agent Guide

> How TaskPilot turns task execution into an agentic workflow.

在 TaskPilot 中，Agent 不是绕过任务系统的“外挂脚本”。  
它运行在调度器和生命周期管理之内，接受同样的并发控制、超时控制、取消机制和可观测约束。

[Back to README](../README.md)

---

## The Loop

Agent 的工作方式可以简化为三个动作：

```text
Think -> Act -> Observe -> Think ...
```

- **Think**：理解任务目标、上下文和当前状态，决定下一步策略
- **Act**：调用 Skills 或外部工具执行动作
- **Observe**：读取执行结果，判断继续、重试、切换策略或结束

这让任务从“固定步骤执行”变成“基于反馈推进”。

---

## Skills

Skills 是 Agent 的能力边界。TaskPilot 将它拆成两类：

### Executable Skills

Executable Skills 是可被 Agent 调用的函数能力，通过 `@skill` 注册。  
它们适合封装数据库查询、HTTP 请求、任务管理、通用工具函数等动作。

### Knowledge Skills

Knowledge Skills 是 Markdown 文档中的知识片段。  
它们不会直接执行代码，而是注入到 Agent 的上下文中，用来约束策略、补充领域规则和沉淀最佳实践。

---

## Built-in Tool Areas

TaskPilot 内置的 Agentic Tools 主要覆盖四类能力：

- Database：查询、读取单条记录、执行写操作
- HTTP：调用外部接口
- Task：查询任务状态、列出执行中任务、请求取消任务
- Utils：时间、哈希、批处理、trace id 等通用能力

这些工具都通过 Skills 框架暴露给 Agent，而不是直接散落在业务流程中。

---

## Model Adapters

不同 LLM 对工具描述格式的要求不同。  
TaskPilot 将技能定义和模型格式拆开，通过 Tool Spec Adapter 将同一组 Skills 序列化为不同模型可理解的工具描述。

这意味着：

- 技能只需要定义一次
- 模型接入可以独立演进
- OpenAI、Claude 或其它格式可以共存

---

## Extension Points

你可以从这些位置扩展 Agent 系统：

- 新增 Executable Skill，接入新的系统能力
- 新增 Knowledge Skill，沉淀业务规则和操作经验
- 新增 Tool Spec Adapter，支持新的模型接口
- 新增 Dependency Resolver，适配测试、多环境或多租户场景

---

## Boundary

Agent 可以让任务执行更灵活，但它不应该绕开任务系统本身。

在 TaskPilot 中：

- 任务是否开始，由 `jobs` 调度
- 任务是否取消，由生命周期管理器协调
- 工具能做什么，由 Skills 注册表治理
- 外部系统如何访问，由 `infra` 封装

这条边界让智能行为可以增长，同时仍然保留可测试、可审计、可回收的工程结构。
