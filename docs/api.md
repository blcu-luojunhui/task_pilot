# API Guide

> The small public surface of TaskPilot.

TaskPilot 的 API 保持克制：提交任务、取消任务、检查健康状态，以及暴露 Prometheus 指标。  
更多运行方式见 [Quickstart](quickstart.md)，状态机语义见 [Project Guide](project.md)。

[Back to README](../README.md)

---

## Base URL

本地默认地址：

```text
http://127.0.0.1:6060
```

所有业务接口都挂在 `/api` 前缀下。

---

## Health Check

检查应用、MySQL 连接池和日志服务状态。

```http
GET /api/health
```

示例：

```bash
curl http://127.0.0.1:6060/api/health
```

---

## Run Task

提交一个任务给调度器执行。

```http
POST /api/run_task
Content-Type: application/json
```

请求体：

```json
{
  "task_name": "my_task",
  "date_string": "2025-04-28"
}
```

字段说明：

- `task_name`：任务处理器名称，必填
- `date_string`：任务业务日期，可选
- 其它字段会被保留并传递给任务处理逻辑

示例：

```bash
curl -X POST http://127.0.0.1:6060/api/run_task \
  -H "Content-Type: application/json" \
  -d '{"task_name":"my_task","date_string":"2025-04-28"}'
```

---

## Cancel Task

请求取消一个任务。

```http
POST /api/cancel_task
Content-Type: application/json
```

请求体：

```json
{
  "trace_id": "Task-20250428143022-a1b2c3d4e5f6g7h8"
}
```

示例：

```bash
curl -X POST http://127.0.0.1:6060/api/cancel_task \
  -H "Content-Type: application/json" \
  -d '{"trace_id":"Task-20250428143022-a1b2c3d4e5f6g7h8"}'
```

取消是协作式的：接口先把任务标记为 `CANCEL_REQUESTED`，随后由生命周期管理器发现并取消运行中的 `asyncio.Task`。

---

## Metrics

暴露 Prometheus 格式指标。

```http
GET /api/metrics
```

示例：

```bash
curl http://127.0.0.1:6060/api/metrics
```

---

## Typical Flow

1. 调用 `POST /api/run_task` 提交任务
2. 使用返回的 `trace_id` 追踪执行链路
3. 必要时调用 `POST /api/cancel_task` 请求取消
4. 通过日志、健康检查和 `/api/metrics` 观察系统状态
