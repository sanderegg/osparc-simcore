import json

# pylint: disable=too-many-arguments
import logging
from pathlib import Path
from typing import Optional, Tuple

import aiofiles
from aiohttp import ClientError, ClientPayloadError, ClientSession, web
from models_library.api_schemas_storage import (
    FileUploadCompleteFutureResponse,
    FileUploadCompleteResponse,
    FileUploadCompleteState,
    FileUploadCompletionBody,
    FileUploadSchema,
    UploadedPart,
)
from models_library.generics import Envelope
from models_library.utils.fastapi_encoders import jsonable_encoder
from pydantic import ByteSize, parse_obj_as
from pydantic.networks import AnyUrl
from servicelib.utils import logged_gather
from settings_library.r_clone import RCloneSettings
from tenacity._asyncio import AsyncRetrying
from tenacity.before_sleep import before_sleep_log
from tenacity.retry import retry_if_exception_type
from tenacity.stop import stop_after_delay
from tenacity.wait import wait_fixed
from tqdm import tqdm
from yarl import URL

from ..node_ports_common.client_session_manager import ClientSessionContextManager
from . import exceptions, storage_client
from .constants import SIMCORE_LOCATION, ETag
from .r_clone import RCloneFailedError, is_r_clone_available, sync_local_to_s3

log = logging.getLogger(__name__)

CHUNK_SIZE = 16 * 1024 * 1024


async def _get_location_id_from_location_name(
    user_id: int,
    store: str,
    session: ClientSession,
) -> str:
    resp = await storage_client.get_storage_locations(session, user_id)
    for location in resp:
        if location.name == store:
            return f"{location.id}"
    # location id not found
    raise exceptions.S3InvalidStore(store)


async def _get_download_link(
    user_id: int,
    store_id: str,
    file_id: str,
    session: ClientSession,
    link_type: storage_client.LinkType,
) -> URL:
    """
    :raises exceptions.S3InvalidPathError
    :raises exceptions.StorageInvalidCall
    :raises exceptions.StorageServerIssue
    """
    link: AnyUrl = await storage_client.get_download_file_link(
        session, file_id, store_id, user_id, link_type
    )
    if not link:
        raise exceptions.S3InvalidPathError(file_id)

    return URL(link)


async def _get_upload_links(
    user_id: int,
    store_id: str,
    file_id: str,
    session: ClientSession,
    link_type: storage_client.LinkType,
    file_size: Optional[ByteSize],
) -> FileUploadSchema:
    """
    :raises exceptions.S3InvalidPathError: _description_
    """
    links: FileUploadSchema = await storage_client.get_upload_file_links(
        session, file_id, store_id, user_id, link_type, file_size
    )
    if not links:
        raise exceptions.S3InvalidPathError(file_id)

    return links


async def _download_link_to_file(session: ClientSession, url: URL, file_path: Path):
    log.debug("Downloading from %s to %s", url, file_path)
    async with session.get(url) as response:
        if response.status == 404:
            raise exceptions.InvalidDownloadLinkError(url)
        if response.status > 299:
            raise exceptions.TransferError(url)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        # SEE https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Length
        file_size = int(response.headers.get("Content-Length", 0)) or None
        try:
            with tqdm(
                desc=f"downloading {file_path} [{file_size} bytes]",
                total=file_size,
                unit="byte",
                unit_scale=True,
            ) as pbar:
                async with aiofiles.open(file_path, "wb") as file_pointer:
                    chunk = await response.content.read(CHUNK_SIZE)
                    while chunk:
                        await file_pointer.write(chunk)
                        pbar.update(len(chunk))
                        chunk = await response.content.read(CHUNK_SIZE)
                log.debug("Download complete")
        except ClientPayloadError as exc:
            raise exceptions.TransferError(url) from exc


async def _file_sender(file_path: Path, file_size: int):
    with tqdm(
        desc=f"uploading {file_path} [{file_size} bytes]",
        total=file_size,
        unit="byte",
        unit_scale=True,
    ) as pbar:
        async with aiofiles.open(file_path, "rb") as f:
            chunk = await f.read(CHUNK_SIZE)
            while chunk:
                pbar.update(len(chunk))
                yield chunk
                chunk = await f.read(CHUNK_SIZE)


async def _file_part_sender(file: Path, *, offset: int, bytes_to_send: int):
    chunk_size = CHUNK_SIZE
    async with aiofiles.open(file, "rb") as f:
        await f.seek(offset)
        num_read_bytes = 0
        while chunk := await f.read(min(chunk_size, bytes_to_send - num_read_bytes)):
            num_read_bytes += len(chunk)
            yield chunk


async def _upload_file_part(
    session: ClientSession,
    file: Path,
    part_index: int,
    file_offset: int,
    this_file_chunk_size: int,
    num_parts: int,
    upload_url: AnyUrl,
) -> tuple[int, ETag]:
    log.debug(
        "--> uploading %s of %s, [%s]...",
        f"{this_file_chunk_size=}",
        f"{file=}",
        f"{part_index+1}/{num_parts}",
    )
    response = await session.put(
        upload_url,
        data=_file_part_sender(
            file,
            offset=file_offset,
            bytes_to_send=this_file_chunk_size,
        ),
        headers={
            "Content-Length": f"{this_file_chunk_size}",
        },
    )
    response.raise_for_status()
    # NOTE: the response from minio does not contain a json body
    assert response.status == web.HTTPOk.status_code
    assert response.headers
    assert "Etag" in response.headers
    received_e_tag = json.loads(response.headers["Etag"])
    log.info(
        "--> completed upload %s of %s, [%s], %s",
        f"{this_file_chunk_size=}",
        f"{file=}",
        f"{part_index+1}/{num_parts}",
        f"{received_e_tag=}",
    )
    return (part_index, received_e_tag)


async def _upload_file_to_presigned_links(
    session: ClientSession, file_upload_links: FileUploadSchema, file: Path
) -> list[UploadedPart]:
    log.debug("Uploading from %s to %s", f"{file=}", f"{file_upload_links=}")
    file_size = file.stat().st_size

    file_chunk_size = int(file_upload_links.chunk_size)
    num_urls = len(file_upload_links.urls)
    last_chunk_size = file_size - file_chunk_size * (num_urls - 1)
    upload_tasks = []
    for index, upload_url in enumerate(file_upload_links.urls):
        this_file_chunk_size = (
            file_chunk_size if (index + 1) < num_urls else last_chunk_size
        )
        upload_tasks.append(
            _upload_file_part(
                session,
                file,
                index,
                index * file_chunk_size,
                this_file_chunk_size,
                num_urls,
                upload_url,
            )
        )
    try:
        results = await logged_gather(*upload_tasks, log=log, max_concurrency=12)
        part_to_etag = [
            UploadedPart(number=index + 1, e_tag=e_tag) for index, e_tag in results
        ]
        log.info(
            "Uploaded %s, received %s",
            f"{file=}",
            f"{part_to_etag=}",
        )
        return part_to_etag
    except ClientError as exc:
        raise exceptions.S3TransferError(f"Could not upload file {file}:{exc}") from exc


async def _complete_upload(
    session: ClientSession, upload_links: FileUploadSchema, parts: list[UploadedPart]
) -> ETag:
    log.debug("completing upload of %s", f"{upload_links=} with {parts=}")
    async with session.post(
        upload_links.links.complete_upload,
        json=jsonable_encoder(FileUploadCompletionBody(parts=parts)),
    ) as resp:
        resp.raise_for_status()
        # now poll for state
        file_upload_complete_response = parse_obj_as(
            Envelope[FileUploadCompleteResponse], await resp.json()
        )
        assert file_upload_complete_response.data  # nosec
    state_url = file_upload_complete_response.data.links.state
    log.info(
        "completed upload of %s",
        f"{upload_links=} with {parts=}, received {file_upload_complete_response=}",
    )

    log.debug("waiting for upload completion...")
    async for attempt in AsyncRetrying(
        reraise=True,
        wait=wait_fixed(0.5),
        stop=stop_after_delay(60),
        retry=retry_if_exception_type(ValueError),
        before_sleep=before_sleep_log(log, logging.DEBUG),
    ):
        with attempt:
            async with session.post(state_url) as resp:
                resp.raise_for_status()
                future_enveloped = parse_obj_as(
                    Envelope[FileUploadCompleteFutureResponse], await resp.json()
                )
                assert future_enveloped.data  # nosec
                if future_enveloped.data.state == FileUploadCompleteState.NOK:
                    raise ValueError("upload not ready yet")
            assert future_enveloped.data.e_tag  # nosec
            log.debug(
                "multipart upload completed in %s, received %s",
                attempt.retry_state.retry_object.statistics,
                f"{future_enveloped.data.e_tag=}",
            )
            return future_enveloped.data.e_tag
    raise exceptions.S3TransferError(
        f"Could not complete the upload of file {upload_links=}"
    )


async def get_download_link_from_s3(
    *,
    user_id: int,
    store_name: Optional[str],
    store_id: Optional[str],
    s3_object: str,
    link_type: storage_client.LinkType,
    client_session: Optional[ClientSession] = None,
) -> URL:
    """
    :raises exceptions.NodeportsException
    :raises exceptions.S3InvalidPathError
    :raises exceptions.StorageInvalidCall
    :raises exceptions.StorageServerIssue
    """
    if store_name is None and store_id is None:
        raise exceptions.NodeportsException(msg="both store name and store id are None")

    async with ClientSessionContextManager(client_session) as session:
        if store_name is not None:
            store_id = await _get_location_id_from_location_name(
                user_id, store_name, session
            )
        assert store_id is not None  # nosec
        return await _get_download_link(
            user_id, store_id, s3_object, session, link_type
        )


async def get_upload_links_from_s3(
    *,
    user_id: int,
    store_name: Optional[str],
    store_id: Optional[str],
    s3_object: str,
    link_type: storage_client.LinkType,
    client_session: Optional[ClientSession] = None,
    file_size: Optional[ByteSize] = None,
) -> Tuple[str, FileUploadSchema]:
    if store_name is None and store_id is None:
        raise exceptions.NodeportsException(msg="both store name and store id are None")

    async with ClientSessionContextManager(client_session) as session:
        if store_name is not None:
            store_id = await _get_location_id_from_location_name(
                user_id, store_name, session
            )
        assert store_id is not None  # nosec
        return (
            store_id,
            await _get_upload_links(
                user_id, store_id, s3_object, session, link_type, file_size
            ),
        )


async def download_file_from_s3(
    *,
    user_id: int,
    store_name: Optional[str],
    store_id: Optional[str],
    s3_object: str,
    local_folder: Path,
    client_session: Optional[ClientSession] = None,
) -> Path:
    """Downloads a file from S3

    :param session: add app[APP_CLIENT_SESSION_KEY] session here otherwise default is opened/closed every call
    :type session: ClientSession, optional
    :raises exceptions.S3InvalidPathError
    :raises exceptions.StorageInvalidCall
    :return: path to downloaded file
    """
    log.debug(
        "Downloading from store %s:id %s, s3 object %s, to %s",
        store_name,
        store_id,
        s3_object,
        local_folder,
    )

    async with ClientSessionContextManager(client_session) as session:
        # get the s3 link
        download_link = await get_download_link_from_s3(
            user_id=user_id,
            store_name=store_name,
            store_id=store_id,
            s3_object=s3_object,
            client_session=session,
            link_type=storage_client.LinkType.PRESIGNED,
        )

        # the link contains the file name
        if not download_link:
            raise exceptions.S3InvalidPathError(s3_object)

        return await download_file_from_link(
            download_link,
            local_folder,
            client_session=session,
        )


async def download_file_from_link(
    download_link: URL,
    destination_folder: Path,
    file_name: Optional[str] = None,
    client_session: Optional[ClientSession] = None,
) -> Path:
    # a download link looks something like:
    # http://172.16.9.89:9001/simcore-test/269dec55-6d18-4901-a767-b567db23d425/4ccf4e2e-a6cd-4f77-a255-4c36fa1b1c72/test.test?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=s3access/20190719/us-east-1/s3/aws4_request&X-Amz-Date=20190719T142431Z&X-Amz-Expires=259200&X-Amz-SignedHeaders=host&X-Amz-Signature=90268f3b580b38c1aad128475936c6f5fd335d11d01ec143cca1056d92a724b5
    local_file_path = destination_folder / (file_name or Path(download_link.path).name)

    # remove an already existing file if present
    if local_file_path.exists():
        local_file_path.unlink()

    async with ClientSessionContextManager(client_session) as session:
        await _download_link_to_file(session, download_link, local_file_path)

    return local_file_path


async def _abort_upload(
    session: ClientSession, upload_links: FileUploadSchema, *, reraise_exceptions: bool
) -> None:
    try:
        async with session.post(upload_links.links.abort_upload) as resp:
            resp.raise_for_status()
    except ClientError:
        log.warning("Error while aborting upload", exc_info=True)
        if reraise_exceptions:
            raise


async def upload_file(
    *,
    user_id: int,
    store_id: Optional[str],
    store_name: Optional[str],
    s3_object: str,
    local_file_path: Path,
    client_session: Optional[ClientSession] = None,
    r_clone_settings: Optional[RCloneSettings] = None,
) -> Tuple[str, str]:
    """Uploads a file to S3

    :param session: add app[APP_CLIENT_SESSION_KEY] session here otherwise default is opened/closed every call
    :type session: ClientSession, optional
    :raises exceptions.NodeportsException
    :raises exceptions.S3InvalidPathError
    :return: stored id
    """
    log.debug(
        "Uploading %s to %s:%s@%s",
        f"{local_file_path=}",
        f"{store_id=}",
        f"{store_name=}",
        f"{s3_object=}",
    )
    use_rclone = (
        await is_r_clone_available(r_clone_settings) and store_id == SIMCORE_LOCATION
    )

    async with ClientSessionContextManager(client_session) as session:
        upload_links = None
        try:
            store_id, upload_links = await get_upload_links_from_s3(
                user_id=user_id,
                store_name=store_name,
                store_id=store_id,
                s3_object=s3_object,
                client_session=session,
                link_type=storage_client.LinkType.S3
                if use_rclone
                else storage_client.LinkType.PRESIGNED,
                file_size=ByteSize(local_file_path.stat().st_size),
            )
            # NOTE: in case of S3 upload, there are no multipart uploads, so this remains empty
            uploaded_parts: list[UploadedPart] = []
            if use_rclone:
                assert r_clone_settings  # nosec
                await sync_local_to_s3(
                    session=session,
                    r_clone_settings=r_clone_settings,
                    s3_object=s3_object,
                    local_file_path=local_file_path,
                    user_id=user_id,
                    store_id=store_id,
                )
            else:
                uploaded_parts = await _upload_file_to_presigned_links(
                    session, upload_links, local_file_path
                )
            # complete the upload
            e_tag = await _complete_upload(
                session,
                upload_links,
                uploaded_parts,
            )
        except (RCloneFailedError, exceptions.S3TransferError) as exc:
            log.error("The upload failed with an unexpected error:", exc_info=True)
            if upload_links:
                # abort the upload correctly, so it can revert back to last version
                await _abort_upload(session, upload_links, reraise_exceptions=False)
                log.warning("Upload aborted")
            raise exceptions.S3TransferError from exc

        return store_id, e_tag


async def entry_exists(
    user_id: int,
    store_id: str,
    s3_object: str,
    client_session: Optional[ClientSession] = None,
) -> bool:
    """Returns True if metadata for s3_object is present"""
    try:
        async with ClientSessionContextManager(client_session) as session:
            log.debug("Will request metadata for s3_object=%s", s3_object)

            result = await storage_client.get_file_metadata(
                session, s3_object, store_id, user_id
            )
            log.debug("Result for metadata s3_object=%s, result=%s", s3_object, result)
            return result.get("object_name") == s3_object if result else False
    except exceptions.S3InvalidPathError:
        return False


async def get_file_metadata(
    user_id: int,
    store_id: str,
    s3_object: str,
    client_session: Optional[ClientSession] = None,
) -> Tuple[str, str]:
    async with ClientSessionContextManager(client_session) as session:
        log.debug("Will request metadata for s3_object=%s", s3_object)
        result = await storage_client.get_file_metadata(
            session, s3_object, store_id, user_id
        )
    if not result:
        raise exceptions.StorageInvalidCall(f"The file '{s3_object}' cannot be found")
    log.debug("Result for metadata s3_object=%s, result=%s", s3_object, result)
    return (f"{result.get('location_id', '')}", result.get("entity_tag", ""))


async def delete_file(
    user_id: int,
    store_id: str,
    s3_object: str,
    client_session: Optional[ClientSession] = None,
) -> None:
    async with ClientSessionContextManager(client_session) as session:
        log.debug("Will delete file for s3_object=%s", s3_object)
        await storage_client.delete_file(session, s3_object, store_id, user_id)
