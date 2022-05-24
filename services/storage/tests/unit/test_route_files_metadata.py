# pylint: disable=protected-access
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument


import os
import urllib.parse

from aiohttp.test_utils import TestClient
from simcore_service_storage.constants import SIMCORE_S3_ID
from simcore_service_storage.dsm import DataStorageManager
from simcore_service_storage.models import FileMetaData
from tests.helpers.utils import parse_db

pytest_simcore_core_services_selection = ["postgres"]
pytest_simcore_ops_services_selection = ["adminer"]


async def test_s3_files_metadata(
    client: TestClient,
    dsm_mockup_db: dict[str, FileMetaData],
    dsm_fixture: DataStorageManager,
):
    id_file_count, _id_name_map = parse_db(dsm_mockup_db)
    # NOTE: this is really a joke
    dsm_fixture.has_project_db = False

    # list files for every user
    for _id in id_file_count:
        resp = await client.get("/v0/locations/0/files/metadata?user_id={}".format(_id))
        payload = await resp.json()
        assert resp.status == 200, str(payload)

        data, error = tuple(payload.get(k) for k in ("data", "error"))
        assert not error
        assert len(data) == id_file_count[_id]

    # list files fileterd by uuid
    for d in dsm_mockup_db.keys():
        fmd = dsm_mockup_db[d]
        assert fmd.project_id
        uuid_filter = f"{fmd.project_id}/{fmd.node_id}"
        resp = await client.get(
            "/v0/locations/0/files/metadata?user_id={}&uuid_filter={}".format(
                fmd.user_id, urllib.parse.quote(uuid_filter, safe="")
            )
        )
        payload = await resp.json()
        assert resp.status == 200, str(payload)

        data, error = tuple(payload.get(k) for k in ("data", "error"))
        assert not error
        for d in data:
            assert os.path.join(d["project_id"], d["node_id"]) == uuid_filter


async def test_s3_file_metadata(client, dsm_mockup_db):
    # go through all files and get them
    for d in dsm_mockup_db.keys():
        fmd = dsm_mockup_db[d]
        resp = await client.get(
            "/v0/locations/0/files/{}/metadata?user_id={}".format(
                urllib.parse.quote(fmd.file_uuid, safe=""), fmd.user_id
            )
        )
        payload = await resp.json()
        assert resp.status == 200, str(payload)

        data, error = tuple(payload.get(k) for k in ("data", "error"))
        assert not error
        assert data


async def test_s3_datasets_metadata(client: TestClient):
    assert client.app
    url = (
        client.app.router["get_datasets_metadata"]
        .url_for(location_id=str(SIMCORE_S3_ID))
        .with_query(user_id="21")
    )
    resp = await client.get(f"{url}")
    payload = await resp.json()
    assert resp.status == 200, str(payload)
    data, error = tuple(payload.get(k) for k in ("data", "error"))
    assert not error


async def test_s3_files_datasets_metadata(client: TestClient):
    assert client.app
    url = (
        client.app.router["get_files_metadata_dataset"]
        .url_for(location_id=str(SIMCORE_S3_ID), dataset_id="aa")
        .with_query(user_id="21")
    )
    resp = await client.get(f"{url}")
    payload = await resp.json()
    assert resp.status == 200, str(payload)
    data, error = tuple(payload.get(k) for k in ("data", "error"))
    assert not error
