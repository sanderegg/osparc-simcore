import asyncio
import logging
import urllib.parse
from contextlib import AsyncExitStack
from dataclasses import dataclass

from aiobotocore.session import AioSession, get_session
from botocore.client import Config
from pydantic import AnyUrl, ByteSize, PositiveInt, parse_obj_as
from settings_library.s3 import S3Settings
from types_aiobotocore_s3 import S3Client

from .s3_utils import compute_num_file_chunks

log = logging.getLogger(__name__)


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
        num_upload_links, chunk_size = compute_num_file_chunks(file_size)
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
    ) -> ETag:
        response = await self.client.complete_multipart_upload(
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
        return response["ETag"]

    async def delete_file(self, bucket: str, file_id: FileID) -> None:
        await self.client.delete_object(Bucket=bucket, Key=file_id)

    @staticmethod
    def compute_s3_url(bucket: str, file_id: FileID) -> AnyUrl:
        return parse_obj_as(AnyUrl, f"s3://{bucket}/{urllib.parse.quote(file_id)}")
