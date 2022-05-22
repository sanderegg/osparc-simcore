# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable


import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, Optional
from uuid import uuid4

import botocore.exceptions
import pytest
from aiohttp import ClientSession
from faker import Faker
from pydantic import ByteSize, parse_obj_as
from simcore_service_storage.s3_client import (
    FileID,
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


async def _clean_bucket_content(storage_s3_client: StorageS3Client, bucket: str):
    response = await storage_s3_client.client.list_objects_v2(Bucket=bucket)
    while response["KeyCount"] > 0:
        await storage_s3_client.client.delete_objects(
            Bucket=bucket,
            Delete={
                "Objects": [
                    {"Key": obj["Key"]} for obj in response["Contents"] if "Key" in obj
                ]
            },
        )
        response = await storage_s3_client.client.list_objects_v2(Bucket=bucket)


async def _remove_all_buckets(storage_s3_client: StorageS3Client):
    response = await storage_s3_client.client.list_buckets()
    bucket_names = [
        bucket["Name"] for bucket in response["Buckets"] if "Name" in bucket
    ]
    await asyncio.gather(
        *(_clean_bucket_content(storage_s3_client, bucket) for bucket in bucket_names)
    )
    await asyncio.gather(
        *(
            storage_s3_client.client.delete_bucket(Bucket=bucket)
            for bucket in bucket_names
        )
    )


@pytest.fixture
async def storage_s3_client(
    app_settings: Settings,
) -> AsyncIterator[StorageS3Client]:
    assert app_settings.STORAGE_S3
    async with AsyncExitStack() as exit_stack:
        storage_s3_client = await StorageS3Client.create(
            exit_stack, app_settings.STORAGE_S3
        )
        # check that no bucket is lying around
        assert storage_s3_client
        response = await storage_s3_client.client.list_buckets()
        assert not response[
            "Buckets"
        ], f"for testing puproses, there should be no bucket lying around! {response=}"
        yield storage_s3_client
        # cleanup
        await _remove_all_buckets(storage_s3_client)


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


@pytest.fixture
async def storage_s3_bucket(
    storage_s3_client: StorageS3Client, faker: Faker
) -> AsyncIterator[str]:
    response = await storage_s3_client.client.list_buckets()
    assert not response["Buckets"]
    bucket_name = faker.pystr()
    await storage_s3_client.create_bucket(bucket_name)
    response = await storage_s3_client.client.list_buckets()
    assert response["Buckets"]
    assert bucket_name in [
        bucket_struct.get("Name") for bucket_struct in response["Buckets"]
    ], f"failed creating {bucket_name}"

    yield bucket_name
    # cleanup the bucket
    await _clean_bucket_content(storage_s3_client, bucket_name)
    # remove bucket
    await storage_s3_client.client.delete_bucket(Bucket=bucket_name)
    response = await storage_s3_client.client.list_buckets()
    assert bucket_name not in [
        bucket_struct.get("Name") for bucket_struct in response["Buckets"]
    ], f"{bucket_name} is already in S3, please check why"


async def test_create_single_presigned_upload_link(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    faker: Faker,
    create_file_of_size: Callable[[ByteSize], Path],
):
    file = create_file_of_size(parse_obj_as(ByteSize, "1Mib"))
    file_uuid = f"{uuid4()}/{uuid4()}/{file.name}"
    presigned_url = await storage_s3_client.create_single_presigned_upload_link(
        storage_s3_bucket, file_uuid
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
    response = await storage_s3_client.client.get_object(
        Bucket=storage_s3_bucket, Key=file_uuid
    )
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
    storage_s3_bucket: str,
    create_file_of_size: Callable[[ByteSize], Path],
    file_size: ByteSize,
):
    file = create_file_of_size(file_size)
    upload_links = await storage_s3_client.create_multipart_upload_links(
        storage_s3_bucket, file.name, parse_obj_as(ByteSize, file.stat().st_size)
    )
    assert upload_links

    # upload the file
    part_to_etag: list[UploadedPart] = await upload_file_to_presigned_link(
        file, upload_links
    )

    # check it is not yet completed
    with pytest.raises(botocore.exceptions.ClientError):
        await storage_s3_client.client.head_object(
            Bucket=storage_s3_bucket, Key=file.name
        )

    # check we have the multipart upload listed
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=storage_s3_bucket
    )
    assert response
    assert "Uploads" in response
    assert len(response["Uploads"]) == 1
    assert "UploadId" in response["Uploads"][0]
    assert response["Uploads"][0]["UploadId"] == upload_links.upload_id

    # now complete it
    received_e_tag = await storage_s3_client.complete_multipart_upload(
        storage_s3_bucket, file.name, upload_links.upload_id, part_to_etag
    )

    # check that the multipart upload is not listed anymore
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=storage_s3_bucket
    )
    assert response
    assert "Uploads" not in response

    # check the object is complete
    response = await storage_s3_client.client.head_object(
        Bucket=storage_s3_bucket, Key=file.name
    )
    assert response
    assert response["ContentLength"] == file.stat().st_size
    assert response["ETag"] == f"{received_e_tag}"


async def test_abort_multipart_upload(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    create_file_of_size: Callable[[ByteSize], Path],
):
    file = create_file_of_size(parse_obj_as(ByteSize, "100Mib"))
    upload_links = await storage_s3_client.create_multipart_upload_links(
        storage_s3_bucket, file.name, parse_obj_as(ByteSize, file.stat().st_size)
    )
    assert upload_links

    # upload the file
    await upload_file_to_presigned_link(file, upload_links)

    # check it is not yet completed
    with pytest.raises(botocore.exceptions.ClientError):
        await storage_s3_client.client.head_object(
            Bucket=storage_s3_bucket, Key=file.name
        )

    # check we have the multipart upload listed
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=storage_s3_bucket
    )
    assert response
    assert "Uploads" in response
    assert len(response["Uploads"]) == 1
    assert "UploadId" in response["Uploads"][0]
    assert response["Uploads"][0]["UploadId"] == upload_links.upload_id

    # now abort it
    await storage_s3_client.abort_multipart_upload(
        storage_s3_bucket, file.name, upload_links.upload_id
    )

    # now check that the listing is empty
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=storage_s3_bucket
    )
    assert response
    assert "Uploads" not in response

    # check it is not available
    with pytest.raises(botocore.exceptions.ClientError):
        await storage_s3_client.client.head_object(
            Bucket=storage_s3_bucket, Key=file.name
        )


@pytest.fixture
def upload_file(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    create_file_of_size: Callable[[ByteSize], Path],
) -> Callable[..., Awaitable[FileID]]:
    async def _uploader(file_id: Optional[FileID] = None) -> FileID:
        file = create_file_of_size(parse_obj_as(ByteSize, "1Mib"))
        if not file_id:
            file_id = file.name
        presigned_url = await storage_s3_client.create_single_presigned_upload_link(
            storage_s3_bucket, file_id
        )
        assert presigned_url

        # upload the file
        async with ClientSession() as session:
            response = await session.put(presigned_url, data=file.open("rb"))
            response.raise_for_status()

        # check the object is complete
        response = await storage_s3_client.client.head_object(
            Bucket=storage_s3_bucket, Key=file_id
        )
        assert response
        assert response["ContentLength"] == file.stat().st_size
        return file_id

    return _uploader


async def test_delete_file(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    upload_file: Callable[..., Awaitable[FileID]],
):
    file_id = await upload_file()

    # delete the file
    await storage_s3_client.delete_file(storage_s3_bucket, file_id)

    # check it is not available
    with pytest.raises(botocore.exceptions.ClientError):
        await storage_s3_client.client.head_object(
            Bucket=storage_s3_bucket, Key=file_id
        )


async def test_delete_files_in_project_node(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    upload_file: Callable[..., Awaitable[FileID]],
    faker: Faker,
):
    # we upload files in these paths
    project_1 = uuid4()
    project_2 = uuid4()
    node_1 = uuid4()
    node_2 = uuid4()
    node_3 = uuid4()
    upload_paths = (
        "",
        f"{project_1}/",
        f"{project_1}/{node_1}/",
        f"{project_1}/{node_2}/",
        f"{project_1}/{node_2}/",
        f"{project_1}/{node_3}/",
        f"{project_1}/{node_3}/",
        f"{project_1}/{node_3}/",
        f"{project_2}/",
        f"{project_2}/{node_1}/",
        f"{project_2}/{node_2}/",
        f"{project_2}/{node_2}/",
        f"{project_2}/{node_2}/",
        f"{project_2}/{node_2}/",
        f"{project_2}/{node_3}/",
        f"{project_2}/{node_3}/states/",
        f"{project_2}/{node_3}/some_folder_of_sort/",
    )

    uploaded_file_ids = await asyncio.gather(
        *(upload_file(file_id=f"{path}{faker.file_name()}") for path in upload_paths)
    )
    assert len(uploaded_file_ids) == len(upload_paths)

    async def _assert_deleted(*, deleted_ids: tuple[str, ...]):
        for file_id in uploaded_file_ids:
            if file_id.startswith(deleted_ids):
                with pytest.raises(botocore.exceptions.ClientError):
                    await storage_s3_client.client.head_object(
                        Bucket=storage_s3_bucket, Key=file_id
                    )
            else:
                response = await storage_s3_client.client.head_object(
                    Bucket=storage_s3_bucket, Key=file_id
                )
                assert response
                assert response["ETag"]

    # now let's delete some files and check they are correctly deleted
    await storage_s3_client.delete_files_in_project_node(
        storage_s3_bucket, project_1, node_3
    )
    await _assert_deleted(deleted_ids=(f"{project_1}/{node_3}",))

    # delete some stuff in project 2
    await storage_s3_client.delete_files_in_project_node(
        storage_s3_bucket, project_2, node_3
    )
    await _assert_deleted(
        deleted_ids=(
            f"{project_1}/{node_3}",
            f"{project_2}/{node_3}",
        )
    )

    # completely delete project 2
    await storage_s3_client.delete_files_in_project_node(
        storage_s3_bucket, project_2, None
    )
    await _assert_deleted(
        deleted_ids=(
            f"{project_1}/{node_3}",
            f"{project_2}",
        )
    )
