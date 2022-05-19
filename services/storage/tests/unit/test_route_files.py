# pylint: disable=redefined-outer-name
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

import urllib.parse
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Type

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient
from aiopg.sa import Engine
from faker import Faker
from models_library.api_schemas_storage import FileUploadSchema
from models_library.projects import ProjectID
from models_library.projects_nodes import NodeID
from models_library.users import UserID
from pydantic import ByteSize, parse_obj_as
from pytest_simcore.helpers.utils_assert import assert_status
from simcore_postgres_database.models.file_meta_data import file_meta_data

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


@pytest.fixture
def upload_file_link(
    client: TestClient,
) -> Callable[..., Awaitable[FileUploadSchema]]:
    async def _link_creator(
        user_id: UserID, location_id: int, file_uuid: str, **query_kwargs
    ) -> FileUploadSchema:
        assert client.app

        url = (
            client.app.router["upload_file"]
            .url_for(
                location_id=f"{location_id}",
                file_id=urllib.parse.quote(file_uuid, safe=""),
            )
            .with_query(**query_kwargs, user_id=user_id)
        )
        response = await client.put(f"{url}")
        data, error = await assert_status(response, web.HTTPOk)
        assert not error
        assert data
        received_file_upload = FileUploadSchema.parse_obj(data)
        assert received_file_upload
        return received_file_upload

    return _link_creator


async def assert_file_meta_data_in_db(
    aiopg_engine: Engine,
    *,
    file_uuid: str,
    expected_entry_exists: bool,
    expected_file_size: Optional[int] = None,
    expected_upload_id: bool = False,
):
    if expected_entry_exists and expected_file_size == None:
        assert True, "Invalid usage of assertion, expected_file_size cannot be None"

    async with aiopg_engine.acquire() as conn:
        result = await conn.execute(
            file_meta_data.select().where(file_meta_data.c.file_uuid == file_uuid)
        )
        db_data = await result.fetchall()
        assert db_data is not None
        assert len(db_data) == (1 if expected_entry_exists else 0)
        if expected_entry_exists:
            row = db_data[0]
            assert (
                row[file_meta_data.c.file_size] == expected_file_size
            ), "entry in file_meta_data was not initialized correctly, size should be set to -1"
            if expected_upload_id:
                assert (
                    row[file_meta_data.c.upload_id] is not None
                ), "multipart upload shall have an upload_id, it is missing!"
            else:
                assert (
                    row[file_meta_data.c.upload_id] is None
                ), "single file upload should not have an upload_id"


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
    user_id: UserID,
    location_id: int,
    file_uuid: str,
    url_query: dict[str, str],
    expected_link_scheme: str,
    expected_link_query_keys: list[str],
    expected_chunk_size: int,
    aiopg_engine: Engine,
    upload_file_link: Callable[..., Awaitable[FileUploadSchema]],
    cleanup_user_projects_file_metadata: None,
):
    # create upload file link
    received_file_upload = await upload_file_link(
        user_id, location_id, file_uuid, **url_query
    )
    # check links, there should be only 1
    assert len(received_file_upload.urls) == 1
    assert received_file_upload.urls[0].scheme == expected_link_scheme
    assert received_file_upload.urls[0].path
    assert received_file_upload.urls[0].path.endswith(f"{file_uuid}")
    # the chunk_size
    assert received_file_upload.chunk_size == expected_chunk_size
    if expected_link_query_keys:
        assert received_file_upload.urls[0].query
        query = {
            query_str.split("=")[0]: query_str.split("=")[1]
            for query_str in received_file_upload.urls[0].query.split("&")
        }
        for key in expected_link_query_keys:
            assert key in query
    else:
        assert not received_file_upload.urls[0].query

    # now check the entry in the database is correct, there should be only one
    await assert_file_meta_data_in_db(
        aiopg_engine,
        file_uuid=file_uuid,
        expected_entry_exists=True,
        expected_file_size=-1,
    )


@dataclass(frozen=True)
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
                expected_num_links=8739,
                expected_chunk_size=parse_obj_as(ByteSize, "600MiB"),
            ),
            id="5TiB file",
        ),
        pytest.param(
            MultiPartParam(
                link_type="s3",
                file_size=parse_obj_as(ByteSize, "255GiB"),
                expected_response=web.HTTPOk,
                expected_num_links=1,
                expected_chunk_size=parse_obj_as(ByteSize, "255GiB"),
            ),
            id="5TiB file",
        ),
    ],
)
async def test_create_upload_file_presigned_with_file_size_returns_multipart_links_if_bigger_than_99MiB(
    client: TestClient,
    user_id: UserID,
    location_id: int,
    file_uuid: str,
    test_param: MultiPartParam,
    aiopg_engine: Engine,
    upload_file_link: Callable[..., Awaitable[FileUploadSchema]],
    cleanup_user_projects_file_metadata: None,
):
    # create upload file link
    received_file_upload = await upload_file_link(
        user_id,
        location_id,
        file_uuid,
        link_type=test_param.link_type,
        file_size=int(test_param.file_size.to("b")),
    )
    # number of links
    assert len(received_file_upload.urls) == test_param.expected_num_links
    # all links are unique
    assert len(set(received_file_upload.urls)) == len(received_file_upload.urls)
    assert received_file_upload.chunk_size == test_param.expected_chunk_size

    # now check the entry in the database is correct, there should be only one
    await assert_file_meta_data_in_db(
        aiopg_engine,
        file_uuid=file_uuid,
        expected_entry_exists=True,
        expected_file_size=-1,
        expected_upload_id=True,
    )


async def test_delete_unuploaded_file_correctly_cleans_up_db(
    aiopg_engine: Engine,
    client: TestClient,
    user_id: UserID,
    location_id: int,
    file_uuid: str,
    upload_file_link: Callable[..., Awaitable[FileUploadSchema]],
):
    assert client.app
    # create upload file link
    await upload_file_link(
        user_id,
        location_id,
        file_uuid,
    )
    # we shall have an entry in the db, waiting for upload
    await assert_file_meta_data_in_db(
        aiopg_engine,
        file_uuid=file_uuid,
        expected_entry_exists=True,
        expected_file_size=-1,
        expected_upload_id=False,
    )

    # delete/abort file upload
    delete_url = (
        client.app.router["delete_file"]
        .url_for(
            location_id=f"{location_id}", file_id=urllib.parse.quote(file_uuid, safe="")
        )
        .with_query(user_id=user_id)
    )
    response = await client.delete(f"{delete_url}")
    data, error = await assert_status(response, web.HTTPNoContent)
    assert not error
    assert not data

    # the DB shall be cleaned up
    await assert_file_meta_data_in_db(
        aiopg_engine,
        file_uuid=file_uuid,
        expected_entry_exists=False,
    )
