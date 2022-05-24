# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable

import asyncio

from aiohttp.test_utils import TestClient

pytest_simcore_core_services_selection = ["postgres"]
pytest_simcore_ops_services_selection = ["adminer"]


async def test_setup_dsm_cleaner(client: TestClient):
    all_tasks = asyncio.all_tasks()
    assert any(t.get_name().startswith("dsm_cleaner_task") for t in all_tasks)
