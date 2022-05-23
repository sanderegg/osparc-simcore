# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable


import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import AsyncIterator, Awaitable, Callable, Final, Optional
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

DEFAULT_EXPIRATION_SECS: Final[int] = 10


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
    create_file_of_size: Callable[[ByteSize], Path],
):
    file = create_file_of_size(parse_obj_as(ByteSize, "1Mib"))
    file_uuid = f"{uuid4()}/{uuid4()}/{file.name}"
    presigned_url = await storage_s3_client.create_single_presigned_upload_link(
        storage_s3_bucket, file_uuid, expiration_secs=DEFAULT_EXPIRATION_SECS
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
    response = await storage_s3_client.client.head_object(
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
    upload_file_multipart_presigned_link_without_completion: Callable[
        ..., Awaitable[tuple[FileID, MultiPartUploadLinks, list[UploadedPart]]]
    ],
    file_size: ByteSize,
):
    (
        file_id,
        upload_links,
        uploaded_parts,
    ) = await upload_file_multipart_presigned_link_without_completion(file_size)

    # now complete it
    received_e_tag = await storage_s3_client.complete_multipart_upload(
        storage_s3_bucket, file_id, upload_links.upload_id, uploaded_parts
    )

    # check that the multipart upload is not listed anymore
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=storage_s3_bucket
    )
    assert response
    assert "Uploads" not in response

    # check the object is complete
    response = await storage_s3_client.client.head_object(
        Bucket=storage_s3_bucket, Key=file_id
    )
    assert response
    assert response["ContentLength"] == file_size
    assert response["ETag"] == f"{received_e_tag}"


async def test_abort_multipart_upload(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    upload_file_multipart_presigned_link_without_completion: Callable[
        ..., Awaitable[tuple[FileID, MultiPartUploadLinks, list[UploadedPart]]]
    ],
):
    (
        file_id,
        upload_links,
        _,
    ) = await upload_file_multipart_presigned_link_without_completion(
        parse_obj_as(ByteSize, "100Mib")
    )

    # now abort it
    await storage_s3_client.abort_multipart_upload(
        storage_s3_bucket, file_id, upload_links.upload_id
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
            Bucket=storage_s3_bucket, Key=file_id
        )


async def test_break_completion_of_multipart_upload(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    upload_file_multipart_presigned_link_without_completion: Callable[
        ..., Awaitable[tuple[FileID, MultiPartUploadLinks, list[UploadedPart]]]
    ],
):
    file_size = parse_obj_as(ByteSize, "1000Mib")
    (
        file_id,
        upload_links,
        uploaded_parts,
    ) = await upload_file_multipart_presigned_link_without_completion(file_size)
    # let's break the completion very quickly task and see what happens
    VERY_SHORT_TIMEOUT = 0.2
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            storage_s3_client.complete_multipart_upload(
                storage_s3_bucket, file_id, upload_links.upload_id, uploaded_parts
            ),
            timeout=VERY_SHORT_TIMEOUT,
        )
    # check we have the multipart upload initialized and listed
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=storage_s3_bucket
    )
    assert response
    assert "Uploads" in response
    assert len(response["Uploads"]) == 1
    assert "UploadId" in response["Uploads"][0]
    assert response["Uploads"][0]["UploadId"] == upload_links.upload_id

    # now wait
    await asyncio.sleep(10)

    # check that the completion of the update completed...
    response = await storage_s3_client.client.list_multipart_uploads(
        Bucket=storage_s3_bucket
    )
    assert response
    assert "Uploads" not in response

    # check the object is complete
    response = await storage_s3_client.client.head_object(
        Bucket=storage_s3_bucket, Key=file_id
    )
    assert response
    assert response["ContentLength"] == file_size


@pytest.fixture
def upload_file_single_presigned_link(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    create_file_of_size: Callable[[ByteSize], Path],
) -> Callable[..., Awaitable[FileID]]:
    async def _uploader(file_id: Optional[FileID] = None) -> FileID:
        file = create_file_of_size(parse_obj_as(ByteSize, "1Mib"))
        if not file_id:
            file_id = file.name
        presigned_url = await storage_s3_client.create_single_presigned_upload_link(
            storage_s3_bucket, file_id, expiration_secs=DEFAULT_EXPIRATION_SECS
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

        # check the object is complete
        response = await storage_s3_client.client.head_object(
            Bucket=storage_s3_bucket, Key=file_id
        )
        assert response
        assert response["ContentLength"] == file.stat().st_size
        return file_id

    return _uploader


@pytest.fixture
def upload_file_multipart_presigned_link_without_completion(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    create_file_of_size: Callable[[ByteSize], Path],
) -> Callable[..., Awaitable[tuple[FileID, MultiPartUploadLinks, list[UploadedPart]]]]:
    async def _uploader(
        file_size: ByteSize,
        file_id: Optional[FileID] = None,
    ) -> tuple[FileID, MultiPartUploadLinks, list[UploadedPart]]:
        file = create_file_of_size(file_size)
        if not file_id:
            file_id = file.name
        upload_links = await storage_s3_client.create_multipart_upload_links(
            storage_s3_bucket,
            file_id,
            ByteSize(file.stat().st_size),
            expiration_secs=DEFAULT_EXPIRATION_SECS,
        )
        assert upload_links

        # check there is no file yet
        with pytest.raises(botocore.exceptions.ClientError):
            await storage_s3_client.client.head_object(
                Bucket=storage_s3_bucket, Key=file.name
            )

        # check we have the multipart upload initialized and listed
        response = await storage_s3_client.client.list_multipart_uploads(
            Bucket=storage_s3_bucket
        )
        assert response
        assert "Uploads" in response
        assert len(response["Uploads"]) == 1
        assert "UploadId" in response["Uploads"][0]
        assert response["Uploads"][0]["UploadId"] == upload_links.upload_id

        # upload the file
        uploaded_parts: list[UploadedPart] = await upload_file_to_presigned_link(
            file,
            upload_links,
        )
        assert len(uploaded_parts) == len(upload_links.urls)

        # check there is no file yet
        with pytest.raises(botocore.exceptions.ClientError):
            await storage_s3_client.client.head_object(
                Bucket=storage_s3_bucket, Key=file.name
            )

        # check we have the multipart upload initialized and listed
        response = await storage_s3_client.client.list_multipart_uploads(
            Bucket=storage_s3_bucket
        )
        assert response
        assert "Uploads" in response
        assert len(response["Uploads"]) == 1
        assert "UploadId" in response["Uploads"][0]
        assert response["Uploads"][0]["UploadId"] == upload_links.upload_id

        return (
            file_id,
            upload_links,
            uploaded_parts,
        )

    return _uploader


async def test_delete_file(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    upload_file_single_presigned_link: Callable[..., Awaitable[FileID]],
):
    file_id = await upload_file_single_presigned_link()

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
    upload_file_single_presigned_link: Callable[..., Awaitable[FileID]],
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
        *(
            upload_file_single_presigned_link(file_id=f"{path}{faker.file_name()}")
            for path in upload_paths
        )
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


async def test_create_single_presigned_download_link(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    upload_file_single_presigned_link: Callable[..., Awaitable[FileID]],
    tmp_path: Path,
    faker: Faker,
):
    file_id = await upload_file_single_presigned_link()

    presigned_url = await storage_s3_client.create_single_presigned_download_link(
        storage_s3_bucket, file_id, expiration_secs=DEFAULT_EXPIRATION_SECS
    )

    assert presigned_url

    dest_file = tmp_path / faker.file_name()
    # download the file
    async with ClientSession() as session:
        response = await session.get(presigned_url)
        response.raise_for_status()
        with dest_file.open("wb") as fp:
            fp.write(await response.read())
    assert dest_file.exists()

    response = await storage_s3_client.client.head_object(
        Bucket=storage_s3_bucket, Key=file_id
    )
    assert response
    assert response["ETag"]
    assert dest_file.stat().st_size == response["ContentLength"]
