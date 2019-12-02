import pytest
from pathlib import Path
import yaml
from yarl import URL


@pytest.fixture(scope='session')
def docker_compose_file(osparc_simcore_root_dir: Path, tmpdir: Path):
    """ Get the current main docker-compose file"""
    dc_path = osparc_simcore_root_dir / "services" / "docker-compose.yml"
    assert dc_path.exists()

    tmp_dc_path = tmpdir.mkdir("redis").join("docker-compose.yml")
    assert tmp_dc_path.exists()

    main_docker_compose_specs = yaml.safe_load(dc_path)
    redis_docker_compose_specs["version"] = main_docker_compose_specs["version"]
    redis_docker_compose_specs["services"]["redis"] = main_docker_compose_specs["services"]["redis"]

    yaml.safe_dump(redis_docker_compose_specs, tmp_dc_path)

    yield tmp_dc_path

@pytest.fixture(scope='session')
def redis_service(docker_services, docker_ip):

    url = URL(f"redis://{docker_ip}:{docker_services.port_for("redis", 6379)}")

    docker_services.wait_until_responsive(
        check=lambda: is_redis_responsive(url),
        timeout=30.0,
        pause=0.1,
    )
    return url