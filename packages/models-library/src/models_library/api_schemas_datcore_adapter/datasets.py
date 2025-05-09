from datetime import datetime
from enum import Enum, unique
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, ByteSize, Field


class DatasetMetaData(BaseModel):
    id: str
    display_name: str
    size: Annotated[
        ByteSize | None, Field(description="Size of the dataset in bytes if available")
    ]


@unique
class DataType(str, Enum):
    FILE = "FILE"
    FOLDER = "FOLDER"


class PackageMetaData(BaseModel):
    path: Path
    display_path: Path
    package_id: str
    name: str
    filename: str
    s3_bucket: str
    size: ByteSize
    created_at: datetime
    updated_at: datetime


class FileMetaData(BaseModel):
    dataset_id: str
    package_id: str
    id: str
    name: str
    type: str
    path: Path
    size: int
    created_at: datetime
    last_modified_at: datetime
    data_type: DataType
