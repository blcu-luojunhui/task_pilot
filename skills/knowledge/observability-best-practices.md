---
name: observability-best-practices
description: 日志和告警的最佳实践
category: observability
scope: agent:*
---

## When to use

- 需要记录任务执行日志时
- 需要发送告警通知时
- 需要追踪任务执行链路时

## Guidelines

- 所有日志必须包含 `trace_id` 用于链路追踪
- 使用结构化日志（dict 格式），便于后续分析
- 日志级别：INFO（正常流程）、WARNING（异常但可恢复）、ERROR（失败）
- 告警应包含足够的上下文信息（task_name、trace_id、error_detail）
- 使用 `dedup_key` 避免重复告警（60 秒去重窗口）
- 日志和告警都是异步队列，不会阻塞任务执行
- 队列满时会丢弃日志，但会记录丢弃数量

## Logging Patterns

### 记录任务事件
```python
await ctx.log.log({
    "timestamp": datetime.now().isoformat(),
    "trace_id": trace_id,
    "event_type": "task_started",
    "task_name": "my_task",
    "params": {"date": "2025-04-28"},
})
```

### 记录错误
```python
await ctx.log.log({
    "timestamp": datetime.now().isoformat(),
    "trace_id": trace_id,
    "event_type": "task_failed",
    "task_name": "my_task",
    "error": str(e),
    "traceback": traceback.format_exc(),
})
```

## Alert Patterns

### 发送告警
```python
await alert_service.send_alert(
    title=f"Task Failed: {task_name}",
    detail={
        "task_name": task_name,
        "trace_id": trace_id,
        "error": error_detail,
        "duration": duration,
    },
    dedup_key=f"task_failed_{task_name}_{trace_id}",
)
```

### 避免告警风暴
使用 `dedup_key` 确保相同问题在 60 秒内只告警一次：
```python
dedup_key = f"timeout_{task_name}"  # 同一任务名的超时只告警一次
```
