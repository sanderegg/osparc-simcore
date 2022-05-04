# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

from aiohttp import web
from aiohttp.test_utils import TestClient
from pytest_simcore.helpers.utils_assert import assert_status
from settings_library.s3 import S3Settings

pytest_simcore_core_services_selection = ["postgres"]
pytest_simcore_ops_services_selection = ["minio", "adminer"]


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
