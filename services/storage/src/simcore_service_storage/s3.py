""" Module to access s3 service

"""
import logging

from aiobotocore.session import get_session
from aiohttp import web
from botocore.client import Config
from tenacity._asyncio import AsyncRetrying
from tenacity.before_sleep import before_sleep_log
from tenacity.stop import stop_after_delay
from tenacity.wait import wait_fixed

from .constants import APP_CONFIG_KEY, APP_S3_KEY
from .utils import MINUTE, RETRY_WAIT_SECS

log = logging.getLogger(__name__)

_APP_S3_SESSION = f"{__name__}.s3_session"


async def setup_s3_client(app):
    log.debug("setup %s.setup.cleanup_ctx", __name__)
    # setup
    storage_s3_settings = app[APP_CONFIG_KEY].STORAGE_S3
    app[_APP_S3_SESSION] = session = get_session()

    async for attempt in AsyncRetrying(
        wait=wait_fixed(RETRY_WAIT_SECS),
        stop=stop_after_delay(2 * MINUTE),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    ):
        with attempt:
            app[APP_S3_KEY] = s3_client = session.create_client(
                "s3",
                endpoint_url=storage_s3_settings.S3_ENDPOINT,
                aws_access_key_id=storage_s3_settings.S3_ACCESS_KEY,
                aws_secret_access_key=storage_s3_settings.S3_SECRET_KEY,
                config=Config(signature_version="s3v4"),
            )
            async with s3_client as client:
                log.debug("Creating bucket: %s", storage_s3_settings.json(indent=2))
                try:
                    await client.create_bucket(
                        Bucket=storage_s3_settings.S3_BUCKET_NAME
                    )
                    log.info(
                        "Bucket %s successfully created [%s]",
                        storage_s3_settings.S3_BUCKET_NAME,
                        attempt.retry_state.retry_object.statistics,
                    )
                except client.exceptions.BucketAlreadyOwnedByYou:
                    log.info(
                        "Bucket %s already exists and is valid [%s]",
                        storage_s3_settings.S3_BUCKET_NAME,
                        attempt.retry_state.retry_object.statistics,
                    )

    yield
    # if app[APP_S3_KEY]:
    #     s3_client = app[APP_S3_KEY]
    #     await s3_client.close()

    # tear-down
    log.debug("tear-down %s.setup.cleanup_ctx", __name__)


def setup_s3(app: web.Application):
    """minio/s3 service setup"""

    log.debug("Setting up %s ...", __name__)
    STORAGE_DISABLE_SERVICES = app[APP_CONFIG_KEY].STORAGE_DISABLE_SERVICES

    if "s3" in STORAGE_DISABLE_SERVICES:
        log.warning("Service '%s' explicitly disabled in config", "s3")
        return

    app.cleanup_ctx.append(setup_s3_client)
