""" Main application entry point

 `python -m simcore_service_director_v2 ...`

"""
import sys
from pathlib import Path

import dotenv
import uvicorn
from fastapi import FastAPI
from simcore_service_director_v2.core.application import init_app
from simcore_service_director_v2.core.settings import AppSettings, BootModeEnum

current_dir = Path(sys.argv[0] if __name__ == "__main__" else __file__).resolve().parent

# NOTE: since some versions until now, this seems to be necessary to load .env file (used in make run-devel)
# SEE https://github.com/tiangolo/fastapi/issues/2336
dotenv.load_dotenv(verbose=True)

# SINGLETON FastAPI app
the_app: FastAPI = init_app()


def main():
    cfg: AppSettings = the_app.state.settings
    uvicorn.run(
        "simcore_service_director_v2.__main__:the_app",
        host=cfg.host,
        port=cfg.port,
        reload=cfg.boot_mode == BootModeEnum.DEVELOPMENT,
        reload_dirs=[
            current_dir,
        ],
        log_level=cfg.log_level_name.lower(),
    )


if __name__ == "__main__":
    main()
