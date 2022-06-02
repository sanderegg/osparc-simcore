import datetime
import urllib.parse
from dataclasses import dataclass
from typing import Literal, Optional
from uuid import UUID

from models_library.api_schemas_storage import ETag, LinkType
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
    S3_BUCKET_NAME_RE,
    S3_FILE_ID_RE,
    SIMCORE_S3_ID,
    SIMCORE_S3_STR,
)

S3BucketName = constr(regex=S3_BUCKET_NAME_RE)
S3FileID = constr(regex=S3_FILE_ID_RE)

FileID = constr(regex=FILE_ID_RE)
UploadID = str


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
    location_id: Literal[SIMCORE_S3_ID, DATCORE_ID]  # type: ignore
    location: Literal[SIMCORE_S3_STR, DATCORE_STR]  # type: ignore
    bucket_name: S3BucketName
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
        bucket: S3BucketName,
        **file_meta_data_kwargs,
    ):

        parts = file_uuid.split("/")
        now = datetime.datetime.utcnow()
        fmd_kwargs = {
            "file_uuid": file_uuid,
            "location_id": SIMCORE_S3_ID,
            "location": SIMCORE_S3_STR,
            "bucket_name": bucket,
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


class FileMetaDataEx(BaseModel):
    """Extend the base type by some additional attributes that shall not end up in the db"""

    fmd: FileMetaData
    parent_id: str = ""


@dataclass
class DatCoreApiToken:
    api_token: Optional[str] = None
    api_secret: Optional[str] = None


@dataclass
class UploadLinks:
    urls: list[AnyUrl]
    chunk_size: ByteSize


class StorageQueryParamsBase(BaseModel):
    user_id: UserID

    class Config:
        allow_population_by_field_name = True
        extra = Extra.forbid


class FilesMetadataQueryParams(StorageQueryParamsBase):
    uuid_filter: str = ""


class SyncMetadataQueryParams(BaseModel):
    dry_run: bool = False
    fire_and_forget: bool = False


class FileDownloadQueryParams(StorageQueryParamsBase):
    link_type: LinkType = LinkType.PRESIGNED

    @validator("link_type", pre=True)
    @classmethod
    def convert_from_lower_case(cls, v):
        if v is not None:
            return f"{v}".upper()
        return v


class FileUploadQueryParams(StorageQueryParamsBase):
    link_type: LinkType = LinkType.PRESIGNED
    file_size: ByteSize = ByteSize(0)

    @validator("link_type", pre=True)
    @classmethod
    def convert_from_lower_case(cls, v):
        if v is not None:
            return f"{v}".upper()
        return v


class DeleteFolderQueryParams(StorageQueryParamsBase):
    node_id: Optional[NodeID] = None


class SearchFilesQueryParams(StorageQueryParamsBase):
    startswith: str = ""


class LocationPathParams(BaseModel):
    location_id: int

    class Config:
        allow_population_by_field_name = True
        extra = Extra.forbid


class FilesMetadataDatasetPathParams(LocationPathParams):
    dataset_id: str


class FilePathParams(LocationPathParams):
    file_id: FileID

    @validator("file_id", pre=True)
    @classmethod
    def unquote(cls, v):
        if v is not None:
            # we do want the / correctly unquoted, but the rest shall still be
            return urllib.parse.unquote(f"{v}")
        return v


class FilePathIsUploadCompletedParams(FilePathParams):
    future_id: str


class SimcoreS3FoldersParams(BaseModel):
    folder_id: str


class CopyAsSoftLinkParams(BaseModel):
    file_id: FileID

    @validator("file_id", pre=True)
    @classmethod
    def unquote(cls, v):
        if v is not None:
            return urllib.parse.unquote(f"{v}")
        return v


class MultiPartUploadLinks(BaseModel):
    upload_id: UploadID
    chunk_size: ByteSize
    urls: list[AnyUrl]


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
