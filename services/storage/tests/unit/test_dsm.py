# pylint: disable=unused-variable
# pylint: disable=unused-argument
# pylint: disable=redefined-outer-name
# pylint: disable=too-many-arguments
# pylint: disable=no-name-in-module
# pylint: disable=no-member
# pylint: disable=too-many-branches

import asyncio
import datetime
import filecmp
import os
import urllib.request
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator, Optional
from uuid import uuid4

import pytest
from aiopg.sa.engine import Engine
from faker import Faker
from models_library.projects import ProjectID
from models_library.users import UserID
from pydantic import ByteSize, parse_obj_as
from simcore_service_storage import db_file_meta_data
from simcore_service_storage.access_layer import InvalidFileIdentifier
from simcore_service_storage.constants import SIMCORE_S3_ID, SIMCORE_S3_STR
from simcore_service_storage.dsm import DataStorageManager, LinkType
from simcore_service_storage.exceptions import FileMetaDataNotFoundError
from simcore_service_storage.models import (
    FileID,
    FileMetaData,
    FileMetaDataEx,
    file_meta_data,
)
from simcore_service_storage.s3_client import StorageS3Client, UploadedPart

pytest_simcore_core_services_selection = ["postgres", "redis"]
pytest_simcore_ops_services_selection = ["adminer"]


@pytest.fixture
def upload_file() -> Callable[..., Awaitable[FileMetaData]]:
    async def _uploader(
        dsm: DataStorageManager, file_metadata: FileMetaData, file_path: Path
    ) -> FileMetaData:
        upload_links = await dsm.create_upload_links(
            file_metadata.user_id,
            file_metadata.file_uuid,
            link_type=LinkType.PRESIGNED,
            file_size_bytes=ByteSize(0),
        )
        assert file_path.exists()
        assert upload_links
        assert upload_links.urls
        assert len(upload_links.urls) == 1
        with file_path.open("rb") as fp:
            d = fp.read()
            req = urllib.request.Request(
                f"{upload_links.urls[0]}", data=d, method="PUT"
            )
            with urllib.request.urlopen(req) as _f:
                entity_tag = _f.headers.get("ETag")
        assert entity_tag is not None
        file_metadata.entity_tag = entity_tag.strip('"')

        await dsm.complete_upload(
            file_metadata.file_uuid,
            file_metadata.user_id,
            [UploadedPart(number=1, e_tag=entity_tag)],
        )
        return file_metadata

    return _uploader


@pytest.fixture
async def dsm_mockup_complete_db(
    storage_dsm: DataStorageManager,
    upload_file: Callable,
    mock_files_factory: Callable[[int], list[Path]],
    create_file_meta_for_s3: Callable[..., FileMetaData],
    cleanup_user_projects_file_metadata: None,
) -> tuple[FileMetaData, FileMetaData]:

    tmp_file = mock_files_factory(2)
    fmd: FileMetaData = create_file_meta_for_s3(tmp_file[0])
    fmd = await upload_file(storage_dsm, fmd, tmp_file[0])

    fmd2: FileMetaData = create_file_meta_for_s3(tmp_file[1])
    fmd2 = await upload_file(storage_dsm, fmd2, tmp_file[1])

    return (fmd, fmd2)


async def test_listing_and_deleting_files(
    dsm_mockup_db: dict[str, FileMetaData], storage_dsm: DataStorageManager
):
    id_name_map = {}
    id_file_count = {}
    for d in dsm_mockup_db.keys():
        md = dsm_mockup_db[d]
        if not md.user_id in id_name_map:
            id_name_map[md.user_id] = md.user_name
            id_file_count[md.user_id] = 1
        else:
            id_file_count[md.user_id] = id_file_count[md.user_id] + 1

    dsm = storage_dsm
    # NOTE: this one is a joke
    dsm.has_project_db = False
    # list files for every user
    for _id in id_file_count:
        data = await dsm.list_files(user_id=_id, location=SIMCORE_S3_STR)
        assert len(data) == id_file_count[_id]

    # Get files from bob from the project biology
    bob_id = 0
    for _id, _name in id_name_map.items():
        if _name == "bob":
            bob_id = _id
            break
    assert not bob_id == 0

    data = await dsm.list_files(
        user_id=bob_id, location=SIMCORE_S3_STR, regex="biology"
    )
    data1 = await dsm.list_files(
        user_id=bob_id, location=SIMCORE_S3_STR, regex="astronomy"
    )
    data = data + data1
    bobs_biostromy_files = []
    for d in dsm_mockup_db.keys():
        md = dsm_mockup_db[d]
        if md.user_id == bob_id and (md.project_name in ("biology", "astronomy")):
            bobs_biostromy_files.append(md)

    assert len(data) == len(bobs_biostromy_files)

    # among bobs bio files, filter by project/node, take first one

    uuid_filter = os.path.join(
        f"{bobs_biostromy_files[0].project_id}", f"{bobs_biostromy_files[0].node_id}"
    )
    filtered_data = await dsm.list_files(
        user_id=bob_id, location=SIMCORE_S3_STR, uuid_filter=f"{uuid_filter}"
    )
    assert filtered_data[0].fmd == bobs_biostromy_files[0]

    for dx in data:
        d = dx.fmd
        await dsm.delete_file(
            user_id=d.user_id, location=SIMCORE_S3_STR, file_uuid=d.file_uuid
        )

    # now we should have less items
    new_size = 0
    for _id in id_file_count:
        data = await dsm.list_files(user_id=_id, location=SIMCORE_S3_STR)
        new_size = new_size + len(data)

    assert len(dsm_mockup_db) == new_size + len(bobs_biostromy_files)
    assert len(dsm_mockup_db) == new_size + len(bobs_biostromy_files)


@pytest.fixture
def create_file_meta_for_s3(
    storage_s3_bucket: str,
    cleanup_user_projects_file_metadata: None,
    user_id: UserID,
    project_id: ProjectID,
) -> Iterator[Callable[..., FileMetaData]]:
    def _creator(tmp_file: Path) -> FileMetaData:
        # create file and upload
        filename = tmp_file.name
        project_name = "battlestar"
        node_name = "galactica"
        node_id = uuid4()
        file_name = filename
        file_uuid = os.path.join(str(project_id), str(node_id), str(file_name))
        display_name = os.path.join(str(project_name), str(node_name), str(file_name))
        created_at = str(datetime.datetime.now())
        file_size = tmp_file.stat().st_size

        d = {
            "object_name": os.path.join(str(project_id), str(node_id), str(file_name)),
            "bucket_name": storage_s3_bucket,
            "file_name": filename,
            "user_id": user_id,
            "user_name": "starbucks",
            "location": SIMCORE_S3_STR,
            "location_id": SIMCORE_S3_ID,
            "project_id": project_id,
            "project_name": project_name,
            "node_id": node_id,
            "node_name": node_name,
            "file_uuid": file_uuid,
            "file_id": file_uuid,
            "raw_file_path": file_uuid,
            "display_file_path": display_name,
            "created_at": created_at,
            "last_modified": created_at,
            "file_size": file_size,
        }

        fmd = FileMetaData.parse_obj(d)

        return fmd

    yield _creator


async def test_update_metadata_from_storage(
    mock_files_factory: Callable[[int], list[Path]],
    storage_dsm: DataStorageManager,
    create_file_meta_for_s3: Callable,
    upload_file: Callable,
):
    tmp_file = mock_files_factory(1)[0]
    fmd: FileMetaData = create_file_meta_for_s3(tmp_file)
    fmd = await upload_file(storage_dsm, fmd, Path(tmp_file))

    assert (
        await storage_dsm.try_update_database_from_storage(  # pylint: disable=protected-access
            "some_fake_uuid", fmd.bucket_name, fmd.object_name, reraise_exceptions=False
        )
        is None
    )

    assert (
        await storage_dsm.try_update_database_from_storage(  # pylint: disable=protected-access
            fmd.file_uuid, "some_fake_bucket", fmd.object_name, reraise_exceptions=False
        )
        is None
    )

    assert (
        await storage_dsm.try_update_database_from_storage(  # pylint: disable=protected-access
            fmd.file_uuid, fmd.bucket_name, "some_fake_object", reraise_exceptions=False
        )
        is None
    )

    file_metadata: Optional[
        FileMetaDataEx
    ] = await storage_dsm.try_update_database_from_storage(  # pylint: disable=protected-access
        fmd.file_uuid, fmd.bucket_name, fmd.object_name, reraise_exceptions=False
    )
    assert file_metadata is not None
    assert file_metadata.fmd.file_size == Path(tmp_file).stat().st_size
    assert file_metadata.fmd.entity_tag == fmd.entity_tag


async def test_links_s3(
    mock_files_factory: Callable[[int], list[Path]],
    storage_dsm: DataStorageManager,
    create_file_meta_for_s3: Callable,
    upload_file: Callable,
):

    tmp_file = mock_files_factory(1)[0]
    fmd: FileMetaData = create_file_meta_for_s3(tmp_file)

    dsm = storage_dsm

    fmd = await upload_file(storage_dsm, fmd, Path(tmp_file))

    # test wrong user
    assert await dsm.list_file(654654654, fmd.location, fmd.file_uuid) is None

    # test wrong location
    assert await dsm.list_file(fmd.user_id, "whatever_location", fmd.file_uuid) is None

    # test wrong file uuid
    with pytest.raises(InvalidFileIdentifier):
        await dsm.list_file(fmd.user_id, fmd.location, "some_fake_uuid")
    # use correctly
    file_metadata: Optional[FileMetaDataEx] = await dsm.list_file(
        fmd.user_id, fmd.location, fmd.file_uuid
    )
    assert file_metadata is not None
    excluded_fields = [
        "project_id",
        "project_name",
        "node_name",
        "user_name",
        "display_file_path",
        "created_at",
        "last_modified",
        "upload_expires_at",
    ]
    for field in FileMetaData.__fields__:
        if field not in excluded_fields:
            assert file_metadata.fmd.__getattribute__(field) == fmd.__getattribute__(
                field
            ), f"{field}: expected {fmd.__getattribute__(field)} vs {file_metadata.fmd.__getattribute__(field)}"

    tmp_file2 = f"{tmp_file}.rec"
    down_url = await dsm.download_link_s3(
        fmd.file_uuid, fmd.user_id, link_type=LinkType.PRESIGNED
    )
    urllib.request.urlretrieve(down_url, tmp_file2)

    assert filecmp.cmp(tmp_file2, tmp_file)


async def test_delete_data_folders(
    storage_dsm: DataStorageManager,
    dsm_mockup_complete_db: tuple[FileMetaData, FileMetaData],
):
    storage_dsm.has_project_db = False  # again the joke
    file_1, file_2 = dsm_mockup_complete_db
    assert file_1.project_id
    assert file_1.node_id
    data = await storage_dsm.list_files(user_id=file_1.user_id, location=SIMCORE_S3_STR)
    response = await storage_dsm.delete_project_simcore_s3(
        user_id=file_1.user_id,
        project_id=file_1.project_id,
        node_id=file_1.node_id,
    )
    data = await storage_dsm.list_files(user_id=file_1.user_id, location=SIMCORE_S3_STR)
    assert len(data) == 1
    assert data[0].fmd.file_name == file_2.file_name
    response = await storage_dsm.delete_project_simcore_s3(
        user_id=file_1.user_id, project_id=file_1.project_id, node_id=None
    )
    data = await storage_dsm.list_files(user_id=file_1.user_id, location=SIMCORE_S3_STR)
    assert not data


async def test_dsm_list_datasets_s3(
    storage_dsm, dsm_mockup_complete_db: tuple[FileMetaData, FileMetaData]
):
    storage_dsm.has_project_db = True
    file_1, _ = dsm_mockup_complete_db

    datasets = await storage_dsm.list_datasets(
        user_id=file_1.user_id, location=SIMCORE_S3_STR
    )

    assert len(datasets) == 1


async def test_sync_table_meta_data(
    storage_dsm: DataStorageManager,
    dsm_mockup_complete_db: tuple[FileMetaData, FileMetaData],
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
):
    storage_dsm.has_project_db = True

    expected_removed_files = []
    # the list should be empty on start
    list_changes: dict[str, Any] = await storage_dsm.synchronise_meta_data_table(
        location=SIMCORE_S3_STR, dry_run=True
    )
    assert "removed" in list_changes
    assert list_changes["removed"] == expected_removed_files

    # now remove the files
    for file_entry in dsm_mockup_complete_db:
        s3_key = f"{file_entry.project_id}/{file_entry.node_id}/{file_entry.file_name}"
        await storage_s3_client.client.delete_object(
            Bucket=storage_s3_bucket, Key=s3_key
        )
        expected_removed_files.append(s3_key)

        # the list should now contain the removed entries
        list_changes: dict[str, Any] = await storage_dsm.synchronise_meta_data_table(
            location=SIMCORE_S3_STR, dry_run=True
        )
        assert "removed" in list_changes
        assert list_changes["removed"] == expected_removed_files

    # now effectively call the function should really remove the files
    list_changes: dict[str, Any] = await storage_dsm.synchronise_meta_data_table(
        location=SIMCORE_S3_STR, dry_run=False
    )
    # listing again will show an empty list again
    list_changes: dict[str, Any] = await storage_dsm.synchronise_meta_data_table(
        location=SIMCORE_S3_STR, dry_run=True
    )
    assert "removed" in list_changes
    assert list_changes["removed"] == []


async def test_dsm_list_dataset_files_s3(
    storage_dsm: DataStorageManager,
    dsm_mockup_complete_db: tuple[FileMetaData, FileMetaData],
):
    storage_dsm.has_project_db = True
    file_1, _ = dsm_mockup_complete_db
    datasets = await storage_dsm.list_datasets(
        user_id=file_1.user_id, location=SIMCORE_S3_STR
    )
    assert len(datasets) == 1
    for d in datasets:
        files = await storage_dsm.list_files_dataset(
            user_id=21, location=SIMCORE_S3_STR, dataset_id=d.dataset_id
        )
        if "Kember" in d.display_name:
            assert len(files) == 2
        else:
            assert len(files) == 0

        if files:
            found = await storage_dsm.search_files_starting_with(
                user_id=21, prefix=files[0].fmd.file_uuid
            )
            assert found
            assert len(found) == 1
            assert found[0].fmd.file_uuid == files[0].fmd.file_uuid
            assert found[0].parent_id == files[0].parent_id
            assert found[0].fmd.node_id == files[0].fmd.node_id
            # NOTE: found and files differ in these attributes
            #  ['project_name', 'node_name', 'file_id', 'raw_file_path', 'display_file_path']
            #  because these are added artificially in list_files


async def test_clean_expired_uploads_cleans_dangling_multipart_uploads(
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
    storage_dsm: DataStorageManager,
    faker: Faker,
):
    file_id = faker.file_name()
    file_size = parse_obj_as(ByteSize, "100Mib")
    upload_links = await storage_s3_client.create_multipart_upload_links(
        storage_s3_bucket, file_id, file_size, expiration_secs=3600
    )

    # ensure we have now an upload id
    all_ongoing_uploads = await storage_s3_client.list_ongoing_multipart_uploads(
        storage_s3_bucket
    )
    assert len(all_ongoing_uploads) == 1
    ongoing_upload_id, ongoing_file_id = all_ongoing_uploads[0]
    assert upload_links.upload_id == ongoing_upload_id
    assert ongoing_file_id == file_id

    # now run the cleaner
    await storage_dsm.clean_expired_uploads()

    # since there is no entry in the db, this upload shall be cleaned up
    assert not await storage_s3_client.list_ongoing_multipart_uploads(storage_s3_bucket)


@pytest.mark.parametrize(
    "file_size",
    [ByteSize(0), parse_obj_as(ByteSize, "10Mib"), parse_obj_as(ByteSize, "100Mib")],
)
@pytest.mark.parametrize("link_type", [LinkType.S3, LinkType.PRESIGNED])
async def test_clean_expired_uploads_cleans_expired_pending_uploads(
    aiopg_engine: Engine,
    storage_dsm: DataStorageManager,
    file_uuid: FileID,
    user_id: UserID,
    link_type: LinkType,
    file_size: ByteSize,
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
):
    await storage_dsm.create_upload_links(user_id, file_uuid, link_type, file_size)
    # ensure the database is correctly set up
    async with aiopg_engine.acquire() as conn:
        fmd = await db_file_meta_data.get(conn, file_uuid)
    assert fmd
    assert fmd.upload_expires_at
    # ensure we have now an upload id
    ongoing_uploads = await storage_s3_client.list_ongoing_multipart_uploads(
        storage_s3_bucket
    )
    if fmd.upload_id:
        assert len(ongoing_uploads) == 1
    else:
        assert not ongoing_uploads

    # now run the cleaner, nothing should happen since the expiration was set to the default of 3600
    await storage_dsm.clean_expired_uploads()
    # check the entries are still the same
    async with aiopg_engine.acquire() as conn:
        fmd_after_clean = await db_file_meta_data.get(conn, file_uuid)
    assert fmd_after_clean == fmd
    assert (
        await storage_s3_client.list_ongoing_multipart_uploads(storage_s3_bucket)
        == ongoing_uploads
    )

    # now change the upload_expires_at entry to simulate and expired entry
    async with aiopg_engine.acquire() as conn:
        await conn.execute(
            file_meta_data.update()
            .where(file_meta_data.c.file_uuid == file_uuid)
            .values(upload_expires_at=datetime.datetime.utcnow())
        )
    await asyncio.sleep(1)
    await storage_dsm.clean_expired_uploads()

    # check the entries were removed
    async with aiopg_engine.acquire() as conn:
        with pytest.raises(FileMetaDataNotFoundError):
            await db_file_meta_data.get(conn, file_uuid)
    # since there is no entry in the db, this upload shall be cleaned up
    assert not await storage_s3_client.list_ongoing_multipart_uploads(storage_s3_bucket)
