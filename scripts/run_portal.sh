#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"

if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
  PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "Python 3 was not found. Install Python 3.11 or newer, then run ./scripts/setup_local.sh." >&2
  exit 1
fi

# The project uses a src/ layout. Adding it explicitly keeps the launcher working
# even when an IDE moves the repository or its editable-install path becomes stale.
export PYTHONPATH="${PROJECT_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
export MPLCONFIGDIR="${PROJECT_ROOT}/.matplotlib"
export PYTHONUNBUFFERED=1

show_help() {
  cat <<'EOF'
Usage: ./scripts/run_portal.sh [view] [extra options]

Views:
  friendly   Plain-language player explorer (default, port 8768)
  stories    Six guided player examples (port 8769)
  report     Plain-language research report (port 8770)
  compact    Compact research explorer (port 8767)
  detailed   Full evidence explorer (port 8766)
  legacy     Original possession-only portal (port 8765)
  check      Verify that the local Python environment can load the project

Examples:
  ./scripts/run_portal.sh
  ./scripts/run_portal.sh stories
  ./scripts/run_portal.sh friendly --port 9000

Press Ctrl+C to stop a running portal.
EOF
}

VIEW="${1:-friendly}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "${VIEW}" in
  -h|--help|help)
    show_help
    exit 0
    ;;
  check)
    "${PYTHON_BIN}" -c \
      "import possession_lab, pandas, numpy, pyarrow, scipy, sklearn, matplotlib, requests, joblib; print('Local environment is ready.')"
    exit 0
    ;;
  friendly)
    COMMAND="all-roles-friendly-portal"
    ;;
  stories)
    COMMAND="all-roles-stories-portal"
    ;;
  report)
    COMMAND="all-roles-report-portal"
    ;;
  compact)
    COMMAND="all-roles-compact-portal"
    ;;
  detailed)
    COMMAND="all-roles-portal"
    ;;
  legacy)
    COMMAND="portal"
    ;;
  *)
    echo "Unknown view: ${VIEW}" >&2
    show_help >&2
    exit 2
    ;;
esac

cd "${PROJECT_ROOT}"
exec "${PYTHON_BIN}" -m possession_lab.cli "${COMMAND}" --root "${PROJECT_ROOT}" "$@"
