# pylint: disable=protected-access
# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument

from aiohttp.test_utils import TestClient
from models_library.users import UserID
from tests.helpers.utils import has_datcore_tokens

pytest_simcore_core_services_selection = ["postgres"]
pytest_simcore_ops_services_selection = ["adminer"]


async def test_locations(client: TestClient, user_id: UserID):
    resp = await client.get("/v0/locations?user_id={}".format(user_id))

    payload = await resp.json()
    assert resp.status == 200, str(payload)

    data, error = tuple(payload.get(k) for k in ("data", "error"))

    _locs = 2 if has_datcore_tokens() else 1
    assert len(data) == _locs
    assert not error
