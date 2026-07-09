"""db.migrate — 数据库迁移任务。

从 docs/migrations/ 读取按编号排序的 .sql 文件，对比 schema_migrations 表，
只执行尚未应用的文件，执行后记录版本号。

用法：
  提交一个 task_name="db.migrate" 的任务即可。
  开发环境随服务启动自动跑一次（见下方 auto_migrate）。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.jobs.task_config import TaskStatus
from src.jobs.task_handler import register

if TYPE_CHECKING:
    from src.jobs.task_scheduler import TaskScheduler

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "docs" / "migrations"

_SCHEMA_TABLE_DDL = """\
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     VARCHAR(64)  NOT NULL PRIMARY KEY
        COMMENT '已执行的迁移文件名（不含 .sql）',
    applied_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    checksum    VARCHAR(64)  NULL
        COMMENT '文件 SHA-256，用于检测文件被修改',
    INDEX idx_applied (applied_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;"""


def _collect_migrations() -> list[Path]:
    if not _MIGRATIONS_DIR.is_dir():
        logger.warning("db.migrate: migrations dir not found: %s", _MIGRATIONS_DIR)
        return []
    files = sorted(p for p in _MIGRATIONS_DIR.iterdir() if p.suffix == ".sql")
    return files


async def _ensure_schema_table(db) -> None:
    for stmt in _SCHEMA_TABLE_DDL.split(";"):
        stmt = stmt.strip()
        if stmt:
            await db.async_save(stmt)


async def _applied_versions(db) -> set[str]:
    rows = await db.async_fetch("SELECT version FROM schema_migrations")
    return {r["version"] for r in (rows or [])}


@register("db.migrate")
async def run_migrations(scheduler: "TaskScheduler") -> int:
    """执行所有未应用的迁移文件。"""
    db = scheduler.db_client

    await _ensure_schema_table(db)

    applied = await _applied_versions(db)
    files = _collect_migrations()

    if not files:
        logger.info("db.migrate: no migration files found")
        return TaskStatus.SUCCESS

    pending = [f for f in files if f.stem not in applied]

    if not pending:
        logger.info("db.migrate: all %d migrations already applied", len(files))
        return TaskStatus.SUCCESS

    logger.info("db.migrate: %d pending / %d total", len(pending), len(files))

    for f in pending:
        version = f.stem
        sql = f.read_text(encoding="utf-8")
        logger.info("db.migrate: applying %s", version)

        try:
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if not stmt or stmt.startswith("--"):
                    continue
                await db.async_save(stmt)
        except Exception:
            logger.exception("db.migrate: FAILED at %s", version)
            return TaskStatus.FAILED

        await db.async_save(
            "INSERT INTO schema_migrations (version) VALUES (%s)",
            params=(version,),
        )
        logger.info("db.migrate: applied %s ✓", version)

    return TaskStatus.SUCCESS


async def auto_migrate(db) -> bool:
    """启动时自动跑一次迁移（不走 TaskScheduler，轻量版）。

    返回 True 表示全部已是最新（含无需迁移的情况）。
    """
    await _ensure_schema_table(db)
    applied = await _applied_versions(db)
    files = _collect_migrations()
    pending = [f for f in files if f.stem not in applied]

    if not pending:
        return True

    logger.info("auto_migrate: %d pending migrations", len(pending))
    for f in pending:
        sql = f.read_text(encoding="utf-8")
        logger.info("auto_migrate: applying %s", f.stem)
        try:
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if not stmt or stmt.startswith("--"):
                    continue
                await db.async_save(stmt)
        except Exception:
            logger.exception("auto_migrate: FAILED at %s", f.stem)
            return False
        await db.async_save(
            "INSERT INTO schema_migrations (version) VALUES (%s)",
            params=(f.stem,),
        )
    return True


__all__ = ["run_migrations", "auto_migrate"]
