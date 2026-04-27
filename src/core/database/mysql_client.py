import logging

from aiomysql import create_pool
from aiomysql.cursors import DictCursor

from src.core.config import GlobalConfigSettings
from src.core.observability import LogService

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, config: GlobalConfigSettings, log_service: LogService):
        self.log_service = log_service
        self.config = config
        self.pools = {}

    async def _log(self, contents: dict):
        await self.log_service.log(contents)

    async def init_pools(self):
        db_config = self.config.default_db
        try:
            pool = await create_pool(
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password,
                db=db_config.db,
                minsize=db_config.minsize,
                maxsize=db_config.maxsize,
                cursorclass=DictCursor,
                autocommit=True,
            )
            self.pools["default"] = pool
            logger.info("Default MySQL pool created successfully")
        except Exception as e:
            await self._log(
                contents={
                    "db_name": "default",
                    "error": str(e),
                    "message": "Failed to create default pool",
                }
            )
            self.pools["default"] = None

    async def close_pools(self):
        for name, pool in self.pools.items():
            if pool:
                pool.close()
                await pool.wait_closed()
                logger.info(f"{name} MySQL pool closed")

    async def async_fetch(
        self, query, db_name="default", params=None, cursor_type=DictCursor
    ):
        pool = self.pools.get(db_name)
        if not pool:
            await self.init_pools()
            pool = self.pools.get(db_name)

        if not pool:
            raise RuntimeError(f"Database pool '{db_name}' not available after init")

        try:
            async with pool.acquire() as conn:
                async with conn.cursor(cursor_type) as cursor:
                    await cursor.execute(query, params)
                    return await cursor.fetchall()
        except Exception as e:
            await self._log(
                contents={
                    "task": "async_fetch",
                    "db_name": db_name,
                    "error": str(e),
                    "query": query,
                }
            )
            raise

    async def async_fetch_one(
        self, query, db_name="default", params=None, cursor_type=DictCursor
    ):
        pool = self.pools.get(db_name)
        if not pool:
            await self.init_pools()
            pool = self.pools.get(db_name)

        if not pool:
            raise RuntimeError(f"Database pool '{db_name}' not available after init")

        try:
            async with pool.acquire() as conn:
                async with conn.cursor(cursor_type) as cursor:
                    await cursor.execute(query, params)
                    return await cursor.fetchone()
        except Exception as e:
            await self._log(
                contents={
                    "task": "async_fetch_one",
                    "db_name": db_name,
                    "error": str(e),
                    "query": query,
                }
            )
            raise

    async def async_save(
        self, query, params, db_name="default", batch: bool = False
    ):
        pool = self.pools.get(db_name)
        if not pool:
            await self.init_pools()
            pool = self.pools.get(db_name)

        if not pool:
            raise RuntimeError(f"Database pool '{db_name}' not available after init")

        async with pool.acquire() as connection:
            async with connection.cursor() as cursor:
                try:
                    if batch:
                        await cursor.executemany(query, params)
                    else:
                        await cursor.execute(query, params)
                    affected_rows = cursor.rowcount
                    await connection.commit()
                    return affected_rows
                except Exception as e:
                    await connection.rollback()
                    await self._log(
                        contents={
                            "task": "async_save",
                            "db_name": db_name,
                            "error": str(e),
                            "query": query,
                        }
                    )
                    raise

    def get_pool(self, db_name="default"):
        return self.pools.get(db_name)

    def list_databases(self):
        return list(self.pools.keys())
