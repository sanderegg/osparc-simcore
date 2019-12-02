# pylint:disable=unused-variable
# pylint:disable=unused-argument
# pylint:disable=redefined-outer-name


import sys
from pathlib import Path

import aioredis
import pytest
import redis
import yaml
from yarl import URL

## current directory
current_dir = Path(sys.argv[0] if __name__ == "__main__" else __file__).resolve().parent

@pytest.fixture(scope='session')
def docker_compose_file(osparc_simcore_root_dir: Path):
    """ Get the current main docker-compose file"""
    dc_path = osparc_simcore_root_dir / "services" / "docker-compose.yml"
    assert dc_path.exists()

    tmp_dc_path = current_dir / "redis-docker-compose.yml"

    with dc_path.open() as fp:
        main_docker_compose_specs = yaml.safe_load(fp)
    redis_docker_compose_specs = {
        "version": main_docker_compose_specs["version"],
        "services": {
            "redis": main_docker_compose_specs["services"]["redis"]
        }
    }
    with tmp_dc_path.open('w') as fp:
        yaml.safe_dump(redis_docker_compose_specs, fp)
    assert tmp_dc_path.exists()
    yield tmp_dc_path

    tmp_dc_path.unlink()

@pytest.fixture(scope='session')
def redis_service(docker_services, docker_ip):

    host = docker_ip
    port = docker_services.port_for('redis', 6379)
    url = URL(f"redis://{host}:{port}")

    docker_services.wait_until_responsive(
        check=lambda: is_redis_responsive(host, port),
        timeout=30.0,
        pause=0.1,
    )
    return url

def is_redis_responsive(host: str, port: str) -> bool:
    r = redis.Redis(host=host, port=port)
    return r.ping() == True

@pytest.fixture
async def redis_client(loop, redis_service):
    client = await aioredis.create_redis_pool(str(redis_service), encoding="utf-8")
    yield client
    client.close()
    await client.wait_closed()
