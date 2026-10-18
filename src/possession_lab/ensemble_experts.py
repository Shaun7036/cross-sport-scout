"""Reusable physical-profile experts for the cross-sport ensemble.

The sport and role heads are fitted by the ensemble orchestrator.  This module
therefore works only with within-head numeric physical measurements and avoids
learning a misleading global encoding for sport or position labels.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

DEFAULT_NUMERIC_FEATURES = ("height_cm", "weight_kg", "age")
RANDOM_STATE = 42


def _as_unique_names(values: Sequence[str], *, label: str) -> list[str]:
    names = [str(value) for value in values]
    if not names:
        raise ValueError(f"{label} must contain at least one feature")
    if len(names) != len(set(names)):
        raise ValueError(f"{label} contains duplicate feature names")
    return names


class ArchetypeRegressor(RegressorMixin, BaseEstimator):
    """Soft mixture of physical archetypes with shrunken outcome means.

    Missing values are median-imputed with statistics learned on the training
    fold.  Missing dimensions are then omitted from distance calculations, so
    an athlete with no measurements receives the training archetype priors
    rather than an arbitrary hard assignment to the median profile.

    Parameters are deliberately conservative because the estimator is intended
    to be one expert in a validated ensemble, not a stand-alone causal model.
    """

    def __init__(
        self,
        numeric_features: Sequence[str] = DEFAULT_NUMERIC_FEATURES,
        *,
        include_bmi: bool = True,
        max_clusters: int = 3,
        min_cluster_size: int = 15,
        shrinkage: float = 20.0,
        bandwidth: float | None = None,
        random_state: int = RANDOM_STATE,
        n_init: int = 20,
    ) -> None:
        self.numeric_features = numeric_features
        self.include_bmi = include_bmi
        self.max_clusters = max_clusters
        self.min_cluster_size = min_cluster_size
        self.shrinkage = shrinkage
        self.bandwidth = bandwidth
        self.random_state = random_state
        self.n_init = n_init

    def _resolve_features(self) -> list[str]:
        names = _as_unique_names(self.numeric_features, label="numeric_features")
        if self.include_bmi and "bmi" not in names:
            names.append("bmi")
        return names

    @staticmethod
    def _require_frame(X: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(X, pd.DataFrame):
            raise TypeError("ArchetypeRegressor requires X to be a pandas DataFrame")
        return X

    def _raw_features(
        self, X: pd.DataFrame, feature_names: Sequence[str]
    ) -> tuple[np.ndarray, np.ndarray]:
        X = self._require_frame(X)
        frame = pd.DataFrame(index=X.index)
        for feature in feature_names:
            if feature == "bmi" and self.include_bmi:
                height = pd.to_numeric(
                    X["height_cm"] if "height_cm" in X else pd.Series(np.nan, index=X.index),
                    errors="coerce",
                )
                weight = pd.to_numeric(
                    X["weight_kg"] if "weight_kg" in X else pd.Series(np.nan, index=X.index),
                    errors="coerce",
                )
                valid = height.gt(0) & weight.ge(0)
                derived = pd.Series(np.nan, index=X.index, dtype=float)
                derived.loc[valid] = weight.loc[valid] / (height.loc[valid] / 100.0) ** 2
                if "bmi" in X:
                    supplied = pd.to_numeric(X["bmi"], errors="coerce")
                    derived = derived.combine_first(supplied)
                frame[feature] = derived
            elif feature in X:
                frame[feature] = pd.to_numeric(X[feature], errors="coerce")
            else:
                # Optional fields such as age may be absent at cold-start time.
                frame[feature] = np.nan
        values = frame.to_numpy(dtype=float)
        values[~np.isfinite(values)] = np.nan
        observed = np.isfinite(values)
        return values, observed

    @staticmethod
    def _target(y: object, n_rows: int) -> np.ndarray:
        values = np.asarray(y, dtype=float)
        if values.ndim == 2 and values.shape[1] == 1:
            values = values[:, 0]
        if values.ndim != 1 or len(values) != n_rows:
            raise ValueError("y must be one-dimensional and have the same number of rows as X")
        if not np.isfinite(values).all():
            raise ValueError("y must contain only finite numeric scores")
        return values

    @staticmethod
    def _weights(sample_weight: object, n_rows: int) -> np.ndarray:
        if sample_weight is None:
            return np.ones(n_rows, dtype=float)
        weights = np.asarray(sample_weight, dtype=float)
        if weights.ndim != 1 or len(weights) != n_rows:
            raise ValueError("sample_weight must be one-dimensional and match X")
        if not np.isfinite(weights).all() or (weights < 0).any():
            raise ValueError("sample_weight must contain finite, non-negative values")
        if not weights.sum() > 0:
            raise ValueError("sample_weight must have positive total weight")
        return weights

    def _validated_hyperparameters(self) -> None:
        if not isinstance(self.max_clusters, int) or self.max_clusters < 1:
            raise ValueError("max_clusters must be a positive integer")
        if not isinstance(self.min_cluster_size, int) or self.min_cluster_size < 1:
            raise ValueError("min_cluster_size must be a positive integer")
        if not np.isfinite(self.shrinkage) or self.shrinkage < 0:
            raise ValueError("shrinkage must be finite and non-negative")
        if self.bandwidth is not None and (
            not np.isfinite(self.bandwidth) or self.bandwidth <= 0
        ):
            raise ValueError("bandwidth must be finite and positive when provided")
        if not isinstance(self.n_init, int) or self.n_init < 1:
            raise ValueError("n_init must be a positive integer")

    def fit(
        self,
        X: pd.DataFrame,
        y: object,
        sample_weight: object = None,
    ) -> ArchetypeRegressor:
        """Fit physical archetypes and their regularized outcome means."""
        X = self._require_frame(X)
        self._validated_hyperparameters()
        model_features = self._resolve_features()
        raw, _ = self._raw_features(X, model_features)
        target = self._target(y, len(X))
        weights = self._weights(sample_weight, len(X))

        positive = weights > 0
        raw = raw[positive]
        target = target[positive]
        weights = weights[positive]
        if not len(target):  # Defensive; _weights already rejects zero total weight.
            raise ValueError("No positive-weight training observations")

        self.model_features_ = np.asarray(model_features, dtype=object)
        self.feature_names_in_ = self.model_features_.copy()
        self.n_features_in_ = len(model_features)
        self.n_training_samples_ = int(len(target))
        self.training_weight_ = float(weights.sum())

        self.imputer_ = SimpleImputer(strategy="median", keep_empty_features=True)
        imputed = self.imputer_.fit_transform(raw)
        self.scaler_ = StandardScaler()
        scaled = self.scaler_.fit_transform(imputed, sample_weight=weights)

        unique_rows = int(np.unique(scaled, axis=0).shape[0])
        maximum = min(
            self.max_clusters,
            max(1, len(target) // self.min_cluster_size),
            max(1, unique_rows),
        )
        selected: KMeans | None = None
        labels: np.ndarray | None = None
        for n_clusters in range(maximum, 0, -1):
            candidate = KMeans(
                n_clusters=n_clusters,
                n_init=self.n_init,
                random_state=self.random_state,
                algorithm="lloyd",
            )
            candidate.fit(scaled, sample_weight=weights)
            candidate_labels = candidate.labels_
            counts = np.bincount(candidate_labels, minlength=n_clusters)
            if n_clusters == 1 or counts.min() >= self.min_cluster_size:
                selected = candidate
                labels = candidate_labels
                break
        if selected is None or labels is None:  # pragma: no cover - n_clusters=1 always succeeds
            raise RuntimeError("Unable to fit an archetype partition")

        self.kmeans_ = selected
        self.n_clusters_ = int(selected.n_clusters)
        self.cluster_centers_ = selected.cluster_centers_.copy()
        self.cluster_centers_original_ = self.scaler_.inverse_transform(self.cluster_centers_)
        self.cluster_counts_ = np.bincount(labels, minlength=self.n_clusters_).astype(int)
        self.cluster_support_ = np.bincount(
            labels, weights=weights, minlength=self.n_clusters_
        ).astype(float)
        self.cluster_priors_ = self.cluster_support_ / self.cluster_support_.sum()
        self.global_mean_ = float(np.average(target, weights=weights))

        raw_means = np.empty(self.n_clusters_, dtype=float)
        for cluster in range(self.n_clusters_):
            member = labels == cluster
            raw_means[cluster] = float(np.average(target[member], weights=weights[member]))
        self.cluster_raw_means_ = raw_means
        self.cluster_means_ = (
            self.cluster_support_ * raw_means + self.shrinkage * self.global_mean_
        ) / (self.cluster_support_ + self.shrinkage)

        if self.bandwidth is not None:
            self.bandwidth_ = float(self.bandwidth)
        elif self.n_clusters_ == 1:
            self.bandwidth_ = 1.0
        else:
            squared = ((scaled[:, None, :] - self.cluster_centers_[None, :, :]) ** 2).sum(axis=2)
            assigned = np.sqrt(squared[np.arange(len(scaled)), labels])
            within = assigned[assigned > 1e-12]
            within_scale = float(np.median(within)) if len(within) else 0.0
            center_delta = self.cluster_centers_[:, None, :] - self.cluster_centers_[None, :, :]
            center_distance = np.sqrt((center_delta**2).sum(axis=2))
            between = center_distance[np.triu_indices(self.n_clusters_, k=1)]
            between = between[between > 1e-12]
            overlap_floor = 0.25 * float(np.median(between)) if len(between) else 0.0
            self.bandwidth_ = max(within_scale, overlap_floor, 1e-6)
        return self

    def _membership(
        self, X: pd.DataFrame
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        check_is_fitted(
            self,
            ["imputer_", "scaler_", "cluster_centers_", "cluster_means_", "bandwidth_"],
        )
        raw, observed = self._raw_features(X, self.model_features_)
        scaled = self.scaler_.transform(self.imputer_.transform(raw))
        delta = scaled[:, None, :] - self.cluster_centers_[None, :, :]
        # Imputation makes transforms finite; the mask prevents an unavailable
        # measurement from creating false evidence for a particular archetype.
        squared_distance = ((delta**2) * observed[:, None, :]).sum(axis=2)
        logits = -0.5 * squared_distance / (self.bandwidth_**2)
        logits += np.log(np.maximum(self.cluster_priors_, np.finfo(float).tiny))[None, :]
        logits -= logits.max(axis=1, keepdims=True)
        probability = np.exp(logits)
        probability /= probability.sum(axis=1, keepdims=True)
        return probability, squared_distance, observed

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Return the continuous soft-archetype outcome estimate."""
        probability, _, _ = self._membership(X)
        return probability @ self.cluster_means_

    def describe(self, X: pd.DataFrame) -> list[dict]:
        """Explain memberships and local training support for each input row."""
        probability, squared_distance, observed = self._membership(X)
        prediction = probability @ self.cluster_means_
        names = [str(name) for name in self.model_features_]
        results: list[dict] = []
        for row in range(len(probability)):
            if observed[row].any():
                nearest = int(np.argmin(squared_distance[row]))
                nearest_distance: float | None = float(np.sqrt(squared_distance[row, nearest]))
            else:
                nearest = int(np.argmax(self.cluster_priors_))
                nearest_distance = None
            denominator = np.sum(
                probability[row] ** 2 / np.maximum(self.cluster_support_, np.finfo(float).tiny)
            )
            effective_support = float(1.0 / denominator)
            archetypes = []
            for cluster in range(self.n_clusters_):
                archetypes.append(
                    {
                        "archetype": cluster,
                        "probability": float(probability[row, cluster]),
                        "support": float(self.cluster_support_[cluster]),
                        "training_rows": int(self.cluster_counts_[cluster]),
                        "outcome_mean": float(self.cluster_means_[cluster]),
                    }
                )
            results.append(
                {
                    "prediction": float(prediction[row]),
                    "nearest_archetype": nearest,
                    "nearest_center_distance": nearest_distance,
                    "nearest_center": {
                        name: float(value)
                        for name, value in zip(names, self.cluster_centers_original_[nearest])
                    },
                    "probabilities": {
                        str(cluster): float(probability[row, cluster])
                        for cluster in range(self.n_clusters_)
                    },
                    "archetypes": archetypes,
                    "effective_support": effective_support,
                    "observed_feature_fraction": float(observed[row].mean()),
                    "observed_features": [
                        name for name, available in zip(names, observed[row]) if available
                    ],
                    "missing_features": [
                        name for name, available in zip(names, observed[row]) if not available
                    ],
                }
            )
        return results


def _preprocessor(numeric_features: list[str], categorical_features: list[str]) -> ColumnTransformer:
    transformers = []
    if numeric_features:
        transformers.append(
            (
                "numeric",
                Pipeline(
                    [
                        (
                            "imputer",
                            SimpleImputer(
                                strategy="median", add_indicator=True, keep_empty_features=True
                            ),
                        ),
                        ("scaler", StandardScaler()),
                    ]
                ),
                numeric_features,
            )
        )
    if categorical_features:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent", keep_empty_features=True)),
                        ("encoder", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
                    ]
                ),
                categorical_features,
            )
        )
    return ColumnTransformer(transformers, remainder="drop")


def make_experts(
    numeric_features: list[str], categorical_features: list[str] | None = None
) -> dict[str, BaseEstimator]:
    """Build deterministic, regularized experts for an ensemble head.

    Sport and role should normally be handled by the caller's separate heads.
    Categorical support is retained for carefully selected within-head context
    fields, with unknown inference-time levels ignored safely.
    """
    numeric = _as_unique_names(numeric_features, label="numeric_features")
    categorical = [] if categorical_features is None else [str(x) for x in categorical_features]
    if len(categorical) != len(set(categorical)):
        raise ValueError("categorical_features contains duplicate feature names")
    overlap = set(numeric) & set(categorical)
    if overlap:
        raise ValueError(f"Features cannot be both numeric and categorical: {sorted(overlap)}")

    def prepare() -> ColumnTransformer:
        return _preprocessor(numeric, categorical)

    return {
        "archetype": ArchetypeRegressor(
            numeric_features=numeric,
            include_bmi={"height_cm", "weight_kg"}.issubset(numeric),
        ),
        "ridge": Pipeline(
            [("prepare", prepare()), ("model", Ridge(alpha=10.0))]
        ),
        "hist_gradient_boosting": Pipeline(
            [
                ("prepare", prepare()),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        max_depth=3,
                        min_samples_leaf=20,
                        l2_regularization=10.0,
                        learning_rate=0.05,
                        max_iter=200,
                        early_stopping=False,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
        "extra_trees": Pipeline(
            [
                ("prepare", prepare()),
                (
                    "model",
                    ExtraTreesRegressor(
                        n_estimators=200,
                        min_samples_leaf=15,
                        max_features=1.0,
                        n_jobs=1,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
    }
