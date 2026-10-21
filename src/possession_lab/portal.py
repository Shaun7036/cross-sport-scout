"""Export a read-only presentation snapshot from the saved ensemble.

No acquisition or fitting happens here. Inference is batched once per expert
and role, rather than invoking the interactive scorer for every roster entry.
The primary-score gates match that scorer, with one explicit presentation-only
abstention: EPL defender outputs remain under data review for partial blocks.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from possession_lab.ensemble import athlete_partition, eligible_rows, load_ensemble
from possession_lab.ensemble_features import prepare_profile_features
from possession_lab.ensemble_score import (
    EXPERT_KEYS,
    MODEL_FEATURES,
    OOD_MAHALANOBIS_SQUARED,
    _finite_matrix,
    _finite_vector,
    _spec_field,
)
from possession_lab.io import sha256

SPORTS = {
    "nfl": ("NFL", "2025"),
    "nba": ("NBA", "2025–26"),
    "nhl": ("NHL", "2025–26"),
    "epl": ("Premier League", "2025–26"),
}
ROLE_LABELS = {
    "nfl:EDGE": "Edge defender",
    "nfl:IDL": "Interior defensive line",
    "nfl:LB": "Linebacker",
    "nfl:OLB_HYBRID": "Hybrid outside linebacker",
    "nfl:CB": "Cornerback",
    "nfl:S": "Safety",
    "nba:guard": "Guard",
    "nba:forward": "Forward",
    "nba:center": "Center",
    "nhl:defense": "Defense",
    "nhl:center": "Center",
    "nhl:wing": "Wing",
    "epl:DEF": "Defender",
    "epl:MID": "Midfielder",
    "epl:FWD": "Forward",
}
COMPONENTS = ("baseline50", *EXPERT_KEYS, "shared")
DATA_REVIEW_HEAD = "epl:DEF"
DATA_REVIEW_NOTE = (
    "EPL defender ratings are withheld: missing match-level blocks were partially summed "
    "in the existing training target. The saved model has not been repaired or retrained."
)
SOURCES = [
    {
        "id": "nflverse",
        "sports": ["nfl"],
        "label": "nflverse: archived rosters, play-by-play and participation",
        "url": "https://github.com/nflverse/nflverse-data",
        "note": "Consult upstream attribution and provider-specific terms; participation has separate terms.",
    },
    {
        "id": "sportsdataverse",
        "sports": ["nba"],
        "label": "SportsDataverse: ESPN NBA roster, profile and box-score archives",
        "url": "https://github.com/sportsdataverse/sportsdataverse-data",
        "note": "Public access is not a grant of unrestricted redistribution of underlying ESPN/NBA data.",
    },
    {
        "id": "moneypuck",
        "sports": ["nhl"],
        "label": "MoneyPuck: designated regular-season skater downloads",
        "url": "https://moneypuck.com/data.htm",
        "note": "Free non-commercial use and ad-hoc journalism with clear MoneyPuck attribution; contact for other uses.",
    },
    {
        "id": "nhl",
        "sports": ["nhl"],
        "label": "NHL Stats: season-filtered skater bios",
        "url": "https://www.nhl.com/stats/skaters",
        "note": "Bios are current/undated profiles, not verified annual measurements.",
    },
    {
        "id": "vaastav",
        "sports": ["epl"],
        "label": "Vaastav Fantasy Premier League archives: player universe and minutes",
        "url": "https://github.com/vaastav/Fantasy-Premier-League",
        "note": "FPL roster universe is not a complete registration list of every Premier League club.",
    },
    {
        "id": "fpl_core",
        "sports": ["epl"],
        "label": "FPL-Core-Insights: 2025–26 match-level defensive events",
        "url": "https://github.com/olbauday/FPL-Core-Insights",
        "note": "Do not assume an unrestricted redistribution license; blocks have a documented completeness issue.",
    },
    {
        "id": "espn",
        "sports": ["epl"],
        "label": "ESPN club roster profiles: matched height and weight",
        "url": "https://www.espn.com/soccer/league/_/name/eng.1",
        "note": "Partial matched coverage; undated profile measurements, not verified historical season measurements.",
    },
]
EVENTS = {
    "nfl": [
        ("sacks", "Sack credits"),
        ("qb_hits", "Quarterback-hit credits"),
        ("interceptions", "Interceptions"),
        ("passes_defended", "Passes defended"),
        ("forced_fumbles", "Forced fumbles"),
        ("negative_play_tackle_credits", "Negative-play tackle credits"),
    ],
    "nba": [("steals", "Steals"), ("blocks", "Blocks"), ("defensive_rebounds", "Defensive rebounds")],
    "nhl": [
        ("takeaways", "Takeaways"),
        ("blocks", "Blocks"),
        ("hits", "Hits"),
        ("faceoff_wins", "Faceoff wins"),
        ("giveaways", "Giveaways"),
    ],
    "epl": [
        ("recoveries", "Ball recoveries"),
        ("tackles_won", "Tackles won"),
        ("interceptions", "Interceptions"),
        ("blocks", "Blocks (under review)"),
    ],
}


def _safe(value: Any) -> Any:
    """Strict JSON: unavailable and infinite diagnostics are null, never NaN."""
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, Mapping):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_safe(v) for v in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (int, np.integer)) and not isinstance(value, (bool, np.bool_)):
        return int(value)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (datetime, pd.Timestamp, Path)):
        return str(value)
    return value


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_safe(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n"
    )


def _weights(head: Mapping) -> dict[str, float]:
    supplied = head.get("stack_weights")
    if not isinstance(supplied, Mapping):
        raise ValueError("Fitted head is missing stack_weights")
    if "shared" not in supplied and "shared_expert" in supplied:
        supplied = {**supplied, "shared": supplied["shared_expert"]}
    weights = np.asarray([supplied.get(k, 0) for k in COMPONENTS], dtype=float)
    if not np.isfinite(weights).all() or np.any(weights < -1e-10):
        raise ValueError("stack_weights must be finite and non-negative")
    weights = np.maximum(weights, 0)
    if weights.sum() <= 0:
        raise ValueError("stack_weights must have positive total weight")
    return dict(zip(COMPONENTS, (weights / weights.sum()).tolist()))


def _predict(model: Any, frame: pd.DataFrame, label: str) -> np.ndarray:
    values = np.asarray(model.predict(frame), dtype=float).reshape(-1)
    if len(values) != len(frame) or not np.isfinite(values).all():
        raise ValueError(f"{label} returned non-finite or incorrectly sized predictions")
    return np.clip(values, 0, 100)


def _nearest(description: Mapping) -> dict:
    index = description.get("nearest_archetype")
    center = description.get("nearest_center", {})
    clusters = description.get("archetypes", [])
    cluster = next((c for c in clusters if c.get("archetype") == index), {})
    return {
        "index": index,
        "height_cm": center.get("height_cm"),
        "weight_kg": center.get("weight_kg"),
        "mean_target": cluster.get("outcome_mean"),
        "membership": description.get("probabilities", {}).get(str(index)),
    }


def _empty_result(key: str, role: str, status: str, message: str) -> dict:
    return {
        "head": key,
        "role": role,
        "role_label": ROLE_LABELS.get(key, role),
        "status": status,
        "efficacy_rating": None,
        "exploratory_estimate": None,
        "interval": None,
        "physical_fit": None,
        "out_of_domain": None,
        "expert_predictions": {},
        "nearest_archetype": None,
        "explanation": [message],
        "warnings": [],
    }


def score_profiles(artifact: dict, profiles: pd.DataFrame) -> list[dict[str, dict]]:
    """Score a roster in batches, returning head-keyed results in input order.

    The only learned input columns are height_cm and weight_kg. Missing bodies
    and known non-adults are retained as unavailable, without imputation. The
    optional age field is used solely to enforce the adult reference domain.
    """
    if tuple(artifact.get("features", ())) != MODEL_FEATURES:
        raise ValueError("Portal requires the saved height_cm/weight_kg feature contract")
    frame = prepare_profile_features(profiles).reset_index(drop=True)
    body = frame[list(MODEL_FEATURES)].to_numpy(float)
    complete = np.isfinite(body).all(axis=1) & (body > 0).all(axis=1)
    adult = frame.age.isna().to_numpy() | frame.age.between(18, 100).to_numpy()
    valid = complete & adult
    positions = np.flatnonzero(valid)
    inputs = frame.loc[valid, list(MODEL_FEATURES)].reset_index(drop=True)
    values = inputs.to_numpy(float)
    results: list[dict[str, dict]] = [{} for _ in range(len(frame))]
    for key, head in artifact["heads"].items():
        role = _spec_field(head["spec"], "role")
        summary = head.get("summary", {})
        evidence = summary.get("status", "insufficient_support")
        fitted = "experts" in head and evidence != "insufficient_support"
        if fitted and evidence not in {"evidence_supported", "no_evidence"}:
            raise ValueError(f"Unrecognized head evidence status: {evidence}")
        for index in range(len(frame)):
            if not complete[index]:
                result = _empty_result(
                    key,
                    role,
                    "missing_measurements",
                    "Height and weight are both required; missing values were not imputed.",
                )
            elif not adult[index]:
                result = _empty_result(
                    key,
                    role,
                    "insufficient_support",
                    "The saved model uses adult athlete references; this recorded age is outside its supported adult range.",
                )
            else:
                result = _empty_result(
                    key,
                    role,
                    "insufficient_support",
                    "Too few independent eligible athletes to fit and evaluate this role.",
                )
            results[index][key] = result
        if not fitted or not len(inputs):
            continue
        weights = _weights(head)
        method = head.get("selected_method")
        if method not in {"stack", "baseline"}:
            raise ValueError("selected_method must be 'stack' or 'baseline'")
        predictions = {"baseline50": np.full(len(inputs), 50.0)}
        for name in EXPERT_KEYS:
            predictions[name] = _predict(head["experts"][name], inputs, f"{key}/{name}")
        center = _finite_vector(head.get("shared_center"), name="shared_center", length=2)
        scale = _finite_vector(head.get("shared_scale"), name="shared_scale", length=2)
        if np.any(scale <= 0):
            raise ValueError("shared_scale must be positive")
        standardized = pd.DataFrame((values - center) / scale, columns=MODEL_FEATURES)
        predictions["shared"] = _predict(artifact["shared_expert"], standardized, "shared expert")
        stack = np.clip(sum(weights[k] * predictions[k] for k in COMPONENTS), 0, 100)
        selected = stack if method == "stack" else predictions["baseline50"]
        radius = float(head.get("calibration_radius"))
        if np.isnan(radius) or radius < 0:
            raise ValueError("calibration_radius must be non-negative")
        intervals = np.column_stack((np.clip(selected - radius, 0, 100), np.clip(selected + radius, 0, 100)))
        reference = head["body_reference"]
        body_center = _finite_vector(reference.get("center"), name="body_reference.center", length=2)
        inverse = _finite_matrix(
            reference.get("inverse_covariance"), name="body_reference.inverse_covariance", shape=(2, 2)
        )
        lower = _finite_vector(reference.get("lower"), name="body_reference.lower", length=2)
        upper = _finite_vector(reference.get("upper"), name="body_reference.upper", length=2)
        if np.any(lower > upper):
            raise ValueError("body_reference.lower cannot exceed body_reference.upper")
        delta = values - body_center
        # Keep the interactive scorer's exact 2x2 operation order. A fully
        # vectorized contraction can differ by one ulp at a training-distance
        # tie, incorrectly shifting the empirical physical-fit percentile.
        # These tiny quadratic forms are cheap; all fitted-model inference is
        # still batched once per expert, including archetype explanations.
        distances = np.fromiter((d @ inverse @ d for d in delta), dtype=float, count=len(delta))
        if np.any(distances < -1e-8):
            raise ValueError("Invalid body-reference inverse covariance")
        distances = np.maximum(distances, 0)
        outside = ((values < lower) | (values > upper)).any(axis=1)
        ood = outside | (distances > OOD_MAHALANOBIS_SQUARED)
        observed_distances = np.asarray(reference.get("distances", []), dtype=float)
        observed_distances = observed_distances[np.isfinite(observed_distances) & (observed_distances >= 0)]
        fits = (
            100
            * (
                1
                - np.searchsorted(np.sort(observed_distances), distances, side="right")
                / len(observed_distances)
            )
            if len(observed_distances)
            else [None] * len(inputs)
        )
        descriptions = head["experts"]["archetype"].describe(inputs)
        if not isinstance(descriptions, list) or len(descriptions) != len(inputs):
            raise ValueError("Archetype describe() returned an incorrectly sized batch")
        for offset, index in enumerate(positions):
            under_review = key == DATA_REVIEW_HEAD
            status = (
                "data_review"
                if under_review
                else "out_of_domain"
                if ood[offset]
                else "provisional"
                if evidence == "evidence_supported"
                else "no_evidence"
            )
            warnings = []
            if under_review:
                warnings.append(DATA_REVIEW_NOTE)
            if ood[offset]:
                warnings.append("Outside the training body domain; this is unsupported extrapolation.")
            if evidence == "no_evidence":
                warnings.append("Held-out checks did not establish improvement over the neutral 50 baseline.")
            if not summary.get("improvement_statistically_established", False):
                warnings.append("Predictive improvement is not statistically established.")
            coverage = summary.get("metrics", {}).get("interval_90_empirical_coverage")
            if coverage is not None and coverage < 0.8:
                warnings.append(
                    f"The nominal 90% interval covered only {100 * coverage:.1f}% of test athletes."
                )
            explanation = [
                "Only listed height and weight drive this fitted comparison; age and event totals are not learned inputs.",
                "Physical fit describes body-profile similarity, not skill or a probability of success.",
            ]
            if method == "baseline":
                explanation.append(
                    "Model selection chose the neutral baseline: the selected estimate is exactly 50, not a personalized forecast."
                )
            else:
                explanation.append(
                    "The selected estimate blends independently refitted role experts; it is not a blend of the earlier sport classifiers."
                )
            results[index][key] = {
                "head": key,
                "role": role,
                "role_label": ROLE_LABELS.get(key, role),
                "status": status,
                "efficacy_rating": float(selected[offset]) if status == "provisional" else None,
                "exploratory_estimate": float(selected[offset]),
                "interval": intervals[offset].tolist(),
                "physical_fit": fits[offset],
                "out_of_domain": bool(ood[offset]),
                "expert_predictions": {k: float(v[offset]) for k, v in predictions.items()},
                "nearest_archetype": _nearest(descriptions[offset]),
                "explanation": explanation,
                "warnings": warnings,
            }
    return _safe(results)


def _source_commit(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _head_metadata(key: str, head: Mapping, training: pd.DataFrame) -> dict:
    spec, summary = head["spec"], head.get("summary", {})
    role = _spec_field(spec, "role")
    domains = spec.get("domains", {}) if isinstance(spec, Mapping) else spec.domains
    fitted = "experts" in head
    candidate = _weights(head) if fitted else None
    active = (
        {k: float(k == "baseline50") for k in COMPONENTS}
        if head.get("selected_method") == "baseline"
        else candidate
    )
    reference = head.get("body_reference", {})
    reference_rows = training.loc[training["head"].eq(key)]
    medians = reference_rows[list(MODEL_FEATURES)].median() if len(reference_rows) else pd.Series(dtype=float)
    archetypes = []
    archetype = head.get("experts", {}).get("archetype")
    centers = getattr(archetype, "cluster_centers_original_", [])
    names = list(getattr(archetype, "model_features_", MODEL_FEATURES))
    for index, center in enumerate(centers):
        body = dict(zip(names, center))
        means = getattr(archetype, "cluster_means_", [])
        support = getattr(archetype, "cluster_support_", [])
        archetypes.append(
            {
                "index": index,
                "height_cm": body.get("height_cm"),
                "weight_kg": body.get("weight_kg"),
                "mean_target": means[index] if len(means) > index else None,
                "support": support[index] if len(support) > index else None,
            }
        )
    limitations = [
        "Contemporaneous elite-peer activity target, not a future forecast or sport-transfer validation.",
        "Height/weight only; coach assessments, awareness, speed, wingspan and event totals are not prediction inputs.",
        "Listed physical measurements are not verified annually; physical similarity is not efficacy.",
    ]
    limitations.extend(summary.get("abstention_reasons", []))
    if key == DATA_REVIEW_HEAD:
        limitations.append(DATA_REVIEW_NOTE)
    return {
        "role_label": ROLE_LABELS.get(key, role),
        "status": summary.get("status", "insufficient_support"),
        "target_domains": domains,
        "selected_method": head.get("selected_method"),
        "candidate_weights": candidate,
        "active_weights": active,
        "train_rows": summary.get("train_rows"),
        "train_athletes": summary.get("train_athletes"),
        "calibration_athletes": summary.get("calibration_athletes"),
        "test_athletes": summary.get("test_athletes"),
        "metrics": summary.get("metrics", {}),
        "nested_cv": summary.get("nested_cv", {}),
        "evaluation": summary.get("evaluation"),
        "evidence_grade": summary.get("evidence_grade"),
        "improvement_statistically_established": summary.get("improvement_statistically_established", False),
        "bootstrap": summary.get("mse_improvement_cluster_bootstrap", {}),
        "interval_diagnostic": summary.get("interval_diagnostic", {}),
        "limitations": limitations,
        "reference": {
            "median_height_cm": medians.get("height_cm"),
            "median_weight_kg": medians.get("weight_kg"),
            "center": reference.get("center"),
            "ranges": {
                "height_cm": [reference["lower"][0], reference["upper"][0]],
                "weight_kg": [reference["lower"][1], reference["upper"][1]],
            }
            if reference
            else {},
        },
        "archetypes": archetypes,
        "data_review": key == DATA_REVIEW_HEAD,
    }


def _sport_results(player: dict, scores: Mapping[str, dict]) -> dict:
    grouped = {}
    for sport in SPORTS:
        roles = [dict(v) for k, v in scores.items() if k.startswith(sport + ":")]
        if not roles:
            continue
        rated = [r for r in roles if r["efficacy_rating"] is not None]
        best = sorted(rated, key=lambda r: (-r["efficacy_rating"], r["role"]))[0] if rated else None
        native = next((r for r in roles if sport == player["sport"] and r["role"] == player["role"]), None)
        fallback = max(roles, key=lambda r: r["physical_fit"] if r["physical_fit"] is not None else -1)
        default = native or best or fallback
        if sport == player["sport"] and native is None:
            warning = "No fitted head exists for this player's recorded role; this is a comparison with another role, not a rating of their actual role."
            for role in roles:
                role["warnings"] = [*role["warnings"], warning]
        grouped[sport] = {
            "default_role": default["role"],
            "best_role": best["role"] if best else None,
            "efficacy_rating": best["efficacy_rating"] if best else None,
            "roles": roles,
        }
    return grouped


def _observed(row: pd.Series, partial_blocks: set[str]) -> dict:
    sport = row.sport
    notes = ["Native-season event totals are descriptive context only; they are not inference inputs."]
    if pd.notna(row.get("opportunity")) and row.opportunity == 0:
        notes.append(
            "No playing opportunity is observed in this snapshot. Any displayed model estimate is a body-only comparison, not observed playing efficacy."
        )
    if sport == "nhl":
        notes.append(
            "Appearance-based regular-season skaters only; zero-game roster players and goalies are outside this source universe."
        )
    if sport == "nfl":
        notes.append(
            "Opportunity is observed defensive player-plays, not a guaranteed complete official snap total."
        )
        if (
            row.get("games_missing_participation", 0) > 0
            or row.get("event_credits_without_participation", 0) > 0
        ):
            notes.append(
                "Some participation coverage is missing or event credits have no matched participation."
            )
    if sport == "nba" and row.get("event_total_status") != "sum_of_observed_regular_season_box_scores":
        notes.append(
            "Check the cached roster/box-score coverage before interpreting unavailable or zero event totals."
        )
    withheld_blocks = sport == "epl" and (row.role == "DEF" or str(row.player_id) in partial_blocks)
    if withheld_blocks:
        notes.append(
            "Blocks are withheld: defender targets are under review and/or some match-level block values are missing; a partial sum is not a complete season total."
        )
    if sport == "epl":
        notes.append(
            "FPL archive player universe; defensive metrics use the enhanced 2025–26 match-detail source."
        )
    notes.append(
        "Measurement dates are unknown or unverified; listed height/weight must not be treated as annual measured change."
    )
    metrics = [
        {
            "key": key,
            "label": label,
            "value": None if key == "blocks" and withheld_blocks else row.get(key),
            "unit": "credits" if sport == "nfl" else "count",
        }
        for key, label in EVENTS[sport]
    ]
    return {
        "metrics": metrics,
        "opportunity": row.get("opportunity"),
        "opportunity_unit": "observed defensive player-plays" if sport == "nfl" else "minutes",
        "quality_notes": notes,
    }


def build_portal(root: Path, output_dir: Path | None = None) -> dict:
    """Write manifest + per-player JSON from local 2025 panels and saved models.

    ``output_dir`` is the website root (defaults to ``root / 'portal'``).
    Existing unrelated files are never deleted; the new manifest names exactly
    the current generated player-detail set. Return the JSON-safe manifest.
    """
    root = Path(root).resolve()
    output = Path(output_dir).resolve() if output_dir is not None else root / "portal"
    artifact = load_ensemble(root)  # Includes the registered model SHA-256 check.
    panels, sources = [], {}
    for sport in SPORTS:
        path = root / "data" / "processed" / sport / "player_seasons.parquet"
        fingerprint = sha256(path)
        expected = artifact.get("data_sources", {}).get(sport, {}).get("sha256")
        if expected and fingerprint != expected:
            raise ValueError(f"{sport} panel differs from the saved model's training snapshot")
        frame = prepare_profile_features(pd.read_parquet(path))
        frame["sport"] = sport
        frame["athlete_id"] = sport + ":" + frame.player_id.astype(str)
        if frame.duplicated(["athlete_id", "season"]).any():
            raise ValueError(f"Duplicate player-season keys in {sport}")
        frame["partition"] = frame.athlete_id.map(athlete_partition)
        panels.append(frame)
        sources[sport] = {
            "path": str(path.relative_to(root)),
            "sha256": fingerprint,
            "rows": len(frame),
            "snapshot_rows": int(frame.season.eq(2025).sum()),
            "model_snapshot_sha256": expected,
            "model_snapshot_matches": fingerprint == expected if expected else None,
        }
    all_rows = pd.concat(panels, ignore_index=True)
    training_parts = []
    for key, head in artifact["heads"].items():
        if "experts" not in head:
            continue
        part = eligible_rows(all_rows.loc[all_rows.season.between(2021, 2025)], head["spec"])
        part = part.loc[part.partition.eq("train")].copy()
        part["head"] = key
        training_parts.append(part)
    training = (
        pd.concat(training_parts, ignore_index=True)
        if training_parts
        else pd.DataFrame(columns=["athlete_id", "head", *MODEL_FEATURES])
    )
    trained_ids = set(training.athlete_id)
    snapshot = (
        all_rows.loc[all_rows.season.eq(2025)]
        .sort_values(["sport", "name", "athlete_id"])
        .reset_index(drop=True)
    )
    if snapshot.athlete_id.duplicated().any():
        raise ValueError("Duplicate athlete IDs in the portal snapshot")
    scores = score_profiles(artifact, snapshot)
    game_path = root / "data" / "processed" / "epl" / "player_games.parquet"
    partial_blocks = set()
    if game_path.exists():
        games = pd.read_parquet(game_path, columns=["player_id", "season", "blocks"])
        counts = games.loc[games.season.eq(2025)].groupby("player_id").blocks.agg(["size", "count"])
        partial_blocks = set(counts.index[counts["count"] < counts["size"]].astype(str))
        sources["epl_games"] = {
            "path": str(game_path.relative_to(root)),
            "sha256": sha256(game_path),
            "purpose": "Block-completeness audit only; not a model input",
        }
    else:
        # Cannot establish completeness; withholding all EPL block totals is safer.
        partial_blocks = set(snapshot.loc[snapshot.sport.eq("epl"), "player_id"].astype(str))
    catalog = []
    for index, row in snapshot.iterrows():
        body = np.asarray([row.height_cm, row.weight_kg], dtype=float)
        player = {
            "id": row.athlete_id,
            "name": row["name"],
            "sport": row.sport,
            "team": row.get("teams") if pd.notna(row.get("teams")) else row.get("team"),
            "role": row.role,
            "season": 2025,
            "height_cm": row.height_cm,
            "weight_kg": row.weight_kg,
            "age": row.age,
            "has_measurements": bool(np.isfinite(body).all() and (body > 0).all()),
            "detail_path": "data/players/"
            + hashlib.sha256(row.athlete_id.encode()).hexdigest()[:20]
            + ".json",
        }
        player = _safe(player)
        detail = {
            "player": player,
            "sport_results": _sport_results(player, scores[index]),
            "observed": _observed(row, partial_blocks),
            "model_partition": row.partition,
            "included_in_training": row.athlete_id in trained_ids,
        }
        _write(output / player["detail_path"], detail)
        catalog.append(player)
    measured = [p for p in catalog if p["has_measurements"]]
    preferred = next(
        (
            p
            for name in ("T.J. Watt", "T. J. Watt", "Sidney Crosby", "Connor McDavid")
            for p in measured
            if p["name"] == name
        ),
        None,
    )
    default = preferred or (measured[0] if measured else catalog[0] if catalog else None)
    model_path = root / "models" / "ensemble" / "unified.joblib"
    exporter_path = Path(__file__)
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": {
            "version": artifact["version"],
            "trained_at": artifact.get("trained_at"),
            "sha256": sha256(model_path),
            "learned_features": list(MODEL_FEATURES),
        },
        "snapshot": {"season": 2025, "label": "2025 NFL · 2025–26 NBA, NHL & Premier League"},
        "sports": [
            {
                "id": sport,
                "label": label,
                "season_label": season,
                "roles": [
                    {
                        "id": _spec_field(h["spec"], "role"),
                        "label": ROLE_LABELS.get(k, _spec_field(h["spec"], "role")),
                        "head": k,
                    }
                    for k, h in artifact["heads"].items()
                    if _spec_field(h["spec"], "sport") == sport
                ],
            }
            for sport, (label, season) in SPORTS.items()
        ],
        "players": catalog,
        "defaults": {
            "player_id": default["id"] if default else None,
            "sport": default["sport"] if default else "nfl",
        },
        "heads": {k: _head_metadata(k, h, training) for k, h in artifact["heads"].items()},
        "sources": SOURCES,
        "datasets": sources,
        "provenance": {
            "source_commit": _source_commit(root),
            "exporter_sha256": sha256(exporter_path),
            "snapshot_matches_model_datasets": all(
                sources[s]["model_snapshot_matches"] is True for s in SPORTS
            ),
        },
        "counts": {
            "players": len(catalog),
            "players_with_measurements": len(measured),
            "fitted_heads": sum("experts" in h for h in artifact["heads"].values()),
        },
        "interpretation": "Exploratory body-associated possession/disruption activity relative to elite peers in a role. Not a probability of roster selection, a sport-switching forecast, or a causal measure of defensive ability.",
        "limitations": [
            "Only height and weight are learned. Awareness, reaction speed, agility, technique and coaching context are not quantified.",
            "Models use contemporaneous 2025 outcomes for evaluation; training includes 2025 athletes in the training partition. This is not a future-season forecast.",
            "Physical-fit percentiles are body similarity only and are never multiplied into the efficacy rating.",
            "Public sources have unequal player universes and measurement dates; this catalog is not a verified complete all-rostered-player census.",
            "A point-gate pass is provisional, not statistically established predictive improvement.",
            DATA_REVIEW_NOTE,
            "Source terms may restrict redistribution. Private presentation does not replace permission or licensing review.",
        ],
    }
    manifest = _safe(manifest)
    _write(output / "data" / "manifest.json", manifest)
    return manifest
