# pylint:disable=unused-variable
# pylint:disable=unused-argument
# pylint:disable=redefined-outer-name

import json
import sys
from asyncio import Future
from pathlib import Path
from uuid import uuid4

import aio_pika
import pytest

from mock import call
from servicelib.application import create_safe_application
from servicelib.application_keys import APP_CONFIG_KEY
from simcore_sdk.config.rabbit import eval_broker
from simcore_service_webserver.computation import setup_computation
from simcore_service_webserver.computation_config import CONFIG_SECTION_NAME
from simcore_service_webserver.db import setup_db
from simcore_service_webserver.login import setup_login
from simcore_service_webserver.rest import setup_rest
from simcore_service_webserver.security import setup_security
from simcore_service_webserver.security_roles import UserRole
from simcore_service_webserver.session import setup_session
from simcore_service_webserver.socketio import setup_sockets
from utils_login import LoggedUser

API_VERSION = "v0"

# Selection of core and tool services started in this swarm fixture (integration)
core_services = [
    'apihub',
    'postgres',
    'rabbit'
]

ops_services = [
]

@pytest.fixture(scope='session')
def here() -> Path:
    return Path(sys.argv[0] if __name__ == "__main__" else __file__).resolve().parent

@pytest.fixture
def client(loop, aiohttp_client,
        app_config,    ## waits until swarm with *_services are up
        rabbit_service ## waits until rabbit is responsive
    ):
    assert app_config["rest"]["version"] == API_VERSION
    assert API_VERSION in app_config["rest"]["location"]

    app_config['storage']['enabled'] = False
    app_config["db"]["init_tables"] = True # inits postgres_service

    # fake config
    app = create_safe_application()
    app[APP_CONFIG_KEY] = app_config
    setup_db(app)
    setup_session(app)
    setup_security(app)
    setup_rest(app)
    setup_login(app)
    setup_computation(app)
    setup_sockets(app)

    yield loop.run_until_complete(aiohttp_client(app, server_kwargs={
        'port': app_config["main"]["port"],
        'host': app_config['main']['host']
    }))

@pytest.fixture
async def logged_user(client, user_role: UserRole):
    """ adds a user in db and logs in with client

    NOTE: `user_role` fixture is defined as a parametrization below!!!
    """
    async with LoggedUser(
        client,
        {"role": user_role.name},
        check_if_succeeds = user_role!=UserRole.ANONYMOUS
    ) as user:
        yield user

@pytest.fixture
def rabbit_config(app_config):
    rb_config = app_config[CONFIG_SECTION_NAME]
    yield rb_config

@pytest.fixture
def rabbit_broker(rabbit_config):
    rabbit_broker = eval_broker(rabbit_config)
    yield rabbit_broker

@pytest.fixture
async def pika_connection(loop, rabbit_broker):
    connection = await aio_pika.connect(rabbit_broker, ssl=True, connection_attempts=100)
    yield connection
    await connection.close()

@pytest.fixture
async def log_channel(loop, rabbit_config, pika_connection):
    channel = await pika_connection.channel()
    pika_log_channel = rabbit_config["channels"]["log"]
    logs_exchange = await channel.declare_exchange(
        pika_log_channel, aio_pika.ExchangeType.FANOUT,
        auto_delete=True
    )
    yield logs_exchange

@pytest.fixture
async def progress_channel(loop, rabbit_config, pika_connection):
    channel = await pika_connection.channel()
    pika_progress_channel = rabbit_config["channels"]["log"]
    progress_exchange = await channel.declare_exchange(
        pika_progress_channel, aio_pika.ExchangeType.FANOUT,
        auto_delete=True
    )
    yield progress_exchange

@pytest.fixture(scope="session")
def node_uuid() -> str:
    return str(uuid4())

@pytest.fixture(scope="session")
def user_id() -> str:
    return "some_id"

@pytest.fixture(scope="session")
def project_id() -> str:
    return "some_project_id"

@pytest.fixture(scope="session")
def fake_log_message(node_uuid: str, user_id: str, project_id: str):
    yield {
        "Channel":"Log",
        "Messages": ["Some fake message"],
        "Node": node_uuid,
        "user_id": user_id,
        "project_id": project_id
    }

@pytest.fixture(scope="session")
def fake_progress_message(node_uuid: str, user_id: str, project_id: str):
    yield {
        "Channel":"Progress",
        "Progress": 0.56,
        "Node": node_uuid,
        "user_id": user_id,
        "project_id": project_id
    }

# ------------------------------------------

async def assert_rabbit_websocket_connection(socket_event_name, logged_user, socketio_client, mocker, rabbit_channel, channel_message):
    sio = await socketio_client()
    # register mock function
    log_fct = mocker.Mock()    
    sio.on(socket_event_name, handler=log_fct)    
    # the user id is not the one from the logged user, there should be no call to the function
    for i in range(1000):
        await rabbit_channel.publish(
            aio_pika.Message(
                body=json.dumps(channel_message).encode(),
                content_type="text/json"), routing_key = ""
            )
    log_fct.assert_not_called()

    # let's set the correct user id
    channel_message["user_id"] = logged_user["id"]
    for i in range(1000):
        await rabbit_channel.publish(
            aio_pika.Message(
                body=json.dumps(channel_message).encode(),
                content_type="text/json"), routing_key = ""
            )
    log_fct.assert_called()
    calls = [call(json.dumps(channel_message))]
    log_fct.assert_has_calls(calls)

@pytest.mark.parametrize("user_role", [    
    (UserRole.GUEST),
    (UserRole.USER),
    (UserRole.TESTER),
])
async def test_rabbit_log_connection(loop, client, logged_user, 
                                    socketio_client, log_channel, 
                                    mocker, fake_log_message):
    await assert_rabbit_websocket_connection('logger', logged_user, socketio_client, mocker, log_channel, fake_log_message)

@pytest.mark.parametrize("user_role", [    
    (UserRole.GUEST),
    (UserRole.USER),
    (UserRole.TESTER),
])
async def test_rabbit_progress_connection(loop, client, logged_user, 
                                    socketio_client, progress_channel, 
                                    mocker, fake_progress_message):
    await assert_rabbit_websocket_connection('progress', logged_user, socketio_client, mocker, progress_channel, fake_progress_message)
