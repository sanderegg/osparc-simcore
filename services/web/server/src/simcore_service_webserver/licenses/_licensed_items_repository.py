import logging
from typing import Any, Literal, cast

from aiohttp import web
from models_library.licenses import (
    LicensedItemDB,
    LicensedItemID,
    LicensedItemUpdateDB,
    LicensedResourceType,
)
from models_library.products import ProductName
from models_library.resource_tracker import PricingPlanId
from models_library.rest_ordering import OrderBy, OrderDirection
from pydantic import NonNegativeInt
from simcore_postgres_database.models.licensed_items import licensed_items
from simcore_postgres_database.utils_repos import (
    get_columns_from_db_model,
    pass_or_acquire_connection,
    transaction_context,
)
from sqlalchemy import asc, desc, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import select

from ..db.plugin import get_asyncpg_engine
from .errors import LicensedItemNotFoundError

_logger = logging.getLogger(__name__)


_SELECTION_ARGS = get_columns_from_db_model(licensed_items, LicensedItemDB)


def _create_insert_query(
    display_name: str,
    licensed_resource_name: str,
    licensed_resource_type: LicensedResourceType,
    licensed_resource_data: dict[str, Any] | None,
    product_name: ProductName | None,
    pricing_plan_id: PricingPlanId | None,
):
    return (
        postgresql.insert(licensed_items)
        .values(
            licensed_resource_name=licensed_resource_name,
            licensed_resource_type=licensed_resource_type,
            licensed_resource_data=licensed_resource_data,
            display_name=display_name,
            pricing_plan_id=pricing_plan_id,
            product_name=product_name,
            created=func.now(),
            modified=func.now(),
        )
        .returning(*_SELECTION_ARGS)
    )


async def create(
    app: web.Application,
    connection: AsyncConnection | None = None,
    *,
    display_name: str,
    licensed_resource_name: str,
    licensed_resource_type: LicensedResourceType,
    licensed_resource_data: dict[str, Any] | None = None,
    product_name: ProductName | None = None,
    pricing_plan_id: PricingPlanId | None = None,
) -> LicensedItemDB:

    query = _create_insert_query(
        display_name,
        licensed_resource_name,
        licensed_resource_type,
        licensed_resource_data,
        product_name,
        pricing_plan_id,
    )
    async with transaction_context(get_asyncpg_engine(app), connection) as conn:
        result = await conn.execute(query)
        row = result.one()
        return LicensedItemDB.model_validate(row)


async def create_if_not_exists(
    app: web.Application,
    connection: AsyncConnection | None = None,
    *,
    display_name: str,
    licensed_resource_name: str,
    licensed_resource_type: LicensedResourceType,
    licensed_resource_data: dict[str, Any] | None = None,
    product_name: ProductName | None = None,
    pricing_plan_id: PricingPlanId | None = None,
) -> LicensedItemDB:

    insert_or_none_query = _create_insert_query(
        display_name,
        licensed_resource_name,
        licensed_resource_type,
        licensed_resource_data,
        product_name,
        pricing_plan_id,
    ).on_conflict_do_nothing()

    async with transaction_context(get_asyncpg_engine(app), connection) as conn:
        result = await conn.execute(insert_or_none_query)
        row = result.one_or_none()

        if row is None:
            select_query = select(*_SELECTION_ARGS).where(
                (licensed_items.c.licensed_resource_name == licensed_resource_name)
                & (licensed_items.c.licensed_resource_type == licensed_resource_type)
            )

            result = await conn.execute(select_query)
            row = result.one()

        assert row is not None  # nosec
        return LicensedItemDB.model_validate(row)


async def list_(
    app: web.Application,
    connection: AsyncConnection | None = None,
    *,
    product_name: ProductName,
    offset: NonNegativeInt,
    limit: NonNegativeInt,
    order_by: OrderBy,
    # filters
    trashed: Literal["exclude", "only", "include"] = "exclude",
    inactive: Literal["exclude", "only", "include"] = "exclude",
) -> tuple[int, list[LicensedItemDB]]:

    base_query = (
        select(*_SELECTION_ARGS)
        .select_from(licensed_items)
        .where(licensed_items.c.product_name == product_name)
    )

    # Apply trashed filter
    if trashed == "exclude":
        base_query = base_query.where(licensed_items.c.trashed.is_(None))
    elif trashed == "only":
        base_query = base_query.where(licensed_items.c.trashed.is_not(None))

    if inactive == "only":
        base_query = base_query.where(
            licensed_items.c.product_name.is_(None)
            | licensed_items.c.licensed_item_id.is_(None)
        )
    elif inactive == "exclude":
        base_query = base_query.where(
            licensed_items.c.product_name.is_not(None)
            & licensed_items.c.licensed_item_id.is_not(None)
        )

    # Select total count from base_query
    subquery = base_query.subquery()
    count_query = select(func.count()).select_from(subquery)

    # Ordering and pagination
    if order_by.direction == OrderDirection.ASC:
        list_query = base_query.order_by(asc(getattr(licensed_items.c, order_by.field)))
    else:
        list_query = base_query.order_by(
            desc(getattr(licensed_items.c, order_by.field))
        )
    list_query = list_query.offset(offset).limit(limit)

    async with pass_or_acquire_connection(get_asyncpg_engine(app), connection) as conn:
        total_count = await conn.scalar(count_query)

        result = await conn.stream(list_query)
        items: list[LicensedItemDB] = [
            LicensedItemDB.model_validate(row) async for row in result
        ]

        return cast(int, total_count), items


async def get(
    app: web.Application,
    connection: AsyncConnection | None = None,
    *,
    licensed_item_id: LicensedItemID,
    product_name: ProductName,
) -> LicensedItemDB:
    select_query = (
        select(*_SELECTION_ARGS)
        .select_from(licensed_items)
        .where(
            (licensed_items.c.licensed_item_id == licensed_item_id)
            & (licensed_items.c.product_name == product_name)
        )
    )

    async with pass_or_acquire_connection(get_asyncpg_engine(app), connection) as conn:
        result = await conn.execute(select_query)
        row = result.one_or_none()
        if row is None:
            raise LicensedItemNotFoundError(licensed_item_id=licensed_item_id)
        return LicensedItemDB.model_validate(row)


async def get_by_resource_identifier(
    app: web.Application,
    connection: AsyncConnection | None = None,
    *,
    licensed_resource_name: str,
    licensed_resource_type: LicensedResourceType,
) -> LicensedItemDB:
    select_query = select(*_SELECTION_ARGS).where(
        (licensed_items.c.licensed_resource_name == licensed_resource_name)
        & (licensed_items.c.licensed_resource_type == licensed_resource_type)
    )

    async with pass_or_acquire_connection(get_asyncpg_engine(app), connection) as conn:
        result = await conn.execute(select_query)
        row = result.one_or_none()
        if row is None:
            raise LicensedItemNotFoundError(
                licensed_item_id="Unkown",
                licensed_resource_name=licensed_resource_name,
                licensed_resource_type=licensed_resource_type,
            )
        return LicensedItemDB.model_validate(row)


async def update(
    app: web.Application,
    connection: AsyncConnection | None = None,
    *,
    product_name: ProductName,
    licensed_item_id: LicensedItemID,
    updates: LicensedItemUpdateDB,
) -> LicensedItemDB:
    # NOTE: at least 'touch' if updated_values is empty
    _updates = {
        **updates.model_dump(exclude_unset=True),
        licensed_items.c.modified.name: func.now(),
    }

    # trashing
    assert "trash" in dict(LicensedItemUpdateDB.model_fields)  # nosec
    if trash := _updates.pop("trash", None):
        _updates[licensed_items.c.trashed.name] = func.now() if trash else None

    async with transaction_context(get_asyncpg_engine(app), connection) as conn:
        result = await conn.execute(
            licensed_items.update()
            .values(**_updates)
            .where(
                (licensed_items.c.licensed_item_id == licensed_item_id)
                & (licensed_items.c.product_name == product_name)
            )
            .returning(*_SELECTION_ARGS)
        )
        row = result.one_or_none()
        if row is None:
            raise LicensedItemNotFoundError(licensed_item_id=licensed_item_id)
        return LicensedItemDB.model_validate(row)


async def delete(
    app: web.Application,
    connection: AsyncConnection | None = None,
    *,
    licensed_item_id: LicensedItemID,
    product_name: ProductName,
) -> None:
    async with transaction_context(get_asyncpg_engine(app), connection) as conn:
        await conn.execute(
            licensed_items.delete().where(
                (licensed_items.c.licensed_item_id == licensed_item_id)
                & (licensed_items.c.product_name == product_name)
            )
        )
