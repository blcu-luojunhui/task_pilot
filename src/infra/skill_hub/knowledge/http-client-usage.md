---
name: http-client-usage
description: HTTP 客户端的使用方法和最佳实践
category: http
scope: agent:*
---

## When to use

- 需要调用外部 API 时
- 需要抓取网页内容时
- 需要发送 webhook 通知时

## Guidelines

- 使用 `async with AsyncHttpClient()` 确保资源正确释放
- 默认超时 10 秒，可通过 `timeout` 参数调整
- 自动处理 JSON 响应，返回 dict
- 自动处理文本响应，返回 str
- HTTP 错误会抛出异常并记录日志
- 支持自定义 headers 和 query parameters
- 连接池最大 100 个连接，自动复用

## Common Patterns

### GET 请求
```python
async with AsyncHttpClient() as client:
    data = await client.get(
        "https://api.example.com/articles",
        params={"date": "2025-04-28", "limit": 10},
    )
```

### POST JSON
```python
async with AsyncHttpClient() as client:
    result = await client.post(
        "https://api.example.com/webhook",
        json={"event": "task_completed", "trace_id": trace_id},
    )
```

### POST Form Data
```python
async with AsyncHttpClient() as client:
    result = await client.post(
        "https://api.example.com/submit",
        data={"key": "value"},
    )
```

### 自定义 Headers
```python
async with AsyncHttpClient(default_headers={"Authorization": "Bearer token"}) as client:
    data = await client.get("https://api.example.com/protected")
```
