# Quickstart

> 用最少步骤把 TaskPilot 跑起来。架构细节见 [Project Guide](project.md)，接口说明见 [API Guide](api.md)。

[Back to README](../README.md)

## Requirements

- Python 3.11+
- MySQL 5.7+，Docker Compose 默认使用 MySQL 8.0
- Node.js 18+，用于前端开发和构建

## 1. 准备配置

```bash
cp .env.example .env
```

编辑 `.env`，至少确认数据库和 LLM 配置：

```text
TASK_PILOT_DB_HOST=localhost
TASK_PILOT_DB_PORT=3306
TASK_PILOT_DB_USER=root
TASK_PILOT_DB_PASSWORD=changeme
TASK_PILOT_DB_DB=task_pilot
TASK_TABLE=task_manager

LLM_API_KEY=your-api-key
```

Docker Compose 会读取根目录 `.env`。前端如需独立配置，可参考 `frontend/.env.example`。

## 2A. 本地启动后端

安装依赖：

```bash
pip install -r requirements.txt
```

准备 MySQL，并初始化表结构：

```bash
mysql -h 127.0.0.1 -u root -p -e "CREATE DATABASE IF NOT EXISTS task_pilot"
mysql -h 127.0.0.1 -u root -p task_pilot < init.sql
```

启动服务：

```bash
hypercorn app:app -c config.toml
```

后端默认监听 `0.0.0.0:6060`。

## 2B. Docker Compose 启动

Docker Compose 会同时启动应用和 MySQL，并挂载 `init.sql` 完成表结构初始化。

```bash
docker-compose up -d
docker-compose ps
```

这种方式适合快速体验后端和数据库闭环。

## 3. 启动前端

开发模式：

```bash
cd frontend
npm install
npm run dev
```

前端开发服务默认监听 `http://127.0.0.1:5173`。

生产构建并由后端托管：

```bash
cd frontend
npm install
npm run build
cd ..
FRONTEND_DIST=frontend/dist hypercorn app:app -c config.toml
```

如果未构建前端，访问 `/` 会返回提示；API 不受影响。

## 4. Smoke Test

检查健康状态：

```bash
curl http://127.0.0.1:6060/api/health
```

查看可用工具区域：

```bash
curl http://127.0.0.1:6060/api/agent/tool_areas
```

提交一个任务：

```bash
curl -X POST http://127.0.0.1:6060/api/run_task \
  -H "Content-Type: application/json" \
  -d '{"task_name":"my_task","date_string":"2026-06-12"}'
```

如果任务名不存在，接口会返回可读错误；可用任务名通过 `GET /api/task_names` 查看。

## Configuration Reference

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
| `LLM_API_KEY` | 默认 LLM API key | required for Agent |

## Database

任务表结构维护在根目录 [`init.sql`](../init.sql)。核心字段包括：

- `task_name`：任务处理器名称。
- `task_status`：任务状态机值。
- `trace_id`：单次任务执行的追踪 ID。
- `data`：任务附加数据。

完整状态语义见 [Project Guide](project.md)。
