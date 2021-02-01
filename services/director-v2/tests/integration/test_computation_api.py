# pylint:disable=unused-variable
# pylint:disable=unused-argument
# pylint:disable=redefined-outer-name
# pylint:disable=protected-access
# pylint:disable=no-value-for-parameter
# pylint:disable=too-many-arguments

from copy import deepcopy
from random import randint
from typing import Any, Callable, Dict, List
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from models_library.projects_nodes_io import NodeID
from models_library.projects_state import RunningState
from models_library.settings.rabbit import RabbitConfig
from models_library.settings.redis import RedisConfig
from pydantic.networks import AnyHttpUrl
from pydantic.types import PositiveInt
from simcore_postgres_database.models.comp_tasks import comp_tasks
from simcore_postgres_database.models.projects import ProjectType, projects
from simcore_postgres_database.models.users import UserRole, UserStatus, users
from simcore_service_director_v2.models.domains.projects import ProjectAtDB
from simcore_service_director_v2.models.schemas.comp_tasks import ComputationTaskOut
from sqlalchemy import literal_column
from starlette import status
from starlette.testclient import TestClient
from tenacity import retry, retry_if_exception_type, stop_after_delay, wait_random
from yarl import URL

core_services = [
    "director",
    "redis",
    "rabbit",
    "sidecar",
    "storage",
    "postgres",
]
ops_services = ["minio", "adminer"]

COMPUTATION_URL: str = "v2/computations"


@pytest.fixture(autouse=True)
def minimal_configuration(
    sleeper_service: Dict[str, str],
    jupyter_service: Dict[str, str],
    redis_service: RedisConfig,
    postgres_db: sa.engine.Engine,
    postgres_host_config: Dict[str, str],
    rabbit_service: RabbitConfig,
    simcore_services: Dict[str, URL],
    monkeypatch,
):
    pass


@pytest.fixture
def user_id() -> PositiveInt:
    return randint(0, 10000)


@pytest.fixture
def user_db(postgres_db: sa.engine.Engine, user_id: PositiveInt) -> Dict:
    with postgres_db.connect() as con:
        result = con.execute(
            users.insert()
            .values(
                id=user_id,
                name="test user",
                email="test@user.com",
                password_hash="testhash",
                status=UserStatus.ACTIVE,
                role=UserRole.USER,
            )
            .returning(literal_column("*"))
        )

        user = result.first()

        yield dict(user)

        con.execute(users.delete().where(users.c.id == user["id"]))


@pytest.fixture
def fake_workbench_without_outputs(
    fake_workbench_as_dict: Dict[str, Any]
) -> Dict[str, Any]:
    workbench = deepcopy(fake_workbench_as_dict)
    # remove all the outputs from the workbench
    for _, data in workbench.items():
        data["outputs"] = {}

    return workbench


@pytest.fixture
def project(postgres_db: sa.engine.Engine, user_db: Dict) -> Callable:
    created_project_ids = []

    def creator(**overrides) -> ProjectAtDB:
        project_config = {
            "uuid": uuid4(),
            "name": "my test project",
            "type": ProjectType.STANDARD.name,
            "description": "my test description",
            "prj_owner": user_db["id"],
            "access_rights": {"1": {"read": True, "write": True, "delete": True}},
            "thumbnail": "",
            "workbench": {},
        }
        project_config.update(**overrides)
        with postgres_db.connect() as con:
            result = con.execute(
                projects.insert()
                .values(**project_config)
                .returning(literal_column("*"))
            )

            project = ProjectAtDB.parse_obj(result.first())
            created_project_ids.append(project.uuid)
            return project

    yield creator

    # cleanup
    with postgres_db.connect() as con:
        for pid in created_project_ids:
            con.execute(projects.delete().where(projects.c.uuid == str(pid)))


@pytest.fixture
def update_project_workbench_with_comp_tasks(postgres_db: sa.engine.Engine) -> Callable:
    def updator(project_uuid: str):
        with postgres_db.connect() as con:
            result = con.execute(
                projects.select().where(projects.c.uuid == project_uuid)
            )
            prj_row = result.first()
            prj_workbench = prj_row.workbench

            result = con.execute(
                comp_tasks.select().where(comp_tasks.c.project_id == project_uuid)
            )
            # let's get the results and run_hash
            for task_row in result:
                # pass these to the project workbench
                prj_workbench[task_row.node_id]["outputs"] = task_row.outputs
                prj_workbench[task_row.node_id]["runHash"] = task_row.run_hash

            con.execute(
                projects.update()
                .values(workbench=prj_workbench)
                .where(projects.c.uuid == project_uuid)
            )

    yield updator


@pytest.mark.parametrize(
    "body,exp_response",
    [
        (
            {"user_id": "some invalid id", "project_id": "not a uuid"},
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
        (
            {"user_id": 2, "project_id": "not a uuid"},
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        ),
        (
            {"user_id": 3, "project_id": "16e60a5d-834e-4267-b44d-3af49171bf21"},
            status.HTTP_404_NOT_FOUND,
        ),
    ],
)
def test_invalid_computation(client: TestClient, body: Dict, exp_response: int):
    # create a bunch of invalid stuff
    response = client.post(
        COMPUTATION_URL,
        json=body,
    )
    assert (
        response.status_code == exp_response
    ), f"response code is {response.status_code}, error: {response.text}"


def test_start_empty_computation(
    client: TestClient,
    user_id: PositiveInt,
    project: Callable,
):
    # send an empty project to process
    empty_project = project()
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(empty_project.uuid),
            "start_pipeline": True,
        },
    )
    assert (
        response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    ), f"response code is {response.status_code}, error: {response.text}"


def _assert_pipeline_status(
    client: TestClient,
    url: AnyHttpUrl,
    user_id: PositiveInt,
    project_uuid: UUID,
    wait_for_states: List[RunningState] = None,
) -> ComputationTaskOut:
    if not wait_for_states:
        wait_for_states = [
            RunningState.SUCCESS,
            RunningState.FAILED,
            RunningState.ABORTED,
        ]

    MAX_TIMEOUT_S = 60

    @retry(
        stop=stop_after_delay(MAX_TIMEOUT_S),
        wait=wait_random(0, 2),
        retry=retry_if_exception_type(AssertionError),
        reraise=True,
    )
    def check_pipeline_state() -> ComputationTaskOut:
        response = client.get(url, params={"user_id": user_id})
        assert (
            response.status_code == status.HTTP_202_ACCEPTED
        ), f"response code is {response.status_code}, error: {response.text}"
        task_out = ComputationTaskOut.parse_obj(response.json())
        assert task_out.id == project_uuid
        assert task_out.url == f"{client.base_url}/v2/computations/{project_uuid}"
        print("Pipeline is in ", task_out.state)
        assert task_out.state in wait_for_states
        return task_out

    task_out = check_pipeline_state()

    return task_out


@pytest.mark.parametrize(
    "subgraph_elements,exp_pipeline_dag_adj_list_1st_run",
    [
        pytest.param([0, 1], {1: []}, id="element 0,1"),
        pytest.param(
            [1, 2, 4],
            {1: [2], 2: [4], 3: [4], 4: []},
            id="element 1,2,4",
        ),
    ],
)
def test_run_partial_computation(
    client: TestClient,
    user_id: PositiveInt,
    project: Callable,
    update_project_workbench_with_comp_tasks: Callable,
    fake_workbench_without_outputs: Dict[str, Any],
    subgraph_elements: List[int],
    exp_pipeline_dag_adj_list_1st_run: Dict[str, List[str]],
):
    # send a valid project with sleepers
    sleepers_project = project(workbench=fake_workbench_without_outputs)
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(sleepers_project.uuid),
            "start_pipeline": True,
            "subgraph": [
                str(node_id)
                for index, node_id in enumerate(sleepers_project.workbench)
                if index in subgraph_elements
            ],
        },
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"

    task_out = ComputationTaskOut.parse_obj(response.json())

    assert task_out.id == sleepers_project.uuid
    assert task_out.state == RunningState.PUBLISHED
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert (
        task_out.stop_url
        == f"{client.base_url}/v2/computations/{sleepers_project.uuid}:stop"
    )
    # convert the ids to the node uuids from the project
    workbench_node_uuids = list(sleepers_project.workbench.keys())
    expected_adj_list_1st_run: Dict[NodeID, List[NodeID]] = {}
    expected_adj_list_2nd_run: Dict[NodeID, List[NodeID]] = {}
    for conv in [expected_adj_list_1st_run, expected_adj_list_2nd_run]:
        for node_key, next_nodes in exp_pipeline_dag_adj_list_1st_run.items():
            conv[NodeID(workbench_node_uuids[node_key])] = [
                NodeID(workbench_node_uuids[n]) for n in next_nodes
            ]
    assert task_out.pipeline == expected_adj_list_1st_run

    # now wait for the computation to finish
    task_out = _assert_pipeline_status(
        client, task_out.url, user_id, sleepers_project.uuid
    )
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert task_out.stop_url == None

    assert (
        task_out.state == RunningState.SUCCESS
    ), f"the pipeline complete with state {task_out.state}"

    # run it a second time. the tasks are all up-to-date, nothing should be run
    # FIXME: currently the webserver is the one updating the projects table so we need to fake this by copying the run_hash
    update_project_workbench_with_comp_tasks(str(sleepers_project.uuid))
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(sleepers_project.uuid),
            "start_pipeline": True,
            "subgraph": [
                str(node_id)
                for index, node_id in enumerate(sleepers_project.workbench)
                if index in subgraph_elements
            ],
        },
    )
    assert (
        response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    ), f"response code is {response.status_code}, error: {response.text}"

    # force run it this time.
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(sleepers_project.uuid),
            "start_pipeline": True,
            "subgraph": [
                str(node_id)
                for index, node_id in enumerate(sleepers_project.workbench)
                if index in subgraph_elements
            ],
            "force_restart": True,
        },
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"

    task_out = ComputationTaskOut.parse_obj(response.json())

    assert task_out.id == sleepers_project.uuid
    assert task_out.state == RunningState.PUBLISHED
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert (
        task_out.stop_url
        == f"{client.base_url}/v2/computations/{sleepers_project.uuid}:stop"
    )
    assert task_out.pipeline == expected_adj_list_2nd_run


def test_run_computation(
    client: TestClient,
    user_id: PositiveInt,
    project: Callable,
    fake_workbench_without_outputs: Dict[str, Any],
):
    # send a valid project with sleepers
    sleepers_project = project(workbench=fake_workbench_without_outputs)
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(sleepers_project.uuid),
            "start_pipeline": True,
        },
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"

    task_out = ComputationTaskOut.parse_obj(response.json())

    assert task_out.id == sleepers_project.uuid
    assert task_out.state == RunningState.PUBLISHED
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert (
        task_out.stop_url
        == f"{client.base_url}/v2/computations/{sleepers_project.uuid}:stop"
    )

    # now wait for the computation to finish
    task_out = _assert_pipeline_status(
        client, task_out.url, user_id, sleepers_project.uuid
    )
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert task_out.stop_url == None

    assert (
        task_out.state == RunningState.SUCCESS
    ), f"the pipeline complete with state {task_out.state}"


def test_abort_computation(
    client: TestClient,
    user_id: PositiveInt,
    project: Callable,
    fake_workbench_without_outputs: Dict[str, Any],
):
    # send a valid project with sleepers
    sleepers_project = project(workbench=fake_workbench_without_outputs)
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(sleepers_project.uuid),
            "start_pipeline": True,
        },
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"

    task_out = ComputationTaskOut.parse_obj(response.json())

    assert task_out.id == sleepers_project.uuid
    assert task_out.state == RunningState.PUBLISHED
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert (
        task_out.stop_url
        == f"{client.base_url}/v2/computations/{sleepers_project.uuid}:stop"
    )

    # wait until the pipeline is started
    task_out = _assert_pipeline_status(
        client,
        task_out.url,
        user_id,
        sleepers_project.uuid,
        wait_for_states=[RunningState.STARTED],
    )
    assert (
        task_out.state == RunningState.STARTED
    ), f"pipeline is not in the expected starting state but in {task_out.state}"
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert (
        task_out.stop_url
        == f"{client.base_url}/v2/computations/{sleepers_project.uuid}:stop"
    )

    # now abort the pipeline
    response = client.post(f"{task_out.stop_url}", json={"user_id": user_id})
    assert (
        response.status_code == status.HTTP_202_ACCEPTED
    ), f"response code is {response.status_code}, error: {response.text}"
    task_out = ComputationTaskOut.parse_obj(response.json())
    assert (
        str(task_out.url)
        == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    )
    assert task_out.stop_url == None

    # check that the pipeline is aborted/stopped
    task_out = _assert_pipeline_status(
        client,
        task_out.url,
        user_id,
        sleepers_project.uuid,
        wait_for_states=[RunningState.ABORTED],
    )
    assert task_out.state == RunningState.ABORTED


def test_update_and_delete_computation(
    client: TestClient,
    user_id: PositiveInt,
    project: Callable,
    fake_workbench_without_outputs: Dict[str, Any],
):
    # send a valid project with sleepers
    sleepers_project = project(workbench=fake_workbench_without_outputs)
    response = client.post(
        COMPUTATION_URL,
        json={"user_id": user_id, "project_id": str(sleepers_project.uuid)},
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"

    task_out = ComputationTaskOut.parse_obj(response.json())

    assert task_out.id == sleepers_project.uuid
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert not task_out.stop_url

    # update the pipeline
    response = client.post(
        COMPUTATION_URL,
        json={"user_id": user_id, "project_id": str(sleepers_project.uuid)},
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"

    task_out = ComputationTaskOut.parse_obj(response.json())

    assert task_out.id == sleepers_project.uuid
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert not task_out.stop_url

    # update the pipeline
    response = client.post(
        COMPUTATION_URL,
        json={"user_id": user_id, "project_id": str(sleepers_project.uuid)},
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"

    task_out = ComputationTaskOut.parse_obj(response.json())

    assert task_out.id == sleepers_project.uuid
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert not task_out.stop_url

    # start it now
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(sleepers_project.uuid),
            "start_pipeline": True,
        },
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"
    task_out = ComputationTaskOut.parse_obj(response.json())
    assert task_out.id == sleepers_project.uuid
    assert task_out.state == RunningState.PUBLISHED
    assert task_out.url == f"{client.base_url}/v2/computations/{sleepers_project.uuid}"
    assert (
        task_out.stop_url
        == f"{client.base_url}/v2/computations/{sleepers_project.uuid}:stop"
    )

    # wait until the pipeline is started
    task_out = _assert_pipeline_status(
        client,
        task_out.url,
        user_id,
        sleepers_project.uuid,
        wait_for_states=[RunningState.STARTED],
    )
    assert (
        task_out.state == RunningState.STARTED
    ), f"pipeline is not in the expected starting state but in {task_out.state}"

    # now try to update the pipeline, is expected to be forbidden
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(sleepers_project.uuid),
        },
    )
    assert (
        response.status_code == status.HTTP_403_FORBIDDEN
    ), f"response code is {response.status_code}, error: {response.text}"

    # try to delete the pipeline, is expected to be forbidden if force parameter is false (default)
    response = client.delete(task_out.url, json={"user_id": user_id})
    assert (
        response.status_code == status.HTTP_403_FORBIDDEN
    ), f"response code is {response.status_code}, error: {response.text}"

    # try again with force=True this should abort and delete the pipeline
    response = client.delete(task_out.url, json={"user_id": user_id, "force": True})
    assert (
        response.status_code == status.HTTP_204_NO_CONTENT
    ), f"response code is {response.status_code}, error: {response.text}"


def test_pipeline_with_no_comp_services_still_create_correct_comp_tasks(
    client: TestClient,
    user_id: PositiveInt,
    project: Callable,
    jupyter_service: Dict[str, str],
):
    # create a workbench with just a dynamic service
    project_with_dynamic_node = project(
        workbench={
            "39e92f80-9286-5612-85d1-639fa47ec57d": {
                "key": jupyter_service["image"]["name"],
                "version": jupyter_service["image"]["tag"],
                "label": "my sole dynamic service",
            }
        }
    )

    # this pipeline is not runnable as there are no computational services
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(project_with_dynamic_node.uuid),
            "start_pipeline": True,
        },
    )
    assert (
        response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    ), f"response code is {response.status_code}, error: {response.text}"

    # still this pipeline shall be createable if we do not want to start it
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(project_with_dynamic_node.uuid),
            "start_pipeline": False,
        },
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"


def test_pipeline_with_control_pipeline_made_of_dynamic_services_are_allowed(
    client: TestClient,
    user_id: PositiveInt,
    project: Callable,
    jupyter_service: Dict[str, str],
):
    # create a workbench with just 2 dynamic service in a cycle
    project_with_dynamic_node = project(
        workbench={
            "39e92f80-9286-5612-85d1-639fa47ec57d": {
                "key": jupyter_service["image"]["name"],
                "version": jupyter_service["image"]["tag"],
                "label": "the controller",
            },
            "09b92a4b-8bf4-49ad-82d3-1855c5a4957a": {
                "key": jupyter_service["image"]["name"],
                "version": jupyter_service["image"]["tag"],
                "label": "the model",
            },
        }
    )

    # this pipeline is not runnable as there are no computational services and it contains a cycle
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(project_with_dynamic_node.uuid),
            "start_pipeline": True,
        },
    )
    assert (
        response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    ), f"response code is {response.status_code}, error: {response.text}"

    # still this pipeline shall be createable if we do not want to start it
    response = client.post(
        COMPUTATION_URL,
        json={
            "user_id": user_id,
            "project_id": str(project_with_dynamic_node.uuid),
            "start_pipeline": False,
        },
    )
    assert (
        response.status_code == status.HTTP_201_CREATED
    ), f"response code is {response.status_code}, error: {response.text}"
