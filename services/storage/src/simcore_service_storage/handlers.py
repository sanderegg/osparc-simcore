import asyncio
import json
import logging
import urllib.parse
from contextlib import contextmanager
from typing import Any, Optional

from aiohttp import web
from aiohttp.web import RouteTableDef
from models_library.api_schemas_storage import (
    FileUploadCompletionBody,
    FileUploadLinks,
    FileUploadSchema,
    LinkType,
)
from models_library.projects import ProjectID
from models_library.utils.fastapi_encoders import jsonable_encoder
from pydantic import AnyUrl, ValidationError, parse_obj_as
from servicelib.aiohttp.application_keys import APP_CONFIG_KEY
from servicelib.aiohttp.requests_validation import (
    parse_request_body_as,
    parse_request_path_parameters_as,
    parse_request_query_parameters_as,
)
from servicelib.mimetype_constants import MIMETYPE_APPLICATION_JSON
from settings_library.s3 import S3Settings
from simcore_service_storage.exceptions import FileMetaDataNotFoundError

# Exclusive for simcore-s3 storage -----------------------
from . import sts
from ._meta import api_vtag
from .access_layer import InvalidFileIdentifier
from .constants import APP_DSM_KEY, DATCORE_STR, SIMCORE_S3_ID, SIMCORE_S3_STR
from .db_tokens import get_api_token_and_secret
from .dsm import DataStorageManager, DatCoreApiToken, UploadLinks
from .models import (
    CopyAsSoftLinkParams,
    DeleteFolderQueryParams,
    FileDownloadQueryParams,
    FileMetaDataEx,
    FilePathIsUploadCompletedParams,
    FilePathParams,
    FilesMetadataDatasetPathParams,
    FilesMetadataQueryParams,
    FileUploadQueryParams,
    FoldersBody,
    LocationPathParams,
    SearchFilesQueryParams,
    SimcoreS3FoldersParams,
    SoftCopyBody,
    StorageQueryParamsBase,
    SyncMetadataQueryParams,
)
from .settings import Settings
from .utils import create_upload_completion_task_name, get_location_from_id

log = logging.getLogger(__name__)

routes = RouteTableDef()

UPLOAD_TASKS_KEY = f"{__name__}.upload_tasks"


async def _prepare_storage_manager(
    params: dict, query: dict, request: web.Request
) -> DataStorageManager:
    # FIXME: scope properly, either request or app level!!
    # Notice that every request is changing tokens!
    # I would rather store tokens in request instead of in dsm
    # or creating an different instance of dsm per request

    INIT_STR = "init"
    dsm: DataStorageManager = request.app[APP_DSM_KEY]
    user_id = query.get("user_id")
    location_id = params.get("location_id")
    location = (
        get_location_from_id(location_id) if location_id is not None else INIT_STR
    )

    if user_id and location in (INIT_STR, DATCORE_STR):
        # TODO: notify from db instead when tokens changed, then invalidate resource which enforces
        # re-query when needed.

        # updates from db
        token_info = await get_api_token_and_secret(request.app, int(user_id))
        if all(token_info):
            dsm.datcore_tokens[user_id] = DatCoreApiToken(*token_info)
        else:
            dsm.datcore_tokens.pop(user_id, None)
    return dsm


@contextmanager
def handle_storage_errors():
    """Basic policies to translate low-level errors into HTTP errors"""
    # TODO: include _prepare_storage_manager?
    # TODO: middleware? decorator?
    try:

        yield

    except InvalidFileIdentifier as err:
        raise web.HTTPUnprocessableEntity(
            reason=f"{err} is an invalid file identifier"
        ) from err
    except FileMetaDataNotFoundError as err:
        raise web.HTTPNotFound(reason=f"{err}") from err
    except ValidationError as err:
        raise web.HTTPUnprocessableEntity(reason=f"{err}")


# HANDLERS ---------------------------------------------------


@routes.get(f"/{api_vtag}/locations", name="get_storage_locations")  # type: ignore
async def get_storage_locations(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    log.debug(
        "received call to get_storage_locations with %s",
        f"{query_params=}",
    )

    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            {}, jsonable_encoder(query_params), request
        )
        locs = await dsm.locations(query_params.user_id)

        return {"error": None, "data": locs}


@routes.get(f"/{api_vtag}/locations/{{location_id}}/datasets")  # type: ignore
async def get_datasets_metadata(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    path_params = parse_request_path_parameters_as(LocationPathParams, request)
    log.debug(
        "received call to get_datasets_metadata with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )
        data = await dsm.list_datasets(
            query_params.user_id, get_location_from_id(path_params.location_id)
        )
        return {"error": None, "data": data}


@routes.get(f"/{api_vtag}/locations/{{location_id}}/files/metadata")  # type: ignore
async def get_files_metadata(request: web.Request):
    query_params = parse_request_query_parameters_as(FilesMetadataQueryParams, request)
    path_params = parse_request_path_parameters_as(LocationPathParams, request)
    log.debug(
        "received call to get_files_metadata with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )
        data = await dsm.list_files(
            user_id=query_params.user_id,
            location=get_location_from_id(path_params.location_id),
            uuid_filter=query_params.uuid_filter,
        )
        data_as_dict = []
        for d in data:
            log.info("DATA %s", jsonable_encoder(d.fmd))
            data_as_dict.append({**jsonable_encoder(d.fmd), "parent_id": d.parent_id})

        return {"error": None, "data": data_as_dict}


@routes.get(f"/{api_vtag}/locations/{{location_id}}/datasets/{{dataset_id}}/metadata")  # type: ignore
async def get_files_metadata_dataset(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    path_params = parse_request_path_parameters_as(
        FilesMetadataDatasetPathParams, request
    )
    log.debug(
        "received call to get_files_metadata_dataset with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )
        data = await dsm.list_files_dataset(
            user_id=query_params.user_id,
            location=get_location_from_id(path_params.location_id),
            dataset_id=path_params.dataset_id,
        )
        data_as_dict = []
        for d in data:
            log.info("DATA %s", jsonable_encoder(d.fmd))
            data_as_dict.append({**jsonable_encoder(d.fmd), "parent_id": d.parent_id})

        return {"error": None, "data": data_as_dict}


@routes.get(
    f"/{api_vtag}/locations/{{location_id}}/files/{{file_id}}/metadata",
    name="get_file_metadata",
)  # type: ignore
async def get_file_metadata(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    path_params = parse_request_path_parameters_as(FilePathParams, request)
    log.debug(
        "received call to get_files_metadata_dataset with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )
        data = await dsm.list_file(
            user_id=query_params.user_id,
            location=get_location_from_id(path_params.location_id),
            file_uuid=path_params.file_id,
        )
        # when no metadata is found
        if data is None:
            # NOTE: This is what happens Larry... data must be an empty {} or else some old
            # dynamic services will FAIL (sic)
            return {"error": "No result found", "data": {}}

        return {
            "error": None,
            "data": {**jsonable_encoder(data.fmd), "parent_id": data.parent_id},
        }


@routes.post(f"/{api_vtag}/locations/{{location_id}}:sync")  # type: ignore
async def synchronise_meta_data_table(request: web.Request):
    query_params = parse_request_query_parameters_as(SyncMetadataQueryParams, request)
    path_params = parse_request_path_parameters_as(LocationPathParams, request)
    log.debug(
        "received call to synchronise_meta_data_table with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )
        sync_results: dict[str, Any] = {
            "removed": [],
        }
        sync_coro = dsm.synchronise_meta_data_table(
            get_location_from_id(path_params.location_id), query_params.dry_run
        )

        if query_params.fire_and_forget:
            settings: Settings = request.app[APP_CONFIG_KEY]

            async def _go():
                timeout = settings.STORAGE_SYNC_METADATA_TIMEOUT
                try:
                    result = await asyncio.wait_for(sync_coro, timeout=timeout)
                    log.info(
                        "Sync metadata table completed: %d entries removed",
                        len(result.get("removed", [])),
                    )
                except asyncio.TimeoutError:
                    log.error("Sync metadata table timed out (%s seconds)", timeout)

            asyncio.create_task(_go(), name="fire&forget sync_task")
        else:
            sync_results = await sync_coro

        sync_results["fire_and_forget"] = query_params.fire_and_forget
        sync_results["dry_run"] = query_params.dry_run

        return {"error": None, "data": sync_results}


@routes.patch(f"/{api_vtag}/locations/{{location_id}}/files/{{file_id}}/metadata")  # type: ignore
async def update_file_meta_data(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    path_params = parse_request_path_parameters_as(FilePathParams, request)
    log.debug(
        "received call to update_file_meta_data with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )

        data: Optional[FileMetaDataEx] = await dsm.update_metadata(
            file_uuid=path_params.file_id, user_id=query_params.user_id
        )
        if data is None:
            raise web.HTTPNotFound(
                reason=f"Could not update metadata for {path_params.file_id}"
            )

        return {
            "error": None,
            "data": {**jsonable_encoder(data.fmd), "parent_id": data.parent_id},
        }


@routes.get(f"/{api_vtag}/locations/{{location_id}}/files/{{file_id}}")  # type: ignore
async def download_file(request: web.Request):
    query_params = parse_request_query_parameters_as(FileDownloadQueryParams, request)
    path_params = parse_request_path_parameters_as(FilePathParams, request)
    log.debug(
        "received call to download_file with %s",
        f"{path_params=}, {query_params=}",
    )

    with handle_storage_errors():
        if (
            path_params.location_id != SIMCORE_S3_ID
            and query_params.link_type == LinkType.S3
        ):
            raise web.HTTPPreconditionFailed(
                reason=f"Only allowed to fetch s3 link for '{SIMCORE_S3_STR}'"
            )

        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )

        if get_location_from_id(path_params.location_id) == SIMCORE_S3_STR:
            link = await dsm.download_link_s3(
                path_params.file_id, query_params.user_id, query_params.link_type
            )
        else:
            link = await dsm.download_link_datcore(
                query_params.user_id, path_params.file_id
            )

        return {"error": None, "data": {"link": link}}


@routes.put(f"/{api_vtag}/locations/{{location_id}}/files/{{file_id}}")  # type: ignore
async def upload_file(request: web.Request):
    query_params = parse_request_query_parameters_as(FileUploadQueryParams, request)
    path_params = parse_request_path_parameters_as(FilePathParams, request)

    log.debug(
        "received call to upload_file with %s",
        f"{path_params=}, {query_params=}",
    )

    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )

        links: UploadLinks = await dsm.create_upload_links(
            user_id=query_params.user_id,
            file_uuid=path_params.file_id,
            link_type=query_params.link_type,
            file_size_bytes=query_params.file_size,
        )

        abort_url = request.url.join(
            request.app.router["abort_upload_file"]
            .url_for(
                location_id=f"{path_params.location_id}",
                file_id=urllib.parse.quote(path_params.file_id, safe=""),
            )
            .with_query(user_id=query_params.user_id)
        )
        complete_url = request.url.join(
            request.app.router["complete_upload_file"]
            .url_for(
                location_id=f"{path_params.location_id}",
                file_id=urllib.parse.quote(path_params.file_id, safe=""),
            )
            .with_query(user_id=query_params.user_id)
        )
        response = FileUploadSchema(
            chunk_size=links.chunk_size,
            urls=links.urls,
            links=FileUploadLinks(
                abort_upload=parse_obj_as(AnyUrl, f"{abort_url}"),
                complete_upload=parse_obj_as(
                    AnyUrl,
                    f"{complete_url}",
                ),
            ),
        )

    return {"data": json.loads(response.json(by_alias=True))}


@routes.post(f"/{api_vtag}/locations/{{location_id}}/files/{{file_id}}:abort")  # type: ignore
async def abort_upload_file(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    path_params = parse_request_path_parameters_as(FilePathParams, request)
    log.debug(
        "received call to abort_upload_file with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )
        await dsm.abort_upload(path_params.file_id, query_params.user_id)
    return web.HTTPNoContent(content_type=MIMETYPE_APPLICATION_JSON)


@routes.post(f"/{api_vtag}/locations/{{location_id}}/files/{{file_id}}:complete")  # type: ignore
async def complete_upload_file(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    path_params = parse_request_path_parameters_as(FilePathParams, request)
    body = await parse_request_body_as(FileUploadCompletionBody, request)
    log.debug(
        "received call to complete_upload_file with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )
        # NOTE: completing a multipart upload on AWS can take up to several minutes
        # therefore we wait a bit to see if it completes fast and return a 204
        # if it returns slow we return a 202 - Accepted, the client will have to check later
        # for completeness

        # TODO: check how BackgroundTask in fastapi is done. this would be a nice addition to make this kind
        # of constructions
        task = asyncio.create_task(
            dsm.complete_upload(path_params.file_id, query_params.user_id, body.parts),
            name=create_upload_completion_task_name(
                query_params.user_id, path_params.file_id
            ),
        )
        request.app[UPLOAD_TASKS_KEY][task.get_name()] = task
        complete_task_state_url = request.url.join(
            request.app.router["is_completed_upload_file"]
            .url_for(
                location_id=f"{path_params.location_id}",
                file_id=urllib.parse.quote(path_params.file_id, safe=""),
                future_id=task.get_name(),
            )
            .with_query(user_id=query_params.user_id)
        )

        return web.json_response(
            status=web.HTTPAccepted.status_code,
            headers={"Content-Location": f"{complete_task_state_url}"},
            data={"data": {"links": {"state": f"{complete_task_state_url}"}}},
        )


@routes.post(f"/{api_vtag}/locations/{{location_id}}/files/{{file_id}}:complete/futures/{{future_id}}", name="is_completed_upload_file")  # type: ignore
async def is_completed_upload_file(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    path_params = parse_request_path_parameters_as(
        FilePathIsUploadCompletedParams, request
    )
    log.debug(
        "received call to is completed upload file with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        # NOTE: completing a multipart upload on AWS can take up to several minutes
        # therefore we wait a bit to see if it completes fast and return a 204
        # if it returns slow we return a 202 - Accepted, the client will have to check later
        # for completeness
        task_name = create_upload_completion_task_name(
            query_params.user_id, path_params.file_id
        )
        assert task_name == path_params.future_id  # nosec
        # first check if the task is in the app
        if task := request.app[UPLOAD_TASKS_KEY].get(task_name):
            if task.done():
                task.result()
                request.app[UPLOAD_TASKS_KEY].pop(task_name)
                return web.json_response(
                    status=web.HTTPOk.status_code, data={"data": {"state": "ok"}}
                )
            # the task is still running
            return web.json_response(
                status=web.HTTPOk.status_code, data={"data": {"state": "nok"}}
            )
        # there is no task, either wrong call or storage was restarted
        # we try to get the file to see if it exists in S3
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )
        if await dsm.list_file(
            user_id=query_params.user_id,
            location=get_location_from_id(path_params.location_id),
            file_uuid=path_params.file_id,
        ):
            return web.json_response(
                status=web.HTTPOk.status_code, data={"data": {"state": "ok"}}
            )
    raise web.HTTPNotFound(
        reason="Not found. Upload could not be completed. Please try again and contact support if it fails again."
    )


@routes.delete(f"/{api_vtag}/locations/{{location_id}}/files/{{file_id}}")  # type: ignore
async def delete_file(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    path_params = parse_request_path_parameters_as(FilePathParams, request)
    log.debug(
        "received call to delete_file with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            jsonable_encoder(path_params), jsonable_encoder(query_params), request
        )
        await dsm.delete_file(
            user_id=query_params.user_id,
            location=get_location_from_id(path_params.location_id),
            file_uuid=path_params.file_id,
        )

        return web.HTTPNoContent(content_type=MIMETYPE_APPLICATION_JSON)


@routes.post(f"/{api_vtag}/simcore-s3:access")  # type: ignore
async def get_or_create_temporary_s3_access(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    log.debug(
        "received call to get_or_create_temporary_s3_access with %s",
        f"{query_params=}",
    )
    with handle_storage_errors():
        s3_settings: S3Settings = await sts.get_or_create_temporary_token_for_user(
            request.app, query_params.user_id
        )
        return {"data": s3_settings.dict()}


@routes.post(f"/{api_vtag}/simcore-s3/folders", name="copy_folders_from_project")  # type: ignore
async def create_folders_from_project(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    body = await parse_request_body_as(FoldersBody, request)
    log.debug(
        "received call to create_folders_from_project with %s",
        f"{body=}, {query_params=}",
    )

    assert set(body.nodes_map.keys()) == set(body.source["workbench"].keys())  # nosec
    assert set(body.nodes_map.values()) == set(
        body.destination["workbench"].keys()
    )  # nosec

    # TODO: validate project with jsonschema instead??
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            params={"location_id": SIMCORE_S3_ID},
            query=jsonable_encoder(query_params),
            request=request,
        )
        await dsm.deep_copy_project_simcore_s3(
            query_params.user_id, body.source, body.destination, body.nodes_map
        )

    raise web.HTTPCreated(
        text=json.dumps(body.destination), content_type=MIMETYPE_APPLICATION_JSON
    )


@routes.delete(f"/{api_vtag}/simcore-s3/folders/{{folder_id}}")  # type: ignore
async def delete_folders_of_project(request: web.Request):
    query_params = parse_request_query_parameters_as(DeleteFolderQueryParams, request)
    path_params = parse_request_path_parameters_as(SimcoreS3FoldersParams, request)
    log.debug(
        "received call to delete_folders_of_project with %s",
        f"{path_params=}, {query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            params={"location_id": SIMCORE_S3_ID},
            query=jsonable_encoder(query_params),
            request=request,
        )
        await dsm.delete_project_simcore_s3(
            query_params.user_id,
            ProjectID(path_params.folder_id),
            query_params.node_id,
        )

    raise web.HTTPNoContent(content_type=MIMETYPE_APPLICATION_JSON)


@routes.post(f"/{api_vtag}/simcore-s3/files/metadata:search")  # type: ignore
async def search_files_starting_with(request: web.Request):
    query_params = parse_request_query_parameters_as(SearchFilesQueryParams, request)
    log.debug(
        "received call to search_files_starting_with with %s",
        f"{query_params=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            params={"location_id": SIMCORE_S3_ID},
            query=jsonable_encoder(query_params),
            request=request,
        )

        data = await dsm.search_files_starting_with(
            query_params.user_id, prefix=query_params.startswith
        )
        log.debug(
            "Found %d files starting with '%s'", len(data), query_params.startswith
        )

        return [{**jsonable_encoder(d.fmd), "parent_id": d.parent_id} for d in data]


@routes.post(f"/{api_vtag}/files/{{file_id}}:soft-copy", name="copy_as_soft_link")  # type: ignore
async def copy_as_soft_link(request: web.Request):
    query_params = parse_request_query_parameters_as(StorageQueryParamsBase, request)
    path_params = parse_request_path_parameters_as(CopyAsSoftLinkParams, request)
    body = await parse_request_body_as(SoftCopyBody, request)
    log.debug(
        "received call to copy_as_soft_link with %s",
        f"{path_params=}, {query_params=}, {body=}",
    )
    with handle_storage_errors():
        dsm = await _prepare_storage_manager(
            params={"location_id": SIMCORE_S3_ID},
            query=jsonable_encoder(query_params),
            request=request,
        )
        file_link = await dsm.create_soft_link(
            query_params.user_id, path_params.file_id, body.link_id
        )

        data = {**jsonable_encoder(file_link.fmd), "parent_id": file_link.parent_id}
        return data
