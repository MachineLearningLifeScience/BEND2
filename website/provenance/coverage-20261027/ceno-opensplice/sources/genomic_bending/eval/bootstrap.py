from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd


def group_bootstrap_ci(
    per_group: pd.DataFrame,
    metric: str,
    replicates: int = 2000,
    seed: int = 20260822,
    confidence: float = 0.95,
) -> tuple[float, float]:
    values = per_group[metric].dropna().to_numpy(dtype=float)
    if len(values) < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    draws = rng.choice(values, size=(replicates, len(values)), replace=True).mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    return tuple(float(value) for value in np.quantile(draws, [alpha, 1.0 - alpha]))


def paired_group_bootstrap(
    first: pd.DataFrame,
    second: pd.DataFrame,
    metric: str,
    group_column: str = "unit_id",
    replicates: int = 2000,
    seed: int = 20260822,
    confidence: float = 0.95,
    reducer: Callable[[np.ndarray], float] = np.mean,
) -> dict[str, float]:
    paired = (
        first[[group_column, metric]]
        .merge(second[[group_column, metric]], on=group_column, suffixes=("_first", "_second"))
        .dropna()
    )
    differences = paired[f"{metric}_first"].to_numpy() - paired[f"{metric}_second"].to_numpy()
    if not len(differences):
        raise ValueError("No paired groups available")
    rng = np.random.default_rng(seed)
    samples = rng.choice(differences, size=(replicates, len(differences)), replace=True)
    estimates = np.apply_along_axis(reducer, 1, samples)
    alpha = (1.0 - confidence) / 2.0
    return {
        "difference": float(reducer(differences)),
        "ci_low": float(np.quantile(estimates, alpha)),
        "ci_high": float(np.quantile(estimates, 1.0 - alpha)),
        "probability_first_better": float(np.mean(estimates > 0)),
        "n_groups": int(len(differences)),
    }
