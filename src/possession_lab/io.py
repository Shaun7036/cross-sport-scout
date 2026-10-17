"""Downloads, provenance, and tabular IO used by all sport adapters."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (Path, pd.Timestamp, datetime)):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if value is pd.NA:
        return None
    raise TypeError(f"Not JSON serializable: {type(value)}")


def write_json(path: Path | str, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=json_default, allow_nan=False) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expected_snapshot_hash(dest: Path, url: str) -> str | None:
    for parent in dest.resolve().parents:
        if (parent / "pyproject.toml").is_file():
            manifest = parent / "metadata" / "download_manifest.json"
            if not manifest.exists():
                return None
            relative = str(dest.resolve().relative_to(parent))
            entries = json.loads(manifest.read_text()).get("files", [])
            return next(
                (
                    entry["sha256"]
                    for entry in entries
                    if entry.get("path") == relative and entry.get("url") == url
                ),
                None,
            )
    return None


def fetch(
    url: str,
    dest: Path | str,
    *,
    source: str,
    license_note: str,
    timeout: int = 90,
    force: bool = False,
) -> Path:
    """Cache a designated public download and its immutable source sidecar.

    curl handles OS certificate configuration consistently on this host. A partial
    download is never promoted to the cache. Existing hashes are checked on reuse.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    sidecar = dest.with_name(dest.name + ".source.json")
    expected_hash = _expected_snapshot_hash(dest, url)
    accept_updates = os.environ.get("POSSESSION_LAB_ACCEPT_SOURCE_UPDATES") == "1"
    if dest.exists() and not force:
        if sidecar.exists():
            old = json.loads(sidecar.read_text())
            actual_hash = sha256(dest)
            if old.get("sha256") != actual_hash:
                raise ValueError(f"Cached file failed integrity check: {dest}")
            if old.get("url") != url:
                raise ValueError(f"Cache path belongs to another source: {dest}")
            if expected_hash and actual_hash != expected_hash and not accept_updates:
                raise ValueError(
                    f"Cached snapshot differs from tracked manifest: {dest}; use --accept-source-updates for a new experiment."
                )
            return dest
        # Never silently bless a pre-existing file as a new download.
        raise ValueError(f"Unregistered cache file has no provenance sidecar: {dest}")
    descriptor, temporary = tempfile.mkstemp(prefix=dest.name + ".", suffix=".part", dir=dest.parent)
    os.close(descriptor)
    temporary_path = Path(temporary)
    try:
        command = [
            "curl",
            "-L",
            "--fail",
            "--silent",
            "--show-error",
            "--retry",
            "2",
            "--connect-timeout",
            "20",
            "--max-time",
            str(timeout),
            "--user-agent",
            "possession-lab/0.1 research",
            "--output",
            str(temporary_path),
            url,
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Download failed ({result.returncode}) {url}: {result.stderr[-1200:]}")
        if temporary_path.stat().st_size == 0:
            raise ValueError(f"Empty download: {url}")
        # An error page returned with status 200 must not become a CSV/Parquet.
        head = temporary_path.open("rb").read(512).lower().lstrip()
        if dest.suffix in {".csv", ".parquet", ".zip"} and (
            head.startswith(b"<!doctype html") or head.startswith(b"<html")
        ):
            raise ValueError(f"HTML received instead of data: {url}")
        digest = sha256(temporary_path)
        if expected_hash and digest != expected_hash and not accept_updates:
            raise ValueError(
                f"Upstream source changed since the tracked snapshot: {url}. "
                "Use --accept-source-updates to record a new data version and rerun its evaluation."
            )
        if force and dest.exists():
            # Keep the previous content-addressed snapshot if refreshing a source.
            previous = dest.with_name(f"{dest.stem}.{sha256(dest)[:12]}{dest.suffix}")
            if not previous.exists():
                previous.write_bytes(dest.read_bytes())
            if sidecar.exists():
                previous.with_name(previous.name + ".source.json").write_bytes(sidecar.read_bytes())
        temporary_path.replace(dest)
        write_json(
            sidecar,
            {
                "url": url,
                "source": source,
                "license_note": license_note,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "sha256": digest,
                "bytes": dest.stat().st_size,
            },
        )
        print(f"Downloaded {dest}: {dest.stat().st_size:,} bytes", flush=True)
        return dest
    finally:
        temporary_path.unlink(missing_ok=True)


def read_frame(path: Path | str, **kwargs: Any) -> pd.DataFrame:
    path = Path(path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path, **kwargs)
    if path.suffix in {".csv", ".zip", ".gz"}:
        return pd.read_csv(path, low_memory=False, **kwargs)
    if path.suffix == ".json":
        return pd.read_json(path, **kwargs)
    raise ValueError(f"Unsupported table format: {path.suffix}")


def save_frame(frame: pd.DataFrame, path: Path | str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)


def collect_manifest(root: Path) -> dict:
    entries = []
    for path in sorted((root / "data" / "raw").rglob("*.source.json")):
        row = json.loads(path.read_text())
        row["path"] = str(path.with_name(path.name.removesuffix(".source.json")).relative_to(root))
        entries.append(row)
    result = {"files": entries, "file_count": len(entries), "bytes": sum(x["bytes"] for x in entries)}
    write_json(root / "metadata" / "download_manifest.json", result)
    return result
