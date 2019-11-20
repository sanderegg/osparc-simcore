# pylint:disable=wildcard-import
# pylint:disable=unused-import
# pylint:disable=unused-variable
# pylint:disable=unused-argument
# pylint:disable=redefined-outer-name

from asyncio import Future
from copy import deepcopy

import pytest
import socketio
from aiohttp import web

from servicelib.application import create_safe_application
from servicelib.rest_responses import unwrap_envelope
from simcore_service_webserver.db import setup_db
from simcore_service_webserver.director import setup_director
from simcore_service_webserver.login import setup_login
from simcore_service_webserver.projects import setup_projects
from simcore_service_webserver.rest import setup_rest
from simcore_service_webserver.security import setup_security
from simcore_service_webserver.security_roles import UserRole
from simcore_service_webserver.session import setup_session
from simcore_service_webserver.socketio import registry, setup_sockets
from simcore_service_webserver.socketio.config import get_socket_registry
from simcore_service_webserver.users import setup_users
from simcore_service_webserver.utils import now_str
from utils_assert import assert_status
from utils_login import LoggedUser
from utils_projects import NewProject

API_VERSION = "v0"

@pytest.fixture
async def mocked_director_handlers(loop, mocker):
    # Note: this needs to be activated before the setup takes place
    mocks = []
    running_service_dict = {
        "published_port": "23423",
        "service_uuid": "some_service_uuid",
        "service_key": "some_service_key",
        "service_version": "some_service_version",
        "service_host": "some_service_host",
        "service_port": "some_service_port",
        "service_state": "some_service_state"
    }
    mocked_director_handler = mocker.patch('simcore_service_webserver.director.handlers.running_interactive_services_post',
                return_value=web.json_response({"data":running_service_dict}, status=web.HTTPCreated.status_code))
    mocks.append(mocked_director_handler)
    yield mocks

@pytest.fixture
def client(loop, aiohttp_client, app_cfg, postgres_service, mocked_director_handlers):    
    cfg = deepcopy(app_cfg)

    assert cfg["rest"]["version"] == API_VERSION
    assert API_VERSION in cfg["rest"]["location"]
    cfg["db"]["init_tables"] = True # inits postgres_service
    cfg["projects"]["enabled"] = True
    cfg["director"]["enabled"] = True

    # fake config
    app = create_safe_application(cfg)

    # activates only security+restAPI sub-modules
    setup_db(app)
    setup_session(app)
    setup_security(app)
    setup_rest(app)
    setup_login(app)
    setup_users(app)
    setup_sockets(app)
    setup_projects(app)
    setup_director(app)


    yield loop.run_until_complete(aiohttp_client(app, server_kwargs={
        'port': cfg["main"]["port"],
        'host': cfg['main']['host']
    }))

@pytest.fixture()
async def logged_user(client, user_role: UserRole):
    """ adds a user in db and logs in with client

    NOTE: `user_role` fixture is defined as a parametrization below!!!
    """
    async with LoggedUser(
        client,
        {"role": user_role.name},
        check_if_succeeds = user_role!=UserRole.ANONYMOUS
    ) as user:
        print("-----> logged in user", user_role)
        yield user
        print("<----- logged out user", user_role)

@pytest.fixture
def empty_project():
    empty_project = {
        "uuid": "0000000-invalid-uuid",
        "name": "Empty name",
        "description": "some description of an empty project",
        "prjOwner": "I'm the empty project owner, hi!",
        "creationDate": now_str(),
        "lastChangeDate": now_str(),
        "thumbnail": "",
        "workbench": {}
    }
    yield empty_project

@pytest.fixture
async def empty_user_project(client, empty_project, logged_user):
    async with NewProject(
        empty_project,
        client.app,
        user_id=logged_user["id"]
    ) as project:
        print("-----> added project", project["name"])
        yield project
        print("<----- removed project", project["name"])

@pytest.mark.parametrize("user_role", [
    (UserRole.GUEST),
    (UserRole.USER),
    (UserRole.TESTER),
])
async def test_interactive_services_removed_after_logout(loop, logged_user, empty_user_project, client, mocked_director_handlers):
    # create dynamic service
    url = client.app.router["running_interactive_services_post"].url_for().with_query(
        {
            "project_id": empty_user_project["uuid"],
            "service_key": "simcore/services/dynamic/3d-viewer",
            "service_tag": "1.4.2",
            "service_uuid": "some_uuid"
        })
    
    resp = await client.post(url)
    data, _error = await assert_status(resp, expected_cls=web.HTTPCreated)
    # mocked_director_handlers["running_interactive_services_post"].assert_called_once()
    # logout
    # assert dynamic service is removed

async def test_interactive_services_remain_after_websocket_reconnection(loop):
    # login
    # create websocket
    # create study
    # create dynamic service
    # disconnect websocket
    # reconnect websocket
    # assert dynamic service is still around
    pass

async def test_interactive_services_removed_after_websocket_disconnection_for_some_time(loop):
    # login
    # create websocket
    # create study
    # create dynamic service
    # disconnect websocket
    # wait for specific delay
    # assert dynamic service is removed
    pass
