# pylint:disable=unused-variable
# pylint:disable=unused-argument
# pylint:disable=redefined-outer-name
# pylint:disable=too-many-arguments


from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Generator

import pytest
import sqlalchemy as sa
from models_library.api_schemas_resource_usage_tracker.licensed_items_checkouts import (
    LicensedItemCheckoutGet,
    LicensedItemsCheckoutsPage,
)
from models_library.resource_tracker_licensed_items_purchases import (
    LicensedItemsPurchasesCreate,
)
from servicelib.rabbitmq import RabbitMQRPCClient
from servicelib.rabbitmq.rpc_interfaces.resource_usage_tracker import (
    licensed_items_checkouts,
    licensed_items_purchases,
)
from servicelib.rabbitmq.rpc_interfaces.resource_usage_tracker.errors import (
    NotEnoughAvailableSeatsError,
)
from simcore_postgres_database.models.resource_tracker_licensed_items_checkouts import (
    resource_tracker_licensed_items_checkouts,
)
from simcore_postgres_database.models.resource_tracker_licensed_items_purchases import (
    resource_tracker_licensed_items_purchases,
)
from simcore_postgres_database.models.resource_tracker_service_runs import (
    resource_tracker_service_runs,
)

pytest_simcore_core_services_selection = [
    "postgres",
    "rabbit",
]
pytest_simcore_ops_services_selection = [
    "adminer",
]


_USER_ID_1 = 1
_WALLET_ID = 6


@pytest.fixture()
def resource_tracker_service_run_id(
    postgres_db: sa.engine.Engine, random_resource_tracker_service_run
) -> Generator[str, None, None]:
    with postgres_db.connect() as con:
        result = con.execute(
            resource_tracker_service_runs.insert()
            .values(
                **random_resource_tracker_service_run(
                    user_id=_USER_ID_1, wallet_id=_WALLET_ID
                )
            )
            .returning(resource_tracker_service_runs.c.service_run_id)
        )
        row = result.first()
        assert row

        yield row[0]

        con.execute(resource_tracker_licensed_items_checkouts.delete())
        con.execute(resource_tracker_licensed_items_purchases.delete())
        con.execute(resource_tracker_service_runs.delete())


async def test_rpc_licensed_items_checkouts_workflow(
    mocked_redis_server: None,
    resource_tracker_service_run_id: str,
    rpc_client: RabbitMQRPCClient,
):
    # List licensed items checkouts
    output = await licensed_items_checkouts.get_licensed_items_checkouts_page(
        rpc_client,
        product_name="osparc",
        filter_wallet_id=_WALLET_ID,
    )
    assert output.total == 0
    assert output.items == []

    # Purchase license item
    _create_data = LicensedItemsPurchasesCreate(
        product_name="osparc",
        licensed_item_id="beb16d18-d57d-44aa-a638-9727fa4a72ef",
        key="Duke",
        version="1.0.0",
        wallet_id=_WALLET_ID,
        wallet_name="My Wallet",
        pricing_plan_id=1,
        pricing_unit_id=1,
        pricing_unit_cost_id=1,
        pricing_unit_cost=Decimal(10),
        start_at=datetime.now(tz=UTC),
        expire_at=datetime.now(tz=UTC) + timedelta(days=1),
        num_of_seats=5,
        purchased_by_user=_USER_ID_1,
        user_email="test@test.com",
        purchased_at=datetime.now(tz=UTC),
    )
    created_item = await licensed_items_purchases.create_licensed_item_purchase(
        rpc_client, data=_create_data
    )

    # Checkout with num of seats
    checkout = await licensed_items_checkouts.checkout_licensed_item(
        rpc_client,
        licensed_item_id=created_item.licensed_item_id,
        key=created_item.key,
        version=created_item.version,
        wallet_id=_WALLET_ID,
        product_name="osparc",
        num_of_seats=3,
        service_run_id=resource_tracker_service_run_id,
        user_id=_USER_ID_1,
        user_email="test@test.com",
    )

    # List licensed items checkouts
    output = await licensed_items_checkouts.get_licensed_items_checkouts_page(
        rpc_client,
        product_name="osparc",
        filter_wallet_id=_WALLET_ID,
    )
    assert output.total == 1
    assert isinstance(output, LicensedItemsCheckoutsPage)

    # Get licensed items checkouts
    output = await licensed_items_checkouts.get_licensed_item_checkout(
        rpc_client,
        product_name="osparc",
        licensed_item_checkout_id=output.items[0].licensed_item_checkout_id,
    )
    assert isinstance(output, LicensedItemCheckoutGet)

    # Release num of seats
    license_item_checkout = await licensed_items_checkouts.release_licensed_item(
        rpc_client,
        licensed_item_checkout_id=checkout.licensed_item_checkout_id,
        product_name="osparc",
    )
    assert license_item_checkout
    assert isinstance(license_item_checkout.stopped_at, datetime)


async def test_rpc_licensed_items_checkouts_can_checkout_older_version(
    mocked_redis_server: None,
    resource_tracker_service_run_id: str,
    rpc_client: RabbitMQRPCClient,
):
    # List licensed items checkouts
    output = await licensed_items_checkouts.get_licensed_items_checkouts_page(
        rpc_client,
        product_name="osparc",
        filter_wallet_id=_WALLET_ID,
    )
    assert output.total == 0
    assert output.items == []

    # Purchase license item
    _create_data = LicensedItemsPurchasesCreate(
        product_name="osparc",
        licensed_item_id="beb16d18-d57d-44aa-a638-9727fa4a72ef",
        key="Duke",
        version="2.0.0",
        wallet_id=_WALLET_ID,
        wallet_name="My Wallet",
        pricing_plan_id=1,
        pricing_unit_id=1,
        pricing_unit_cost_id=1,
        pricing_unit_cost=Decimal(10),
        start_at=datetime.now(tz=UTC),
        expire_at=datetime.now(tz=UTC) + timedelta(days=1),
        num_of_seats=5,
        purchased_by_user=_USER_ID_1,
        user_email="test@test.com",
        purchased_at=datetime.now(tz=UTC),
    )
    created_item = await licensed_items_purchases.create_licensed_item_purchase(
        rpc_client, data=_create_data
    )

    # Checkout with num of seats
    checkout = await licensed_items_checkouts.checkout_licensed_item(
        rpc_client,
        licensed_item_id=created_item.licensed_item_id,
        key="Duke",
        version="1.0.0",  # <-- Older version
        wallet_id=_WALLET_ID,
        product_name="osparc",
        num_of_seats=3,
        service_run_id=resource_tracker_service_run_id,
        user_id=_USER_ID_1,
        user_email="test@test.com",
    )

    # List licensed items checkouts
    output = await licensed_items_checkouts.get_licensed_items_checkouts_page(
        rpc_client,
        product_name="osparc",
        filter_wallet_id=_WALLET_ID,
    )
    assert output.total == 1
    assert isinstance(output, LicensedItemsCheckoutsPage)

    # Get licensed items checkouts
    output = await licensed_items_checkouts.get_licensed_item_checkout(
        rpc_client,
        product_name="osparc",
        licensed_item_checkout_id=output.items[0].licensed_item_checkout_id,
    )
    assert isinstance(output, LicensedItemCheckoutGet)

    # Release num of seats
    license_item_checkout = await licensed_items_checkouts.release_licensed_item(
        rpc_client,
        licensed_item_checkout_id=checkout.licensed_item_checkout_id,
        product_name="osparc",
    )
    assert license_item_checkout
    assert isinstance(license_item_checkout.stopped_at, datetime)


async def test_rpc_licensed_items_checkouts_can_not_checkout_newer_version(
    mocked_redis_server: None,
    resource_tracker_service_run_id: str,
    rpc_client: RabbitMQRPCClient,
):
    # List licensed items checkouts
    output = await licensed_items_checkouts.get_licensed_items_checkouts_page(
        rpc_client,
        product_name="osparc",
        filter_wallet_id=_WALLET_ID,
    )
    assert output.total == 0
    assert output.items == []

    # Purchase license item
    _create_data = LicensedItemsPurchasesCreate(
        product_name="osparc",
        licensed_item_id="beb16d18-d57d-44aa-a638-9727fa4a72ef",
        key="Duke",
        version="2.0.0",  # <-- Older version
        wallet_id=_WALLET_ID,
        wallet_name="My Wallet",
        pricing_plan_id=1,
        pricing_unit_id=1,
        pricing_unit_cost_id=1,
        pricing_unit_cost=Decimal(10),
        start_at=datetime.now(tz=UTC),
        expire_at=datetime.now(tz=UTC) + timedelta(days=1),
        num_of_seats=5,
        purchased_by_user=_USER_ID_1,
        user_email="test@test.com",
        purchased_at=datetime.now(tz=UTC),
    )
    created_item = await licensed_items_purchases.create_licensed_item_purchase(
        rpc_client, data=_create_data
    )

    # Checkout with num of seats
    with pytest.raises(NotEnoughAvailableSeatsError):
        await licensed_items_checkouts.checkout_licensed_item(
            rpc_client,
            licensed_item_id=created_item.licensed_item_id,
            key="Duke",
            version="3.0.0",  # <-- Newer version
            wallet_id=_WALLET_ID,
            product_name="osparc",
            num_of_seats=3,
            service_run_id=resource_tracker_service_run_id,
            user_id=_USER_ID_1,
            user_email="test@test.com",
        )
