import random
from pathlib import Path
from typing import Optional

import pytest
from aiohttp import ClientSession
from pydantic import ByteSize, parse_obj_as
from simcore_service_storage.models import ETag, FileID, FileMetaData
from simcore_service_storage.utils import (
    MAX_CHUNK_SIZE,
    download_to_file_or_raise,
    is_file_entry_valid,
)


async def test_download_files(tmpdir):

    destination = Path(tmpdir) / "data"
    expected_size = MAX_CHUNK_SIZE * 3 + 1000

    async with ClientSession() as session:
        total_size = await download_to_file_or_raise(
            session, f"https://httpbin.org/bytes/{expected_size}", destination
        )
        assert destination.exists()
        assert expected_size == total_size
        assert destination.stat().st_size == total_size


@pytest.mark.parametrize(
    "file_size, entity_tag, expected_validity",
    [
        (-1, None, False),
        (0, None, False),
        (random.randint(1, 1000000), None, False),
        (-1, "some_valid_entity_tag", False),
        (0, "some_valid_entity_tag", False),
        (random.randint(1, 1000000), "some_valid_entity_tag", True),
    ],
)
def test_file_entry_valid(
    file_size: int, entity_tag: Optional[ETag], expected_validity: bool
):
    file_uuid = FileID(Path("api") / Path("abcd") / Path("xx.dat"))
    fmd = FileMetaData.from_simcore_node(
        user_id=12, file_uuid=file_uuid, bucket="test-bucket"
    )
    fmd.file_size = parse_obj_as(ByteSize, file_size)
    fmd.entity_tag = entity_tag
    assert is_file_entry_valid(fmd) == expected_validity
