import uuid
from pathlib import Path

import pytest
from models_library.projects import ProjectID
from models_library.projects_nodes_io import NodeID
from pydantic import ValidationError, parse_obj_as
from simcore_service_storage.constants import SIMCORE_S3_ID, SIMCORE_S3_STR
from simcore_service_storage.models import FileID, FileMetaData


@pytest.mark.parametrize(
    "file_id",
    ["test", "test/hop", "gogo", "//file.name"],
)
def test_file_id_raises_error(file_id: str):
    with pytest.raises(ValidationError):
        parse_obj_as(FileID, file_id)


@pytest.mark.parametrize(
    "file_id",
    [
        "project_1/node_3/file.asd",
        "project_1/node_3/file045asf-45_!...***",
        "26a59e74-2d41-11ea-ae9e-02420a0002af/d9a73c4a-a757-5395-ab33-eb845d122a3b/out_1",
        "api/09aea585-73ec-3087-9754-3b9cd5d1989a/file_with_number.txt",
    ],
)
def test_file_id(file_id: str):
    parsed_file_id = parse_obj_as(FileID, file_id)
    assert parsed_file_id
    assert parsed_file_id == file_id


def test_fmd_build():
    file_uuid = FileID(Path("api") / Path("abcd") / Path("xx.dat"))
    fmd = FileMetaData.from_simcore_node(
        user_id=12, file_uuid=file_uuid, bucket="test-bucket"
    )

    assert not fmd.node_id
    assert not fmd.project_id
    assert fmd.file_name == "xx.dat"
    assert fmd.object_name == "api/abcd/xx.dat"
    assert fmd.file_uuid == file_uuid
    assert fmd.location == SIMCORE_S3_STR
    assert fmd.location_id == SIMCORE_S3_ID
    assert fmd.bucket_name == "test-bucket"

    file_uuid = f"{uuid.uuid4()}/{uuid.uuid4()}/xx.dat"
    fmd = FileMetaData.from_simcore_node(
        user_id=12, file_uuid=file_uuid, bucket="test-bucket"
    )

    assert fmd.node_id == NodeID(file_uuid.split("/")[1])
    assert fmd.project_id == ProjectID(file_uuid.split("/")[0])
    assert fmd.file_name == "xx.dat"
    assert fmd.object_name == file_uuid
    assert fmd.file_uuid == file_uuid
    assert fmd.location == SIMCORE_S3_STR
    assert fmd.location_id == SIMCORE_S3_ID
    assert fmd.bucket_name == "test-bucket"


def test_fmd_raises_if_invalid_location():
    file_uuid = FileID(Path("api") / Path("abcd") / Path("xx.dat"))
    fmd = FileMetaData.from_simcore_node(
        user_id=12, file_uuid=file_uuid, bucket="test-bucket"
    )
    with pytest.raises(ValidationError):
        FileMetaData.parse_obj(fmd.copy(update={"location_id": 456}).dict())

    with pytest.raises(ValidationError):
        FileMetaData.parse_obj(
            fmd.copy(update={"location": "some place deep in space"}).dict()
        )
