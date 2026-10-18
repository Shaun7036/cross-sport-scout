"""Cross-fitted sport/role efficacy ensemble and reproducible evaluation.

The common response is a contemporary elite-peer activity percentile, not a
probability of playing professionally. Every target reference and expert is
re-fitted inside athlete-disjoint folds. No held-out event labels are predictors.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures

from possession_lab.ensemble_evaluation import (
    bootstrap_improvement,
    evaluate_predictions,
    finite_conformal_radius,
    fit_simplex_weights,
)
from possession_lab.ensemble_experts import make_experts
from possession_lab.ensemble_features import prepare_profile_features
from possession_lab.ensemble_targets import HeadSpec, SeasonalRoleTarget, athlete_weights, head_specs
from possession_lab.io import sha256, write_json

VERSION = "efficacy-ensemble-v1"
# Freeze cohort assignments even when the model version changes. This value
# deliberately matches the initial v1 run, without coupling future experiments.
SPLIT_SALT = "efficacy-ensemble-v1"
FEATURES = ["height_cm", "weight_kg"]
EXPERTS = ["baseline50", "archetype", "ridge", "hist_gradient_boosting", "extra_trees", "shared"]


def athlete_partition(athlete_id: str) -> str:
    """Stable identity partition, independent of row order, season and outcomes."""
    value = int(hashlib.sha256(f"{SPLIT_SALT}:{athlete_id}".encode()).hexdigest()[:12], 16) % 10
    return "train" if value < 6 else "calibration" if value < 8 else "test"


def eligible_rows(frame: pd.DataFrame, spec: HeadSpec) -> pd.DataFrame:
    """Never impute outcome labels or required body measurements."""
    metrics = sorted({m for d in spec.domains.values() for m in d["metrics"]})
    part = frame.loc[(frame.sport == spec.sport) & (frame.role == spec.role)].copy()
    if spec.sport == "epl":
        part = part.loc[part.season == 2025].copy()
    required = ["opportunity", *FEATURES, *metrics]
    for name in required:
        part[name] = pd.to_numeric(part[name], errors="coerce")
    valid = np.isfinite(part[required]).all(axis=1)
    valid &= part.opportunity.ge(spec.min_opportunity)
    valid &= part.height_cm.gt(0) & part.weight_kg.gt(0)
    valid &= part[metrics].ge(0).all(axis=1)
    if "age" in part:
        valid &= part.age.isna() | part.age.ge(18)
    return part.loc[valid].copy()


def load_panels(root: Path) -> tuple[pd.DataFrame, dict]:
    panels, sources = [], {}
    for sport in ["nfl", "nba", "nhl", "epl"]:
        path = root / "data" / "processed" / sport / "player_seasons.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Run {sport} acquisition/processing first: {path}")
        frame = prepare_profile_features(pd.read_parquet(path))
        frame = frame.loc[frame.season.between(2021, 2025)].copy()
        frame["sport"] = sport
        frame["athlete_id"] = sport + ":" + frame.player_id.astype(str)
        frame["partition"] = frame.athlete_id.map(athlete_partition)
        if frame.duplicated(["athlete_id", "season"]).any():
            raise ValueError(f"Duplicate player-season keys in {sport}")
        panels.append(frame)
        sources[sport] = {
            "path": str(path.relative_to(root)),
            "sha256": sha256(path),
            "rows": len(frame),
            "athletes": frame.athlete_id.nunique(),
        }
    all_rows = pd.concat(panels, ignore_index=True)
    eligible = pd.concat([eligible_rows(all_rows, s) for s in head_specs().values()])
    eligible = eligible.sort_index().copy()
    eligible["row_id"] = eligible.index
    eligible["head"] = eligible.sport + ":" + eligible.role
    return eligible, sources


def group_folds(frame: pd.DataFrame, n_splits: int = 3):
    """All seasons and any role changes for an athlete remain in one fold."""
    groups = frame.athlete_id
    if groups.nunique() < n_splits:
        raise ValueError("Not enough independent athletes for cross-fitting")
    yield from GroupKFold(n_splits=n_splits).split(frame, groups=groups)


def _weighted_location(frame):
    values = frame[FEATURES].to_numpy(float)
    weights = athlete_weights(frame)
    center = np.average(values, axis=0, weights=weights)
    scale = np.sqrt(np.average((values - center) ** 2, axis=0, weights=weights))
    return center, np.maximum(scale, 1.0)


def _fit_estimator(estimator, frame, target, weights):
    if hasattr(estimator, "steps"):
        estimator.fit(frame, target, model__sample_weight=weights)
    else:
        estimator.fit(frame, target, sample_weight=weights)
    return estimator


def fit_experts(frame: pd.DataFrame, specs: dict[str, HeadSpec], *, fast=False) -> dict:
    """Fit one collection of experts on training athletes only."""
    bundle = {"heads": {}, "features": FEATURES, "version": VERSION}
    shared_x, shared_y, shared_w = [], [], []
    sport_heads = Counter(s.sport for s in specs.values())
    for key, spec in specs.items():
        part = frame.loc[frame["head"] == key]
        if part.athlete_id.nunique() < 10:
            continue
        target = SeasonalRoleTarget(spec).fit(part)
        y = target.transform(part).efficacy_target.to_numpy(float)
        weights = athlete_weights(part)
        experts = make_experts(FEATURES)
        # BMI is a deterministic restatement of the two dimensions and must not
        # acquire a third vote in Euclidean archetype distances.
        experts["archetype"].set_params(include_bmi=False)
        if fast:
            experts["extra_trees"].set_params(model__n_estimators=25)
            experts["hist_gradient_boosting"].set_params(model__max_iter=35)
            experts["archetype"].set_params(n_init=3)
        for expert in experts.values():
            _fit_estimator(expert, part, y, weights)
        center, scale = _weighted_location(part)
        z = (part[FEATURES] - center) / scale
        shared_x.append(z)
        shared_y.append(y)
        # Equal sport mass, then equal role mass, then equal athlete mass.
        shared_w.append(weights / weights.sum() / sport_heads[spec.sport])
        bundle["heads"][key] = {
            "spec": spec,
            "target": target,
            "experts": experts,
            "shared_center": center,
            "shared_scale": scale,
        }
    if not shared_x:
        raise ValueError("No supported sport-role head has enough training athletes")
    weights = np.concatenate(shared_w)
    weights *= len(weights) / weights.sum()
    shared = make_pipeline(PolynomialFeatures(degree=2, include_bias=False), Ridge(alpha=100.0))
    shared.fit(pd.concat(shared_x), np.concatenate(shared_y), ridge__sample_weight=weights)
    bundle["shared_expert"] = shared
    return bundle


def predict_experts(bundle: dict, frame: pd.DataFrame, *, targets=True) -> pd.DataFrame:
    """Produce a fixed-order matrix; no inference-time re-ranking of candidates."""
    result = []
    for key, head in bundle["heads"].items():
        part = frame.loc[frame["head"] == key]
        if not len(part):
            continue
        row = part[["row_id", "athlete_id", "head", "season"]].copy()
        row["baseline50"] = 50.0
        for name, expert in head["experts"].items():
            row[name] = np.clip(expert.predict(part), 0, 100)
        z = (part[FEATURES] - head["shared_center"]) / head["shared_scale"]
        row["shared"] = np.clip(bundle["shared_expert"].predict(z), 0, 100)
        if targets:
            # All v1 folds have contemporaneous reference rows in every season.
            row["target"] = head["target"].transform(part).efficacy_target
        result.append(row)
    return pd.concat(result).sort_index() if result else pd.DataFrame()


def crossfit(frame: pd.DataFrame, specs, *, fast=False, n_splits=3) -> pd.DataFrame:
    predictions = []
    for fold, (train_idx, val_idx) in enumerate(group_folds(frame, n_splits)):
        train, val = frame.iloc[train_idx], frame.iloc[val_idx]
        assert not set(train.athlete_id) & set(val.athlete_id)
        bundle = fit_experts(train, specs, fast=fast)
        pred = predict_experts(bundle, val)
        pred["fold"] = fold
        predictions.append(pred)
    return pd.concat(predictions).sort_index()


def fit_stacks(predictions: pd.DataFrame, keys) -> dict:
    stacks = {}
    for key in keys:
        part = predictions.loc[predictions["head"] == key]
        if not len(part):
            stacks[key] = np.array([1.0, 0, 0, 0, 0, 0])
        else:
            stacks[key] = fit_simplex_weights(
                part[EXPERTS].to_numpy(), part.target.to_numpy(), athlete_weights(part)
            )
    return stacks


def nested_predictions(frame, specs, *, fast=False):
    """Outer folds assess a stack whose weights came from inner OOF rows."""
    results = []
    for fold, (train_idx, val_idx) in enumerate(group_folds(frame)):
        print(f"Nested ensemble evaluation: outer fold {fold + 1}/3", flush=True)
        train, val = frame.iloc[train_idx], frame.iloc[val_idx]
        inner = crossfit(train, specs, fast=fast)
        weights = fit_stacks(inner, specs)
        bundle = fit_experts(train, specs, fast=fast)
        pred = predict_experts(bundle, val)
        pred["stack"] = np.nan
        for key, weight in weights.items():
            mask = pred["head"] == key
            pred.loc[mask, "stack"] = pred.loc[mask, EXPERTS].to_numpy() @ weight
        pred["outer_fold"] = fold
        results.append(pred)
    return pd.concat(results).sort_index()


def body_reference(frame):
    # Undated measurements repeat across careers; one latest row per athlete.
    reference = frame.sort_values("season").drop_duplicates("athlete_id", keep="last")
    values = reference[FEATURES].to_numpy(float)
    center = values.mean(axis=0)
    covariance = np.cov(values, rowvar=False)
    # Small diagonal stabilization is important for narrow role-specific builds.
    covariance = 0.95 * covariance + 0.05 * np.diag(np.maximum(np.diag(covariance), 1.0))
    inverse = np.linalg.pinv(covariance)
    delta = values - center
    distances = np.einsum("ij,jk,ik->i", delta, inverse, delta)
    return {
        "center": center,
        "inverse_covariance": inverse,
        "distances": distances,
        "lower": values.min(axis=0),
        "upper": values.max(axis=0),
    }


def _metrics(part, column):
    return evaluate_predictions(part.target.to_numpy(), part[column].to_numpy(), part.athlete_id.to_numpy())


def _sensitivity(frame, test, spec, original):
    # Compare the construct with equal domain and equal atomic weights. These
    # are not new trained models or opportunities to tune test performance.
    equal = HeadSpec(
        spec.sport,
        spec.role,
        spec.min_opportunity,
        {
            name: {"weight": 1.0, "metrics": {m: 1.0 for m in d["metrics"]}}
            for name, d in spec.domains.items()
        },
        spec.evaluation,
    )
    alternate = SeasonalRoleTarget(equal).fit(frame).transform(test).efficacy_target.to_numpy()
    rho = float(spearmanr(original, alternate).statistic) if len(test) > 2 else np.nan
    return {
        "specification": "equal domain and equal within-domain atomic weights",
        "target_rank_correlation": rho if np.isfinite(rho) else None,
        "mean_absolute_percentile_change": float(np.mean(np.abs(original - alternate))),
    }


def evidence_diagnostics(summary):
    """Separate exploratory point checks from established improvement evidence.

    These diagnostics do not choose or retune a predictor. All test results,
    including unsuccessful heads and undercoverage, remain visible.
    """
    if "metrics" not in summary:
        return summary
    summary = dict(summary)
    test, cv = summary["metrics"], summary["nested_cv"]
    reasons = []
    if (cv["relative_mse_improvement"] or 0) <= 0.01:
        reasons.append("Nested athlete-heldout CV did not improve MSE by more than 1%.")
    if (cv["spearman"] or 0) <= 0:
        reasons.append("Nested CV did not show positive rank association.")
    if (test["relative_mse_improvement"] or 0) <= 0:
        reasons.append("Frozen test MSE did not improve over neutral 50.")
    if (test["spearman"] or 0) <= 0:
        reasons.append("Frozen test did not show positive rank association.")
    if summary["test_athletes"] < 15:
        reasons.append("Fewer than 15 independent test athletes.")
    if summary["calibration_athletes"] < 9:
        reasons.append("Fewer than 9 independent calibration athletes.")
    lower = summary["mse_improvement_cluster_bootstrap"]["lower95"]
    summary["improvement_statistically_established"] = lower is not None and lower > 0
    summary["evidence_grade"] = (
        "provisional_point_gate_passed"
        if summary["status"] == "evidence_supported"
        else "insufficient_predictive_evidence"
    )
    summary["abstention_reasons"] = reasons
    summary["interval_diagnostic"] = (
        "Observed test coverage is below 80% for a nominal 90% interval; these intervals are not well calibrated. Do not interpret their nominal level as reliable."
        if test["interval_90_empirical_coverage"] < 0.8
        else "Empirical test coverage is reported, not guaranteed; sample sizes and distribution shift limit interpretation."
    )
    return summary


def train_ensemble(root: Path, *, fast=False) -> dict:
    root = Path(root)
    frame, sources = load_panels(root)
    all_specs = head_specs()
    train = frame.loc[frame.partition == "train"].copy()
    calibration = frame.loc[(frame.partition == "calibration") & (frame.season == 2025)].copy()
    test = frame.loc[(frame.partition == "test") & (frame.season == 2025)].copy()
    assert not set(train.athlete_id) & (set(calibration.athlete_id) | set(test.athlete_id))
    assert not set(calibration.athlete_id) & set(test.athlete_id)
    specs, skipped = {}, {}
    for key, spec in all_specs.items():
        part = train.loc[train["head"] == key]
        total = frame.loc[frame["head"] == key].athlete_id.nunique()
        if part.athlete_id.nunique() < 50:
            skipped[key] = {
                "spec": spec,
                "summary": {
                    "status": "insufficient_support",
                    "train_athletes": part.athlete_id.nunique(),
                    "eligible_athletes": total,
                    "reason": "Requires at least 50 measured training athletes; held-out counts never decide which experts are trained.",
                },
            }
        else:
            specs[key] = spec
    train = train.loc[train["head"].isin(specs)].copy()
    print(f"Training {len(specs)} supported heads; {len(skipped)} abstaining for low coverage", flush=True)
    nested = nested_predictions(train, specs, fast=fast)
    print("Fitting final athlete-disjoint OOF stack weights", flush=True)
    oof = crossfit(train, specs, fast=fast)
    weights = fit_stacks(oof, specs)
    artifact = fit_experts(train, specs, fast=fast)
    cal_pred = predict_experts(artifact, calibration)
    test_pred = predict_experts(artifact, test)
    report, evaluation = {}, []
    for key, head in artifact["heads"].items():
        training_part = train.loc[train["head"] == key]
        outer = nested.loc[nested["head"] == key]
        metrics_cv = _metrics(outer, "stack")
        cv_pass = metrics_cv["relative_mse_improvement"] > 0.01 and (metrics_cv["spearman"] or 0) > 0
        method = "stack" if cv_pass else "baseline"
        stack = weights[key]
        head["stack_weights"] = dict(zip(EXPERTS, stack.tolist()))
        head["selected_method"] = method
        head["body_reference"] = body_reference(training_part)
        for predictions in [cal_pred, test_pred]:
            mask = predictions["head"] == key
            predictions.loc[mask, "candidate_stack"] = predictions.loc[mask, EXPERTS].to_numpy() @ stack
            predictions.loc[mask, "prediction"] = (
                predictions.loc[mask, "candidate_stack"] if cv_pass else 50.0
            )
        cal = cal_pred.loc[cal_pred["head"] == key].sort_values("season").drop_duplicates("athlete_id")
        held = test_pred.loc[test_pred["head"] == key].sort_values("season").drop_duplicates("athlete_id")
        residuals = np.abs(cal.target - cal.prediction)
        radius = finite_conformal_radius(residuals.to_numpy(), coverage=0.9)
        head["calibration_radius"] = radius
        metrics = _metrics(held, "prediction")
        candidate_metrics = _metrics(held, "candidate_stack")
        bootstrap = bootstrap_improvement(
            held.target.to_numpy(), held.prediction.to_numpy(), held.athlete_id.to_numpy()
        )
        # This is a release/evidence gate, not model selection or test tuning.
        # Frozen weights and predictions are reported even when the gate fails.
        supported = (
            cv_pass
            and metrics["relative_mse_improvement"] > 0
            and (metrics["spearman"] or 0) > 0
            and len(cal) >= 9
            and len(held) >= 15
        )
        test_intervals = np.column_stack(
            [np.maximum(0, held.prediction - radius), np.minimum(100, held.prediction + radius)]
        )
        coverage = np.mean((held.target >= test_intervals[:, 0]) & (held.target <= test_intervals[:, 1]))
        metrics["interval_90_empirical_coverage"] = float(coverage)
        metrics["interval_90_mean_width"] = float(np.mean(test_intervals[:, 1] - test_intervals[:, 0]))
        summary = {
            "status": "evidence_supported" if supported else "no_evidence",
            "evidence_grade": "exploratory_heldout_support"
            if supported
            else "insufficient_predictive_evidence",
            "selected_method": method,
            "train_rows": len(training_part),
            "train_athletes": training_part.athlete_id.nunique(),
            "calibration_athletes": len(cal),
            "test_athletes": len(held),
            "evaluation": head["spec"].evaluation,
            "nested_cv": metrics_cv,
            "metrics": metrics,
            "candidate_metrics": candidate_metrics,
            "mse_improvement_cluster_bootstrap": bootstrap,
            "calibration_radius": radius if np.isfinite(radius) else None,
            "target": head["target"].describe(),
            "expert_weights": head["stack_weights"],
            "target_weight_sensitivity": _sensitivity(
                training_part, test.loc[held.index], head["spec"], held.target.to_numpy()
            )
            if len(held)
            else None,
            "uncertainty": "90% split-conformal residual interval; nominal coverage is not guaranteed under drift or extrapolation.",
        }
        summary = evidence_diagnostics(summary)
        head["summary"] = summary
        report[key] = summary
        evaluation.append(
            {
                "head": key,
                "sport": head["spec"].sport,
                "role": head["spec"].role,
                "status": summary["status"],
                "train_athletes": summary["train_athletes"],
                "test_athletes": len(held),
                **metrics,
            }
        )
    artifact["heads"].update(skipped)
    report.update({key: value["summary"] for key, value in skipped.items()})
    artifact["trained_at"] = datetime.now(timezone.utc).isoformat()
    artifact["data_sources"] = sources
    artifact["fast_development_fit"] = fast
    artifact["interpretation"] = (
        "Contemporaneous elite-peer possession/disruption activity percentile; not cross-sport success probability."
    )
    directory = root / "reports" / "ensemble"
    directory.mkdir(parents=True, exist_ok=True)
    model_path = root / "models" / "ensemble" / "unified.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, model_path, compress=3)
    write_json(
        directory / "evaluation.json",
        {
            "version": VERSION,
            "features": FEATURES,
            "heads": report,
            "data_sources": sources,
            "fast_development_fit": fast,
        },
    )
    evaluation_frame = pd.DataFrame(evaluation)
    evaluation_frame.to_csv(directory / "evaluation.csv", index=False)
    pd.DataFrame(
        {key: value["stack_weights"] for key, value in artifact["heads"].items() if "stack_weights" in value}
    ).T.to_csv(directory / "expert_weights.csv", index_label="head")
    for name, predictions in [
        ("nested", nested),
        ("oof", oof),
        ("calibration", cal_pred),
        ("test", test_pred),
    ]:
        predictions.to_parquet(directory / f"predictions_{name}.parquet", index=False)
    registry = {
        "version": VERSION,
        "path": str(model_path.relative_to(root)),
        "sha256": sha256(model_path),
        "trained_at": artifact["trained_at"],
        "data_sources": sources,
        "fast_development_fit": fast,
        "features": FEATURES,
        "reference_seasons": sorted(train.season.unique().tolist()),
        "split_salt": SPLIT_SALT,
        "support_policy": "At least 50 distinct measured training athletes; no held-out eligibility-count gate.",
        "split": "SHA256 athlete partitions 60/20/20; calibration/test only 2025; train includes 2025.",
        "heads": {k: v["status"] for k, v in report.items()},
    }
    write_json(directory / "model_registry.json", registry)
    _write_report(directory, report, evaluation_frame)
    _plot_results(directory, evaluation_frame, artifact)
    print(f"Unified ensemble saved: {model_path}", flush=True)
    return registry


def load_ensemble(root: Path) -> dict:
    root = Path(root)
    registry_path = root / "reports" / "ensemble" / "model_registry.json"
    if not registry_path.exists():
        raise FileNotFoundError("Train the unified model first: possession-lab train-ensemble")
    registry = json.loads(registry_path.read_text())
    path = root / registry["path"]
    expected_path = root / "models" / "ensemble" / "unified.joblib"
    if path.resolve() != expected_path.resolve() or not path.is_file() or sha256(path) != registry["sha256"]:
        raise ValueError(
            "Unified model failed registry integrity check; retrain instead of loading unknown pickle data"
        )
    # Pickle/joblib must never be loaded from an untrusted model registry.
    return joblib.load(path)


def _write_report(directory, report, evaluation):
    rows = []
    for key, summary in report.items():
        metrics = summary.get("metrics", {})
        label = (
            "provisional_point_gate_passed"
            if summary["status"] == "evidence_supported"
            else summary["status"]
        )
        if not metrics:
            rows.append(f"| {key} | {label} | {summary['train_athletes']} | — | — | — | — |")
            continue
        rows.append(
            f"| {key} | {label} | {summary['train_athletes']} | "
            f"{summary.get('test_athletes', 0)} | {metrics.get('mae', float('nan')):.2f} | "
            f"{metrics.get('baseline_mae', float('nan')):.2f} | "
            f"{100 * metrics.get('relative_mse_improvement', float('nan')):.1f}% |"
        )
    macro = evaluation.groupby("sport")[["mae", "baseline_mae", "relative_mse_improvement"]].mean()
    text = """# Unified physical-profile efficacy ensemble

The model estimates a role-specific possession/disruption activity percentile
among eligible elite-league peers. A 70 means an estimated 70th-percentile
activity composite for that role; it is not a 70% chance of professional success.
The scoring output can abstain: experimental point estimates remain
available for auditing, while the primary efficacy rating is null when evidence
or physical-reference coverage is inadequate.

The source snapshot was previously inspected during project QA, so this is not
a blind or prospective benchmark. The highest eligible role is a browsing
summary, not a separately calibrated sport-level or sport-switching prediction.

## Frozen evaluation

Athlete identities are split deterministically into 60% training, 20% calibration,
and 20% test. All seasons for a player stay together. Models use training athletes
from 2021–25, including contemporaneous 2025 reference players. Calibration and
test use only 2025 unseen athletes. This is not a temporal/preseason forecast.
EPL has only 2025 possession labels and weaker, same-season evidence. Targets are
normalized within sport × role × season, including inside every CV fold, because
provider/scoring changes make pooled-year ranks misleading (notably NHL takeaways).

Each head blends four physical experts (ridge, boosted trees, extra trees, soft
archetypes), a shared role-standardized polynomial ridge, and a neutral 50 expert.
Nonnegative weights use inner athlete-heldout predictions. Outer athlete-heldout
CV gates selection before calibration/test are opened. A final frozen-test
release gate requires positive rank association and MSE improvement; it does not
retune weights. Evidence-supported means exploratory held-out support, not a
statistically established cross-sport transfer claim.

| Sport:role | Evidence status | Train athletes | Test athletes | MAE | Neutral-50 MAE | MSE improvement |
|---|---|---:|---:|---:|---:|---:|
""" + "\n".join(rows)
    text += "\n\nSport-macro results (equal weight per fitted role, including no-evidence heads):\n\n"
    text += "| Sport | MAE | Neutral-50 MAE | MSE improvement |\n|---|---:|---:|---:|\n"
    for sport, row in macro.iterrows():
        text += f"| {sport} | {row.mae:.2f} | {row.baseline_mae:.2f} | {100 * row.relative_mse_improvement:.1f}% |\n"
    established = sum(h.get("improvement_statistically_established", False) for h in report.values())
    point_passed = sum(h["status"] == "evidence_supported" for h in report.values())
    text += f"\n{point_passed} heads pass the exploratory point checks; {established} have a bootstrap 95% MSE-improvement interval wholly above zero. Passing a point check is not statistical confirmation.\n"
    for key, h in report.items():
        if h.get("metrics", {}).get("interval_90_empirical_coverage", 1) < 0.8:
            coverage = h["metrics"]["interval_90_empirical_coverage"]
            text += f"\nInterval warning: {key} has only {100 * coverage:.1f}% observed test coverage for its nominal 90% interval. This undercoverage must not be hidden or corrected using test labels.\n"
    text += """

## Interpretation and limits

Only height and weight are learned common-model inputs. Age/BMI and optional
testing measurements are retained/reported but not silently turned into learned
mental or agility traits. Body measurements are often undated/current snapshots,
so repeated historical rows do not establish changing annual physiques. Missing
height/weight and missing target components are excluded rather than imputed.
At least 50 measured training athletes are required per head; held-out counts do
not decide expert inclusion. EPL forwards currently lack this support, and goalkeepers are
outside the target construct. Physical similarity is separate from efficacy.

Intervals use untouched calibration-athlete residuals (90% split-conformal order
statistic); finite-sample assumptions may fail under selection or distribution
shift. The test coverage/width and athlete-cluster bootstrap improvement intervals
are in evaluation.json. Wide intervals describe genuine uncertainty and must not
be hidden. Body OOD detection abstains outside raw training bounds or the 99%
two-dimensional Mahalanobis ellipse. League, coaching, role, pace and scorer
effects remain. Hits/blocks/pressures are disruption proxies, not demonstrated
possession changes. The chosen composite weights are research assumptions;
equal-domain-weight target sensitivity is included, not optimized against test.

Run `possession-lab efficacy --profile examples/athlete.json` to inspect all roles.
See [design and methods](../../docs/ensemble_design.md) for the full contract.
"""
    (directory / "findings.md").write_text(text)


def _plot_results(directory, evaluation, artifact):
    os.environ.setdefault("MPLCONFIGDIR", str(directory.parents[1] / ".matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    table = evaluation.sort_values("head")
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), constrained_layout=True)
    axes[0].barh(table["head"], table.relative_mse_improvement * 100, color="#357f9e")
    axes[0].axvline(0, color="black", linewidth=0.7)
    axes[0].set_xlabel("Held-out MSE improvement over neutral 50 (%)")
    axes[0].set_title("Unseen 2025 athletes; frozen models")
    axes[1].barh(table["head"], table.interval_90_empirical_coverage * 100, color="#6d9d7c")
    axes[1].axvline(90, color="black", linestyle="--", linewidth=1)
    axes[1].set_xlim(0, 102)
    axes[1].set_xlabel("Empirical coverage of nominal 90% interval (%)")
    axes[1].set_title("Unseen test athletes; coverage is provisional")
    fig.savefig(directory / "evaluation.png", dpi=170)
    plt.close(fig)
    keys = sorted(k for k, h in artifact["heads"].items() if "stack_weights" in h)
    matrix = np.array([[artifact["heads"][k]["stack_weights"][e] for e in EXPERTS] for k in keys])
    fig, axis = plt.subplots(figsize=(9, 6), constrained_layout=True)
    im = axis.imshow(matrix, vmin=0, vmax=1, cmap="Blues", aspect="auto")
    axis.set_yticks(range(len(keys)), keys)
    axis.set_xticks(range(len(EXPERTS)), EXPERTS, rotation=25, ha="right")
    axis.set_title("Nonnegative ensemble weights learned from athlete-heldout OOF rows")
    for i in range(len(keys)):
        for j in range(len(EXPERTS)):
            axis.text(
                j,
                i,
                f"{matrix[i, j]:.2f}",
                ha="center",
                va="center",
                color="white" if matrix[i, j] > 0.5 else "black",
                fontsize=8,
            )
    fig.colorbar(im, ax=axis, label="Stack weight")
    fig.savefig(directory / "expert_weights.png", dpi=170)
    plt.close(fig)
