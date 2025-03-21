import asyncio
import logging
from typing import Protocol, cast

from aiohttp import web
from models_library.api_schemas_webserver.permalinks import ProjectPermalink
from models_library.projects import ProjectID

from .exceptions import PermalinkFactoryError, PermalinkNotAllowedError
from .models import ProjectDict

_PROJECT_PERMALINK = f"{__name__}"
_logger = logging.getLogger(__name__)


class CreateLinkCoroutine(Protocol):
    async def __call__(
        self, request: web.Request, project_uuid: ProjectID
    ) -> ProjectPermalink:
        ...


def register_factory(app: web.Application, factory_coro: CreateLinkCoroutine):
    if _create := app.get(_PROJECT_PERMALINK):
        msg = f"Permalink factory can only be set once: registered {_create}"
        raise PermalinkFactoryError(msg)
    app[_PROJECT_PERMALINK] = factory_coro


def _get_factory(app: web.Application) -> CreateLinkCoroutine:
    if _create := app.get(_PROJECT_PERMALINK):
        return cast(CreateLinkCoroutine, _create)

    msg = "Undefined permalink factory. Check plugin initialization."
    raise PermalinkFactoryError(msg)


_PERMALINK_CREATE_TIMEOUT_S = 2


async def _create_permalink(
    request: web.Request, project_uuid: ProjectID
) -> ProjectPermalink:
    create_coro: CreateLinkCoroutine = _get_factory(request.app)

    try:
        permalink: ProjectPermalink = await asyncio.wait_for(
            create_coro(request=request, project_uuid=project_uuid),
            timeout=_PERMALINK_CREATE_TIMEOUT_S,
        )
        return permalink
    except TimeoutError as err:
        msg = f"Permalink factory callback '{create_coro}' timed out after {_PERMALINK_CREATE_TIMEOUT_S} secs"
        raise PermalinkFactoryError(msg) from err


async def update_or_pop_permalink_in_project(
    request: web.Request, project: ProjectDict
) -> ProjectPermalink | None:
    """Updates permalink entry in project

    Creates a permalink for this project and assigns it to project["permalink"]

    If fails, it pops it from project (so it is not set in the pydantic model. SEE ProjectGet.permalink)
    """
    try:
        permalink = await _create_permalink(request, project_uuid=project["uuid"])

        assert permalink  # nosec
        project["permalink"] = permalink

        return permalink

    except (PermalinkNotAllowedError, PermalinkFactoryError):
        project.pop("permalink", None)

    return None


async def aggregate_permalink_in_project(
    request: web.Request, project: ProjectDict
) -> ProjectDict:
    """
    Adapter to use in parallel aggregation of fields in a project dataset
    """
    await update_or_pop_permalink_in_project(request, project)
    return project


__all__: tuple[str, ...] = ("ProjectPermalink",)
