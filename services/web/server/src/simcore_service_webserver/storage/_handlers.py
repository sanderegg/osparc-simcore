"""Handlers exposed by storage subsystem

Mostly resolves and redirect to storage API
"""

import logging
import urllib.parse
from typing import Any, Final, NamedTuple
from urllib.parse import quote, unquote

from aiohttp import ClientTimeout, web
from models_library.projects_nodes_io import LocationID
from models_library.storage_schemas import (
    FileUploadCompleteResponse,
    FileUploadCompletionBody,
    FileUploadSchema,
    LinkType,
)
from models_library.utils.fastapi_encoders import jsonable_encoder
from pydantic import AnyUrl, BaseModel, ByteSize, TypeAdapter
from servicelib.aiohttp import status
from servicelib.aiohttp.client_session import get_client_session
from servicelib.aiohttp.requests_validation import (
    parse_request_body_as,
    parse_request_path_parameters_as,
    parse_request_query_parameters_as,
)
from servicelib.aiohttp.rest_responses import create_data_response
from servicelib.common_headers import X_FORWARDED_PROTO
from servicelib.request_keys import RQT_USERID_KEY
from servicelib.rest_responses import unwrap_envelope
from yarl import URL

from .._meta import API_VTAG
from ..login.decorators import login_required
from ..security.decorators import permission_required
from .schemas import StorageFileIDStr
from .settings import StorageSettings, get_plugin_settings

log = logging.getLogger(__name__)


def _get_base_storage_url(app: web.Application) -> URL:
    settings: StorageSettings = get_plugin_settings(app)
    return URL(settings.base_url, encoded=True)


def _get_storage_vtag(app: web.Application) -> str:
    settings: StorageSettings = get_plugin_settings(app)
    storage_prefix: str = settings.STORAGE_VTAG
    return storage_prefix


def _to_storage_url(request: web.Request) -> URL:
    """Converts web-api url to storage-api url"""
    userid = request[RQT_USERID_KEY]

    # storage service API endpoint
    url = _get_base_storage_url(request.app)

    basepath_index = 3
    # strip basepath from webserver API path (i.e. webserver api version)
    # >>> URL('http://storage:1234/v5/storage/asdf/').raw_parts[3:]
    suffix = "/".join(request.url.parts[basepath_index:])
    # we need to quote anything before the column, but not the column
    if (column_index := suffix.find(":")) > 0:
        fastapi_encoded_suffix = (
            urllib.parse.quote(suffix[:column_index], safe="/") + suffix[column_index:]
        )
    else:
        fastapi_encoded_suffix = urllib.parse.quote(suffix, safe="/")

    return (
        url.joinpath(fastapi_encoded_suffix, encoded=True)
        .with_query(request.query)
        .update_query(user_id=userid)
    )


def _from_storage_url(
    request: web.Request, storage_url: AnyUrl, url_encode: str | None
) -> AnyUrl:
    """Converts storage-api url to web-api url"""
    assert storage_url.path  # nosec

    prefix = f"/{_get_storage_vtag(request.app)}"
    converted_url = str(
        request.url.with_path(
            f"/v0/storage{storage_url.path.removeprefix(prefix)}", encoded=True
        ).with_scheme(request.headers.get(X_FORWARDED_PROTO, request.url.scheme))
    )
    if url_encode:
        converted_url = converted_url.replace(
            url_encode, quote(unquote(url_encode), safe="")
        )

    webserver_url: AnyUrl = TypeAdapter(AnyUrl).validate_python(f"{converted_url}")
    return webserver_url


class _ResponseTuple(NamedTuple):
    payload: Any
    status_code: int


async def _forward_request_to_storage(
    request: web.Request, method: str, body: dict[str, Any] | None = None, **kwargs
) -> _ResponseTuple:
    url = _to_storage_url(request)
    session = get_client_session(request.app)

    async with session.request(
        method.upper(), url, ssl=False, json=body, **kwargs
    ) as resp:
        if resp.status >= status.HTTP_400_BAD_REQUEST:
            raise web.HTTPException(reason=await resp.text())
        payload = await resp.json()
        return _ResponseTuple(payload=payload, status_code=resp.status)


# ---------------------------------------------------------------------

routes = web.RouteTableDef()
_path_prefix = f"/{API_VTAG}/storage/locations"


@routes.get(_path_prefix, name="list_storage_locations")
@login_required
@permission_required("storage.files.*")
async def list_storage_locations(request: web.Request) -> web.Response:
    payload, resp_status = await _forward_request_to_storage(request, "GET", body=None)
    return create_data_response(payload, status=resp_status)


@routes.get(_path_prefix + "/{location_id}/datasets", name="list_datasets_metadata")
@login_required
@permission_required("storage.files.*")
async def list_datasets_metadata(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID

    parse_request_path_parameters_as(_PathParams, request)

    payload, resp_status = await _forward_request_to_storage(request, "GET", body=None)
    return create_data_response(payload, status=resp_status)


@routes.get(
    _path_prefix + "/{location_id}/files/metadata",
    name="get_files_metadata",
)
@login_required
@permission_required("storage.files.*")
async def get_files_metadata(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID

    parse_request_path_parameters_as(_PathParams, request)

    class _QueryParams(BaseModel):
        uuid_filter: str = ""
        expand_dirs: bool = True

    parse_request_query_parameters_as(_QueryParams, request)

    payload, resp_status = await _forward_request_to_storage(request, "GET", body=None)
    return create_data_response(payload, status=resp_status)


_LIST_ALL_DATASETS_TIMEOUT_S: Final[int] = 60


@routes.get(
    _path_prefix + "/{location_id}/datasets/{dataset_id}/metadata",
    name="list_dataset_files_metadata",
)
@login_required
@permission_required("storage.files.*")
async def list_dataset_files_metadata(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID
        dataset_id: str

    parse_request_path_parameters_as(_PathParams, request)

    class _QueryParams(BaseModel):
        uuid_filter: str = ""
        expand_dirs: bool = True

    parse_request_query_parameters_as(_QueryParams, request)

    payload, resp_status = await _forward_request_to_storage(
        request,
        "GET",
        body=None,
        timeout=ClientTimeout(total=_LIST_ALL_DATASETS_TIMEOUT_S),
    )
    return create_data_response(payload, status=resp_status)


@routes.get(
    _path_prefix + "/{location_id}/files/{file_id}/metadata",
    name="get_file_metadata",
)
@login_required
@permission_required("storage.files.*")
async def get_file_metadata(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID
        file_id: StorageFileIDStr

    parse_request_path_parameters_as(_PathParams, request)

    payload, resp_status = await _forward_request_to_storage(request, "GET")
    return create_data_response(payload, status=resp_status)


@routes.get(
    _path_prefix + "/{location_id}/files/{file_id}",
    name="download_file",
)
@login_required
@permission_required("storage.files.*")
async def download_file(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID
        file_id: StorageFileIDStr

    parse_request_path_parameters_as(_PathParams, request)

    class _QueryParams(BaseModel):
        link_type: LinkType = LinkType.PRESIGNED

    parse_request_query_parameters_as(_QueryParams, request)

    payload, resp_status = await _forward_request_to_storage(request, "GET", body=None)
    return create_data_response(payload, status=resp_status)


@routes.put(
    _path_prefix + "/{location_id}/files/{file_id}",
    name="upload_file",
)
@login_required
@permission_required("storage.files.*")
async def upload_file(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID
        file_id: StorageFileIDStr

    path_params = parse_request_path_parameters_as(_PathParams, request)

    class _QueryParams(BaseModel):
        file_size: ByteSize | None = None
        link_type: LinkType = LinkType.PRESIGNED
        is_directory: bool = False

    parse_request_query_parameters_as(_QueryParams, request)

    payload, resp_status = await _forward_request_to_storage(request, "PUT", body=None)
    data, _ = unwrap_envelope(payload)
    file_upload_schema = FileUploadSchema.model_validate(data)
    # NOTE: since storage is fastapi-based it returns file_id not url encoded and aiohttp does not like it
    # /v0/locations/{location_id}/files/{file_id:non-encoded-containing-slashes}:complete --> /v0/storage/locations/{location_id}/files/{file_id:non-encode}:complete
    storage_encoded_file_id = quote(path_params.file_id, safe="/")
    file_upload_schema.links.complete_upload = _from_storage_url(
        request,
        file_upload_schema.links.complete_upload,
        url_encode=storage_encoded_file_id,
    )
    file_upload_schema.links.abort_upload = _from_storage_url(
        request,
        file_upload_schema.links.abort_upload,
        url_encode=storage_encoded_file_id,
    )
    return create_data_response(
        jsonable_encoder(file_upload_schema), status=resp_status
    )


@routes.post(
    _path_prefix + "/{location_id}/files/{file_id}:complete",
    name="complete_upload_file",
)
@login_required
@permission_required("storage.files.*")
async def complete_upload_file(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID
        file_id: StorageFileIDStr

    path_params = parse_request_path_parameters_as(_PathParams, request)
    body_item = await parse_request_body_as(FileUploadCompletionBody, request)

    payload, resp_status = await _forward_request_to_storage(
        request, "POST", body=body_item.model_dump()
    )
    data, _ = unwrap_envelope(payload)
    storage_encoded_file_id = quote(path_params.file_id, safe="/")
    file_upload_complete = FileUploadCompleteResponse.model_validate(data)
    file_upload_complete.links.state = _from_storage_url(
        request, file_upload_complete.links.state, url_encode=storage_encoded_file_id
    )
    return create_data_response(
        jsonable_encoder(file_upload_complete), status=resp_status
    )


@routes.post(
    _path_prefix + "/{location_id}/files/{file_id}:abort",
    name="abort_upload_file",
)
@login_required
@permission_required("storage.files.*")
async def abort_upload_file(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID
        file_id: StorageFileIDStr

    parse_request_path_parameters_as(_PathParams, request)

    payload, resp_status = await _forward_request_to_storage(request, "POST", body=None)
    return create_data_response(payload, status=resp_status)


@routes.post(
    _path_prefix + "/{location_id}/files/{file_id}:complete/futures/{future_id}",
    name="is_completed_upload_file",
)
@login_required
@permission_required("storage.files.*")
async def is_completed_upload_file(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID
        file_id: StorageFileIDStr
        future_id: str

    parse_request_path_parameters_as(_PathParams, request)

    payload, resp_status = await _forward_request_to_storage(request, "POST", body=None)
    return create_data_response(payload, status=resp_status)


@routes.delete(
    _path_prefix + "/{location_id}/files/{file_id}",
    name="delete_file",
)
@login_required
@permission_required("storage.files.*")
async def delete_file(request: web.Request) -> web.Response:
    class _PathParams(BaseModel):
        location_id: LocationID
        file_id: StorageFileIDStr

    parse_request_path_parameters_as(_PathParams, request)

    payload, resp_status = await _forward_request_to_storage(
        request, "DELETE", body=None
    )
    return create_data_response(payload, status=resp_status)
