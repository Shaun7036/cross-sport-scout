from pathlib import Path
from subprocess import run

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts" / "run_portal.sh"


def test_local_launcher_can_import_src_project_from_another_directory(tmp_path):
    result = run(
        [str(LAUNCHER), "check"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Local environment is ready." in result.stdout


def test_local_launcher_documents_every_portal_view():
    result = run(
        [str(LAUNCHER), "--help"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    for view in ("friendly", "stories", "report", "compact", "detailed", "legacy"):
        assert view in result.stdout


def test_local_launcher_rejects_unknown_view():
    result = run(
        [str(LAUNCHER), "unknown-view"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 2
    assert "Unknown view" in result.stderr
