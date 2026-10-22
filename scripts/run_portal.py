"""Cross-platform launcher for every Athlete Translation Lab portal view."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
PORTAL_COMMANDS = {
    "friendly": "all-roles-friendly-portal",
    "stories": "all-roles-stories-portal",
    "report": "all-roles-report-portal",
    "compact": "all-roles-compact-portal",
    "detailed": "all-roles-portal",
    "legacy": "portal",
}
REQUIRED_MODULES = (
    "possession_lab",
    "pandas",
    "numpy",
    "pyarrow",
    "scipy",
    "sklearn",
    "matplotlib",
    "requests",
    "joblib",
)


def help_text() -> str:
    return """Usage: run_portal.py [view] [extra options]

Views:
  friendly   Plain-language player explorer (default, port 8768)
  stories    Six guided player examples (port 8769)
  report     Plain-language research report (port 8770)
  compact    Compact research explorer (port 8767)
  detailed   Full evidence explorer (port 8766)
  legacy     Original possession-only portal (port 8765)
  check      Verify that the local Python environment can load the project

Examples:
  uv run python scripts/run_portal.py friendly
  uv run python scripts/run_portal.py stories
  uv run python scripts/run_portal.py friendly --port 9000

Press Ctrl+C to stop a running portal.
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    view = args.pop(0) if args else "friendly"

    if view in {"-h", "--help", "help"}:
        print(help_text(), end="")
        return 0
    if view == "check":
        for module in REQUIRED_MODULES:
            importlib.import_module(module)
        print("Local environment is ready.")
        return 0
    if view not in PORTAL_COMMANDS:
        print(f"Unknown view: {view}\n", file=sys.stderr)
        print(help_text(), file=sys.stderr, end="")
        return 2

    from possession_lab.cli import main as cli_main

    sys.argv = [
        "athlete-translation-lab",
        PORTAL_COMMANDS[view],
        "--root",
        str(PROJECT_ROOT),
        *args,
    ]
    cli_main()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(SRC))
    os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib"))
    raise SystemExit(main())
