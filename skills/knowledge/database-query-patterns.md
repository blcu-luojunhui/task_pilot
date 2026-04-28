---
name: database-query-patterns
description: 数据库查询的最佳实践和常见模式
category: database
scope: agent:*
---

## When to use

- 需要从 MySQL 查询数据时
- 需要批量插入/更新数据时
- 需要事务支持时

## Guidelines

- 使用参数化查询防止 SQL 注入：`async_fetch(query, params=(val1, val2))`
- 批量操作使用 `async_save(..., batch=True)` 提升性能
- 查询单条记录用 `async_fetch_one()`，多条用 `async_fetch()`
- 所有数据库操作都是异步的，必须 `await`
- 连接池会自动管理连接，无需手动关闭
- 查询失败会自动记录日志并抛出异常
- 使用 DictCursor 返回字典格式结果，方便访问字段

## Common Patterns

### 查询列表
```python
rows = await ctx.db.async_fetch(
    "SELECT * FROM articles WHERE date_string = %s LIMIT %s",
    params=(date, limit),
)
```

### 查询单条
```python
row = await ctx.db.async_fetch_one(
    "SELECT * FROM task_manager WHERE trace_id = %s",
    params=(trace_id,),
)
```

### 插入数据
```python
affected = await ctx.db.async_save(
    "INSERT INTO articles (title, content) VALUES (%s, %s)",
    params=(title, content),
)
```

### 批量插入
```python
data = [(title1, content1), (title2, content2)]
affected = await ctx.db.async_save(
    "INSERT INTO articles (title, content) VALUES (%s, %s)",
    params=data,
    batch=True,
)
```
