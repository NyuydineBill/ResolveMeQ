#!/bin/bash
# Build and push Gunicorn Docker image to Docker Hub using environment variables
# Usage: Set DOCKERHUB_USERNAME, DOCKERHUB_PASSWORD, DOCKERHUB_REPO, and optionally IMAGE_TAG

set -e

: "${DOCKERHUB_USERNAME:?Environment variable DOCKERHUB_USERNAME not set}"
: "${DOCKERHUB_PASSWORD:?Environment variable DOCKERHUB_PASSWORD not set}"
: "${DOCKERHUB_REPO:?Environment variable DOCKERHUB_REPO not set}"
IMAGE_TAG=${IMAGE_TAG:-latest}

# Log in to Docker Hub
echo "$DOCKERHUB_PASSWORD" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin

# Build the image
DOCKER_IMAGE="$DOCKERHUB_REPO:$IMAGE_TAG"
docker build -f Dockerfile.gunicorn -t "$DOCKER_IMAGE" .

echo "Pushing $DOCKER_IMAGE to Docker Hub..."
docker push "$DOCKER_IMAGE"

echo "Done."
