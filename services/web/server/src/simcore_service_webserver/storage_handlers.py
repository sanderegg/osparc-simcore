""" Handlers exposed by storage subsystem

    Mostly resolves and redirect to storage API
"""
import logging
import urllib
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from aiohttp import ClientResponse, web
from models_library.api_schemas_storage import (
    FileUploadCompletionBody,
    FileUploadSchema,
    UploadedPart,
)
from models_library.users import UserID
from models_library.utils.fastapi_encoders import jsonable_encoder
from pydantic import AnyUrl, parse_obj_as
from servicelib.aiohttp.client_session import get_client_session
from servicelib.aiohttp.rest_responses import unwrap_envelope
from servicelib.aiohttp.rest_utils import extract_and_validate
from servicelib.request_keys import RQT_USERID_KEY
from yarl import URL

from .login.decorators import login_required
from .security_decorators import permission_required
from .storage_settings import StorageSettings, get_plugin_settings

log = logging.getLogger(__name__)


def _get_base_storage_url(app: web.Application) -> URL:
    settings: StorageSettings = get_plugin_settings(app)

    # storage service API endpoint
    return URL(settings.base_url)


def _resolve_storage_url(request: web.Request) -> URL:
    """Composes a new url against storage API"""
    userid = request[RQT_USERID_KEY]

    # storage service API endpoint
    endpoint = _get_base_storage_url(request.app)

    BASEPATH_INDEX = 3
    # strip basepath from webserver API path (i.e. webserver api version)
    # >>> URL('http://storage:1234/v5/storage/asdf/').raw_parts[3:]
    #    ('asdf', '')
    suffix = "/".join(request.url.raw_parts[BASEPATH_INDEX:])

    # TODO: check request.query to storage! unsafe!?
    url = (endpoint / suffix).with_query(request.query).update_query(user_id=userid)
    return url


async def _request_storage(request: web.Request, method: str, **kwargs):
    await extract_and_validate(request)

    url = _resolve_storage_url(request)
    # _token_data, _token_secret = _get_token_key_and_secret(request)

    body = None
    if request.can_read_body:
        body = await request.json()

    session = get_client_session(request.app)
    async with session.request(
        method.upper(), url, ssl=False, json=body, **kwargs
    ) as resp:
        payload = await resp.json()
        return payload


async def safe_unwrap(
    resp: ClientResponse,
) -> Tuple[Optional[Union[Dict[str, Any], List[Dict[str, Any]]]], Optional[Dict]]:
    if resp.status != 200:
        body = await resp.text()
        raise web.HTTPException(reason=f"Unexpected response: '{body}'")

    payload = await resp.json()
    if not isinstance(payload, dict):
        raise web.HTTPException(reason=f"Did not receive a dict: '{payload}'")

    data, error = unwrap_envelope(payload)

    return data, error


def extract_link(data: Optional[Dict]) -> str:
    if data is None or "link" not in data:
        raise web.HTTPException(reason=f"No url found in response: '{data}'")

    return data["link"]


# ---------------------------------------------------------------------


@login_required
@permission_required("storage.files.*")
async def get_storage_locations(request: web.Request):
    payload = await _request_storage(request, "GET")
    return payload


@login_required
@permission_required("storage.files.*")
async def get_datasets_metadata(request: web.Request):
    payload = await _request_storage(request, "GET")
    return payload


@login_required
@permission_required("storage.files.*")
async def get_files_metadata(request: web.Request):
    payload = await _request_storage(request, "GET")
    return payload


@login_required
@permission_required("storage.files.*")
async def get_files_metadata_dataset(request: web.Request):
    payload = await _request_storage(request, "GET")
    return payload


@login_required
@permission_required("storage.files.*")
async def get_file_metadata(request: web.Request):
    payload = await _request_storage(request, "GET")
    return payload


@login_required
@permission_required("storage.files.*")
async def update_file_meta_data(request: web.Request):
    raise NotImplementedError
    # payload = await _request_storage(request, 'PATCH' or 'PUT'???) See projects
    # return payload


@login_required
@permission_required("storage.files.*")
async def download_file(request: web.Request):
    payload = await _request_storage(request, "GET")
    return payload


@login_required
@permission_required("storage.files.*")
async def upload_file(request: web.Request):
    payload = await _request_storage(request, "PUT")
    file_upload_schema = FileUploadSchema.parse_obj(
        safe_unwrap(payload.get("data", {}))
    )
    file_upload_schema.links.complete_upload = parse_obj_as(
        AnyUrl,
        URL(file_upload_schema.links.complete_upload).with_path(
            f"/storage/{file_upload_schema.links.complete_upload.path}"
        ),
    )
    file_upload_schema.links.abort_upload = parse_obj_as(
        AnyUrl,
        URL(file_upload_schema.links.abort_upload).with_path(
            f"/storage/{file_upload_schema.links.abort_upload.path}"
        ),
    )

    return {"data": jsonable_encoder(file_upload_schema)}


@login_required
@permission_required("storage.files.*")
async def complete_upload_file(request: web.Request):
    payload = await _request_storage(request, "POST")
    return payload


@login_required
@permission_required("storage.files.*")
async def is_completed_upload_file(request: web.Request):
    payload = await _request_storage(request, "POST")
    return payload


@login_required
@permission_required("storage.files.*")
async def delete_file(request: web.Request):
    payload = await _request_storage(request, "DELETE")
    return payload


@login_required
@permission_required("storage.files.sync")
async def synchronise_meta_data_table(request: web.Request):
    payload = await _request_storage(request, "POST")
    return payload


async def get_storage_locations_for_user(
    app: web.Application, user_id: int
) -> List[Dict[str, Any]]:
    session = get_client_session(app)

    url: URL = _get_base_storage_url(app) / "locations"
    params = dict(user_id=user_id)
    async with session.get(url, ssl=False, params=params) as resp:
        data, _ = cast(List[Dict[str, Any]], await safe_unwrap(resp))
        return data


async def get_project_files_metadata(
    app: web.Application, location_id: str, uuid_filter: str, user_id: int
) -> List[Dict[str, Any]]:
    session = get_client_session(app)

    url: URL = (
        _get_base_storage_url(app) / "locations" / location_id / "files" / "metadata"
    )
    params = dict(user_id=user_id, uuid_filter=uuid_filter)
    async with session.get(url, ssl=False, params=params) as resp:
        data, _ = await safe_unwrap(resp)

        if data is None:
            raise web.HTTPException(reason=f"No url found in response: '{data}'")
        if not isinstance(data, list):
            raise web.HTTPException(
                reason=f"No list payload received as data: '{data}'"
            )

        return data


async def get_file_download_url(
    app: web.Application, location_id: str, file_id: str, user_id: int
) -> str:
    session = get_client_session(app)

    url: URL = (
        _get_base_storage_url(app)
        / "locations"
        / location_id
        / "files"
        / urllib.parse.quote(file_id, safe="")
    )
    params = dict(user_id=user_id)
    async with session.get(url, ssl=False, params=params) as resp:
        data, _ = await safe_unwrap(resp)
        return extract_link(data)


async def get_file_upload_url(
    app: web.Application, location_id: str, file_id: str, user_id: int
) -> str:
    session = get_client_session(app)

    url: URL = (
        _get_base_storage_url(app)
        / "locations"
        / location_id
        / "files"
        / urllib.parse.quote(file_id, safe="")
    )
    params = dict(user_id=user_id)
    async with session.put(url, ssl=False, params=params) as resp:
        data, _ = await safe_unwrap(resp)
    file_upload_schema = FileUploadSchema.parse_obj(data)
    assert file_upload_schema.urls  # nosec
    return file_upload_schema.urls[0]


async def complete_file_upload(
    app: web.Application,
    location_id: str,
    file_id: str,
    user_id: UserID,
    parts: list[UploadedPart],
) -> AnyUrl:
    session = get_client_session(app)

    url: URL = (
        _get_base_storage_url(app)
        / "locations"
        / location_id
        / "files"
        / f"{urllib.parse.quote(file_id, safe='')}:complete"
    )
    params = dict(user_id=user_id)
    async with session.post(
        url,
        ssl=False,
        params=params,
        json=FileUploadCompletionBody.construct(parts=parts),
    ) as resp:
        data, _ = await safe_unwrap(resp)
    state_url = parse_obj_as(AnyUrl, data.get("links", {}).get("state", None))
    return state_url
