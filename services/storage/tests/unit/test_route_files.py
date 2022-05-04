# pylint: disable=redefined-outer-name
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

import urllib.parse

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from faker import Faker
from models_library.projects import ProjectID
from models_library.projects_nodes import NodeID
from pydantic import HttpUrl, parse_obj_as
from pytest_simcore.helpers.utils_assert import assert_status

pytest_simcore_core_services_selection = ["postgres"]
pytest_simcore_ops_services_selection = ["minio", "adminer"]


@pytest.fixture
def node_id(faker: Faker):
    return NodeID(faker.uuid4())


@pytest.fixture
def file_uuid(project_id: ProjectID, node_id: NodeID, faker: Faker) -> str:
    return f"{project_id}/{node_id}/{faker.file_name()}"


@pytest.fixture
def location_id() -> int:
    return 0


async def test_create_upload_file_default_returns_presigned_link(
    client: TestClient, location_id: int, file_uuid: str
):
    assert client.app
    url = (
        client.app.router["upload_file"]
        .url_for(
            location_id=f"{location_id}", fileId=urllib.parse.quote(file_uuid, safe="")
        )
        .with_query(user_id=1)
    )
    response = await client.put(f"{url}")
    data, error = await assert_status(response, web.HTTPOk)
    assert not error
    assert data
    assert "link" in data
    link = parse_obj_as(HttpUrl, data["link"])
    assert link.scheme == "http"
    assert link.path == f"/simcore/{file_uuid}"
    assert link.query
    query = {
        query_str.split("=")[0]: query_str.split("=")[1]
        for query_str in link.query.split("&")
    }
    for key in [
        "X-Amz-Algorithm",
        "X-Amz-Credential",
        "X-Amz-Date",
        "X-Amz-Expires",
        "X-Amz-Signature",
        "X-Amz-SignedHeaders",
    ]:
        assert key in query
