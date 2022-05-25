import datetime
import urllib.parse
from dataclasses import dataclass
from typing import Literal, Optional
from uuid import UUID

from models_library.api_schemas_storage import LinkType
from models_library.projects import ProjectID
from models_library.projects_nodes import NodeID
from models_library.users import UserID
from pydantic import (
    AnyUrl,
    BaseModel,
    ByteSize,
    Extra,
    Field,
    constr,
    parse_obj_as,
    validate_arguments,
    validator,
)
from simcore_postgres_database.storage_models import (
    file_meta_data,
    groups,
    metadata,
    projects,
    tokens,
    user_to_groups,
    users,
)

from .constants import (
    DATCORE_ID,
    DATCORE_STR,
    FILE_ID_RE,
    SIMCORE_S3_ID,
    SIMCORE_S3_STR,
)

FileID = constr(regex=FILE_ID_RE)
UploadID = str
ETag = str


@dataclass
class DatasetMetaData:
    dataset_id: str = ""
    display_name: str = ""


def is_uuid(value: str) -> bool:
    try:
        UUID(str(value))
    except ValueError:
        return False
    else:
        return True


class FileMetaData(BaseModel):
    file_uuid: FileID
    location_id: Literal[SIMCORE_S3_ID, DATCORE_ID]
    location: Literal[SIMCORE_S3_STR, DATCORE_STR]
    bucket_name: str
    object_name: FileID
    project_id: Optional[ProjectID]
    project_name: Optional[str] = Field(default=None, deprecated=True)
    node_id: Optional[NodeID]
    node_name: Optional[str] = Field(default=None, deprecated=True)
    file_name: str
    user_id: UserID
    user_name: str = Field(default=None, deprecated=True)
    file_id: FileID
    raw_file_path: FileID
    display_file_path: str = Field(..., deprecated=True)
    created_at: datetime.datetime
    last_modified: datetime.datetime
    file_size: ByteSize = ByteSize(-1)
    entity_tag: Optional[ETag] = None
    is_soft_link: bool = False
    upload_id: Optional[str] = None
    upload_expires_at: Optional[datetime.datetime] = None

    class Config:
        orm_mode = True
        extra = Extra.forbid
        schema_extra = {
            "examples": [
                {
                    "file_uuid": "api/abcd/xx.dat",
                    "location_id": SIMCORE_S3_ID,
                    "location": SIMCORE_S3_STR,
                    "bucket_name": "test-bucket",
                    "object_name": "api/abcd/xx.dat",
                    "file_name": "xx.dat",
                    "user_id": 12,
                    "file_id": "api/abcd/xx.dat",
                    "raw_file_path": "api/abcd/xx.dat",
                }
            ]
        }

    @validator("location_id", pre=True)
    @classmethod
    def ensure_location_is_integer(cls, v):
        if v is not None:
            return int(v)
        return v

    @classmethod
    @validate_arguments
    def from_simcore_node(
        cls,
        user_id: UserID,
        file_uuid: FileID,
        bucket_name: str,
        **file_meta_data_kwargs,
    ):

        parts = file_uuid.split("/")
        now = datetime.datetime.utcnow()
        fmd_kwargs = {
            "file_uuid": file_uuid,
            "location_id": SIMCORE_S3_ID,
            "location": SIMCORE_S3_STR,
            "bucket_name": bucket_name,
            "object_name": file_uuid,
            "file_name": parts[2],
            "user_id": user_id,
            "project_id": parse_obj_as(ProjectID, parts[0])
            if is_uuid(parts[0])
            else None,
            "node_id": parse_obj_as(NodeID, parts[1]) if is_uuid(parts[1]) else None,
            "file_id": file_uuid,
            "raw_file_path": file_uuid,
            "display_file_path": "not/yet/implemented",
            "created_at": now,
            "last_modified": now,
            "file_size": ByteSize(-1),
            "entity_tag": None,
            "is_soft_link": False,
            "upload_id": None,
            "upload_expires_at": None,
        }
        fmd_kwargs.update(**file_meta_data_kwargs)
        return cls.parse_obj(fmd_kwargs)


@dataclass
class FileMetaDataEx:
    """Extend the base type by some additional attributes that shall not end up in the db"""

    fmd: FileMetaData
    parent_id: str = ""

    def __str__(self):
        _str = str(self.fmd)
        _str += "  {0: <25}: {1}\n".format("parent_id", str(self.parent_id))
        return _str


@dataclass
class DatCoreApiToken:
    api_token: Optional[str] = None
    api_secret: Optional[str] = None


@dataclass
class UploadLinks:
    urls: list[AnyUrl]
    chunk_size: ByteSize


class FileUploadQueryParams(BaseModel):
    user_id: UserID
    link_type: LinkType = LinkType.PRESIGNED
    file_size: ByteSize = ByteSize(0)

    class Config:
        allow_population_by_field_name = True
        extra = Extra.forbid

    @validator("link_type", pre=True)
    @classmethod
    def convert_from_lower_case(cls, v):
        if v is not None:
            return f"{v}".upper()
        return v


class FilePathParams(BaseModel):
    location_id: int
    file_id: FileID

    class Config:
        allow_population_by_field_name = True
        extra = Extra.forbid

    @validator("file_id", pre=True)
    @classmethod
    def unquote(cls, v):
        if v is not None:
            return urllib.parse.unquote(f"{v}")
        return v


__all__ = (
    "file_meta_data",
    "tokens",
    "metadata",
    "DatCoreApiToken",
    "FileMetaData",
    "FileMetaDataEx",
    "FileID",
    "UploadID",
    "UploadLinks",
    "ETag",
    "projects",
    "users",
    "groups",
    "user_to_groups",
)
