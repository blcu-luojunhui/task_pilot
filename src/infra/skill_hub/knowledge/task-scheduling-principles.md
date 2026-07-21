---
name: task-scheduling-principles
description: 任务调度系统的核心原则和最佳实践
category: task-management
scope: agent:*
---

## When to use

- 需要调度异步任务时
- 需要控制任务并发数时
- 需要实现分布式任务协调时
- 需要任务超时检测和自动恢复时

## Guidelines

- 使用 trace_id 追踪任务全生命周期
- 通过 MySQL 行锁实现分布式任务锁，避免重复执行
- 设置合理的 timeout 和 max_concurrent 参数
- 失败任务应记录详细错误信息并触发告警
- 使用 TaskStatus 状态机管理任务状态流转
- 取消任务使用协作式取消（CancelledError），而非强制 kill
- 优雅关闭时先停止接收新任务，再等待运行中任务完成

## Task State Machine

```
INIT (0) → PROCESSING (1) → SUCCESS (2) / FAILED (99) / CANCELLED (3)
                ↓
         CANCEL_REQUESTED (4)
```

## Concurrency Control

每个任务名可独立配置：
- `timeout`: 超时阈值（秒）
- `max_concurrent`: 最大并发数
- `alert_on_failure`: 失败时是否告警

调度器在执行前自动检查：
1. 扫描该任务名下所有 PROCESSING 状态的记录
2. 超时任务 → 强制释放 + 触发告警
3. 活跃任务数 >= max_concurrent → 拒绝执行 + 触发告警
