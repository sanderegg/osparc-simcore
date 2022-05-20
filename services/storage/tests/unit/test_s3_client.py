# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import AsyncIterator, Callable

import botocore.exceptions
import pytest
from aiohttp import ClientSession
from faker import Faker
from moto.server import ThreadedMotoServer
from pydantic import ByteSize, parse_obj_as
from simcore_service_storage.s3_client import StorageS3Client
from simcore_service_storage.settings import Settings


@pytest.fixture
def mock_config(mocked_s3_server: ThreadedMotoServer, monkeypatch: pytest.MonkeyPatch):
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
    presigned_url = await s3_client.create_single_presigned_upload_link(
        bucket, file.name
    )
    assert presigned_url

    # upload the file
    async with ClientSession() as session:
        response = await session.put(presigned_url, data=file.open("rb"))
        response.raise_for_status()

    # check it is there
    response = await s3_client.client.get_object(Bucket=bucket, Key=file.name)
    assert response
    assert response["ContentLength"] == file.stat().st_size
