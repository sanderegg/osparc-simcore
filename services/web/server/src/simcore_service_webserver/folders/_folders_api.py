# pylint: disable=unused-argument

import logging

from aiohttp import web
from aiopg.sa.engine import Engine
from models_library.api_schemas_webserver.folders import FolderGet
from models_library.folders import FolderID
from models_library.products import ProductName
from models_library.projects_access import AccessRights
from models_library.rest_ordering import OrderBy
from models_library.users import GroupID, UserID
from pydantic import NonNegativeInt, parse_obj_as
from simcore_postgres_database import utils_folders as folders_db

from .._constants import APP_DB_ENGINE_KEY
from ..users.api import get_user

_logger = logging.getLogger(__name__)


async def create_folder(
    app: web.Application,
    user_id: UserID,
    folder_name: str,
    description: str | None,
    parent_folder_id: FolderID | None,
    product_name: ProductName,
) -> FolderID:
    user = await get_user(app, user_id=user_id)

    engine: Engine = app[APP_DB_ENGINE_KEY]
    async with engine.acquire() as connection:
        # NOTE: folder permissions are checked inside the function
        folder_id = await folders_db.folder_create(
            connection,
            product_name=product_name,
            name=folder_name,
            gid=user["primary_gid"],
            description=description if description else "",
            parent=parent_folder_id,
        )
    return FolderID(folder_id)


async def get_folder(
    app: web.Application,
    user_id: UserID,
    folder_id: FolderID,
    product_name: ProductName,
) -> FolderGet:
    raise NotImplementedError


async def list_folders(
    app: web.Application,
    user_id: UserID,
    product_name: ProductName,
    folder_id: FolderID | None,
    offset: NonNegativeInt,
    limit: int,
    order_by: OrderBy,
) -> list[FolderGet]:
    user = await get_user(app, user_id=user_id)

    engine: Engine = app[APP_DB_ENGINE_KEY]
    async with engine.acquire() as connection:
        # NOTE: folder permissions are checked inside the function
        folder_list_db: list[folders_db.FolderEntry] = await folders_db.folder_list(
            connection,
            product_name=product_name,
            folder_id=folder_id,
            gid=user["primary_gid"],
            offset=offset,
            limit=limit,
        )
    return [
        FolderGet(
            folder_id=folder.id,
            parent_folder_id=folder.parent_folder,
            name=folder.name,
            description=folder.description,
            created_at=folder.created,
            modified_at=folder.modified,
            owner=folder.owner,
            my_access_rights=parse_obj_as(
                AccessRights, folder.my_access_rights.to_dict()
            ),
            access_rights=parse_obj_as(
                dict[GroupID, AccessRights],
                {key: value.to_dict() for key, value in folder.access_rights.items()},
            ),
        )
        for folder in folder_list_db
    ]


async def update_folder(
    app: web.Application,
    user_id: UserID,
    folder_id: FolderID,
    name: str,
    description: str | None,
    product_name: ProductName,
) -> None:
    user = await get_user(app, user_id=user_id)

    engine: Engine = app[APP_DB_ENGINE_KEY]
    async with engine.acquire() as connection:
        # NOTE: folder permissions are checked inside the function
        await folders_db.folder_update(
            connection,
            product_name=product_name,
            folder_id=folder_id,
            gid=user["primary_gid"],
            name=name,
            description=description,
        )


async def delete_folder(
    app: web.Application,
    user_id: UserID,
    folder_id: FolderID,
    product_name: ProductName,
) -> None:
    user = await get_user(app, user_id=user_id)

    engine: Engine = app[APP_DB_ENGINE_KEY]
    async with engine.acquire() as connection:
        # NOTE: folder permissions are checked inside the function
        await folders_db.folder_delete(
            connection,
            product_name=product_name,
            folder_id=folder_id,
            gid=user["primary_gid"],
        )
