# pylint:disable=unused-variable
# pylint:disable=unused-argument
# pylint:disable=redefined-outer-name

import sys
from pathlib import Path
from typing import Dict

import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from starlette.testclient import TestClient

from simcore_service_catalog.core.application import init_app

current_dir = Path(sys.argv[0] if __name__ == "__main__" else __file__).resolve().parent


@pytest.fixture
def app(
    monkeypatch, devel_environ: Dict[str, str], postgres_db: sa.engine.Engine
) -> FastAPI:
    # Emulates environ so settings can get config
    for key, value in devel_environ.items():
        monkeypatch.setenv(key, value)

    app = init_app()
    yield app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as cli:
        # Note: this way we ensure the events are run in the application
        yield cli
