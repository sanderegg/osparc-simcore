from functools import wraps

from aiohttp import web

from . import get_event_registry
from .types import SignalType


def observe(event: SignalType, app: web.Application):
    def decorator(func):
        event_registry = get_event_registry(app)
        if func not in event_registry[event]:
            event_registry[event].append(func)
        @wraps(func)
        def wrapped(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapped
    return decorator
