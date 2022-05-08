# pylint: disable=redefined-outer-name
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

import urllib.parse
from dataclasses import dataclass
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


@dataclass
class MultiPartParam:
    link_type: str
    file_size: ByteSize
    expected_response: Type[web.HTTPException]
    expected_num_links: int
    expected_chunk_size: ByteSize


@pytest.mark.parametrize(
    "test_param",
    [
        pytest.param(
            MultiPartParam(
                link_type="presigned",
                file_size=parse_obj_as(ByteSize, "1MiB"),
                expected_response=web.HTTPOk,
                expected_num_links=1,
                expected_chunk_size=parse_obj_as(ByteSize, "1MiB"),
            ),
            id="1MiB file",
        ),
        pytest.param(
            MultiPartParam(
                link_type="presigned",
                file_size=parse_obj_as(ByteSize, "10MiB"),
                expected_response=web.HTTPOk,
                expected_num_links=1,
                expected_chunk_size=parse_obj_as(ByteSize, "10MiB"),
            ),
            id="10MiB file",
        ),
        pytest.param(
            MultiPartParam(
                link_type="presigned",
                file_size=parse_obj_as(ByteSize, "100MiB"),
                expected_response=web.HTTPOk,
                expected_num_links=10,
                expected_chunk_size=parse_obj_as(ByteSize, "10MiB"),
            ),
            id="100MiB file",
        ),
        pytest.param(
            MultiPartParam(
                link_type="presigned",
                file_size=parse_obj_as(ByteSize, "5TiB"),
                expected_response=web.HTTPOk,
                expected_num_links=1000,
                expected_chunk_size=parse_obj_as(ByteSize, "5GiB"),
            ),
            id="5TiB file",
        ),
    ],
)
async def test_create_upload_file_with_file_size_can_return_multipart_links(
    client: TestClient,
    user_id: UserID,
    location_id: int,
    file_uuid: str,
    cleanup_user_projects_file_metadata,
    test_param: MultiPartParam,
):
    assert client.app
    url = (
        client.app.router["upload_file"]
        .url_for(
            location_id=f"{location_id}", fileId=urllib.parse.quote(file_uuid, safe="")
        )
        .with_query(
            link_type=test_param.link_type,
            user_id=user_id,
            file_size=int(test_param.file_size.to("b")),
        )
    )
    response = await client.put(f"{url}")

    data, error = await assert_status(response, test_param.expected_response)
    assert not error
    assert data
    assert "urls" in data
    assert isinstance(data["urls"], list)
    assert len(data["urls"]) == test_param.expected_num_links
    # all elements are unique
    assert len(set(data["urls"])) == len(data["urls"])
    assert "chunk_size" in data
    assert isinstance(data["chunk_size"], int)
    assert data["chunk_size"] == int(test_param.expected_chunk_size.to("b"))
