# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import AsyncIterator, Callable
from uuid import uuid4

import botocore.exceptions
import pytest
from aiohttp import ClientSession
from faker import Faker
from pydantic import ByteSize, parse_obj_as
from simcore_service_storage.s3_client import (
    MultiPartUploadLinks,
    StorageS3Client,
    UploadedPart,
)
from simcore_service_storage.settings import Settings
from tests.helpers.file_utils import upload_file_to_presigned_link


@pytest.fixture
def mock_config(mocked_s3_server_envs, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("STORAGE_POSTGRES", "null")


async def test_storage_s3_client_creation(app_settings: Settings):
    async with AsyncExitStack() as exit_stack:
        s3_client = await StorageS3Client.create(exit_stack, app_settings.STORAGE_S3)
        assert s3_client
        response = await s3_client.client.list_buckets()
        assert not response["Buckets"]
    with pytest.raises(botocore.exceptions.HTTPClientError):
        await s3_client.client.list_buckets()


@pytest.fixture
async def s3_client(app_settings: Settings) -> AsyncIterator[StorageS3Client]:
    async with AsyncExitStack() as exit_stack:
        s3_client = await StorageS3Client.create(exit_stack, app_settings.STORAGE_S3)
        assert s3_client
        response = await s3_client.client.list_buckets()
        assert not response["Buckets"]
        yield s3_client

        # cleanup, remove all buckets
        response = await s3_client.client.list_buckets()
        bucket_names = [bucket["Name"] for bucket in response["Buckets"]]
        for bucket in bucket_names:
            response = await s3_client.client.list_objects_v2(Bucket=bucket)
            while response["KeyCount"] > 0:
                await s3_client.client.delete_objects(
                    Bucket=bucket,
                    Delete={
                        "Objects": [{"Key": obj["Key"]} for obj in response["Contents"]]
                    },
                )
                response = await s3_client.client.list_objects_v2(Bucket=bucket)

        await asyncio.gather(
            *(s3_client.client.delete_bucket(Bucket=bucket) for bucket in bucket_names)
        )


async def test_create_bucket(s3_client: StorageS3Client, faker: Faker):
    response = await s3_client.client.list_buckets()
    assert not response["Buckets"]
    bucket = faker.pystr()
    await s3_client.create_bucket(bucket)
    response = await s3_client.client.list_buckets()
    assert response["Buckets"]
    assert len(response["Buckets"]) == 1
    assert "Name" in response["Buckets"][0]
    assert response["Buckets"][0]["Name"] == bucket


@pytest.fixture
async def bucket(s3_client: StorageS3Client, faker: Faker) -> str:
    bucket = faker.pystr()
    response = await s3_client.client.list_buckets()

    assert bucket not in [
        bucket_struct.get("Name") for bucket_struct in response["Buckets"]
    ]
    await s3_client.create_bucket(bucket)
    response = await s3_client.client.list_buckets()
    assert response["Buckets"]
    assert bucket in [
        bucket_struct.get("Name") for bucket_struct in response["Buckets"]
    ]
    return bucket


async def test_create_single_presigned_upload_link(
    s3_client: StorageS3Client,
    bucket: str,
    faker: Faker,
    create_file_of_size: Callable[[ByteSize], Path],
):
    file = create_file_of_size(parse_obj_as(ByteSize, "1Mib"))
    file_uuid = f"{uuid4()}/{uuid4()}/{file.name}"
    presigned_url = await s3_client.create_single_presigned_upload_link(
        bucket, file_uuid
    )
    assert presigned_url

    # upload the file with a fake multipart upload links structure
    await upload_file_to_presigned_link(
        file,
        MultiPartUploadLinks(
            upload_id="fake",
            chunk_size=parse_obj_as(ByteSize, file.stat().st_size),
            urls=[presigned_url],
        ),
    )

    # check it is there
    response = await s3_client.client.get_object(Bucket=bucket, Key=file_uuid)
    assert response
    assert response["ContentLength"] == file.stat().st_size


@pytest.mark.parametrize(
    "file_size",
    [
        parse_obj_as(ByteSize, "10Mib"),
        parse_obj_as(ByteSize, "100Mib"),
        parse_obj_as(ByteSize, "1000Mib"),
    ],
)
async def test_create_multipart_presigned_upload_link(
    s3_client: StorageS3Client,
    bucket: str,
    create_file_of_size: Callable[[ByteSize], Path],
    file_size: ByteSize,
):
    file = create_file_of_size(file_size)
    upload_links = await s3_client.create_multipart_upload_links(
        bucket, file.name, parse_obj_as(ByteSize, file.stat().st_size)
    )
    assert upload_links

    # upload the file
    part_to_etag: list[UploadedPart] = await upload_file_to_presigned_link(
        file, upload_links
    )

    # check it is not yet completed
    with pytest.raises(botocore.exceptions.ClientError):
        await s3_client.client.head_object(Bucket=bucket, Key=file.name)

    # check we have the multipart upload listed
    response = await s3_client.client.list_multipart_uploads(Bucket=bucket)
    assert response
    assert "Uploads" in response
    assert len(response["Uploads"]) == 1
    assert "UploadId" in response["Uploads"][0]
    assert response["Uploads"][0]["UploadId"] == upload_links.upload_id

    # now complete it
    received_e_tag = await s3_client.complete_multipart_upload(
        bucket, file.name, upload_links.upload_id, part_to_etag
    )

    # check that the multipart upload is not listed anymore
    response = await s3_client.client.list_multipart_uploads(Bucket=bucket)
    assert response
    assert "Uploads" not in response

    # check the object is complete
    response = await s3_client.client.head_object(Bucket=bucket, Key=file.name)
    assert response
    assert response["ContentLength"] == file.stat().st_size
    assert response["ETag"] == f"{received_e_tag}"


async def test_abort_multipart_upload(
    s3_client: StorageS3Client,
    bucket: str,
    create_file_of_size: Callable[[ByteSize], Path],
):
    file = create_file_of_size(parse_obj_as(ByteSize, "100Mib"))
    upload_links = await s3_client.create_multipart_upload_links(
        bucket, file.name, parse_obj_as(ByteSize, file.stat().st_size)
    )
    assert upload_links

    # upload the file
    await upload_file_to_presigned_link(file, upload_links)

    # check it is not yet completed
    with pytest.raises(botocore.exceptions.ClientError):
        await s3_client.client.head_object(Bucket=bucket, Key=file.name)

    # check we have the multipart upload listed
    response = await s3_client.client.list_multipart_uploads(Bucket=bucket)
    assert response
    assert "Uploads" in response
    assert len(response["Uploads"]) == 1
    assert "UploadId" in response["Uploads"][0]
    assert response["Uploads"][0]["UploadId"] == upload_links.upload_id

    # now abort it
    await s3_client.abort_multipart_upload(bucket, file.name, upload_links.upload_id)

    # now check that the listing is empty
    response = await s3_client.client.list_multipart_uploads(Bucket=bucket)
    assert response
    assert "Uploads" not in response

    # check it is not available
    with pytest.raises(botocore.exceptions.ClientError):
        await s3_client.client.head_object(Bucket=bucket, Key=file.name)


async def test_delete_file(
    s3_client: StorageS3Client,
    bucket: str,
    create_file_of_size: Callable[[ByteSize], Path],
):

    file = create_file_of_size(parse_obj_as(ByteSize, "1Mib"))
    presigned_url = await s3_client.create_single_presigned_upload_link(
        bucket, file.name
    )
    assert presigned_url

    # upload the file
    async with ClientSession() as session:
        response = await session.put(presigned_url, data=file.open("rb"))
        response.raise_for_status()

    # check the object is complete
    response = await s3_client.client.head_object(Bucket=bucket, Key=file.name)
    assert response
    assert response["ContentLength"] == file.stat().st_size

    # delete the file
    await s3_client.delete_file(bucket, file.name)

    # check it is not available
    with pytest.raises(botocore.exceptions.ClientError):
        await s3_client.client.head_object(Bucket=bucket, Key=file.name)
