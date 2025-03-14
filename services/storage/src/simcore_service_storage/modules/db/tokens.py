import logging
from typing import Any

import sqlalchemy as sa
from fastapi import FastAPI
from models_library.users import UserID
from simcore_postgres_database.storage_models import tokens
from sqlalchemy.ext.asyncio import AsyncEngine

from . import get_db_engine

_logger = logging.getLogger(__name__)


async def _get_tokens_from_db(engine: AsyncEngine, user_id: UserID) -> dict[str, Any]:
    async with engine.connect() as conn:
        result = await conn.execute(
            sa.select(
                tokens,
            ).where(tokens.c.user_id == user_id)
        )
        row = result.one_or_none()
        return row._asdict() if row else {}


async def get_api_token_and_secret(
    app: FastAPI, user_id: UserID
) -> tuple[str | None, str | None]:
    engine = get_db_engine(app)
    data = await _get_tokens_from_db(engine, user_id)

    data = data.get("token_data", {})
    api_token = data.get("token_key")
    api_secret = data.get("token_secret")

    return api_token, api_secret
