# Quickstart

## 环境要求

- Python 3.11+
- MySQL 5.7+

---

## 安装与启动

```bash
pip install -r requirements.txt

# 本地开发
hypercorn app:app -c app_config.toml
```

Docker 方式：

```bash
docker-compose up -d
```

默认监听：`0.0.0.0:6060`

---

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `TASK_PILOT_DB_HOST` | MySQL 地址 | `localhost` |
| `TASK_PILOT_DB_PORT` | MySQL 端口 | `3306` |
| `TASK_PILOT_DB_USER` | MySQL 用户 | `root` |
| `TASK_PILOT_DB_PASSWORD` | MySQL 密码 | 必填 |
| `TASK_PILOT_DB_DB` | 数据库名 | `task_pilot` |
| `TASK_TABLE` | 任务表名 | `task_manager` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

---

## 数据库初始化

```sql
CREATE TABLE task_manager (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    date_string      VARCHAR(64)    NULL,
    task_name        VARCHAR(256)   NULL,
    task_status      TINYINT        NOT NULL DEFAULT 0
        COMMENT '0:INIT 1:PROCESSING 2:SUCCESS 3:CANCELLED 4:CANCEL_REQUESTED 99:FAILED',
    start_timestamp  BIGINT         NULL,
    finish_timestamp BIGINT         NULL,
    trace_id         VARCHAR(128)   NULL,
    data             JSON           NULL,
    UNIQUE INDEX uk_trace_id (trace_id),
    INDEX idx_date_task (date_string, task_name),
    INDEX idx_status_task_name (task_status, task_name),
    INDEX idx_task_name (task_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

也可以参考仓库根目录的 `init.sql`。

---

## 启动后检查

- 健康检查：`GET /api/health`
- 查看 API 调用示例：[`docs/api.md`](api.md)
