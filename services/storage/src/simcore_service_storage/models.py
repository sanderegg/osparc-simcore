""" Database models

"""
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Union
from uuid import UUID

import attr
from models_library.users import UserID
from pydantic import constr
from simcore_postgres_database.storage_models import (
    file_meta_data,
    groups,
    metadata,
    projects,
    tokens,
    user_to_groups,
    users,
)

from .constants import DATCORE_STR, SIMCORE_S3_ID, SIMCORE_S3_STR

_LOCATION_ID_TO_TAG_MAP = {0: SIMCORE_S3_STR, 1: DATCORE_STR}
UNDEFINED_LOCATION_TAG: str = "undefined"

# NOTE: SAFE S3 characters are found here [https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-keys.html]
_SAFE_S3_FILE_NAME_RE = r"[\w!\-_\.\*\'\(\)]"
_FILE_ID_RE = rf"^({_SAFE_S3_FILE_NAME_RE}+?)\/({_SAFE_S3_FILE_NAME_RE}+?)\/({_SAFE_S3_FILE_NAME_RE}+?)$"

FileID = constr(regex=_FILE_ID_RE)
UploadID = str
ETag = str


def get_location_from_id(location_id: Union[str, int]) -> str:
    try:
        loc_id = int(location_id)
        return _LOCATION_ID_TO_TAG_MAP[loc_id]
    except (ValueError, KeyError):
        return UNDEFINED_LOCATION_TAG


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


class FileMetaData:
    """This is a proposal, probably no everything is needed.
    It is actually an overkill

    file_name       : display name for a file
    location_id     : storage location
    location_name   : storage location display name
    project_id      : project_id
    projec_name     : project display name
    node_id         : node id
    node_name       : display_name
    bucket_name     : name of the bucket
    object_name     : s3 object name = folder/folder/filename.ending
    user_id         : user_id
    user_name       : user_name

    file_uuid       : unique identifier for a file:

        bucket_name/project_id/node_id/file_name = /bucket_name/object_name

    file_id         : unique uuid for the file

        simcore.s3: uuid created upon insertion
        datcore: datcore uuid

    raw_file_path   : raw path to file

        simcore.s3: proj_id/node_id/filename.ending
        emailaddress/...
        datcore: dataset/collection/filename.ending

    display_file_path: human readlable  path to file

        simcore.s3: proj_name/node_name/filename.ending
        my_documents/...
        datcore: dataset/collection/filename.ending

    created_at          : time stamp
    last_modified       : time stamp
    file_size           : size in bytes

    TODO:
    state:  on of OK, UPLOADING, DELETED

    """

    # pylint: disable=attribute-defined-outside-init
    def simcore_from_uuid(
        self,
        user_id: UserID,
        file_uuid: FileID,
        bucket_name: str,
        **file_meta_data_kwargs,
    ):
        parts = file_uuid.split("/")
        if len(parts) == 3:
            self.user_id = user_id
            self.location = SIMCORE_S3_STR
            self.location_id = SIMCORE_S3_ID
            self.bucket_name = bucket_name
            self.object_name = "/".join(parts[:])
            self.file_name = parts[2]
            self.project_id = parts[0] if is_uuid(parts[0]) else None
            self.node_id = parts[1] if is_uuid(parts[1]) else None
            self.file_uuid = file_uuid
            self.file_id = file_uuid
            self.raw_file_path = self.file_uuid
            self.display_file_path = str(
                Path("not") / Path("yet") / Path("implemented")
            )
            self.created_at = str(datetime.datetime.now())
            self.last_modified = self.created_at
            self.file_size = -1
            self.entity_tag = None
            self.is_soft_link = False
            self.upload_id = None
            self.upload_expires_at = None
            for k, v in file_meta_data_kwargs.items():
                self.__setattr__(k, v)

    def __str__(self):
        d = attr.asdict(self)
        _str = ""
        for _d in d:
            _str += "  {0: <25}: {1}\n".format(_d, str(d[_d]))
        return _str


def get_default(column):
    # NOTE: this is temporary. it translates bool text-clauses into python
    # The only defaults in file_meta_data are actually of these type
    if column.server_default:
        return {"false": False, "true": True}.get(str(column.server_default.arg))
    return None


attr.s(
    these={c.name: attr.ib(default=get_default(c)) for c in file_meta_data.c},
    init=True,
    kw_only=True,
)(FileMetaData)


@dataclass
class FileMetaDataEx:
    """Extend the base type by some additional attributes that shall not end up in the db"""

    fmd: FileMetaData
    parent_id: str = ""

    def __str__(self):
        _str = str(self.fmd)
        _str += "  {0: <25}: {1}\n".format("parent_id", str(self.parent_id))
        return _str


__all__ = (
    "file_meta_data",
    "tokens",
    "metadata",
    "FileMetaData",
    "FileMetaDataEx",
    "FileID",
    "UploadID",
    "ETag",
    "projects",
    "users",
    "groups",
    "user_to_groups",
)
