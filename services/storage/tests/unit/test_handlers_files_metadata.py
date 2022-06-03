# pylint: disable=protected-access
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument


import urllib.parse
from pathlib import Path
from random import choice
from typing import Awaitable, Callable

from aiohttp import web
from aiohttp.test_utils import TestClient
from faker import Faker
from models_library.api_schemas_storage import FileMetaData
from models_library.projects import ProjectID
from models_library.users import UserID
from pydantic import ByteSize, parse_obj_as
from pytest_simcore.helpers.utils_assert import assert_status
from simcore_service_storage.models import FileID

pytest_simcore_core_services_selection = ["postgres", "redis"]
pytest_simcore_ops_services_selection = ["adminer"]


async def test_get_files_metadata(
    upload_file: Callable[[ByteSize, str], Awaitable[tuple[Path, FileID]]],
    client: TestClient,
    user_id: UserID,
    location_id: int,
    project_id: ProjectID,
    faker: Faker,
):
    assert client.app

    url = (
        client.app.router["get_files_metadata"]
        .url_for(location_id=f"{location_id}")
        .with_query(user_id=f"{user_id}")
    )

    # this should return an empty list
    response = await client.get(f"{url}")
    data, error = await assert_status(response, web.HTTPOk)
    assert not error
    list_fmds = parse_obj_as(list[FileMetaData], data)
    assert not list_fmds

    # now add some stuff there
    NUM_FILES = 10
    file_size = parse_obj_as(ByteSize, "15Mib")
    files_owned_by_us = []
    for _ in range(NUM_FILES):
        files_owned_by_us.append(await upload_file(file_size, faker.file_name()))
    # we should find these files now
    response = await client.get(f"{url}")
    data, error = await assert_status(response, web.HTTPOk)
    assert not error
    list_fmds = parse_obj_as(list[FileMetaData], data)
    assert len(list_fmds) == NUM_FILES
    # create some more files but with a base common name
    NUM_FILES = 10
    file_size = parse_obj_as(ByteSize, "15Mib")
    files_with_common_name = []
    for _ in range(NUM_FILES):
        files_with_common_name.append(
            await upload_file(file_size, f"common_name-{faker.file_name()}")
        )
    # we should find these files now
    response = await client.get(f"{url}")
    data, error = await assert_status(response, web.HTTPOk)
    assert not error
    list_fmds = parse_obj_as(list[FileMetaData], data)
    assert len(list_fmds) == (2 * NUM_FILES)
    # we can filter them now
    response = await client.get(f"{url.update_query(uuid_filter='common_name')}")
    data, error = await assert_status(response, web.HTTPOk)
    assert not error
    list_fmds = parse_obj_as(list[FileMetaData], data)
    assert len(list_fmds) == (NUM_FILES)


async def test_get_file_metadata(
    upload_file: Callable[[ByteSize, str], Awaitable[tuple[Path, FileID]]],
    client: TestClient,
    user_id: UserID,
    location_id: int,
    project_id: ProjectID,
    file_uuid: FileID,
    faker: Faker,
):
    assert client.app

    url = (
        client.app.router["get_file_metadata"]
        .url_for(
            location_id=f"{location_id}",
            file_id=f"{urllib.parse.quote(file_uuid, safe='')}",
        )
        .with_query(user_id=f"{user_id}")
    )
    # this should return an empty list
    response = await client.get(f"{url}")
    # NOTE: this is weird, do we still need this Ok when nothing found??
    assert response.status == web.HTTPOk.status_code
    assert await response.json() == {"data": {}, "error": "No result found"}
    # data, error = await assert_status(response, web.HTTPOk)
    # assert error == "No result found"
    # assert data == {}
    # now add some stuff there
    NUM_FILES = 10
    file_size = parse_obj_as(ByteSize, "15Mib")
    files_owned_by_us = []
    for _ in range(NUM_FILES):
        files_owned_by_us.append(await upload_file(file_size, faker.file_name()))
    selected_file, selected_file_uuid = choice(files_owned_by_us)
    url = (
        client.app.router["get_file_metadata"]
        .url_for(
            location_id=f"{location_id}",
            file_id=f"{urllib.parse.quote(selected_file_uuid, safe='')}",
        )
        .with_query(user_id=f"{user_id}")
    )
    response = await client.get(f"{url}")
    data, error = await assert_status(response, web.HTTPOk)
    assert not error
    assert data
    fmd = parse_obj_as(FileMetaData, data)
    assert fmd.file_uuid == selected_file_uuid
    assert fmd.file_size == selected_file.stat().st_size
