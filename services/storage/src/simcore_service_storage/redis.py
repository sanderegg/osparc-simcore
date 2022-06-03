import json
import logging
from typing import Optional

import redis.asyncio as aioredis
from aiohttp import web
from settings_library.redis import RedisSettings
from tenacity._asyncio import AsyncRetrying
from tenacity.before_sleep import before_sleep_log
from tenacity.stop import stop_after_delay
from tenacity.wait import wait_fixed

from .constants import (
    APP_CONFIG_KEY,
    APP_REDIS_LOCK_MANAGER_KEY,
    MINUTE,
    RETRY_WAIT_SECS,
)

log = logging.getLogger(__name__)


# SETTINGS --------------------------------------------------------------------------


def get_plugin_settings(app: web.Application) -> RedisSettings:
    settings: Optional[RedisSettings] = app[APP_CONFIG_KEY].WEBSERVER_REDIS
    assert settings, "setup_settings not called?"  # nosec
    assert isinstance(settings, RedisSettings)  # nosec
    return settings


# EVENTS --------------------------------------------------------------------------
async def setup_redis_client(app: web.Application):
    redis_settings: RedisSettings = get_plugin_settings(app)

    async def _create_client(address: str) -> aioredis.Redis:
        client: Optional[aioredis.Redis] = None

        async for attempt in AsyncRetrying(
            stop=stop_after_delay(2 * MINUTE),
            wait=wait_fixed(RETRY_WAIT_SECS),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        ):
            with attempt:
                client = aioredis.from_url(
                    address, encoding="utf-8", decode_responses=True
                )
                if not await client.ping():
                    await client.close(close_connection_pool=True)
                    raise ConnectionError(f"Connection to {address!r} failed")
                log.info(
                    "Connection to %s succeeded with %s [%s]",
                    f"redis at {address=}",
                    f"{client=}",
                    json.dumps(attempt.retry_state.retry_object.statistics),
                )
        assert client  # nosec
        return client

    # create a client for it as well
    app[APP_REDIS_LOCK_MANAGER_KEY] = client_lock_db = await _create_client(
        redis_settings.dsn_locks
    )
    assert client_lock_db  # nosec

    yield

    if client_lock_db is not app[APP_REDIS_LOCK_MANAGER_KEY]:
        log.critical("Invalid redis client for lock db in app")
        await client_lock_db.close(close_connection_pool=True)


def get_redis_lock_manager_client(app: web.Application) -> aioredis.Redis:
    return app[APP_REDIS_LOCK_MANAGER_KEY]


def setup_redis(app: web.Application):
    app.cleanup_ctx.append(setup_redis_client)
