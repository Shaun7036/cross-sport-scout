#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

if command -v uv >/dev/null 2>&1; then
  echo "Setting up the local environment with uv..."
  # Install a real package copy. Some IDE-managed Python builds skip editable
  # install path files, which makes the console command fail after a repo move.
  uv sync --extra dev --no-editable --reinstall-package possession-lab
else
  if ! command -v python3 >/dev/null 2>&1; then
    echo "Python 3 was not found. Install Python 3.11 or newer and try again." >&2
    exit 1
  fi
  echo "uv was not found; setting up the local environment with Python..."
  python3 -m venv .venv
  if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
    .venv/bin/python -m ensurepip --upgrade
  fi
  .venv/bin/python -m pip install ".[dev]"
fi

VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "The .venv Python interpreter was not created correctly." >&2
  exit 1
fi

echo
"${PROJECT_ROOT}/scripts/run_portal.sh" check
echo "Setup complete. Start with: ./scripts/run_portal.sh"
