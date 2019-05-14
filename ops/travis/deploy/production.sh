#!/bin/bash
# as of http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail
IFS=$'\n\t'

# pull the tagged staging build
export DOCKER_IMAGE_PREFIX=${DOCKER_REGISTRY}/
# find the docker image tag
export TAG="${TRAVIS_TAG}"
export ORG=${DOCKER_REGISTRY}
export REPO="webserver"
DOCKER_IMAGE_TAG=$(./ops/travis/helpers/find_staging_version.sh | awk 'END{print}') || exit $?
export DOCKER_IMAGE_TAG
make pull

# show current images on system
docker images

# these variable must be available securely from travis
echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin

# re-tag master build to staging-latest
export DOCKER_IMAGE_PREFIX_NEW=${DOCKER_IMAGE_PREFIX}
export DOCKER_IMAGE_TAG_NEW=production-latest
make tag
export DOCKER_IMAGE_TAG=${DOCKER_IMAGE_TAG_NEW}
export DOCKER_IMAGE_TAG=${DOCKER_IMAGE_TAG_NEW}
make push

# re-tag master to staging-DATE.BUILD_NUMBER.GIT_SHA
TRAVIS_PLATFORM_STAGE_VERSION=production-$(date +"%Y-%m-%d").${TRAVIS_BUILD_NUMBER}.$(git rev-parse HEAD)
export DOCKER_IMAGE_TAG_NEW=$TRAVIS_PLATFORM_STAGE_VERSION
make tag
export DOCKER_IMAGE_PREFIX=${DOCKER_IMAGE_PREFIX_NEW}
export DOCKER_IMAGE_TAG=${DOCKER_IMAGE_TAG_NEW}
make push
