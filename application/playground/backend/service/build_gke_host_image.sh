#!/usr/bin/env bash
# Build the survey/chat GKE host-worker image from the repository root.
# Usage: application/playground/backend/service/build_gke_host_image.sh IMAGE_TAG
set -euo pipefail

IMAGE="${1:?usage: build_gke_host_image.sh IMAGE_TAG}"
ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"

docker build \
  -f "$ROOT/application/playground/backend/service/gke_host_worker.Dockerfile" \
  -t "$IMAGE" \
  "$ROOT"
