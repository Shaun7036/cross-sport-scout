from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from possession_lab.ensemble import athlete_partition
from possession_lab.ensemble_score import score_ensemble
from possession_lab.ensemble_targets import HeadSpec
from possession_lab.portal import build_portal, score_profiles


class ConstantModel:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def predict(self, frame):
        assert list(frame.columns) == ["height_cm", "weight_kg"]
        self.calls.append(len(frame))
        return np.full(len(frame), self.value, dtype=float)


class SharedModel(ConstantModel):
    def predict(self, frame):
        self.calls.append(len(frame))
        return 50 + frame.height_cm.to_numpy() * 3 + frame.weight_kg.to_numpy() * 2


class ArchetypeModel(ConstantModel):
    def __init__(self, value):
        super().__init__(value)
        self.description_calls = []
        self.model_features_ = ["height_cm", "weight_kg"]
        self.cluster_centers_original_ = np.array([[180, 80]])
        self.cluster_means_ = [value]
        self.cluster_support_ = [40]

    def describe(self, frame):
        self.description_calls.append(len(frame))
        return [
            {
                "nearest_archetype": 0,
                "nearest_center": {"height_cm": 180, "weight_kg": 80},
                "probabilities": {"0": 1.0},
                "archetypes": [{"archetype": 0, "outcome_mean": self.value}],
            }
            for _ in range(len(frame))
        ]


def _head(sport, role, *, status="evidence_supported", method="stack", radius=8):
    event = {"nfl": "sacks", "nba": "steals", "nhl": "takeaways", "epl": "recoveries"}[sport]
    spec = HeadSpec(sport, role, 150, {"activity": {"weight": 1, "metrics": {event: 1}}})
    summary = {
        "status": status,
        "train_rows": 100,
        "train_athletes": 100,
        "calibration_athletes": 30,
        "test_athletes": 25,
        "metrics": {"stack_mae": np.float64(7.5), "interval_90_empirical_coverage": 0.6},
        "mse_improvement_cluster_bootstrap": {"mean": 1, "lower95": -1, "upper95": 2},
        "improvement_statistically_established": False,
    }
    if status == "insufficient_support":
        return {"spec": spec, "summary": summary}
    return {
        "spec": spec,
        "summary": summary,
        "experts": {
            "archetype": ArchetypeModel(150),
            "ridge": ConstantModel(-20),
            "hist_gradient_boosting": ConstantModel(70),
            "extra_trees": ConstantModel(40),
        },
        # Deliberately not normalized; parity requires the same normalization as core.
        "stack_weights": {
            "baseline50": 0,
            "archetype": 0.4,
            "ridge": 0.2,
            "hist_gradient_boosting": 0.2,
            "extra_trees": 0.4,
            "shared": 0.2,
        },
        "selected_method": method,
        "shared_center": [180.0, 80.0],
        "shared_scale": [10.0, 5.0],
        "body_reference": {
            "center": [180.0, 80.0],
            "inverse_covariance": [[0.01, 0.001], [0.001, 0.01]],
            "distances": [0.0, 1.0, 4.0, 9.0, float("nan")],
            "lower": [160.0, 55.0],
            "upper": [220.0, 130.0],
        },
        "calibration_radius": radius,
    }


def _artifact():
    return {
        "version": "test-v1",
        "features": ["height_cm", "weight_kg"],
        "trained_at": "2026-10-01T00:00:00+00:00",
        "shared_expert": SharedModel(50),
        "heads": {
            "nfl:EDGE": _head("nfl", "EDGE"),
            "nba:guard": _head("nba", "guard", status="no_evidence", method="baseline"),
            "nba:forward": _head("nba", "forward", radius=float("inf")),
            "nhl:center": _head("nhl", "center"),
            "epl:DEF": _head("epl", "DEF"),
            "epl:MID": _head("epl", "MID"),
            "epl:FWD": _head("epl", "FWD", status="insufficient_support"),
        },
    }


def test_batch_matches_core_for_clipped_experts_baseline_intervals_and_body_fit():
    artifact = _artifact()
    frame = pd.DataFrame({"height_cm": [180, 185, 250], "weight_kg": [80, 85, 200], "age": [24, 30, 40]})
    batch = score_profiles(artifact, frame)
    # Each expert and each describe() receives the entire roster exactly once.
    for head in artifact["heads"].values():
        for expert in head.get("experts", {}).values():
            assert expert.calls == [3]
        if "experts" in head:
            assert head["experts"]["archetype"].description_calls == [3]
    assert artifact["shared_expert"].calls == [3] * 6
    for position, profile in enumerate(frame.to_dict("records")):
        core = score_ensemble(artifact, profile)
        for sport, sport_result in core["sports"].items():
            for expected in sport_result["roles"]:
                key = sport + ":" + expected["role"]
                actual = batch[position][key]
                assert actual["exploratory_estimate"] == pytest.approx(expected["experimental_estimate"])
                assert (
                    actual["interval"] == pytest.approx(expected["interval"])
                    if expected["interval"]
                    else actual["interval"] is None
                )
                assert actual["physical_fit"] == pytest.approx(expected["physical_fit"])
                assert actual["out_of_domain"] == expected["out_of_domain"]
                if key == "epl:DEF":
                    assert actual["status"] == "data_review"
                    assert actual["efficacy_rating"] is None
                else:
                    assert actual["efficacy_rating"] == pytest.approx(expected["efficacy_rating"])
                if actual["expert_predictions"]:
                    assert actual["expert_predictions"] == pytest.approx(expected["expert_predictions"])
    assert batch[0]["nba:guard"]["exploratory_estimate"] == 50
    assert batch[0]["nba:forward"]["interval"] == [0, 100]
    assert batch[2]["nba:forward"]["status"] == "out_of_domain"
    assert batch[0]["nfl:EDGE"]["nearest_archetype"] == {
        "index": 0,
        "height_cm": 180,
        "weight_kg": 80,
        "mean_target": 150,
        "membership": 1.0,
    }


def test_missing_and_known_minor_profiles_are_retained_without_imputation():
    artifact = _artifact()
    scores = score_profiles(
        artifact,
        pd.DataFrame(
            {
                "height_cm": [np.nan, 180, 180, 180],
                "weight_kg": [80, np.inf, 80, 80],
                "age": [25, 25, 17, np.nan],
            }
        ),
    )
    assert scores[0]["nfl:EDGE"]["status"] == "missing_measurements"
    assert scores[1]["nfl:EDGE"]["status"] == "missing_measurements"
    assert scores[2]["nfl:EDGE"]["status"] == "insufficient_support"
    assert "adult" in scores[2]["nfl:EDGE"]["explanation"][0]
    assert scores[2]["nfl:EDGE"]["exploratory_estimate"] is None
    assert scores[3]["nfl:EDGE"]["status"] == "provisional"
    assert artifact["heads"]["nfl:EDGE"]["experts"]["ridge"].calls == [1]
    json.dumps(scores, allow_nan=False)


def test_physical_fit_preserves_exact_training_distance_ties():
    artifact = _artifact()
    head = artifact["heads"]["nba:forward"]
    artifact["heads"] = {"nba:forward": head}
    values = np.random.default_rng(82).normal([180, 80], [5, 5], size=(48, 2))
    reference = head["body_reference"]
    reference["center"] = [181.1234, 80.4321]
    reference["inverse_covariance"] = [[0.02345678, 0.0012345], [0.0012345, 0.0345678]]
    delta = values - reference["center"]
    inverse = np.asarray(reference["inverse_covariance"])
    reference["distances"] = [d @ inverse @ d for d in delta]
    frame = pd.DataFrame(values, columns=["height_cm", "weight_kg"])
    actual = score_profiles(artifact, frame)
    for i, profile in enumerate(frame.to_dict("records")):
        expected = score_ensemble(artifact, profile)["sports"]["nba"]["roles"][0]
        assert actual[i]["nba:forward"]["physical_fit"] == expected["physical_fit"]


def _train_id(sport, stem):
    return next(f"{stem}{i}" for i in range(100) if athlete_partition(f"{sport}:{stem}{i}") == "train")


@pytest.fixture
def project(tmp_path, monkeypatch):
    artifact = _artifact()
    monkeypatch.setattr("possession_lab.portal.load_ensemble", lambda root: artifact)
    model = tmp_path / "models/ensemble/unified.joblib"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"synthetic registered model")
    old = _train_id("nfl", "previous")
    ineligible = _train_id("nfl", "ineligible")

    def row(player_id, name, role, **extra):
        return {
            "player_id": player_id,
            "name": name,
            "role": role,
            "season": 2025,
            "height_cm": 180.0,
            "weight_kg": 80.0,
            "age": 25.0,
            "opportunity": 500.0,
            "sacks": 3.0,
            "steals": 4.0,
            "takeaways": 5.0,
            "recoveries": 6.0,
            "blocks": 7.0,
            "teams": "AAA",
            **extra,
        }

    panels = {
        "nfl": [
            row("watt", "T.J. Watt", "EDGE"),
            row(old, "Changed role", "DB_UNKNOWN"),
            row(old, "Changed role", "EDGE", season=2021),
            row(ineligible, "Zero opportunity", "EDGE", opportunity=0),
            row("missing", "Missing body", "EDGE", height_cm=np.nan),
        ],
        "nba": [row("guard", "Guard", "guard")],
        "nhl": [row("center", "Center", "center")],
        "epl": [
            row("def", "Defender", "DEF"),
            row("mid", "Midfielder", "MID"),
            row("gk", "Goalkeeper", "GK"),
            row("minor", "Minor", "MID", age=17),
        ],
    }
    for sport, rows in panels.items():
        path = tmp_path / "data/processed" / sport / "player_seasons.parquet"
        path.parent.mkdir(parents=True)
        pd.DataFrame(rows).to_parquet(path, index=False)
    pd.DataFrame(
        {"player_id": ["def", "mid", "mid"], "season": [2025] * 3, "blocks": [7.0, 3.0, np.nan]}
    ).to_parquet(tmp_path / "data/processed/epl/player_games.parquet", index=False)
    return tmp_path, artifact, old, ineligible


def _detail(root, player):
    return json.loads((root / "portal" / player["detail_path"]).read_text())


def test_export_catalog_native_defaults_context_and_truthful_training_membership(project):
    root, artifact, old, ineligible = project
    manifest = build_portal(root)
    assert manifest["counts"] == {"players": 10, "players_with_measurements": 9, "fitted_heads": 6}
    assert manifest["defaults"] == {"player_id": "nfl:watt", "sport": "nfl"}
    players = {p["id"]: p for p in manifest["players"]}
    assert len(list((root / "portal/data/players").glob("*.json"))) == 10
    assert _detail(root, players[f"nfl:{old}"])["included_in_training"] is True
    assert _detail(root, players[f"nfl:{ineligible}"])["model_partition"] == "train"
    assert _detail(root, players[f"nfl:{ineligible}"])["included_in_training"] is False
    defender = _detail(root, players["epl:def"])
    assert defender["sport_results"]["epl"]["default_role"] == "DEF"
    roles = {r["role"]: r for r in defender["sport_results"]["epl"]["roles"]}
    assert roles["DEF"]["status"] == "data_review"
    assert roles["DEF"]["efficacy_rating"] is None
    assert roles["MID"]["efficacy_rating"] is not None
    assert next(m for m in defender["observed"]["metrics"] if m["key"] == "blocks")["value"] is None
    midfielder = _detail(root, players["epl:mid"])
    assert next(m for m in midfielder["observed"]["metrics"] if m["key"] == "blocks")["value"] is None
    keeper = _detail(root, players["epl:gk"])
    assert keeper["player"]["role"] == "GK"
    assert any("actual role" in w for r in keeper["sport_results"]["epl"]["roles"] for w in r["warnings"])
    missing = _detail(root, players["nfl:missing"])
    assert missing["sport_results"]["nba"]["efficacy_rating"] is None
    assert all(r["status"] == "missing_measurements" for r in missing["sport_results"]["nba"]["roles"])
    assert manifest["heads"]["nba:guard"]["active_weights"] == {
        k: float(k == "baseline50") for k in manifest["heads"]["nba:guard"]["candidate_weights"]
    }
    assert manifest["model"]["sha256"] == hashlib.sha256(b"synthetic registered model").hexdigest()
    assert manifest["model"]["learned_features"] == ["height_cm", "weight_kg"]
    assert manifest["heads"]["epl:DEF"]["data_review"] is True
    assert len(manifest["sources"]) >= 6
    assert json.loads((root / "portal/data/manifest.json").read_text()) == manifest
    json.dumps(manifest, allow_nan=False)


def test_duplicate_snapshot_is_rejected_before_any_inference(project):
    root, artifact, _, _ = project
    path = root / "data/processed/nba/player_seasons.parquet"
    frame = pd.read_parquet(path)
    pd.concat([frame, frame]).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="Duplicate player-season"):
        build_portal(root)
    assert artifact["shared_expert"].calls == []


def test_saved_training_dataset_hash_mismatch_is_rejected(project):
    root, artifact, _, _ = project
    artifact["data_sources"] = {"nfl": {"sha256": "wrong"}}
    with pytest.raises(ValueError, match="training snapshot"):
        build_portal(root)


def test_invalid_batches_fail_closed():
    artifact = _artifact()
    artifact["heads"]["nfl:EDGE"]["stack_weights"]["ridge"] = -1
    with pytest.raises(ValueError, match="non-negative"):
        score_profiles(artifact, pd.DataFrame({"height_cm": [180], "weight_kg": [80]}))
