import json
import sys

import pytest

from possession_lab import cli, ensemble, ensemble_score
from possession_lab.io import write_json


def test_split_is_independent_of_future_model_versions(monkeypatch):
    before = [ensemble.athlete_partition(f"nba:{n}") for n in range(50)]
    monkeypatch.setattr(ensemble, "VERSION", "future-v99")
    assert [ensemble.athlete_partition(f"nba:{n}") for n in range(50)] == before


def test_efficacy_cli_defaults_to_all_and_preserves_json_profile(tmp_path, monkeypatch, capsys):
    profile = {"height_ft": 6, "height_in": 2, "weight_lb": 210, "wingspan_cm": 197}
    path = tmp_path / "profile.json"
    write_json(path, profile)
    monkeypatch.setattr(ensemble, "load_ensemble", lambda root: {"loaded": True})

    def score(artifact, supplied, sport):
        assert artifact == {"loaded": True}
        assert supplied == profile
        assert sport == "all"
        return {"sports": {"nba": {"efficacy_rating": None}}}

    monkeypatch.setattr(ensemble_score, "score_ensemble", score)
    monkeypatch.setattr(
        sys, "argv", ["possession-lab", "efficacy", "--root", str(tmp_path), "--profile", str(path)]
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["sports"]["nba"]["efficacy_rating"] is None


def test_efficacy_cli_rejects_conflicting_profile_sources(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["possession-lab", "efficacy", "--profile", "x.json", "--age", "25"])
    with pytest.raises(SystemExit):
        cli.main()


def test_efficacy_cli_reports_malformed_json(tmp_path, monkeypatch, capsys):
    path = tmp_path / "bad.json"
    path.write_text("not json")
    monkeypatch.setattr(sys, "argv", ["possession-lab", "efficacy", "--profile", str(path)])
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert "error:" in capsys.readouterr().err


def test_model_load_verifies_hash_before_deserializing(tmp_path, monkeypatch):
    model = tmp_path / "models" / "ensemble" / "unified.joblib"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"not a model")
    write_json(
        tmp_path / "reports" / "ensemble" / "model_registry.json",
        {"path": "models/ensemble/unified.joblib", "sha256": "wrong"},
    )
    called = []
    monkeypatch.setattr(ensemble.joblib, "load", lambda path: called.append(path))
    with pytest.raises(ValueError, match="integrity"):
        ensemble.load_ensemble(tmp_path)
    assert called == []


def test_model_load_rejects_registry_path_traversal(tmp_path, monkeypatch):
    write_json(
        tmp_path / "reports" / "ensemble" / "model_registry.json",
        {"path": "../untrusted.joblib", "sha256": "wrong"},
    )
    called = []
    monkeypatch.setattr(ensemble.joblib, "load", lambda path: called.append(path))
    with pytest.raises(ValueError, match="integrity"):
        ensemble.load_ensemble(tmp_path)
    assert called == []
