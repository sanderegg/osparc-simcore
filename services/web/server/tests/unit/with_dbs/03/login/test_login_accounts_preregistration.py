# pylint: disable=protected-access
# pylint: disable=redefined-outer-name
# pylint: disable=too-many-arguments
# pylint: disable=unused-argument
# pylint: disable=unused-variable


from unittest.mock import MagicMock

import pytest
from aiohttp import ClientResponseError
from aiohttp.test_utils import TestClient
from common_library.users_enums import AccountRequestStatus
from faker import Faker
from models_library.api_schemas_webserver.auth import AccountRequestInfo
from models_library.api_schemas_webserver.users import UserAccountGet
from pytest_mock import MockerFixture
from pytest_simcore.helpers.assert_checks import assert_status
from pytest_simcore.helpers.webserver_login import switch_client_session_to
from pytest_simcore.helpers.webserver_users import NewUser, UserInfoDict
from servicelib.aiohttp import status
from simcore_postgres_database.models.users import UserRole
from simcore_service_webserver.login.constants import MSG_USER_DELETED
from simcore_service_webserver.products.products_service import get_product


@pytest.mark.parametrize(
    "user_role", [role for role in UserRole if role < UserRole.USER]
)
async def test_unregister_account_access_rights(
    client: TestClient, logged_user: UserInfoDict, mocker: MockerFixture
):
    response = await client.post(
        "/v0/auth/unregister",
        json={
            "email": logged_user["email"],
            "password": logged_user["raw_password"],
        },
    )

    with pytest.raises(ClientResponseError) as err_info:
        response.raise_for_status()

    error = err_info.value
    assert error.status in (
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    ), f"{error}"


@pytest.fixture
def mocked_send_email(mocker: MockerFixture) -> MagicMock:
    # OVERRIDES services/web/server/tests/unit/with_dbs/conftest.py:mocked_send_email fixture
    return mocker.patch(
        "simcore_service_webserver.email._core._do_send_mail",
        spec=True,
    )


@pytest.fixture
def mocked_captcha_session(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "simcore_service_webserver.login_accounts._controller_rest.session_service.get_session",
        spec=True,
        return_value={"captcha": "123456"},
    )


@pytest.mark.parametrize(
    "user_role", [role for role in UserRole if role >= UserRole.USER]
)
async def test_unregister_account(
    client: TestClient, logged_user: UserInfoDict, mocked_send_email: MagicMock
):
    assert client.app

    # is logged in
    response = await client.get("/v0/me")
    await assert_status(response, status.HTTP_200_OK)

    # success to request deletion of account
    response = await client.post(
        "/v0/auth/unregister",
        json={
            "email": logged_user["email"],
            "password": logged_user["raw_password"],
        },
    )
    await assert_status(response, status.HTTP_200_OK)

    # sent email?
    mimetext = mocked_send_email.call_args[1]["message"]
    assert mimetext["Subject"]
    assert mimetext["To"] == logged_user["email"]

    # should be logged-out
    response = await client.get("/v0/me")
    await assert_status(response, status.HTTP_401_UNAUTHORIZED)

    # try to login again and get rejected
    response = await client.post(
        "/v0/auth/login",
        json={"email": logged_user["email"], "password": logged_user["raw_password"]},
    )
    _, error = await assert_status(response, status.HTTP_401_UNAUTHORIZED)

    prefix_msg = MSG_USER_DELETED.format(support_email="").strip()
    assert prefix_msg in error["errors"][0]["message"]


@pytest.mark.parametrize(
    "user_role", [role for role in UserRole if role >= UserRole.USER]
)
async def test_cannot_unregister_other_account(
    client: TestClient, logged_user: UserInfoDict, mocked_send_email: MagicMock
):
    assert client.app

    # is logged in
    response = await client.get("/v0/me")
    await assert_status(response, status.HTTP_200_OK)

    # cannot delete another account
    async with NewUser(app=client.app) as other_user:
        response = await client.post(
            "/v0/auth/unregister",
            json={
                "email": other_user["email"],
                "password": other_user["raw_password"],
            },
        )
        await assert_status(response, status.HTTP_409_CONFLICT)


@pytest.mark.parametrize("invalidate", ["email", "raw_password"])
@pytest.mark.parametrize(
    "user_role", [role for role in UserRole if role >= UserRole.USER]
)
async def test_cannot_unregister_invalid_credentials(
    client: TestClient,
    logged_user: UserInfoDict,
    mocked_send_email: MagicMock,
    invalidate: str,
):
    assert client.app

    # check is logged in
    response = await client.get("/v0/me")
    await assert_status(response, status.HTTP_200_OK)

    # check cannot invalid credentials
    credentials = {k: logged_user[k] for k in ("email", "raw_password")}
    credentials[invalidate] += "error"

    response = await client.post(
        "/v0/auth/unregister",
        json={
            "email": credentials["email"],
            "password": credentials["raw_password"],
        },
    )
    await assert_status(response, status.HTTP_409_CONFLICT)


async def test_request_an_account(
    client: TestClient,
    faker: Faker,
    mocked_send_email: MagicMock,
    mocked_captcha_session: MagicMock,
):
    assert client.app
    # A form similar to the one in https://github.com/ITISFoundation/osparc-simcore/pull/5378
    user_data = {
        **AccountRequestInfo.model_json_schema()["example"]["form"],
        # fields required in the form
        "firstName": faker.first_name(),
        "lastName": faker.last_name(),
        "email": faker.email(),
        "address": f"{faker.address()},  {faker.postcode()} {faker.city()} [{faker.state()}]".replace(
            "\n", ", "
        ),
        "country": faker.country(),
    }

    response = await client.post(
        "/v0/auth/request-account",
        json={"form": user_data, "captcha": "123456"},
    )

    await assert_status(response, status.HTTP_204_NO_CONTENT)

    product = get_product(client.app, product_name="osparc")

    # check email was sent
    mimetext = mocked_send_email.call_args[1]["message"]
    assert "account" in mimetext["Subject"].lower()
    assert mimetext["From"] == product.support_email
    assert mimetext["To"] == product.product_owners_email or product.support_email

    # check it appears in PO center
    async with NewUser(
        user_data={
            "email": "po-user@email.com",
            "name": "po-user-fixture",
            "role": UserRole.PRODUCT_OWNER,
        },
        app=client.app,
    ) as product_owner_user, switch_client_session_to(client, product_owner_user):

        response = await client.get(
            "v0/admin/user-accounts?limit=20&offset=0&review_status=PENDING"
        )

        data, _ = await assert_status(response, status.HTTP_200_OK)

        assert len(data) == 1
        user = UserAccountGet.model_validate(data[0])
        assert user.first_name == user_data["firstName"]
        assert not user.registered
        assert user.status is None
        assert user.account_request_status == AccountRequestStatus.PENDING

    # TODO add a test for reregistration `AlreadyPreRegisteredError`
