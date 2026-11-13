from __future__ import annotations

import warnings
from collections.abc import Callable

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import mean_absolute_error, mean_squared_error, ndcg_score


def _safe_correlation(function: Callable, truth: np.ndarray, prediction: np.ndarray) -> float:
    if len(truth) < 2 or np.ptp(truth) == 0 or np.ptp(prediction) == 0:
        return float("nan")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return float(function(truth, prediction).statistic)


def group_metrics(group: pd.DataFrame) -> dict[str, float]:
    truth = group["y_true"].to_numpy(dtype=float)
    prediction = group["y_pred"].to_numpy(dtype=float)
    relevance = truth - np.nanmin(truth)
    ndcg = (
        float(ndcg_score(relevance.reshape(1, -1), prediction.reshape(1, -1)))
        if len(truth) > 1 and np.ptp(relevance) > 0
        else float("nan")
    )
    return {
        "spearman": _safe_correlation(spearmanr, truth, prediction),
        "pearson": _safe_correlation(pearsonr, truth, prediction),
        "rmse": float(np.sqrt(mean_squared_error(truth, prediction))),
        "mae": float(mean_absolute_error(truth, prediction)),
        "direction_accuracy": float(np.mean(np.sign(truth) == np.sign(prediction))),
        "ndcg": ndcg,
        "n": float(len(group)),
    }


def evaluate_predictions(
    frame: pd.DataFrame,
    group_column: str = "unit_id",
    truth_column: str = "y_true",
    prediction_column: str = "y_pred",
) -> tuple[dict[str, float], pd.DataFrame]:
    if frame.columns.duplicated().any():
        duplicates = sorted(set(frame.columns[frame.columns.duplicated()]))
        raise ValueError(f"Duplicate evaluation columns: {duplicates}")
    required = {group_column, truth_column, prediction_column}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing evaluation columns: {sorted(missing)}")
    clean = (
        frame[list(required)]
        .dropna()
        .rename(columns={truth_column: "y_true", prediction_column: "y_pred"})
    )
    rows = []
    for unit, group in clean.groupby(group_column, sort=True):
        rows.append({group_column: unit, **group_metrics(group)})
    per_group = pd.DataFrame(rows)
    macro = {
        f"macro_{metric}": float(per_group[metric].mean(skipna=True))
        for metric in ("spearman", "pearson", "rmse", "mae", "direction_accuracy", "ndcg")
    }
    macro["n_groups"] = int(len(per_group))
    macro["n_records"] = int(len(clean))
    return macro, per_group
