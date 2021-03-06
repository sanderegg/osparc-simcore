#!/usr/bin/env python3
import logging
import os

from aiohttp import web

from servicelib.client_session import persistent_client_session
from servicelib.tracing import setup_tracing
from simcore_service_director import config, registry_cache_task, resources
from simcore_service_director.rest import routing
from simcore_service_director.monitoring import setup_app_monitoring

log = logging.getLogger(__name__)


def setup_app_tracing(app: web.Application, app_name: str) -> bool:
    host = "0.0.0.0" if os.environ.get("SC_BUILD_TARGET") else "127.0.0.1"  # nosec
    port = 8080
    cfg = {
        "enabled": config.TRACING_ENABLED,
        "zipkin_endpoint": config.TRACING_ZIPKIN_ENDPOINT,
    }
    return setup_tracing(app, app_name, host, port, cfg)



def setup_app() -> web.Application:
    api_spec_path = resources.get_path(resources.RESOURCE_OPEN_API)
    app = routing.create_web_app(api_spec_path.parent, api_spec_path.name)

    # NOTE: ensure client session is context is run first, then any further get_client_sesions will be correctly closed
    app.cleanup_ctx.append(persistent_client_session)

    registry_cache_task.setup(app)

    setup_app_monitoring(app, "simcore_service_director")

    setup_app_tracing(app, "simcore_service_director")

    return app


def main() -> None:
    app = setup_app()
    web.run_app(app, port=8080)


if __name__ == "__main__":
    main()
