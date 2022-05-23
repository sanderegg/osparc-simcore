# pylint: disable=unused-variable
# pylint: disable=unused-argument
# pylint: disable=redefined-outer-name
# pylint: disable=too-many-arguments
# pylint: disable=no-name-in-module
# pylint: disable=no-member
# pylint: disable=too-many-branches

import datetime
import filecmp
import os
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

import pytest
from models_library.projects import ProjectID
from models_library.projects_nodes_io import NodeID
from models_library.users import UserID
from pydantic import ByteSize
from simcore_service_storage.access_layer import InvalidFileIdentifier
from simcore_service_storage.constants import SIMCORE_S3_ID, SIMCORE_S3_STR
from simcore_service_storage.dsm import DataStorageManager, LinkType
from simcore_service_storage.models import FileMetaData, FileMetaDataEx
from simcore_service_storage.s3_client import StorageS3Client
from tests.helpers.utils import USER_ID

pytest_simcore_core_services_selection = ["postgres"]
pytest_simcore_ops_services_selection = ["adminer"]


async def test_dsm_s3(
    dsm_mockup_db: dict[str, FileMetaData], dsm_fixture: DataStorageManager
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

    dsm = dsm_fixture
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
        bobs_biostromy_files[0].project_id, bobs_biostromy_files[0].node_id
    )
    filtered_data = await dsm.list_files(
        user_id=bob_id, location=SIMCORE_S3_STR, uuid_filter=str(uuid_filter)
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
) -> Iterator[Callable[..., FileMetaData]]:
    def _creator(tmp_file: Path) -> FileMetaData:
        # create file and upload
        filename = tmp_file.name
        project_id = "api"  # "357879cc-f65d-48b2-ad6c-074e2b9aa1c7"
        project_name = "battlestar"
        node_name = "galactica"
        node_id = "b423b654-686d-4157-b74b-08fa9d90b36e"
        file_name = filename
        file_uuid = os.path.join(str(project_id), str(node_id), str(file_name))
        display_name = os.path.join(str(project_name), str(node_name), str(file_name))
        created_at = str(datetime.datetime.now())
        file_size = tmp_file.stat().st_size

        d = {
            "object_name": os.path.join(str(project_id), str(node_id), str(file_name)),
            "bucket_name": storage_s3_bucket,
            "file_name": filename,
            "user_id": USER_ID,
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

        fmd = FileMetaData(**d)

        return fmd

    yield _creator


async def _upload_file(
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
        req = urllib.request.Request(f"{upload_links.urls[0]}", data=d, method="PUT")
        with urllib.request.urlopen(req) as _f:
            entity_tag = _f.headers.get("ETag")
    assert entity_tag is not None
    file_metadata.entity_tag = entity_tag.strip('"')
    return file_metadata


async def test_update_metadata_from_storage(
    postgres_dsn_url: str,
    mock_files_factory: Callable[[int], list[Path]],
    dsm_fixture: DataStorageManager,
    create_file_meta_for_s3: Callable,
):
    tmp_file = mock_files_factory(1)[0]
    fmd: FileMetaData = create_file_meta_for_s3(tmp_file)
    fmd = await _upload_file(dsm_fixture, fmd, Path(tmp_file))

    assert (
        await dsm_fixture.try_update_database_from_storage(  # pylint: disable=protected-access
            "some_fake_uuid", fmd.bucket_name, fmd.object_name, reraise_exceptions=False
        )
        is None
    )

    assert (
        await dsm_fixture.try_update_database_from_storage(  # pylint: disable=protected-access
            fmd.file_uuid, "some_fake_bucket", fmd.object_name, reraise_exceptions=False
        )
        is None
    )

    assert (
        await dsm_fixture.try_update_database_from_storage(  # pylint: disable=protected-access
            fmd.file_uuid, fmd.bucket_name, "some_fake_object", reraise_exceptions=False
        )
        is None
    )

    file_metadata: Optional[
        FileMetaDataEx
    ] = await dsm_fixture.try_update_database_from_storage(  # pylint: disable=protected-access
        fmd.file_uuid, fmd.bucket_name, fmd.object_name, reraise_exceptions=False
    )
    assert file_metadata is not None
    assert file_metadata.fmd.file_size == Path(tmp_file).stat().st_size
    assert file_metadata.fmd.entity_tag == fmd.entity_tag


async def test_links_s3(
    postgres_dsn_url: str,
    mock_files_factory: Callable[[int], list[Path]],
    dsm_fixture: DataStorageManager,
    create_file_meta_for_s3: Callable,
):

    tmp_file = mock_files_factory(1)[0]
    fmd: FileMetaData = create_file_meta_for_s3(tmp_file)

    dsm = dsm_fixture

    fmd = await _upload_file(dsm_fixture, fmd, Path(tmp_file))

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
    for field in FileMetaData.__attrs_attrs__:
        if field.name not in excluded_fields:
            if field.name == "location_id":
                assert int(
                    file_metadata.fmd.__getattribute__(field.name)
                ) == fmd.__getattribute__(
                    field.name
                ), f"{field.name}: expected {fmd.__getattribute__(field.name)} vs {file_metadata.fmd.__getattribute__(field.name)}"
            else:
                assert file_metadata.fmd.__getattribute__(
                    field.name
                ) == fmd.__getattribute__(
                    field.name
                ), f"{field.name}: expected {fmd.__getattribute__(field.name)} vs {file_metadata.fmd.__getattribute__(field.name)}"

    tmp_file2 = f"{tmp_file}.rec"
    user_id = 0
    down_url = await dsm.download_link_s3(
        fmd.file_uuid, user_id, as_presigned_link=True
    )
    urllib.request.urlretrieve(down_url, tmp_file2)

    assert filecmp.cmp(tmp_file2, tmp_file)


def test_fmd_build():
    file_uuid = str(Path("api") / Path("abcd") / Path("xx.dat"))
    fmd = FileMetaData()
    fmd.simcore_from_uuid(user_id=12, file_uuid=file_uuid, bucket_name="test-bucket")

    assert not fmd.node_id
    assert not fmd.project_id
    assert fmd.file_name == "xx.dat"
    assert fmd.object_name == "api/abcd/xx.dat"
    assert fmd.file_uuid == file_uuid
    assert fmd.location == SIMCORE_S3_STR
    assert fmd.location_id == SIMCORE_S3_ID
    assert fmd.bucket_name == "test-bucket"

    file_uuid = f"{uuid.uuid4()}/{uuid.uuid4()}/xx.dat"
    fmd.simcore_from_uuid(user_id=12, file_uuid=file_uuid, bucket_name="test-bucket")

    assert fmd.node_id == file_uuid.split("/")[1]
    assert fmd.project_id == file_uuid.split("/")[0]
    assert fmd.file_name == "xx.dat"
    assert fmd.object_name == file_uuid
    assert fmd.file_uuid == file_uuid
    assert fmd.location == SIMCORE_S3_STR
    assert fmd.location_id == SIMCORE_S3_ID
    assert fmd.bucket_name == "test-bucket"


async def test_dsm_complete_db(
    dsm_fixture: DataStorageManager,
    dsm_mockup_complete_db: tuple[dict[str, str], dict[str, str]],
):
    dsm = dsm_fixture
    _id = "21"
    dsm.has_project_db = True
    data = await dsm.list_files(user_id=_id, location=SIMCORE_S3_STR)

    assert len(data) == 2
    for dx in data:
        d = dx.fmd
        assert d.display_file_path
        assert d.node_name
        assert d.project_name
        assert d.raw_file_path


async def test_delete_data_folders(
    dsm_fixture: DataStorageManager,
    dsm_mockup_complete_db: tuple[dict[str, str], dict[str, str]],
):
    file_1, file_2 = dsm_mockup_complete_db
    _id = "21"
    data = await dsm_fixture.list_files(user_id=_id, location=SIMCORE_S3_STR)
    response = await dsm_fixture.delete_project_simcore_s3(
        user_id=UserID(_id),
        project_id=ProjectID(file_1["project_id"]),
        node_id=NodeID(file_1["node_id"]),
    )
    data = await dsm_fixture.list_files(user_id=_id, location=SIMCORE_S3_STR)
    assert len(data) == 1
    assert data[0].fmd.file_name == file_2["filename"]
    response = await dsm_fixture.delete_project_simcore_s3(
        user_id=UserID(_id), project_id=ProjectID(file_1["project_id"]), node_id=None
    )
    data = await dsm_fixture.list_files(user_id=_id, location=SIMCORE_S3_STR)
    assert not data


async def test_dsm_list_datasets_s3(dsm_fixture, dsm_mockup_complete_db):
    dsm_fixture.has_project_db = True

    datasets = await dsm_fixture.list_datasets(user_id="21", location=SIMCORE_S3_STR)

    assert len(datasets) == 1
    assert any("Kember" in d.display_name for d in datasets)


async def test_sync_table_meta_data(
    dsm_fixture: DataStorageManager,
    dsm_mockup_complete_db: tuple[dict[str, str], dict[str, str]],
    storage_s3_client: StorageS3Client,
    storage_s3_bucket: str,
):
    dsm_fixture.has_project_db = True

    expected_removed_files = []
    # the list should be empty on start
    list_changes: dict[str, Any] = await dsm_fixture.synchronise_meta_data_table(
        location=SIMCORE_S3_STR, dry_run=True
    )
    assert "removed" in list_changes
    assert list_changes["removed"] == expected_removed_files

    # now remove the files
    for file_entry in dsm_mockup_complete_db:
        s3_key = f"{file_entry['project_id']}/{file_entry['node_id']}/{file_entry['filename']}"
        await storage_s3_client.client.delete_object(
            Bucket=storage_s3_bucket, Key=s3_key
        )
        expected_removed_files.append(s3_key)

        # the list should now contain the removed entries
        list_changes: dict[str, Any] = await dsm_fixture.synchronise_meta_data_table(
            location=SIMCORE_S3_STR, dry_run=True
        )
        assert "removed" in list_changes
        assert list_changes["removed"] == expected_removed_files

    # now effectively call the function should really remove the files
    list_changes: dict[str, Any] = await dsm_fixture.synchronise_meta_data_table(
        location=SIMCORE_S3_STR, dry_run=False
    )
    # listing again will show an empty list again
    list_changes: dict[str, Any] = await dsm_fixture.synchronise_meta_data_table(
        location=SIMCORE_S3_STR, dry_run=True
    )
    assert "removed" in list_changes
    assert list_changes["removed"] == []


async def test_dsm_list_dataset_files_s3(
    dsm_fixture: DataStorageManager,
    dsm_mockup_complete_db: tuple[dict[str, str], dict[str, str]],
):
    dsm_fixture.has_project_db = True

    datasets = await dsm_fixture.list_datasets(user_id="21", location=SIMCORE_S3_STR)
    assert len(datasets) == 1
    assert any("Kember" in d.display_name for d in datasets)
    for d in datasets:
        files = await dsm_fixture.list_files_dataset(
            user_id="21", location=SIMCORE_S3_STR, dataset_id=d.dataset_id
        )
        if "Kember" in d.display_name:
            assert len(files) == 2
        else:
            assert len(files) == 0

        if files:
            found = await dsm_fixture.search_files_starting_with(
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
