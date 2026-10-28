import sys
from pathlib import Path
from subprocess import run

from possession_lab.all_roles_paths import (
    missing_full_snapshot_paths,
    missing_snapshot_help,
    observed_scores_missing_message,
    observed_scores_path,
    requested_portal_output,
)

ROOT = Path(__file__).parents[1]
LAUNCHER = ROOT / "scripts" / "run_portal.sh"
PYTHON_LAUNCHER = ROOT / "scripts" / "run_portal.py"
RESEARCH_LAUNCHER = ROOT / "scripts" / "run_lab.py"


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


def test_research_launcher_can_import_moved_src_project_from_another_directory(tmp_path):
    result = run(
        [sys.executable, str(RESEARCH_LAUNCHER), "--help"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "run-all-roles" in result.stdout


def test_platform_wrappers_use_the_same_uv_launcher():
    bash_setup = (ROOT / "scripts" / "setup_local.sh").read_text()
    powershell_setup = (ROOT / "scripts" / "setup_local.ps1").read_text()
    bash_run = LAUNCHER.read_text()
    powershell_run = (ROOT / "scripts" / "run_portal.ps1").read_text()

    assert "uv sync --extra dev" in bash_setup
    assert "uv sync --extra dev" in powershell_setup
    assert "uv run python scripts/run_portal.py" in bash_run
    assert "uv run python scripts/run_portal.py" in powershell_run


def test_missing_full_snapshot_message_routes_static_users_away_from_research_rebuild(tmp_path):
    missing = missing_full_snapshot_paths(tmp_path)
    message = missing_snapshot_help(tmp_path, missing)

    assert len(missing) == 2
    assert "observed_scores.parquet" in message
    assert "npm --prefix site run dev" in message
    assert "run-all-roles" in message
    assert "Do not start with build-all-roles-portal" in message


def test_existing_full_portal_manifest_skips_research_prerequisites(tmp_path):
    manifest = tmp_path / "portal-all-roles" / "data" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")

    assert missing_full_snapshot_paths(tmp_path) == []


def test_alternate_full_portal_manifest_skips_default_prerequisites(tmp_path):
    alternate = tmp_path / "alternate-portal"
    manifest = alternate / "data" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")

    assert missing_full_snapshot_paths(tmp_path, alternate) == []


def test_observed_scores_error_explains_static_and_research_paths(tmp_path):
    expected = tmp_path / "data" / "processed" / "all_roles" / "observed_scores.parquet"
    message = observed_scores_missing_message(tmp_path)

    assert observed_scores_path(tmp_path) == expected
    assert str(expected) in message
    assert "npm --prefix site run dev" in message
    assert "run-all-roles" in message


def test_requested_portal_output_supports_both_cli_forms(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert requested_portal_output(["--output", "custom"]) == (tmp_path / "custom").resolve()
    assert requested_portal_output(["--output=other"]) == (tmp_path / "other").resolve()
    assert requested_portal_output(["--port", "9000"]) is None
