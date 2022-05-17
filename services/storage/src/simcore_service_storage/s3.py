""" Module to access s3 service

"""
import logging
from contextlib import AsyncExitStack
from dataclasses import dataclass

from aiobotocore.session import AioSession, get_session
from aiohttp import web
from botocore.client import Config
from settings_library.s3 import S3Settings
from tenacity._asyncio import AsyncRetrying
from tenacity.before_sleep import before_sleep_log
from tenacity.stop import stop_after_delay
from tenacity.wait import wait_fixed
from types_aiobotocore_s3 import S3Client

from .constants import APP_CONFIG_KEY, APP_S3_KEY
from .utils import MINUTE, RETRY_WAIT_SECS

log = logging.getLogger(__name__)


@dataclass
class StorageS3Client:
    session: AioSession
    client: S3Client

    @classmethod
    async def create(
        cls, exit_stack: AsyncExitStack, settings: S3Settings
    ) -> "StorageS3Client":
        # upon creation the client automatically tries to connect to the S3 server
        # it raises an exception if it fails
        session = get_session()
        client = await exit_stack.enter_async_context(
            session.create_client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                config=Config(signature_version="s3v4"),
            )
        )
        return cls(session, client)

    async def create_bucket(self, bucket_name: str) -> None:
        log.debug("Creating bucket: %s", bucket_name)

        try:
            await self.client.create_bucket(Bucket=bucket_name)
            log.info("Bucket %s successfully created", bucket_name)
        except self.client.exceptions.BucketAlreadyOwnedByYou:
            log.info(
                "Bucket %s already exists and is owned by us",
                bucket_name,
            )


async def setup_s3_client(app):
    log.debug("setup %s.setup.cleanup_ctx", __name__)
    # setup
    storage_s3_settings = app[APP_CONFIG_KEY].STORAGE_S3

    async with AsyncExitStack() as exit_stack:
        client = None
        async for attempt in AsyncRetrying(
            wait=wait_fixed(RETRY_WAIT_SECS),
            stop=stop_after_delay(2 * MINUTE),
            before_sleep=before_sleep_log(log, logging.WARNING),
            reraise=True,
        ):
            with attempt:
                client = await StorageS3Client.create(exit_stack, storage_s3_settings)
                log.info(
                    "S3 client %s successfully created [%s]",
                    f"{client=}",
                    attempt.retry_state.retry_object.statistics,
                )
        assert client  # nosec
        app[APP_S3_KEY] = client

        yield
        # tear-down
        log.debug("closing %s", f"{client=}")
    log.info("closed s3 client %s", f"{client=}")


async def setup_s3_bucket(app: web.Application):
    storage_s3_settings = app[APP_CONFIG_KEY].STORAGE_S3
    client = get_s3_client(app)
    await client.create_bucket(storage_s3_settings.S3_BUCKET_NAME)
    yield


def setup_s3(app: web.Application):
    """minio/s3 service setup"""

    log.debug("Setting up %s ...", __name__)
    STORAGE_DISABLE_SERVICES = app[APP_CONFIG_KEY].STORAGE_DISABLE_SERVICES

    if "s3" in STORAGE_DISABLE_SERVICES:
        log.warning("Service '%s' explicitly disabled in config", "s3")
        return

    app.cleanup_ctx.append(setup_s3_client)
    app.cleanup_ctx.append(setup_s3_bucket)


def get_s3_client(app: web.Application) -> StorageS3Client:
    assert app[APP_S3_KEY]  # nosec
    return app[APP_S3_KEY]
