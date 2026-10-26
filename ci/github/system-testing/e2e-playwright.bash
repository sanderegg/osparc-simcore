#!/bin/bash
# http://redsymbol.net/articles/unofficial-bash-strict-mode/
# https://github.com/GoogleChrome/puppeteer/blob/master/docs/troubleshooting.md#running-puppeteer-on-travis-ci
set -o errexit  # abort on nonzero exitstatus
set -o nounset  # abort on unbound variable
set -o pipefail # don't hide errors within pipes
IFS=$'\n\t'

# in case it's a Pull request, the env are never available, default to itisfoundation to get a maybe not too old version for caching
DOCKER_IMAGE_TAG=$(exec ci/helpers/build_docker_image_tag.bash)
export DOCKER_IMAGE_TAG

# apt keeps a stalled connection open for a very long time before giving up, so a throttled
# distro mirror can freeze the dependency install for the whole job budget. Making every fetch
# retry on a short timeout lets it recover instead. Playwright calls apt itself, so the options
# need to come from the apt configuration and not from the command line.
harden_apt() {
  sudo -- tee /etc/apt/apt.conf.d/99-ci-acquire >/dev/null <<'EOF'
Acquire::Retries "5";
Acquire::http::Timeout "20";
Acquire::https::Timeout "20";
EOF
}

# retry <attempts> <deadline-seconds> <command...>
# Gives every attempt its own deadline so a stalled download cannot eat the whole job.
retry() {
  local attempts="${1:?number of attempts}" deadline="${2:?deadline in seconds}"
  shift 2
  local attempt status
  local IFS=$' \t\n' # keeps the log lines below readable
  for ((attempt = 1; attempt <= attempts; attempt++)); do
    echo "attempt ${attempt}/${attempts} (deadline ${deadline}s): $*"
    status=0
    timeout "${deadline}" "$@" || status=$?
    if [ "${status}" -eq 0 ]; then
      return 0
    fi
    echo "attempt ${attempt}/${attempts} of '$*' failed with exit code ${status}"
  done
  return 1
}

install() {
  make devenv
  make pull-externals
  # shellcheck source=/dev/null
  source .venv/bin/activate
  harden_apt
  pushd tests/e2e-playwright
  retry 2 360 make install-ci
  popd
}

up_simcore() {
  # shellcheck source=/dev/null
  source .venv/bin/activate
  pushd tests/e2e-playwright
  make up-simcore-ci
  popd
}

test() {
  # shellcheck source=/dev/null
  source .venv/bin/activate
  pushd tests/e2e-playwright
  make test-sleepers
  make test-guided-tours
  make test-platform
  popd
}

dump_docker_logs() {
  # get docker logs
  # NOTE: Timeout avoids issue with dumping logs that hang!
  out_dir=tests/e2e-playwright/test_failures
  mkdir --parents "$out_dir"

  for service_id in $(docker service ls -q); do
    service_name=$(docker service inspect "$service_id" --format="{{.Spec.Name}}")
    echo "Dumping logs for $service_name"
    (timeout 30 docker service logs --timestamps --tail=500 --details "$service_id" >"$out_dir/$service_name.log" 2>&1) || true

    # dump service inspect
    service_dir="$out_dir/$service_name"
    mkdir --parents "$service_dir"
    docker service inspect "$service_id" >"$service_dir/service_inspect.json" 2>&1 || true

    # dump task inspects
    for task_id in $(docker service ps "$service_id" -q); do
      task_info=$(docker inspect "$task_id" --format="{{.Status.ContainerStatus.ContainerID}} {{index .Spec.ContainerSpec.Labels \"com.docker.swarm.task.name\"}}" 2>/dev/null || echo "")
      if [ -n "$task_info" ]; then
        container_id=$(echo "$task_info" | awk '{print $1}')
        task_name=$(echo "$task_info" | awk '{print $2}' | sed 's/.*\.//')
        # Fallback to task_id if task_name is empty
        if [ -z "$task_name" ]; then
          task_name="$task_id"
        fi
        if [ -n "$container_id" ]; then
          docker inspect "$container_id" >"$service_dir/container_${task_name}.json" 2>&1 || true
        fi
      fi
    done
  done
}

# Check if the function exists (bash specific)
if declare -f "$1" >/dev/null; then
  # call arguments verbatim
  "$@"
else
  # Show a helpful error
  echo "'$1' is not a known function name" >&2
  exit 1
fi
