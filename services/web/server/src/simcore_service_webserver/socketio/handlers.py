""" Defines **async** handlers for socket.io server

    SEE https://pypi.python.org/pypi/python-socketio
    SEE http://python-socketio.readthedocs.io/en/latest/
"""
# pylint: disable=C0111
# pylint: disable=W0703

import logging
from typing import Dict

from aiohttp import web

from .. import signals
from ..login.decorators import RQT_USERID_KEY, login_required
from .config import get_socket_registry, get_socket_server

ANONYMOUS_USER_ID = -1
_SOCKET_IO_AIOHTTP_REQUEST_KEY = "aiohttp.request"

log = logging.getLogger(__file__)

async def connect(sid: str, environ: Dict, app: web.Application) -> bool:
    """socketio reserved handler for when the fontend connects through socket.io

    Arguments:
        sid {str} -- the socket ID
        environ {Dict} -- the WSGI environ, among other contains the original request
        app {web.Application} -- the aiohttp app

    Returns:
        [type] -- True if socket.io connection accepted
    """
    request = environ[_SOCKET_IO_AIOHTTP_REQUEST_KEY]
    try:
        await authenticate_user(sid, app, request)
    except web.HTTPUnauthorized:
        log.exception("Websocket connection unauthorized")
        return False

    log.debug("client %s connects", sid)
    return True

@login_required
async def authenticate_user(sid: str, app: web.Application, request: web.Request) -> None:
    """throws web.HTTPUnauthorized when the user is not recognized. Keeps the original request.
    """
    userid = request.get(RQT_USERID_KEY, ANONYMOUS_USER_ID)
    registry = get_socket_registry(app)
    registry.add_socket(userid, sid)
    sio = get_socket_server(app)
    # here we keep the original HTTP request in the socket session storage
    async with sio.session(sid) as socketio_session:
        socketio_session["user_id"] = userid
        socketio_session["request"] = request
    log.info("websocket connection from user %s", userid)


async def disconnect(sid: str, app: web.Application):
    """socketio reserved handler for when the socket.io connection is disconnected.

    Arguments:
        sid {str} -- the socket ID
        app {web.Application} -- the aiohttp app
    """
    sio = get_socket_server(app)
    registry = get_socket_registry(app)
    async with sio.session(sid) as session:
        # request = session["request"]
        #TODO: how to handle different sessions from the same user? (i.e. multiple tabs)
        user_id = registry.find_owner(sid)
        if not registry.remove_socket(sid):
            # mark user for disconnection
            # signal if no socket ids are left
            await signals.emit(signals.SignalType.SIGNAL_USER_DISCONNECT, user_id, app)
    log.debug("client %s disconnected", sid)
