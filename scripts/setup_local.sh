#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv was not found. Install it from https://docs.astral.sh/uv/ and try again." >&2
  exit 1
fi

cd "${PROJECT_ROOT}"
echo "Creating the project environment with uv..."
uv sync --extra dev

echo
uv run python scripts/run_portal.py check
echo "Setup complete. Start with: ./scripts/run_portal.sh friendly"
