"""Loopback-only, read-only static portal server; never expose the repository."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class PortalHandler(SimpleHTTPRequestHandler):
    """Do not list directories or cache an old frozen snapshot during local review."""

    def list_directory(self, path: str):
        self.send_error(404, "Not found")
        return None

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def _entry_index(directory: Path, entry_path: str) -> Path:
    parsed = urlsplit(entry_path)
    if parsed.query or parsed.fragment or not parsed.path.startswith("/"):
        raise ValueError("Portal entry path must be an absolute local URL path")
    if any(part == ".." for part in parsed.path.split("/")):
        raise ValueError("Portal entry path cannot leave the served directory")
    candidate = (directory / parsed.path.lstrip("/")).resolve()
    try:
        candidate.relative_to(directory)
    except ValueError as error:
        raise ValueError("Portal entry path cannot leave the served directory") from error
    return candidate / "index.html" if candidate.is_dir() or parsed.path.endswith("/") else candidate


def serve_portal(
    directory: Path,
    *,
    port: int = 8765,
    entry_path: str = "/",
    label: str = "Possession Lab",
) -> None:
    """Serve only generated static assets on this computer until interrupted."""
    directory = directory.resolve()
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if not _entry_index(directory, entry_path).is_file():
        raise ValueError(f"Portal frontend missing from {directory}")
    if not (directory / "data" / "manifest.json").is_file():
        raise ValueError("Portal data missing; run build-portal first")
    handler = partial(PortalHandler, directory=str(directory))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"{label}: http://127.0.0.1:{port}{entry_path} (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nPortal stopped.")
