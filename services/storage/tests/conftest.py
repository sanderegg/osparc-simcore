# pylint: disable=no-member
# pylint: disable=no-name-in-module
# pylint: disable=redefined-outer-name
# pylint: disable=unsupported-assignment-operation
# pylint: disable=unused-argument
# pylint: disable=unused-variable


import asyncio
import datetime
import os
import sys
import uuid
from contextlib import AsyncExitStack
from pathlib import Path
from random import randrange
from typing import AsyncIterator, Callable, Dict, Iterable, Iterator, List, Optional

import dotenv
import pytest
import simcore_service_storage
from aiohttp.test_utils import TestClient, unused_port
from aiopg.sa import Engine
from faker import Faker
from moto.server import ThreadedMotoServer
from pydantic import ByteSize
from pytest_simcore.helpers.utils_docker import get_localhost_ip
from simcore_service_storage.application import create
from simcore_service_storage.constants import SIMCORE_S3_STR
from simcore_service_storage.dsm import DataStorageManager, DatCoreApiToken
from simcore_service_storage.models import FileMetaData, file_meta_data, projects, users
from simcore_service_storage.s3_client import StorageS3Client
from simcore_service_storage.settings import Settings
from tests.helpers.utils import (
    BUCKET_NAME,
    DATA_DIR,
    USER_ID,
    fill_tables_from_csv_files,
    insert_metadata,
)

pytest_plugins = [
    "pytest_simcore.cli_runner",
    "pytest_simcore.repository_paths",
    "tests.fixtures.data_models",
    "pytest_simcore.pytest_global_environs",
    "pytest_simcore.postgres_service",
    "pytest_simcore.docker_swarm",
    "pytest_simcore.docker_compose",
    "pytest_simcore.tmp_path_extra",
    "pytest_simcore.monkeypatch_extra",
]

CURRENT_DIR = Path(sys.argv[0] if __name__ == "__main__" else __file__).resolve().parent

# TODO: replace by pytest_simcore
sys.path.append(str(CURRENT_DIR / "helpers"))


@pytest.fixture(scope="session")
def here() -> Path:
    return CURRENT_DIR


@pytest.fixture(scope="session")
def package_dir(here) -> Path:
    dirpath = Path(simcore_service_storage.__file__).parent
    assert dirpath.exists()
    return dirpath


@pytest.fixture(scope="session")
def osparc_simcore_root_dir(here) -> Path:
    root_dir = here.parent.parent.parent
    assert root_dir.exists() and any(
        root_dir.glob("services")
    ), "Is this service within osparc-simcore repo?"
    return root_dir


@pytest.fixture(scope="session")
def osparc_api_specs_dir(osparc_simcore_root_dir) -> Path:
    dirpath = osparc_simcore_root_dir / "api" / "specs"
    assert dirpath.exists()
    return dirpath


@pytest.fixture(scope="session")
def project_slug_dir(osparc_simcore_root_dir) -> Path:
    # uses pytest_simcore.environs.osparc_simcore_root_dir
    service_folder = osparc_simcore_root_dir / "services" / "storage"
    assert service_folder.exists()
    assert any(service_folder.glob("src/simcore_service_storage"))
    return service_folder


@pytest.fixture(scope="session")
def project_env_devel_dict(project_slug_dir: Path) -> Dict:
    env_devel_file = project_slug_dir / ".env-devel"
    assert env_devel_file.exists()
    environ = dotenv.dotenv_values(env_devel_file, verbose=True, interpolate=True)
    return environ


@pytest.fixture(scope="function")
def project_env_devel_environment(project_env_devel_dict, monkeypatch) -> None:
    for key, value in project_env_devel_dict.items():
        monkeypatch.setenv(key, value)


## FAKE DATA FIXTURES ----------------------------------------------


@pytest.fixture(scope="function")
def mock_files_factory(tmpdir_factory) -> Callable[[int], List[Path]]:
    def _create_files(count: int) -> List[Path]:
        filepaths = []
        for _i in range(count):
            filepath = Path(tmpdir_factory.mktemp("data")) / f"{uuid.uuid4()}.txt"
            filepath.write_text("Hello world\n")
            filepaths.append(filepath)

        return filepaths

    return _create_files


@pytest.fixture
async def cleanup_user_projects_file_metadata(aiopg_engine: Engine):
    yield
    # cleanup
    async with aiopg_engine.acquire() as conn:
        await conn.execute(file_meta_data.delete())
        await conn.execute(projects.delete())
        await conn.execute(users.delete())


@pytest.fixture
async def dsm_mockup_complete_db(
    postgres_dsn: dict[str, str],
    with_bucket_in_s3: str,
    storage_s3_client: StorageS3Client,
    cleanup_user_projects_file_metadata: None,
) -> AsyncIterator[tuple[dict[str, str], dict[str, str]]]:
    dsn = "postgresql://{user}:{password}@{host}:{port}/{database}".format(
        **postgres_dsn
    )
    fill_tables_from_csv_files(url=dsn)

    file_1 = {
        "project_id": "161b8782-b13e-5840-9ae2-e2250c231001",
        "node_id": "ad9bda7f-1dc5-5480-ab22-5fef4fc53eac",
        "filename": "outputController.dat",
    }
    f = DATA_DIR / "outputController.dat"
    object_name = "{project_id}/{node_id}/{filename}".format(**file_1)
    with f.open("rb") as fp:
        response = await storage_s3_client.client.put_object(
            Bucket=with_bucket_in_s3, Key=object_name, Body=fp
        )
    assert response

    file_2 = {
        "project_id": "161b8782-b13e-5840-9ae2-e2250c231001",
        "node_id": "a3941ea0-37c4-5c1d-a7b3-01b5fd8a80c8",
        "filename": "notebooks.zip",
    }
    f = DATA_DIR / "notebooks.zip"
    object_name = "{project_id}/{node_id}/{filename}".format(**file_2)
    with f.open("rb") as fp:
        response = await storage_s3_client.client.put_object(
            Bucket=with_bucket_in_s3, Key=object_name, Body=fp
        )
    yield (file_1, file_2)


@pytest.fixture
async def dsm_mockup_db(
    postgres_dsn_url,
    with_bucket_in_s3: str,
    storage_s3_client: StorageS3Client,
    mock_files_factory: Callable[[int], List[Path]],
    cleanup_user_projects_file_metadata,
) -> AsyncIterator[dict[str, FileMetaData]]:

    # TODO: use pip install Faker
    users = ["alice", "bob", "chuck", "dennis"]

    projects = [
        "astronomy",
        "biology",
        "chemistry",
        "dermatology",
        "economics",
        "futurology",
        "geology",
    ]
    location = SIMCORE_S3_STR

    nodes = ["alpha", "beta", "gamma", "delta"]

    N = 100
    files = mock_files_factory(N)
    counter = 0
    data = {}

    for _file in files:
        idx = randrange(len(users))
        user_name = users[idx]
        user_id = idx + 10
        idx = randrange(len(projects))
        project_name = projects[idx]
        project_id = idx + 100
        idx = randrange(len(nodes))
        node = nodes[idx]
        node_id = idx + 10000
        file_name = str(counter)
        object_name = Path(str(project_id), str(node_id), str(counter)).as_posix()
        file_uuid = Path(object_name).as_posix()
        raw_file_path = file_uuid
        display_file_path = str(Path(project_name) / Path(node) / Path(file_name))
        created_at = str(datetime.datetime.utcnow())
        file_size = _file.stat().st_size

        with _file.open("rb") as fp:
            response = await storage_s3_client.client.put_object(
                Bucket=with_bucket_in_s3, Key=object_name, Body=fp
            )
        response = await storage_s3_client.client.head_object(
            Bucket=with_bucket_in_s3, Key=object_name
        )
        assert "ETag" in response
        entity_tag = response["ETag"].strip('"')

        d = {
            "file_uuid": file_uuid,
            "location_id": "0",
            "location": location,
            "bucket_name": with_bucket_in_s3,
            "object_name": object_name,
            "project_id": str(project_id),
            "project_name": project_name,
            "node_id": str(node_id),
            "node_name": node,
            "file_name": file_name,
            "user_id": str(user_id),
            "user_name": user_name,
            "file_id": str(uuid.uuid4()),
            "raw_file_path": file_uuid,
            "display_file_path": display_file_path,
            "created_at": created_at,
            "last_modified": created_at,
            "file_size": file_size,
            "entity_tag": entity_tag,
        }

        counter = counter + 1

        data[object_name] = FileMetaData(**d)

        # pylint: disable=no-member

        insert_metadata(postgres_dsn_url, data[object_name])

    response = await storage_s3_client.client.list_objects_v2(Bucket=with_bucket_in_s3)
    total_count = response["KeyCount"]
    assert total_count == N

    yield data


@pytest.fixture(scope="function")
def dsm_fixture(aiopg_engine, client) -> Iterable[DataStorageManager]:

    # FIXME: this should be changed by setting STORAGE_TESTING to True
    dsm_fixture = DataStorageManager(
        engine=aiopg_engine,
        simcore_bucket_name=BUCKET_NAME,
        has_project_db=False,
        app=client.app,
    )

    api_token = os.environ.get("BF_API_KEY", "none")
    api_secret = os.environ.get("BF_API_SECRET", "none")
    dsm_fixture.datcore_tokens[USER_ID] = DatCoreApiToken(api_token, api_secret)

    yield dsm_fixture


@pytest.fixture(scope="module")
def mocked_s3_server() -> Iterator[ThreadedMotoServer]:
    """creates a moto-server that emulates AWS services in place
    NOTE: Never use a bucket with underscores it fails!!
    """
    server = ThreadedMotoServer(ip_address=get_localhost_ip(), port=unused_port())
    # pylint: disable=protected-access
    print(f"--> started mock S3 server on {server._ip_address}:{server._port}")
    print(
        f"--> Dashboard available on [http://{server._ip_address}:{server._port}/moto-api/]"
    )
    server.start()
    yield server
    server.stop()
    print(f"<-- stopped mock S3 server on {server._ip_address}:{server._port}")


@pytest.fixture
def mocked_s3_server_envs(
    mocked_s3_server: ThreadedMotoServer, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("S3_SECURE", "false")
    monkeypatch.setenv(
        "S3_ENDPOINT",
        f"{mocked_s3_server._ip_address}:{mocked_s3_server._port}",  # pylint: disable=protected-access
    )
    monkeypatch.setenv("S3_ACCESS_KEY", "xxx")
    monkeypatch.setenv("S3_SECRET_KEY", "xxx")
    monkeypatch.setenv("S3_BUCKET_NAME", "pytestbucket")


async def _remove_all_buckets(storage_s3_client: StorageS3Client):
    response = await storage_s3_client.client.list_buckets()
    bucket_names = [
        bucket["Name"] for bucket in response["Buckets"] if "Name" in bucket
    ]
    for bucket in bucket_names:
        response = await storage_s3_client.client.list_objects_v2(Bucket=bucket)
        while response["KeyCount"] > 0:
            await storage_s3_client.client.delete_objects(
                Bucket=bucket,
                Delete={
                    "Objects": [
                        {"Key": obj["Key"]}
                        for obj in response["Contents"]
                        if "Key" in obj
                    ]
                },
            )
            response = await storage_s3_client.client.list_objects_v2(Bucket=bucket)

    await asyncio.gather(
        *(
            storage_s3_client.client.delete_bucket(Bucket=bucket)
            for bucket in bucket_names
        )
    )


@pytest.fixture
async def storage_s3_client(
    app_settings: Settings,
) -> AsyncIterator[StorageS3Client]:
    assert app_settings.STORAGE_S3
    async with AsyncExitStack() as exit_stack:
        storage_s3_client = await StorageS3Client.create(
            exit_stack, app_settings.STORAGE_S3
        )
        # check that no bucket is lying around
        assert storage_s3_client
        response = await storage_s3_client.client.list_buckets()
        assert not response[
            "Buckets"
        ], f"for testing puproses, there should be no bucket lying around! {response=}"
        yield storage_s3_client
        # cleanup
        await _remove_all_buckets(storage_s3_client)


@pytest.fixture
async def with_bucket_in_s3(storage_s3_client: StorageS3Client) -> str:
    await storage_s3_client.create_bucket(BUCKET_NAME)
    return BUCKET_NAME


@pytest.fixture
def mock_config(
    aiopg_engine: Engine,
    postgres_host_config: dict[str, str],
    mocked_s3_server_envs,
):
    # NOTE: this can be overriden in tests that do not need all dependencies up
    ...


@pytest.fixture
def app_settings(mock_config) -> Settings:
    test_app_settings = Settings.create_from_envs()
    print(f"{test_app_settings.json(indent=2)=}")
    return test_app_settings


@pytest.fixture
def client(
    event_loop: asyncio.AbstractEventLoop,
    aiohttp_client: Callable,
    unused_tcp_port_factory: Callable[..., int],
    app_settings: Settings,
) -> TestClient:
    app = create(app_settings)
    return event_loop.run_until_complete(
        aiohttp_client(app, server_kwargs={"port": unused_tcp_port_factory()})
    )


@pytest.fixture
def create_file_of_size(tmp_path: Path, faker: Faker) -> Callable[[ByteSize], Path]:
    def _creator(size: ByteSize, name: Optional[str] = None) -> Path:
        file: Path = tmp_path / (name or faker.file_name())
        with file.open("wb") as fp:
            fp.truncate(size)

        assert file.stat().st_size == size
        return file

    return _creator
