# pylint: disable=protected-access
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import simcore_service_storage._meta
from aiohttp import web
from aiohttp.test_utils import TestClient
from pytest_simcore.helpers.utils_assert import assert_status
from simcore_service_storage.access_layer import AccessRights
from simcore_service_storage.app_handlers import HealthCheck
from simcore_service_storage.constants import SIMCORE_S3_ID
from simcore_service_storage.dsm import APP_DSM_KEY, DataStorageManager
from simcore_service_storage.models import FileMetaData
from tests.helpers.utils_project import clone_project_data

current_dir = Path(sys.argv[0] if __name__ == "__main__" else __file__).resolve().parent

pytest_simcore_core_services_selection = ["postgres"]
pytest_simcore_ops_services_selection = ["adminer"]


async def test_health_check(client: TestClient):
    resp = await client.get("/v0/")
    text = await resp.text()

    assert resp.status == 200, text

    payload = await resp.json()
    data, error = tuple(payload.get(k) for k in ("data", "error"))

    assert data
    assert not error

    app_health = HealthCheck.parse_obj(data)
    assert app_health.name == simcore_service_storage._meta.app_name
    assert app_health.version == simcore_service_storage._meta.api_version


async def test_action_check(client):
    QUERY = "mguidon"
    ACTION = "echo"
    FAKE = {"path_value": "one", "query_value": "two", "body_value": {"a": 33, "b": 45}}

    resp = await client.post(f"/v0/check/{ACTION}?data={QUERY}", json=FAKE)
    payload = await resp.json()
    data, error = tuple(payload.get(k) for k in ("data", "error"))

    assert resp.status == 200, str(payload)
    assert data
    assert not error

    # TODO: validate response against specs

    assert data["path_value"] == ACTION
    assert data["query_value"] == QUERY


def get_project_with_data() -> dict[str, Any]:
    projects = []
    with open(current_dir / "../data/projects_with_data.json") as fp:
        projects = json.load(fp)

    # TODO: add schema validation
    return projects


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


@pytest.fixture
def mock_get_project_access_rights(mocker) -> None:
    # NOTE: this avoid having to inject project in database
    for module in ("dsm", "access_layer"):
        mock = mocker.patch(
            f"simcore_service_storage.{module}.get_project_access_rights"
        )
        mock.return_value.set_result(AccessRights.all())


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
    "project_name,project", [(prj["name"], prj) for prj in get_project_with_data()]
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
    "project_name,project", [(prj["name"], prj) for prj in get_project_with_data()]
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
