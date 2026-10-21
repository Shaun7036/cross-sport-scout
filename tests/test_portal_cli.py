"""Portal commands are static export/serve operations, never training commands."""

from pathlib import Path

import pytest

from possession_lab import cli
from possession_lab.portal_server import serve_portal


def test_build_portal_dispatch(monkeypatch, tmp_path, capsys):
    from possession_lab import portal

    calls = []

    def fake_build(root, output_dir=None):
        calls.append((root, output_dir))
        return {"players": [{"id": "test"}]}

    monkeypatch.setattr(portal, "build_portal", fake_build)
    monkeypatch.setattr("sys.argv", ["possession-lab", "build-portal", "--root", str(tmp_path)])
    cli.main()
    assert calls == [(tmp_path, tmp_path / "portal")]
    assert "Exported 1 players" in capsys.readouterr().out


def test_portal_uses_existing_snapshot(monkeypatch, tmp_path):
    from possession_lab import portal, portal_server

    directory = tmp_path / "portal"
    (directory / "data").mkdir(parents=True)
    (directory / "data" / "manifest.json").write_text("{}")
    calls = []
    monkeypatch.setattr(portal, "build_portal", lambda *a, **k: pytest.fail("Must reuse snapshot"))
    monkeypatch.setattr(portal_server, "serve_portal", lambda d, **k: calls.append((d, k)))
    monkeypatch.setattr("sys.argv", ["possession-lab", "portal", "--root", str(tmp_path), "--port", "8989"])
    cli.main()
    assert calls == [(directory, {"port": 8989})]


@pytest.mark.parametrize("extra", [["--sport", "nfl"], ["--port", "0"], ["--port", "65536"]])
def test_portal_rejects_invalid_options(monkeypatch, tmp_path, extra):
    monkeypatch.setattr("sys.argv", ["possession-lab", "portal", "--root", str(tmp_path), *extra])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_serve_requires_frontend_and_snapshot(tmp_path):
    with pytest.raises(ValueError, match="frontend missing"):
        serve_portal(tmp_path)
    (tmp_path / "index.html").write_text("<!doctype html>")
    with pytest.raises(ValueError, match="data missing"):
        serve_portal(tmp_path)


def test_serve_is_loopback_only(monkeypatch, tmp_path):
    from possession_lab import portal_server

    (tmp_path / "index.html").write_text("<!doctype html>")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.json").write_text("{}")
    calls = []

    class FakeServer:
        def __init__(self, address, handler):
            calls.append((address, Path(handler.keywords["directory"])))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def serve_forever(self):
            raise KeyboardInterrupt

    monkeypatch.setattr(portal_server, "ThreadingHTTPServer", FakeServer)
    serve_portal(tmp_path, port=8989)
    assert calls == [(("127.0.0.1", 8989), tmp_path)]
