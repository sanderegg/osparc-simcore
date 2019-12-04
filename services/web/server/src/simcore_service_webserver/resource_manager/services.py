import asyncio
import logging

from aiohttp import web

from ..signals import SignalType, emit, observe
from .config import APP_RESOURCE_MANAGER_TASKS_KEY, get_service_deletion_timeout

log = logging.getLogger(__name__)

async def emit_logout_signal(user_id: str, app: web.Application):
    # let's sleep a bit first
    try:
        await asyncio.sleep(get_service_deletion_timeout(app))
        await emit(SignalType.SIGNAL_USER_LOGOUT, user_id, app)
    except asyncio.CancelledError:
        log.debug("Deletion of services was cancelled")
        raise

@observe(event=SignalType.SIGNAL_USER_DISCONNECT)
async def mark_all_user_services_for_deletion(user_id: str, app: web.Application):
    log.debug("marking services of user %s for deletion...", user_id)
    # create a task that will signal later
    task = asyncio.ensure_future(emit_logout_signal(user_id, app))
    task.type = SignalType.SIGNAL_USER_DISCONNECT
    app[APP_RESOURCE_MANAGER_TASKS_KEY].append(task)


@observe(event=SignalType.SIGNAL_USER_CONNECT)
async def recover_all_user_services_from_deletion(user_id: str, app: web.Application):
    log.debug("recover services of user %s from scheduled deletion...", user_id)
    tasks = app[APP_RESOURCE_MANAGER_TASKS_KEY]
    for task in tasks:
        if task.type is SignalType.SIGNAL_USER_DISCONNECT:
            task.cancel()

async def emit_project_close_signal(user_id: str, project_id: str, app: web.Application):
    # let's sleep a bit first
    try:
        await asyncio.sleep(get_service_deletion_timeout(app))
        await emit(SignalType.SIGNAL_PROJECT_CLOSE, user_id, project_id, app)
    except asyncio.CancelledError:
        log.debug("Deletion of services was cancelled")
        raise

@observe(event=SignalType.SIGNAL_PROJECT_DISCONNECT)
async def mark_all_project_services_for_deletion(user_id: str, project_id: str, app: web.Application):
    log.debug("marking services of user:project %s:%s for deletion...", user_id, project_id)
    # create a task that will signal later
    task = asyncio.ensure_future(emit_project_close_signal(user_id, project_id, app))
    task.type = SignalType.SIGNAL_PROJECT_DISCONNECT
    app[APP_RESOURCE_MANAGER_TASKS_KEY].append(task)


@observe(event=SignalType.SIGNAL_PROJECT_CONNECT)
async def recover_all_project_services_from_deletion(user_id: str, project_id: str, app: web.Application):
    log.debug("recover services of user %s:%s from scheduled deletion...", user_id, project_id)
    tasks = app[APP_RESOURCE_MANAGER_TASKS_KEY]
    for task in tasks:
        if task.type is SignalType.SIGNAL_PROJECT_DISCONNECT:
            task.cancel()