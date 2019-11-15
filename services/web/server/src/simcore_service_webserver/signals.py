import asyncio
import logging
from collections import defaultdict
from enum import Enum
from functools import wraps

log = logging.getLogger(__name__)

event_registry = defaultdict(list)

class SignalName(Enum):
    SIGNAL_USER_CONNECT = 1
    SIGNAL_USER_DISCONNECT = 2


async def emit(event: SignalName, *args, **kwargs):
    if not event_registry[event]:
        return

    coroutines = [observer(*args, **kwargs) for observer in event_registry[event]]
    # all coroutine called in //
    await asyncio.gather(*coroutines, return_exceptions=True)

def observe(event: SignalName):
    def decorator(func):
        if func not in event_registry[event]:
            event_registry[event].append(func)
        @wraps(func)
        def wrapped(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapped
    return decorator
