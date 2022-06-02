# pylint:disable=unused-variable
# pylint:disable=unused-argument
# pylint:disable=redefined-outer-name


from typing import Any, AsyncIterator, Awaitable, Callable
from uuid import UUID

import pytest
import sqlalchemy as sa
from aiopg.sa.engine import Engine
from faker import Faker
from models_library.projects import ProjectID
from models_library.projects_nodes_io import NodeID
from models_library.users import UserID
from pytest_simcore.helpers.rawdata_fakers import random_project, random_user
from simcore_postgres_database.storage_models import projects, users


@pytest.fixture
async def user_id(aiopg_engine: Engine) -> AsyncIterator[UserID]:
    # inject a random user in db

    # NOTE: Ideally this (and next fixture) should be done via webserver API but at this point
    # in time, the webserver service would bring more dependencies to other services
    # which would turn this test too complex.

    # pylint: disable=no-value-for-parameter
    stmt = users.insert().values(**random_user(name="test")).returning(users.c.id)
    print(str(stmt))
    async with aiopg_engine.acquire() as conn:
        result = await conn.execute(stmt)
        row = await result.fetchone()

    assert isinstance(row.id, int)
    yield row.id

    async with aiopg_engine.acquire() as conn:
        await conn.execute(users.delete().where(users.c.id == row.id))


@pytest.fixture
async def project_id(user_id: UserID, aiopg_engine: Engine) -> AsyncIterator[ProjectID]:
    # inject a random project for user in db. This will give user_id, the full project's ownership

    # pylint: disable=no-value-for-parameter
    stmt = (
        projects.insert()
        .values(**random_project(prj_owner=user_id))
        .returning(projects.c.uuid)
    )
    async with aiopg_engine.acquire() as conn:
        result = await conn.execute(stmt)
        [prj_uuid] = (await result.fetchone()).as_tuple()

    yield UUID(prj_uuid)

    async with aiopg_engine.acquire() as conn:
        await conn.execute(projects.delete().where(projects.c.uuid == prj_uuid))


@pytest.fixture
async def create_project_node(
    user_id: UserID, project_id: ProjectID, aiopg_engine: Engine, faker: Faker
) -> AsyncIterator[Callable[..., Awaitable[NodeID]]]:
    async def _creator() -> NodeID:
        async with aiopg_engine.acquire() as conn:
            result = await conn.execute(
                sa.select([projects.c.workbench]).where(
                    projects.c.uuid == f"{project_id}"
                )
            )
            row = await result.fetchone()
            assert row
            project_workbench: dict[str, Any] = row[projects.c.workbench]
            new_node_id = NodeID(faker.uuid4())
            project_workbench.update(
                {
                    f"{new_node_id}": {
                        "key": "simcore/services/frontend/file-picker",
                        "version": "1.0.0",
                        "label": "pytest_fake_node",
                    }
                }
            )
            await conn.execute(
                projects.update()
                .where(projects.c.uuid == f"{project_id}")
                .values(workbench=project_workbench)
            )
        return new_node_id

    yield _creator
