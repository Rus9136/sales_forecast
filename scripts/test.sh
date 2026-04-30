#!/usr/bin/env bash
# Run the test suite inside the sales-forecast-app container.
#
# Stage 1 of the test infrastructure runs against the live container because
# tests/ is not yet baked into the production image. The script syncs the
# test files in via `docker cp` before invoking pytest. Once Stage 8 wires up
# CI, a dedicated test image will replace this approach.
#
# Usage:
#   scripts/test.sh                       # run full suite with coverage
#   scripts/test.sh tests/bonus           # run a subset
#   scripts/test.sh -k waiter --no-cov    # forward args verbatim to pytest
set -euo pipefail

CONTAINER="${SALES_FORECAST_CONTAINER:-sales-forecast-app}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo "ERROR: container '${CONTAINER}' is not running" >&2
  exit 1
fi

# Install dev dependencies inside the container if pytest is missing. This is
# idempotent — pip will skip already-installed packages.
if ! docker exec "${CONTAINER}" python -c "import pytest" 2>/dev/null; then
  echo "Installing dev dependencies in ${CONTAINER}..."
  docker exec -u root "${CONTAINER}" pip install --no-cache-dir \
    pytest==8.3.4 pytest-cov==6.0.0 pytest-asyncio==0.25.2 \
    pytest-mock==3.14.0 freezegun==1.5.1 respx==0.23.1
fi

# Sync tests/ and pyproject.toml into the container (Dockerfile does not copy
# tests, so each run picks up local edits).
docker cp "${PROJECT_ROOT}/tests/." "${CONTAINER}:/app/tests/"
docker cp "${PROJECT_ROOT}/pyproject.toml" "${CONTAINER}:/app/pyproject.toml"

# Default to running the full suite with coverage; allow override via args.
if [[ $# -eq 0 ]]; then
  set -- tests/ --cov --cov-report=term
fi

exec docker exec "${CONTAINER}" python -m pytest "$@"
