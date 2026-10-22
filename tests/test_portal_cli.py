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


def test_build_all_roles_compact_portal_refreshes_shared_export(monkeypatch, tmp_path, capsys):
    from possession_lab import all_roles_portal

    calls = []

    def fake_build(root, output_dir=None):
        calls.append((root, output_dir))
        return {"counts": {"players": 12}}

    monkeypatch.setattr(all_roles_portal, "build_all_roles_portal", fake_build)
    monkeypatch.setattr(
        "sys.argv",
        ["athlete-translation-lab", "build-all-roles-compact-portal", "--root", str(tmp_path)],
    )
    cli.main()
    assert calls == [(tmp_path, tmp_path / "portal-all-roles")]
    assert "Exported 12 players" in capsys.readouterr().out


def test_compact_portal_reuses_shared_snapshot_on_independent_port(monkeypatch, tmp_path):
    from possession_lab import all_roles_portal, portal_server

    directory = tmp_path / "portal-all-roles"
    (directory / "data").mkdir(parents=True)
    (directory / "data" / "manifest.json").write_text("{}")
    (directory / "compact").mkdir()
    (directory / "compact" / "index.html").write_text("<!doctype html>")
    calls = []
    monkeypatch.setattr(
        all_roles_portal,
        "build_all_roles_portal",
        lambda *args, **kwargs: pytest.fail("Must reuse the shared snapshot"),
    )
    monkeypatch.setattr(portal_server, "serve_portal", lambda d, **k: calls.append((d, k)))
    monkeypatch.setattr(
        "sys.argv",
        ["athlete-translation-lab", "all-roles-compact-portal", "--root", str(tmp_path)],
    )
    cli.main()
    assert calls == [
        (
            directory,
            {
                "port": 8767,
                "entry_path": "/compact/",
                "label": "Athlete Translation Lab Compact",
            },
        )
    ]


@pytest.mark.parametrize(
    ("command", "folder", "port", "entry_path", "label"),
    [
        (
            "all-roles-friendly-portal",
            "friendly",
            8768,
            "/friendly/",
            "Athlete Translation Lab Friendly",
        ),
        (
            "all-roles-stories-portal",
            "stories",
            8769,
            "/stories/",
            "Athlete Translation Lab Stories",
        ),
    ],
)
def test_plain_language_portals_reuse_shared_snapshot(
    monkeypatch, tmp_path, command, folder, port, entry_path, label
):
    from possession_lab import all_roles_portal, portal_server

    directory = tmp_path / "portal-all-roles"
    (directory / "data").mkdir(parents=True)
    (directory / "data" / "manifest.json").write_text("{}")
    (directory / folder).mkdir()
    (directory / folder / "index.html").write_text("<!doctype html>")
    calls = []
    monkeypatch.setattr(
        all_roles_portal,
        "build_all_roles_portal",
        lambda *args, **kwargs: pytest.fail("Must reuse the shared snapshot"),
    )
    monkeypatch.setattr(portal_server, "serve_portal", lambda d, **k: calls.append((d, k)))
    monkeypatch.setattr("sys.argv", ["athlete-translation-lab", command, "--root", str(tmp_path)])

    cli.main()

    assert calls == [
        (
            directory,
            {"port": port, "entry_path": entry_path, "label": label},
        )
    ]


def test_report_portal_needs_no_generated_player_snapshot(monkeypatch, tmp_path):
    from possession_lab import all_roles_portal, portal_server

    directory = tmp_path / "portal-all-roles"
    (directory / "report").mkdir(parents=True)
    (directory / "report" / "index.html").write_text("<!doctype html>")
    calls = []
    monkeypatch.setattr(
        all_roles_portal,
        "build_all_roles_portal",
        lambda *args, **kwargs: pytest.fail("The static report must not build player data"),
    )
    monkeypatch.setattr(portal_server, "serve_portal", lambda d, **k: calls.append((d, k)))
    monkeypatch.setattr(
        "sys.argv",
        ["athlete-translation-lab", "all-roles-report-portal", "--root", str(tmp_path)],
    )

    cli.main()

    assert calls == [
        (
            directory,
            {
                "port": 8770,
                "entry_path": "/report/",
                "label": "Athlete Translation Lab Report",
                "require_data": False,
            },
        )
    ]


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


def test_serve_validates_a_nested_entry_path(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html>")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="frontend missing"):
        serve_portal(tmp_path, entry_path="/compact/")
    with pytest.raises(ValueError, match="cannot leave"):
        serve_portal(tmp_path, entry_path="/../private/")
    with pytest.raises(ValueError, match="absolute local URL path"):
        serve_portal(tmp_path, entry_path="compact/")


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
