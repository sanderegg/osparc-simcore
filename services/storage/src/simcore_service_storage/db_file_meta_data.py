import datetime
from typing import Optional

import sqlalchemy as sa
from aiopg.sa.connection import SAConnection
from models_library.projects import ProjectID
from models_library.projects_nodes import NodeID
from models_library.users import UserID
from simcore_postgres_database.models.file_meta_data import file_meta_data
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .exceptions import FileMetaDataNotFoundError
from .models import FileID, FileMetaData, UploadID


async def upsert_file_metadata_for_upload(
    conn: SAConnection,
    user_id: UserID,
    bucket: str,
    file_uuid: FileID,
    **file_meta_data_kwargs,
) -> FileMetaData:
    parts = file_uuid.split("/")
    if len(parts) != 3:
        raise ValueError(f"{file_uuid=} does not follow conventions")

    fmd = FileMetaData()
    fmd.simcore_from_uuid(
        user_id=user_id,
        file_uuid=file_uuid,
        bucket_name=bucket,
        **file_meta_data_kwargs,
    )

    # NOTE: upsert file_meta_data, if the file already exists, we update the whole row
    # so we get the correct time stamps
    insert_statement = pg_insert(file_meta_data).values(**vars(fmd))
    on_update_statement = insert_statement.on_conflict_do_update(
        index_elements=[file_meta_data.c.file_uuid], set_=vars(fmd)
    )
    await conn.execute(on_update_statement)

    return fmd


async def get(conn: SAConnection, file_uuid: FileID) -> FileMetaData:
    result = await conn.execute(
        query=sa.select([file_meta_data]).where(file_meta_data.c.file_uuid == file_uuid)
    )
    if row := await result.fetchone():
        return FileMetaData(**dict(row))  # type: ignore
    raise FileMetaDataNotFoundError(file_uuid=file_uuid)


async def get_upload_id(conn: SAConnection, file_uuid: FileID) -> Optional[UploadID]:
    return await conn.scalar(
        sa.select([file_meta_data.c.upload_id]).where(
            file_meta_data.c.file_uuid == file_uuid
        )
    )


async def list_fmds(
    conn: SAConnection,
    user_id: Optional[UserID] = None,
    project_id: Optional[ProjectID] = None,
    expired_after: Optional[datetime.datetime] = None,
) -> list[FileMetaData]:
    stmt = sa.select([file_meta_data]).where(
        ((file_meta_data.c.user_id == f"{user_id}") if user_id else True)
        & ((file_meta_data.c.project_id == f"{project_id}") if project_id else True)
        & (
            (file_meta_data.c.upload_expires_at < expired_after)
            if expired_after
            else True
        )
    )

    file_metadatas = []
    async for row in await conn.execute(stmt):
        file_metadatas.append(FileMetaData(**dict(row)))
    return file_metadatas


async def exists(conn: SAConnection, file_uuid: FileID) -> bool:
    return bool(
        await conn.scalar(
            sa.select([file_meta_data.c.file_uuid]).where(
                file_meta_data.c.file_uuid == file_uuid
            )
        )
        == file_uuid
    )


async def delete(conn: SAConnection, file_uuid: FileID) -> None:
    await conn.execute(
        file_meta_data.delete().where(file_meta_data.c.file_uuid == file_uuid)
    )


async def delete_all_from_project(conn: SAConnection, project_id: ProjectID) -> None:
    await conn.execute(
        file_meta_data.delete().where(file_meta_data.c.project_id == f"{project_id}")
    )


async def delete_all_from_node(conn: SAConnection, node_id: NodeID) -> None:
    await conn.execute(
        file_meta_data.delete().where(file_meta_data.c.node_id == f"{node_id}")
    )
