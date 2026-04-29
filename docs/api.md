# API Guide

## Health Check

```http
GET /api/health
```

---

## Run Task

```http
POST /api/run_task
Content-Type: application/json

{
  "task_name": "my_task",
  "date_string": "2025-04-28"
}
```

说明：

- `task_name`：任务处理器名称
- `date_string`：任务业务日期（可选，建议传入）

---

## Cancel Task

```http
POST /api/cancel_task
Content-Type: application/json

{
  "trace_id": "Task-20250428143022-a1b2c3d4e5f6g7h8"
}
```

说明：

- 取消采用协作式机制：先标记状态为 `CANCEL_REQUESTED`，再由生命周期管理器轮询并取消运行中的任务

---

## 常见调用顺序

1. 调用 `POST /api/run_task` 创建任务
2. 通过任务结果或状态接口观察执行进度
3. 必要时调用 `POST /api/cancel_task` 触发取消

若你需要完整任务状态语义，请看 [`docs/project.md`](project.md)。
