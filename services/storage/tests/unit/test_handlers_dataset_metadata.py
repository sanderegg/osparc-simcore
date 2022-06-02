from pathlib import Path
from typing import Awaitable, Callable

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from faker import Faker
from models_library.api_schemas_storage import DatasetMetaData, FileMetaData
from models_library.projects import ProjectID
from models_library.projects_nodes import NodeID
from models_library.users import UserID
from pydantic import ByteSize, parse_obj_as
from pytest_simcore.helpers.utils_assert import assert_status
from simcore_service_storage.models import FileID

pytest_simcore_core_services_selection = ["postgres"]
pytest_simcore_ops_services_selection = ["adminer"]


def _file_size(size_str: str):
    return pytest.param(parse_obj_as(ByteSize, size_str), id=size_str)


async def test_get_files_metadata_dataset_with_no_files_returns_empty_array(
    client: TestClient,
    user_id: UserID,
    project_id: ProjectID,
    location_id: int,
):
    assert client.app
    url = (
        client.app.router["get_files_metadata_dataset"]
        .url_for(location_id=f"{location_id}", dataset_id=f"{project_id}")
        .with_query(user_id=user_id)
    )
    response = await client.get(f"{url}")
    data, error = await assert_status(response, web.HTTPOk)
    assert data == []
    assert not error


@pytest.mark.parametrize("file_size", [_file_size("100Mib")])
async def test_get_files_metadata_dataset(
    upload_file: Callable[[ByteSize, str], Awaitable[tuple[Path, FileID]]],
    client: TestClient,
    user_id: UserID,
    project_id: ProjectID,
    node_id: NodeID,
    location_id: int,
    file_size: ByteSize,
    faker: Faker,
):
    assert client.app
    NUM_FILES = 3
    for n in range(NUM_FILES):
        file, file_uuid = await upload_file(file_size, faker.file_name())
        url = (
            client.app.router["get_files_metadata_dataset"]
            .url_for(location_id=f"{location_id}", dataset_id=f"{project_id}")
            .with_query(user_id=user_id)
        )
        response = await client.get(f"{url}")
        data, error = await assert_status(response, web.HTTPOk)
        assert data
        assert not error
        list_fmds = parse_obj_as(list[FileMetaData], data)
        assert len(list_fmds) == (n + 1)
        fmd = list_fmds[n]
        assert fmd.user_id == user_id
        assert fmd.project_id == project_id
        assert fmd.node_id == node_id
        assert fmd.file_name == file.name
        assert fmd.file_id == file_uuid
        assert fmd.file_uuid == file_uuid
        assert fmd.object_name == file_uuid
        assert fmd.file_size == file.stat().st_size
        assert (
            fmd.display_file_path
            == f"{fmd.project_name}/{fmd.node_name}/{fmd.file_name}"
        )


async def test_get_datasets_metadata(
    client: TestClient,
    user_id: UserID,
    location_id: int,
    project_id: ProjectID,
):
    assert client.app

    url = (
        client.app.router["get_datasets_metadata"]
        .url_for(location_id=f"{location_id}")
        .with_query(user_id=f"{user_id}")
    )

    response = await client.get(f"{url}")
    data, error = await assert_status(response, web.HTTPOk)
    assert data
    assert not error
    list_datasets = parse_obj_as(list[DatasetMetaData], data)
    assert len(list_datasets) == 1
    dataset = list_datasets[0]
    assert dataset.dataset_id == project_id
