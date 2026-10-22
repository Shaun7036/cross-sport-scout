"""Location-safe launcher for Athlete Translation Lab research commands.

Using this wrapper keeps a moved or copied virtual environment from pointing
at the repository's previous location.  It is intentionally small so the same
command works from uv on macOS, Windows, and Linux.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"


def main() -> int:
    sys.path.insert(0, str(SRC))
    os.environ.setdefault("MPLCONFIGDIR", str(PROJECT_ROOT / ".matplotlib"))

    from possession_lab.cli import main as cli_main

    cli_main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
