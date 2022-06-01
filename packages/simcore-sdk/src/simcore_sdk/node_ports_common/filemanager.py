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
    FileUploadSchema,
    UploadedPart,
)
from models_library.generics import Envelope
from models_library.utils.fastapi_encoders import jsonable_encoder
from pydantic import parse_obj_as
from pydantic.networks import AnyUrl
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

CHUNK_SIZE = 1 * 1024 * 1024


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
) -> FileUploadSchema:
    """
    :raises exceptions.S3InvalidPathError: _description_
    """
    links: FileUploadSchema = await storage_client.get_upload_file_links(
        session, file_id, store_id, user_id, link_type
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


async def _upload_file_to_link(
    session: ClientSession, upload_links: FileUploadSchema, file_path: Path
) -> ETag:
    log.debug("Uploading from %s to %s", f"{file_path=}", f"{upload_links=}")
    file_size = file_path.stat().st_size
    data_provider = _file_sender(file_path, file_size)
    headers = {"Content-Length": f"{file_size}"}

    assert upload_links.urls  # nosec
    assert len(upload_links.urls) == 1  # nosec

    async with session.put(
        upload_links.urls[0], data=data_provider, headers=headers
    ) as resp:
        if resp.status > 299:
            response_text = await resp.text()
            raise exceptions.S3TransferError(
                "Could not upload file {}:{}".format(file_path, response_text)
            )
        if resp.status != 200:
            response_text = await resp.text()
            raise exceptions.S3TransferError(
                "Issue when uploading file {}:{}".format(file_path, response_text)
            )

        # get the S3 etag from the headers
        e_tag = json.loads(resp.headers.get("Etag", ""))
    log.debug(
        "Uploaded %s to %s, received Etag %s",
        file_path,
        upload_links.urls[0],
        e_tag,
    )
    return e_tag


async def _complete_upload(
    session: ClientSession, upload_links: FileUploadSchema, parts: list[UploadedPart]
) -> ETag:
    async with session.post(
        upload_links.links.complete_upload, json={"parts": jsonable_encoder(parts)}
    ) as resp:
        resp.raise_for_status()
        if resp.status != web.HTTPAccepted.status_code:
            raise exceptions.S3TransferError(
                f"Could not complete the upload of file {upload_links=}"
            )

        # now poll for state
        file_upload_complete_response = parse_obj_as(
            Envelope[FileUploadCompleteResponse], await resp.json()
        )
        assert file_upload_complete_response.data  # nosec
    state_url = file_upload_complete_response.data.links.state

    async for attempt in AsyncRetrying(
        reraise=True,
        wait=wait_fixed(0.5),
        stop=stop_after_delay(60),
        retry=retry_if_exception_type(ValueError),
        before_sleep=before_sleep_log(log, logging.INFO),
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
            await _get_upload_links(user_id, store_id, s3_object, session, link_type),
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
            )
            e_tag = None
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
                # NOTE: this uses 1 presigned link: 5Gb limit on AWS
                e_tag = await _upload_file_to_link(
                    session, upload_links, local_file_path
                )
            # complete the upload
            e_tag = await _complete_upload(
                session,
                upload_links,
                parse_obj_as(list[UploadedPart], [{"number": 1, "e_tag": e_tag}])
                if e_tag
                else [],
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
