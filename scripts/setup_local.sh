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
uv sync --extra dev --reinstall-package possession-lab

# A virtual environment copied in Finder can retain macOS's hidden filesystem
# flag on every child. Python then skips editable-install .pth files even though
# the environment otherwise looks healthy. Clearing that flag is safe and makes
# the interpreter selected directly in DataSpell behave like `uv run`.
if [[ "$(uname -s)" == "Darwin" ]]; then
  chflags -R nohidden "${PROJECT_ROOT}/.venv"
fi

echo
uv run python scripts/run_portal.py check
echo "Setup complete. Start with: ./scripts/run_portal.sh friendly"
