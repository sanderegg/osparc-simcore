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
from models_library.users import UserID
from pydantic import AnyUrl, parse_obj_as
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


_HTTP_PRESIGNED_LINK_QUERY_KEYS = [
    "X-Amz-Algorithm",
    "X-Amz-Credential",
    "X-Amz-Date",
    "X-Amz-Expires",
    "X-Amz-Signature",
    "X-Amz-SignedHeaders",
]


@pytest.mark.parametrize(
    "url_query, expected_link_scheme, expected_link_query_keys",
    [
        ({}, "http", _HTTP_PRESIGNED_LINK_QUERY_KEYS),
        ({"link_type": "presigned"}, "http", _HTTP_PRESIGNED_LINK_QUERY_KEYS),
        ({"link_type": "s3"}, "s3", []),
    ],
)
async def test_create_upload_file_default_returns_single_presigned_link(
    client: TestClient,
    user_id: UserID,
    location_id: int,
    file_uuid: str,
    url_query: dict[str, str],
    expected_link_scheme: str,
    cleanup_user_projects_file_metadata,
    expected_link_query_keys: list[str],
):
    assert client.app
    url = (
        client.app.router["upload_file"]
        .url_for(
            location_id=f"{location_id}", fileId=urllib.parse.quote(file_uuid, safe="")
        )
        .with_query(**url_query, user_id=user_id)
    )
    response = await client.put(f"{url}")
    data, error = await assert_status(response, web.HTTPOk)
    assert not error
    assert data
    assert "link" in data
    link = parse_obj_as(AnyUrl, data["link"])
    assert link.scheme == expected_link_scheme
    assert link.path
    assert link.path.endswith(f"{file_uuid}")
    if expected_link_query_keys:
        assert link.query
        query = {
            query_str.split("=")[0]: query_str.split("=")[1]
            for query_str in link.query.split("&")
        }
        for key in expected_link_query_keys:
            assert key in query
    else:
        assert not link.query
