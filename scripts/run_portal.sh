#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was not found. Run ./scripts/setup_local.sh after installing uv." >&2
  exit 1
fi

cd "${PROJECT_ROOT}"
exec uv run python scripts/run_portal.py "$@"
