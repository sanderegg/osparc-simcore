import logging
from pathlib import Path
from typing import Union

import aiofiles
from aiohttp import ClientSession
from aiohttp.typedefs import StrOrURL
from aiopg.sa.result import ResultProxy, RowProxy

from .models import FileMetaData, FileMetaDataEx

logger = logging.getLogger(__name__)


MAX_CHUNK_SIZE = 1024
RETRY_WAIT_SECS = 2
RETRY_COUNT = 20
CONNECT_TIMEOUT_SECS = 30
MINUTE = 60


async def download_to_file_or_raise(
    session: ClientSession,
    url: StrOrURL,
    destination_path: Union[str, Path],
    *,
    chunk_size=MAX_CHUNK_SIZE,
) -> int:
    """
    Downloads content from url into destination_path

    Returns downloaded file size

    May raise aiohttp.ClientErrors:
     - aiohttp.ClientResponseError if not 2XX
     - aiohttp.ClientPayloadError while streaming chunks
    """
    # SEE Streaming API: https://docs.aiohttp.org/en/stable/streams.html

    dest_file = Path(destination_path)

    total_size = 0
    async with session.get(url, raise_for_status=True) as response:
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(dest_file, mode="wb") as fh:
            async for chunk in response.content.iter_chunked(chunk_size):
                await fh.write(chunk)
                total_size += len(chunk)

    return total_size


def to_meta_data_extended(row: Union[ResultProxy, RowProxy]) -> FileMetaDataEx:
    assert row  # nosec
    meta = FileMetaData(**dict(row))  # type: ignore
    meta_extended = FileMetaDataEx(
        fmd=meta,
        parent_id=str(Path(meta.object_name).parent),
    )  # type: ignore
    return meta_extended


def is_file_entry_valid(file_metadata: FileMetaData) -> bool:
    return (
        file_metadata.entity_tag is not None
        and file_metadata.file_size is not None
        and file_metadata.file_size > 0
    )
