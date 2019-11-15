import asyncio
import logging

from aiohttp import web

from . import get_event_registry
from .types import SignalType

log = logging.getLogger(__name__)

async def emit(event: SignalType, *args, **kwargs, app: web.Application):
    event_registry = get_event_registry(app)
    if not event_registry[event]:
        return

    coroutines = [observer(*args, **kwargs) for observer in event_registry[event]]
    # all coroutine called in //
    await asyncio.gather(*coroutines, return_exceptions=True)
