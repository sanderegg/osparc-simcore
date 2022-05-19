""" Module to access s3 service

"""
import asyncio
import logging
import urllib.parse
from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Final

from aiobotocore.session import AioSession, get_session
from aiohttp import web
from botocore.client import Config
from pydantic import AnyUrl, ByteSize, PositiveInt, parse_obj_as
from settings_library.s3 import S3Settings
from tenacity._asyncio import AsyncRetrying
from tenacity.before_sleep import before_sleep_log
from tenacity.stop import stop_after_delay
from tenacity.wait import wait_fixed
from types_aiobotocore_s3 import S3Client

from .constants import APP_CONFIG_KEY, APP_S3_KEY
from .utils import MINUTE, RETRY_WAIT_SECS

log = logging.getLogger(__name__)

# this is artifically defined, if possible we keep a maximum number of requests for parallel
# uploading. If that is not possible then we create as many upload part as the max part size allows
_MULTIPART_UPLOADS_TARGET_MAX_PART_SIZE: Final[list[ByteSize]] = [
    parse_obj_as(ByteSize, x)
    for x in [
        "10Mib",
        "50Mib",
        "100Mib",
        "200Mib",
        "400Mib",
        "600Mib",
        "800Mib",
        "1Gib",
        "2Gib",
        "3Gib",
        "4Gib",
        "5Gib",
    ]
]
_MULTIPART_MAX_NUMBER_OF_PARTS: Final[int] = 10000

# TODO: create a fct with tenacity to generate the number of links
def _compute_number_links(file_size: ByteSize) -> tuple[int, ByteSize]:
    for chunk in _MULTIPART_UPLOADS_TARGET_MAX_PART_SIZE:
        num_upload_links = int(file_size / chunk) + (1 if file_size % chunk > 0 else 0)
        if num_upload_links < _MULTIPART_MAX_NUMBER_OF_PARTS:
            return (num_upload_links, chunk)
    raise ValueError(
        f"Could not determine number of upload links for {file_size=}",
    )


FileID = str
UploadID = str
ETag = str


@dataclass(frozen=True)
class MultiPartUploadLinks:
    upload_id: UploadID
    chunk_size: ByteSize
    urls: list[AnyUrl]


@dataclass(frozen=True)
class UploadedPart:
    number: PositiveInt
    e_tag: ETag


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

    async def create_bucket(self, bucket: str) -> None:
        log.debug("Creating bucket: %s", bucket)

        try:
            await self.client.create_bucket(Bucket=bucket)
            log.info("Bucket %s successfully created", bucket)
        except self.client.exceptions.BucketAlreadyOwnedByYou:
            log.info(
                "Bucket %s already exists and is owned by us",
                bucket,
            )

    async def create_single_presigned_upload_link(
        self, bucket: str, file_id: FileID
    ) -> AnyUrl:
        generated_link = await self.client.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": file_id},
            ExpiresIn=3600,
        )
        return parse_obj_as(AnyUrl, generated_link)

    async def create_multipart_upload_links(
        self, bucket: str, file_id: FileID, file_size: ByteSize
    ) -> MultiPartUploadLinks:
        # first initiate the multipart upload
        response = await self.client.create_multipart_upload(Bucket=bucket, Key=file_id)
        upload_id = response["UploadId"]
        # compute the number of links, based on the announced file size
        num_upload_links, chunk_size = _compute_number_links(file_size)
        # now create the links
        upload_links = parse_obj_as(
            list[AnyUrl],
            await asyncio.gather(
                *[
                    self.client.generate_presigned_url(
                        "upload_part",
                        Params={
                            "Bucket": bucket,
                            "Key": file_id,
                            "PartNumber": i + 1,
                            "UploadId": upload_id,
                        },
                        ExpiresIn=3600,
                    )
                    for i in range(num_upload_links)
                ]
            ),
        )
        return MultiPartUploadLinks(upload_id, chunk_size, upload_links)

    async def list_ongoing_multipart_uploads(self, bucket: str, file_id: FileID = ""):
        """Returns all the currently ongoing multipart uploads

        NOTE: minio does not implement the same behaviour as AWS here and will
        only return the uploads if a prefix or object name is given [minio issue](https://github.com/minio/minio/issues/7632).

        :return: list of AWS uploads see [boto3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html#S3.Client.list_multipart_uploads)
        """
        return await self.client.list_multipart_uploads(Bucket=bucket, Prefix=file_id)

    async def abort_multipart_upload(
        self, bucket: str, file_id: FileID, upload_id: UploadID
    ) -> None:
        await self.client.abort_multipart_upload(
            Bucket=bucket, Key=file_id, UploadId=upload_id
        )

    async def complete_multipart_upload(
        self,
        bucket: str,
        file_id: FileID,
        upload_id: UploadID,
        uploaded_parts: list[UploadedPart],
    ):
        await self.client.complete_multipart_upload(
            Bucket=bucket,
            Key=file_id,
            UploadId=upload_id,
            MultipartUpload={
                "Parts": [
                    {"ETag": part.e_tag, "PartNumber": part.number}
                    for part in uploaded_parts
                ]
            },
        )

    async def delete_file(self, bucket: str, file_id: FileID) -> None:
        await self.client.delete_object(Bucket=bucket, Key=file_id)

    @staticmethod
    def compute_s3_url(bucket: str, file_id: FileID) -> AnyUrl:
        return parse_obj_as(AnyUrl, f"s3://{bucket}/{urllib.parse.quote(file_id)}")


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
