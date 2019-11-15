import logging
from collections import defaultdict
from typing import Dict

from aiohttp import web

from .config import APP_EVENTS_REGISTRY_KEY
from .types import SignalType

log = logging.getLogger(__name__)

def setup(app: web.Application) -> bool:
    event_registry = defaultdict(list)
    app[APP_EVENTS_REGISTRY_KEY] = event_registry
    return True


def get_event_registry(app: web.Application) -> Dict:
    registry = app[APP_EVENTS_REGISTRY_KEY]
    return registry

# alias
setup_signals = setup

__all__ = (
    'setup_signals'
    'SignalType'
)
