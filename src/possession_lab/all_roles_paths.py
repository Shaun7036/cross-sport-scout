"""Shared paths and actionable prerequisite messages for all-role artifacts."""

from __future__ import annotations

from pathlib import Path


def observed_scores_path(root: Path | str) -> Path:
    """Return the generated observed-score artifact for a project root."""
    return Path(root).resolve() / "data" / "processed" / "all_roles" / "observed_scores.parquet"


def observed_scores_missing_message(root: Path | str, path: Path | None = None) -> str:
    """Explain the static-site path and the full-rebuild path without conflating them."""
    project_root = Path(root).resolve()
    expected = path or observed_scores_path(project_root)
    return (
        f"Observed all-role scores were not found at: {expected}\n"
        "This usually means the command is using the wrong project root, or this checkout "
        "does not contain the local research artifacts that are intentionally excluded from Git.\n"
        "To view the Astro portfolio, no research rebuild is needed. From the repository root run:\n"
        "  npm --prefix site ci\n"
        "  npm --prefix site run dev\n"
        "To rebuild the full private research outputs (cached source data required), run:\n"
        f'  uv run python scripts/run_lab.py run-all-roles --root "{project_root}"\n'
        "Do not start with build-all-roles-portal; run-all-roles creates the observed scores first."
    )


def missing_full_snapshot_paths(
    project_root: Path | str,
    portal_root: Path | str | None = None,
) -> list[Path]:
    """Return local prerequisites missing when a full portal export is absent."""
    root = Path(project_root).resolve()
    portal = Path(portal_root).resolve() if portal_root is not None else root / "portal-all-roles"
    if (portal / "data" / "manifest.json").is_file():
        return []
    prerequisites = [
        observed_scores_path(root),
        root / "models" / "all_roles" / "all_roles_v1.joblib",
    ]
    return [path for path in prerequisites if not path.is_file()]


def missing_snapshot_help(project_root: Path | str, missing: list[Path]) -> str:
    """Build a recovery message for a fresh clone or incomplete local snapshot."""
    root = Path(project_root).resolve()
    missing_lines = "\n".join(f"  - {path}" for path in missing)
    return f"""The full local player snapshot is not available.

Missing local research artifacts:
{missing_lines}

These large/source-dependent files are intentionally excluded from Git. To run the current
Astro portfolio, no research rebuild is needed. From the repository root use:

  npm --prefix site ci
  npm --prefix site run dev

If you have the cached source data and intend to rebuild the full private research portal, use:

  uv run python scripts/run_lab.py run-all-roles --root "{root}"

Then rerun this portal command. Do not start with build-all-roles-portal; run-all-roles creates
the observed scores and trained models first.
"""


def requested_portal_output(args: list[str]) -> Path | None:
    """Return an effective CLI --output path without consuming the remaining arguments."""
    for index, argument in enumerate(args):
        if argument == "--output" and index + 1 < len(args):
            return Path(args[index + 1]).resolve()
        if argument.startswith("--output="):
            return Path(argument.partition("=")[2]).resolve()
    return None
