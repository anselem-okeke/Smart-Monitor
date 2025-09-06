#!/bin/bash
# one-time
docker buildx create --use

# login
docker login -u "${DOCKER_HUB_NAME}"

# build & push (adjust yourhub/yourimage)
docker buildx build --platform linux/amd64,linux/arm64 \
  -t "${DOCKER_HUB_NAME}"/smartmon-sqliteweb:latest \
  --push .

