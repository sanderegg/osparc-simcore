# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Awaitable, Callable

import pytest
import sqlalchemy as sa
from aiohttp import web
from aiohttp.test_utils import TestClient
from aiopg.sa.engine import Engine
from faker import Faker
from models_library.api_schemas_storage import FoldersBody
from models_library.users import UserID
from models_library.utils.fastapi_encoders import jsonable_encoder
from pytest_simcore.helpers.utils_assert import assert_status
from settings_library.s3 import S3Settings
from simcore_postgres_database.storage_models import file_meta_data
from simcore_service_storage.access_layer import AccessRights
from simcore_service_storage.constants import SIMCORE_S3_ID
from simcore_service_storage.dsm import APP_DSM_KEY, DataStorageManager
from simcore_service_storage.models import FileMetaData
from simcore_service_storage.s3_client import StorageS3Client
from tests.helpers.utils_project import clone_project_data

pytest_simcore_core_services_selection = ["postgres"]
pytest_simcore_ops_services_selection = ["adminer"]


@pytest.fixture
def mock_get_project_access_rights(mocker) -> None:
    # NOTE: this avoid having to inject project in database
    for module in ("dsm", "access_layer"):
        mock = mocker.patch(
            f"simcore_service_storage.{module}.get_project_access_rights"
        )
        mock.return_value.set_result(AccessRights.all())


@pytest.fixture
def mock_datcore_download(mocker, client):
    # Use to mock downloading from DATCore
    async def _fake_download_to_file_or_raise(session, url, dest_path):
        print(f"Faking download:  {url} -> {dest_path}")
        Path(dest_path).write_text("FAKE: test_create_and_delete_folders_from_project")

    mocker.patch(
        "simcore_service_storage.dsm.download_to_file_or_raise",
        side_effect=_fake_download_to_file_or_raise,
    )

    dsm = client.app[APP_DSM_KEY]
    assert dsm
    assert isinstance(dsm, DataStorageManager)

    async def mock_download_link_datcore(*args, **kwargs):
        return ["https://httpbin.org/image", "foo.txt"]

    mocker.patch.object(dsm, "download_link_datcore", mock_download_link_datcore)


async def test_simcore_s3_access_returns_default(client: TestClient):
    assert client.app
    url = (
        client.app.router["get_or_create_temporary_s3_access"]
        .url_for()
        .with_query(user_id=1)
    )
    response = await client.post(f"{url}")
    data, error = await assert_status(response, web.HTTPOk)
    assert not error
    assert data
    received_settings = S3Settings.parse_obj(data)
    assert received_settings


async def test_copy_folders_from_non_existing_project(
    client: TestClient,
    user_id: UserID,
    create_project: Callable[[], Awaitable[dict[str, Any]]],
    faker: Faker,
):
    assert client.app
    url = (
        client.app.router["copy_folders_from_project"]
        .url_for()
        .with_query(user_id=user_id)
    )
    src_project = await create_project()
    incorrect_src_project = deepcopy(src_project)
    incorrect_src_project["uuid"] = faker.uuid4()
    dst_project = await create_project()
    incorrect_dst_project = deepcopy(dst_project)
    incorrect_dst_project["uuid"] = faker.uuid4()

    response = await client.post(
        f"{url}",
        json=jsonable_encoder(
            FoldersBody(
                source=incorrect_src_project, destination=dst_project, nodes_map={}
            )
        ),
    )
    data, error = await assert_status(response, web.HTTPNotFound)
    assert error
    assert not data

    response = await client.post(
        f"{url}",
        json=jsonable_encoder(
            FoldersBody(
                source=src_project, destination=incorrect_dst_project, nodes_map={}
            )
        ),
    )
    data, error = await assert_status(response, web.HTTPNotFound)
    assert error
    assert not data


async def test_copy_folders_from_empty_project(
    client: TestClient,
    user_id: UserID,
    create_project: Callable[[], Awaitable[dict[str, Any]]],
    # upload_file: Callable[[ByteSize, str], Awaitable[tuple[Path, FileID]]],
    aiopg_engine: Engine,
    storage_s3_client: StorageS3Client,
):
    assert client.app
    url = (
        client.app.router["copy_folders_from_project"]
        .url_for()
        .with_query(user_id=user_id)
    )

    # we will copy from src to dst
    src_project = await create_project()
    dst_project = await create_project()

    response = await client.post(
        f"{url}",
        json=jsonable_encoder(
            FoldersBody(source=src_project, destination=dst_project, nodes_map={})
        ),
    )
    data, error = await assert_status(response, web.HTTPCreated)
    assert not error
    assert data == jsonable_encoder(dst_project)
    # check there is nothing in the dst project
    async with aiopg_engine.acquire() as conn:
        num_entries = await conn.scalar(
            sa.select([sa.func.count()])
            .select_from(file_meta_data)
            .where(file_meta_data.c.project_id == dst_project["uuid"])
        )
        assert num_entries == 0


current_dir = Path(sys.argv[0] if __name__ == "__main__" else __file__).resolve().parent


def _get_project_with_data() -> dict[str, Any]:
    projects = []
    with open(current_dir / "../data/projects_with_data.json") as fp:
        projects = json.load(fp)

    # TODO: add schema validation
    return projects


async def _create_and_delete_folders_from_project(
    project: dict[str, Any], client: TestClient
):
    destination_project, nodes_map = clone_project_data(project)

    # CREATING
    assert client.app
    url = (
        client.app.router["copy_folders_from_project"].url_for().with_query(user_id="1")
    )
    resp = await client.post(
        f"{url}",
        json={
            "source": project,
            "destination": destination_project,
            "nodes_map": nodes_map,
        },
    )

    data, _error = await assert_status(resp, expected_cls=web.HTTPCreated)

    # data should be equal to the destination project, and all store entries should point to simcore.s3
    for key in data:
        if key != "workbench":
            assert data[key] == destination_project[key]
        else:
            for _node_id, node in data[key].items():
                if "outputs" in node:
                    for _o_id, o in node["outputs"].items():
                        if "store" in o:
                            assert o["store"] == SIMCORE_S3_ID

    # DELETING
    project_id = data["uuid"]
    url = (
        client.app.router["delete_folders_of_project"]
        .url_for(folder_id=project_id)
        .with_query(user_id="1")
    )
    resp = await client.delete(f"{url}")

    await assert_status(resp, expected_cls=web.HTTPNoContent)


@pytest.mark.parametrize(
    "project_name,project", [(prj["name"], prj) for prj in _get_project_with_data()]
)
async def test_create_and_delete_folders_from_project(
    client: TestClient,
    dsm_mockup_db: dict[str, FileMetaData],
    project_name: str,
    project: dict[str, Any],
    mock_get_project_access_rights,
    mock_datcore_download,
):
    source_project = project
    await _create_and_delete_folders_from_project(source_project, client)


@pytest.mark.parametrize(
    "project_name,project", [(prj["name"], prj) for prj in _get_project_with_data()]
)
async def test_create_and_delete_folders_from_project_burst(
    client,
    dsm_mockup_db,
    project_name,
    project,
    mock_get_project_access_rights,
    mock_datcore_download,
):
    source_project = project

    await asyncio.gather(
        *[
            _create_and_delete_folders_from_project(source_project, client)
            for _ in range(100)
        ]
    )
