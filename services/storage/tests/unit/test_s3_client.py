# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable


from contextlib import AsyncExitStack
from pathlib import Path
from typing import Callable
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
    # NOTE: override services/storage/tests/conftest.py::mock_config
    monkeypatch.setenv("STORAGE_POSTGRES", "null")


async def test_storage_storage_s3_client_creation(app_settings: Settings):
    assert app_settings.STORAGE_S3
    async with AsyncExitStack() as exit_stack:
        storage_s3_client = await StorageS3Client.create(
            exit_stack, app_settings.STORAGE_S3
        )
        assert storage_s3_client
        response = await storage_s3_client.client.list_buckets()
        assert not response["Buckets"]
    with pytest.raises(botocore.exceptions.HTTPClientError):
        await storage_s3_client.client.list_buckets()


async def test_create_bucket(storage_s3_client: StorageS3Client, faker: Faker):
    response = await storage_s3_client.client.list_buckets()
    assert not response["Buckets"]
    bucket = faker.pystr()
    await storage_s3_client.create_bucket(bucket)
    response = await storage_s3_client.client.list_buckets()
    assert response["Buckets"]
    assert len(response["Buckets"]) == 1
    assert "Name" in response["Buckets"][0]
    assert response["Buckets"][0]["Name"] == bucket
    # now we create the bucket again, it should silently work even if it exists already
    await storage_s3_client.create_bucket(bucket)
    response = await storage_s3_client.client.list_buckets()
    assert response["Buckets"]
    assert len(response["Buckets"]) == 1
    assert "Name" in response["Buckets"][0]
    assert response["Buckets"][0]["Name"] == bucket


async def test_create_single_presigned_upload_link(
    storage_s3_client: StorageS3Client,
    with_bucket_in_s3: str,
    faker: Faker,
    create_file_of_size: Callable[[ByteSize], Path],
):
    file = create_file_of_size(parse_obj_as(ByteSize, "1Mib"))
    file_uuid = f"{uuid4()}/{uuid4()}/{file.name}"
    presigned_url = await storage_s3_client.create_single_presigned_upload_link(
        with_bucket_in_s3, file_uuid
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
    response = await storage_s3_client.client.get_object(Bucket=bucket, Key=file_uuid)
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
    storage_s3_client: StorageS3Client,
    with_bucket_in_s3: str,
    create_file_of_size: Callable[[ByteSize], Path],
    file_size: ByteSize,
):
    file = create_file_of_size(file_size)
    upload_links = await storage_s3_client.create_multipart_upload_links(
        with_bucket_in_s3, file.name, parse_obj_as(ByteSize, file.stat().st_size)
    )
    assert upload_links

    # upload the file
    part_to_etag: list[UploadedPart] = await upload_file_to_presigned_link(
        file, upload_links
    )

    # check it is not yet completed
    with pytest.raises(botocore.exceptions.ClientError):
        await storage_s3_client.client.head_object(
            Bucket=with_bucket_in_s3, Key=file.name
        )

    # check we have the multipart upload listed
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=with_bucket_in_s3
    )
    assert response
    assert "Uploads" in response
    assert len(response["Uploads"]) == 1
    assert "UploadId" in response["Uploads"][0]
    assert response["Uploads"][0]["UploadId"] == upload_links.upload_id

    # now complete it
    received_e_tag = await storage_s3_client.complete_multipart_upload(
        with_bucket_in_s3, file.name, upload_links.upload_id, part_to_etag
    )

    # check that the multipart upload is not listed anymore
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=with_bucket_in_s3
    )
    assert response
    assert "Uploads" not in response

    # check the object is complete
    response = await storage_s3_client.client.head_object(
        Bucket=with_bucket_in_s3, Key=file.name
    )
    assert response
    assert response["ContentLength"] == file.stat().st_size
    assert response["ETag"] == f"{received_e_tag}"


async def test_abort_multipart_upload(
    storage_s3_client: StorageS3Client,
    with_bucket_in_s3: str,
    create_file_of_size: Callable[[ByteSize], Path],
):
    file = create_file_of_size(parse_obj_as(ByteSize, "100Mib"))
    upload_links = await storage_s3_client.create_multipart_upload_links(
        with_bucket_in_s3, file.name, parse_obj_as(ByteSize, file.stat().st_size)
    )
    assert upload_links

    # upload the file
    await upload_file_to_presigned_link(file, upload_links)

    # check it is not yet completed
    with pytest.raises(botocore.exceptions.ClientError):
        await storage_s3_client.client.head_object(
            Bucket=with_bucket_in_s3, Key=file.name
        )

    # check we have the multipart upload listed
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=with_bucket_in_s3
    )
    assert response
    assert "Uploads" in response
    assert len(response["Uploads"]) == 1
    assert "UploadId" in response["Uploads"][0]
    assert response["Uploads"][0]["UploadId"] == upload_links.upload_id

    # now abort it
    await storage_s3_client.abort_multipart_upload(
        with_bucket_in_s3, file.name, upload_links.upload_id
    )

    # now check that the listing is empty
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=with_bucket_in_s3
    )
    assert response
    assert "Uploads" not in response

    # check it is not available
    with pytest.raises(botocore.exceptions.ClientError):
        await storage_s3_client.client.head_object(
            Bucket=with_bucket_in_s3, Key=file.name
        )


async def test_delete_file(
    storage_s3_client: StorageS3Client,
    with_bucket_in_s3: str,
    create_file_of_size: Callable[[ByteSize], Path],
):

    file = create_file_of_size(parse_obj_as(ByteSize, "1Mib"))
    presigned_url = await storage_s3_client.create_single_presigned_upload_link(
        with_bucket_in_s3, file.name
    )
    assert presigned_url

    # upload the file
    async with ClientSession() as session:
        response = await session.put(presigned_url, data=file.open("rb"))
        response.raise_for_status()

    # check the object is complete
    response = await storage_s3_client.client.head_object(
        Bucket=with_bucket_in_s3, Key=file.name
    )
    assert response
    assert response["ContentLength"] == file.stat().st_size

    # delete the file
    await storage_s3_client.delete_file(with_bucket_in_s3, file.name)

    # check it is not available
    with pytest.raises(botocore.exceptions.ClientError):
        await storage_s3_client.client.head_object(
            Bucket=with_bucket_in_s3, Key=file.name
        )
