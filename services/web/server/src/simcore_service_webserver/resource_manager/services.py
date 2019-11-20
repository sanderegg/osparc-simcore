import asyncio
import logging

from aiohttp import web

from ..signals import SignalType, emit, observe
from .config import APP_RESOURCE_MANAGER_TASKS_KEY, get_service_deletion_timeout

log = logging.getLogger(__name__)



# async def mark_service_for_deletion(service_uuid: str, app: web.Application):
#     pass

async def emit_logout_signal(user_id: str, app: web.Application):
    # let's sleep a bit first
    await asyncio.sleep(get_service_deletion_timeout(app))
    await emit(SignalType.SIGNAL_USER_LOGOUT, user_id, app)

@observe(event=SignalType.SIGNAL_USER_DISCONNECT)
async def mark_all_user_services_for_deletion(user_id: str, app: web.Application):
    log.debug("marking services of user %s for deletion...", user_id)
    # create a task that will signal later
    task = asyncio.ensure_future(emit_logout_signal(user_id, app))
    app[APP_RESOURCE_MANAGER_TASKS_KEY].append(task)


# async def mark_all_project_services_for_deletion(project_id: str, app: web.Application):
#     log.info("marking services of project %s for deletion...", project_id)

@observe(event=SignalType.SIGNAL_USER_CONNECT)
async def recover_all_user_services_from_deletion(user_id: str, app: web.Application):
    log.debug("recover services of user %s from scheduled deletion...", user_id)
    tasks = app[APP_RESOURCE_MANAGER_TASKS_KEY]
    for task in tasks:
        task.cancel()
