import sys
from pathlib import Path
from subprocess import run

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts" / "run_portal.sh"
PYTHON_LAUNCHER = ROOT / "scripts" / "run_portal.py"


def test_local_launcher_can_import_src_project_from_another_directory(tmp_path):
    result = run(
        [sys.executable, str(PYTHON_LAUNCHER), "check"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Local environment is ready." in result.stdout


def test_local_launcher_documents_every_portal_view():
    result = run(
        [sys.executable, str(PYTHON_LAUNCHER), "--help"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    for view in ("profile", "friendly", "stories", "report", "compact", "detailed", "legacy"):
        assert view in result.stdout


def test_local_launcher_rejects_unknown_view():
    result = run(
        [sys.executable, str(PYTHON_LAUNCHER), "unknown-view"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "Unknown view" in result.stderr


def test_platform_wrappers_use_the_same_uv_launcher():
    bash_setup = (ROOT / "scripts" / "setup_local.sh").read_text()
    powershell_setup = (ROOT / "scripts" / "setup_local.ps1").read_text()
    bash_run = LAUNCHER.read_text()
    powershell_run = (ROOT / "scripts" / "run_portal.ps1").read_text()

    assert "uv sync --extra dev" in bash_setup
    assert "uv sync --extra dev" in powershell_setup
    assert "uv run python scripts/run_portal.py" in bash_run
    assert "uv run python scripts/run_portal.py" in powershell_run
