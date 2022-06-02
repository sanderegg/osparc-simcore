# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument

import asyncio
import shutil
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, AsyncIterable, Final, Iterator, Optional
from uuid import uuid4

import aioboto3
import pytest
import sqlalchemy as sa
from _pytest.fixtures import FixtureRequest
from aiohttp import ClientSession
from faker import Faker
from models_library.api_schemas_storage import FileUploadLinks, FileUploadSchema
from pydantic import AnyUrl, ByteSize, parse_obj_as
from pytest_mock.plugin import MockerFixture
from settings_library.r_clone import RCloneSettings
from simcore_postgres_database.models.file_meta_data import file_meta_data
from simcore_sdk.node_ports_common import r_clone

pytest_simcore_core_services_selection = [
    "migration",
    "postgres",
    "storage",
]

pytest_simcore_ops_services_selection = [
    "minio",
    "adminer",
]


WAIT_FOR_S3_BACKEND_TO_UPDATE: Final[float] = 1.0


class _TestException(Exception):
    pass


# FIXTURES


@pytest.fixture(
    params=[
        f"{uuid4()}.bin",
        "some funky name.txt",
        "öä$äö2-34 no extension",
    ]
)
def file_name(request: FixtureRequest) -> str:
    return request.param


@pytest.fixture
def upload_file_dir(tmp_path: Path) -> Iterator[Path]:
    assert tmp_path.is_dir()
    yield tmp_path
    shutil.rmtree(tmp_path)


@pytest.fixture
def file_to_upload(upload_file_dir: Path, file_name: str, faker: Faker) -> Path:
    # generate file with data
    file_path = upload_file_dir / file_name
    file_path.write_text(faker.paragraph(nb_sentences=5))
    return file_path


@pytest.fixture
def local_file_for_download(upload_file_dir: Path, file_name: str) -> Path:
    local_file_path = upload_file_dir / f"__local__{file_name}"
    return local_file_path


@pytest.fixture
def s3_object(project_id: str, node_uuid: str, file_name: str) -> str:
    s3_path = Path(project_id) / node_uuid / file_name
    return f"{s3_path}"


@pytest.fixture
async def cleanup_s3(
    r_clone_settings: RCloneSettings, s3_object: str
) -> AsyncIterable[None]:
    yield
    async with _get_s3_object(r_clone_settings, s3_object) as s3_object_in_s3:
        await s3_object_in_s3.delete()


@pytest.fixture
def raise_error_after_upload(
    mocker: MockerFixture, postgres_db: sa.engine.Engine, s3_object: str
) -> None:
    handler = r_clone._async_command  # pylint: disable=protected-access

    async def _mock_async_command(*cmd: str, cwd: Optional[str] = None) -> str:
        await handler(*cmd, cwd=cwd)
        assert _is_file_present(postgres_db=postgres_db, s3_object=s3_object) is True

        raise _TestException()

    mocker.patch(
        "simcore_sdk.node_ports_common.r_clone._async_command",
        side_effect=_mock_async_command,
    )


@pytest.fixture
async def client_session(filemanager_cfg: None) -> AsyncIterable[ClientSession]:
    async with ClientSession() as session:
        yield session


# UTILS


@asynccontextmanager
async def _get_s3_object(
    r_clone_settings: RCloneSettings, s3_path: str
) -> AsyncGenerator["aioboto3.resources.factory.s3.Object", None]:
    session = aioboto3.Session(
        aws_access_key_id=r_clone_settings.R_CLONE_S3.S3_ACCESS_KEY,
        aws_secret_access_key=r_clone_settings.R_CLONE_S3.S3_SECRET_KEY,
    )
    async with session.resource(
        "s3", endpoint_url=r_clone_settings.R_CLONE_S3.S3_ENDPOINT
    ) as s3:
        s3_object = await s3.Object(
            bucket_name=r_clone_settings.R_CLONE_S3.S3_BUCKET_NAME,
            key=s3_path.removeprefix(r_clone_settings.R_CLONE_S3.S3_BUCKET_NAME),
        )
        yield s3_object


async def _download_s3_object(
    r_clone_settings: RCloneSettings, s3_path: str, local_path: Path
):
    await asyncio.sleep(WAIT_FOR_S3_BACKEND_TO_UPDATE)
    async with _get_s3_object(r_clone_settings, s3_path) as s3_object_in_s3:
        await s3_object_in_s3.download_file(f"{local_path}")


def _is_file_present(postgres_db: sa.engine.Engine, s3_object: str) -> bool:
    with postgres_db.begin() as conn:
        result = conn.execute(
            file_meta_data.select().where(file_meta_data.c.file_uuid == s3_object)
        )
        result_list = list(result)
        result_len = len(result_list)
    assert result_len <= 1, result_list
    return result_len == 1


@pytest.fixture
def fake_upload_file_link(
    r_clone_settings: RCloneSettings, s3_object: str
) -> FileUploadSchema:
    return FileUploadSchema(
        chunk_size=ByteSize(0),
        urls=[
            parse_obj_as(
                AnyUrl,
                f"s3://{r_clone_settings.R_CLONE_S3.S3_BUCKET_NAME}/{urllib.parse.quote( s3_object, safe='')}",
            )
        ],
        links=FileUploadLinks(
            abort_upload=parse_obj_as(AnyUrl, "https://www.fakeabort.com"),
            complete_upload=parse_obj_as(AnyUrl, "https://www.fakecomplete.com"),
        ),
    )


# TESTS
async def test_sync_local_to_s3(
    r_clone_settings: RCloneSettings,
    s3_object: str,
    file_to_upload: Path,
    local_file_for_download: Path,
    postgres_db: sa.engine.Engine,
    fake_upload_file_link: FileUploadSchema,
    cleanup_s3: None,
) -> None:

    await r_clone.sync_local_to_s3(
        file_to_upload, r_clone_settings, fake_upload_file_link
    )

    await _download_s3_object(
        r_clone_settings=r_clone_settings,
        s3_path=s3_object,
        local_path=local_file_for_download,
    )

    # check same file contents after upload and download
    assert file_to_upload.read_text() == local_file_for_download.read_text()
