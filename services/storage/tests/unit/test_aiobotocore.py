# pylint: disable=redefined-outer-name
# pylint: disable=unused-argument
# pylint: disable=unused-variable


from contextlib import AsyncExitStack

import pytest
from aiobotocore.session import get_session
from botocore import exceptions as boto_exceptions
from moto.server import ThreadedMotoServer


@pytest.fixture
def mocked_s3_server():
    server = ThreadedMotoServer()
    server.start()
    yield
    server.stop()


async def test_s3_client_fails_if_no_s3(mocked_s3_server):
    session = get_session()
    with pytest.raises(boto_exceptions.ConnectTimeoutError):
        async with session.create_client("s3") as client:
            assert client
    with pytest.raises(boto_exceptions.ConnectTimeoutError):
        async with AsyncExitStack() as exit_stack:
            client = await exit_stack.enter_async_context(session.create_client("s3"))
            assert client


async def test_s3_client_reconnects_if_s3_server_restarts():
    s3_server = ThreadedMotoServer()
    s3_server.start()
    session = get_session()
    async with session.create_client(
        "s3",
        endpoint_url="http://localhost:5000",
        aws_secret_access_key="xxx",
        aws_access_key_id="xxx",
    ) as client:
        assert client
        response = await client.list_buckets()
        assert response
        assert "Buckets" in response
        assert isinstance(response["Buckets"], list)
        assert not response["Buckets"]

        # stop the server
        s3_server.stop()
        with pytest.raises(boto_exceptions.EndpointConnectionError):
            response = await client.list_buckets()

        # restart the server
        s3_server.start()
        response = await client.list_buckets()
