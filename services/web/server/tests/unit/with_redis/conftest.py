import pytest
from pathlib import Path
import yaml


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

    