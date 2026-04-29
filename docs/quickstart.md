# Quickstart

> Bring TaskPilot up with the smallest moving parts.

这份文档只关注“如何跑起来”。架构细节见 [Project Guide](project.md)，接口说明见 [API Guide](api.md)。

[Back to README](../README.md)

---

## Requirements

- Python 3.11+
- MySQL 5.7+（Docker Compose 默认使用 MySQL 8.0）

---

## Option A: Local

安装依赖：

```bash
pip install -r requirements.txt
```

准备 MySQL，并初始化任务表：

```bash
mysql -h 127.0.0.1 -u root -p task_pilot < init.sql
```

启动服务：

```bash
hypercorn app:app -c app_config.toml
```

服务默认监听 `0.0.0.0:6060`。

---

## Option B: Docker Compose

Docker Compose 会同时启动应用和 MySQL，并挂载 `init.sql` 完成表结构初始化。

```bash
docker-compose up -d
```

查看服务状态：

```bash
docker-compose ps
```

---

## Configuration

常用环境变量：

| Variable | Description | Default |
|---|---|---|
| `TASK_PILOT_DB_HOST` | MySQL host | `localhost` |
| `TASK_PILOT_DB_PORT` | MySQL port | `3306` |
| `TASK_PILOT_DB_USER` | MySQL user | `root` |
| `TASK_PILOT_DB_PASSWORD` | MySQL password | required |
| `TASK_PILOT_DB_DB` | Database name | `task_pilot` |
| `TASK_TABLE` | Task table name | `task_manager` |
| `LOG_LEVEL` | Log level | `INFO` |

Docker Compose 会读取根目录 `.env`。如果本地没有 `.env`，请根据你的 MySQL 配置创建。

---

## Database

任务表结构维护在根目录 [`init.sql`](../init.sql)。  
核心字段包括：

- `task_name`：任务处理器名称
- `task_status`：任务状态机值
- `trace_id`：单次任务执行的追踪 ID
- `data`：任务附加数据

完整状态语义见 [Project Guide](project.md)。

---

## Smoke Test

服务启动后先检查健康状态：

```bash
curl http://127.0.0.1:6060/api/health
```

如果需要提交或取消任务，继续查看 [API Guide](api.md)。
