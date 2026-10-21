"""Loopback-only, read-only static portal server; never expose the repository."""

from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class PortalHandler(SimpleHTTPRequestHandler):
    """Do not list directories or cache an old frozen snapshot during local review."""

    def list_directory(self, path: str):
        self.send_error(404, "Not found")
        return None

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def serve_portal(directory: Path, *, port: int = 8765) -> None:
    """Serve only generated static assets on this computer until interrupted."""
    directory = directory.resolve()
    if not 1 <= port <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    if not (directory / "index.html").is_file():
        raise ValueError(f"Portal frontend missing from {directory}")
    if not (directory / "data" / "manifest.json").is_file():
        raise ValueError("Portal data missing; run build-portal first")
    handler = partial(PortalHandler, directory=str(directory))
    with ThreadingHTTPServer(("127.0.0.1", port), handler) as server:
        print(f"Possession Lab: http://127.0.0.1:{port} (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nPortal stopped.")
