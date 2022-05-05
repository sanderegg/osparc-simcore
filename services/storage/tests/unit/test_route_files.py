# pylint: disable=redefined-outer-name
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

import urllib.parse
from typing import Type

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from faker import Faker
from models_library.projects import ProjectID
from models_library.projects_nodes import NodeID
from models_library.users import UserID
from pydantic import AnyUrl, ByteSize, parse_obj_as
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
    "url_query, expected_link_scheme, expected_link_query_keys, expected_chunk_size",
    [
        pytest.param(
            {},
            "http",
            _HTTP_PRESIGNED_LINK_QUERY_KEYS,
            int(parse_obj_as(ByteSize, "5GiB").to("b")),
            id="default_returns_single_presigned",
        ),
        pytest.param(
            {"link_type": "presigned"},
            "http",
            _HTTP_PRESIGNED_LINK_QUERY_KEYS,
            int(parse_obj_as(ByteSize, "5GiB").to("b")),
            id="presigned_returns_single_presigned",
        ),
        pytest.param(
            {"link_type": "s3"},
            "s3",
            [],
            int(parse_obj_as(ByteSize, "5TiB").to("b")),
            id="s3_returns_single_s3_link",
        ),
    ],
)
async def test_create_upload_file_default_returns_single_link(
    client: TestClient,
    user_id: UserID,
    location_id: int,
    file_uuid: str,
    url_query: dict[str, str],
    expected_link_scheme: str,
    cleanup_user_projects_file_metadata,
    expected_link_query_keys: list[str],
    expected_chunk_size: int,
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
    assert "urls" in data
    assert "chunk_size" in data
    assert isinstance(data["urls"], list)
    assert isinstance(data["chunk_size"], int)
    # check links, there should be only 1
    assert len(data["urls"]) == 1
    link = parse_obj_as(AnyUrl, data["urls"][0])
    assert link.scheme == expected_link_scheme
    assert link.path
    assert link.path.endswith(f"{file_uuid}")
    # the chunk_size
    assert data["chunk_size"] == expected_chunk_size
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


@pytest.mark.skip()
@pytest.mark.parametrize(
    "link_type, file_size, expected_response, expected_num_links,expected_chunk_size",
    [
        # pytest.param(
        #     "presigned",
        #     int(parse_obj_as(ByteSize, "1MiB").to("b")),
        #     web.HTTPOk,
        #     1,
        #     int(parse_obj_as(ByteSize, "1MiB").to("b")),
        #     id="1MiB file",
        # ),
        # pytest.param(
        #     "presigned",
        #     int(parse_obj_as(ByteSize, "10MiB").to("b")),
        #     web.HTTPOk,
        #     1,
        #     int(parse_obj_as(ByteSize, "10MiB").to("b")),
        #     id="10MiB file",
        # ),
        pytest.param(
            "presigned",
            int(parse_obj_as(ByteSize, "100MiB").to("b")),
            web.HTTPOk,
            10,
            int(parse_obj_as(ByteSize, "10MiB").to("b")),
            id="100MiB file",
        ),
    ],
)
async def test_create_upload_file_with_file_size_can_return_multipart_links(
    client: TestClient,
    user_id: UserID,
    location_id: int,
    file_uuid: str,
    cleanup_user_projects_file_metadata,
    link_type: str,
    file_size: int,
    expected_response: Type[web.HTTPException],
    expected_num_links: int,
    expected_chunk_size: int,
):
    assert client.app
    url = (
        client.app.router["upload_file"]
        .url_for(
            location_id=f"{location_id}", fileId=urllib.parse.quote(file_uuid, safe="")
        )
        .with_query(link_type=link_type, user_id=user_id, file_size=file_size)
    )
    response = await client.put(f"{url}")

    data, error = await assert_status(response, expected_response)
    assert not error
    assert data
    assert "urls" in data
    assert isinstance(data["urls"], list)
    assert len(data["urls"]) == expected_num_links
    assert "chunk_size" in data
    assert isinstance(data["chunk_size"], int)
    assert data["chunk_size"] == expected_chunk_size
