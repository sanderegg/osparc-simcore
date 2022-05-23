import pytest
from pydantic import ValidationError, parse_obj_as
from simcore_service_storage.models import FileID


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
