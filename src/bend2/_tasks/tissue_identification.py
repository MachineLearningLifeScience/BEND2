"""Identify a tissue from its predicted expression profile across held-out genes.

Feature and target scaling use training genes only. A shared ridge penalty is
selected on validation genes; the final fit retains training-only membership.
The 51 tissue queries and candidates remain fixed during whole-gene bootstrap.
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from bend2._tasks import TaskResult
from bend2.readouts import matrix

PENALTIES = [10000.0, 1000.0, 100.0, 10.0, 1.0, 0.1]


def rank_order(values):
    """Cache sort order and tie endpoints, independent of bootstrap weights."""
    order = np.argsort(values, axis=0, kind="stable")
    sorted_values = np.take_along_axis(values, order, axis=0)
    n, dimensions = values.shape
    starts, ends = np.empty_like(order), np.empty_like(order)
    for column in range(dimensions):
        boundaries = np.r_[0, np.flatnonzero(np.diff(sorted_values[:, column])) + 1, n]
        widths = np.diff(boundaries)
        starts[:, column] = np.repeat(boundaries[:-1], widths)
        ends[:, column] = np.repeat(boundaries[1:], widths)
    return order, starts, ends


def weighted_ranks(ordered, counts):
    """Exact average ranks of duplicated genes, with zero-weight genes omitted."""
    order, starts, ends = ordered
    cumulative = np.vstack((np.zeros(order.shape[1]), np.cumsum(counts[order], axis=0)))
    low = np.take_along_axis(cumulative, starts, axis=0)
    high = np.take_along_axis(cumulative, ends, axis=0)
    sorted_ranks = (low + high + 1) / 2
    ranks = np.empty_like(sorted_ranks)
    np.put_along_axis(ranks, order, sorted_ranks, axis=0)
    ranks -= (counts.sum() + 1) / 2
    ranks *= np.sqrt(counts.astype(float))[:, None]
    norms = np.linalg.norm(ranks, axis=0)
    return ranks / np.where(norms > 0, norms, np.nan)


def retrieval(ranks, n_tissues):
    correlations = ranks[:, :n_tissues].T @ ranks[:, n_tissues:]
    if not np.isfinite(correlations).all():
        return np.nan, correlations, np.full(n_tissues, np.nan)
    maxima = correlations.max(1)
    tied = np.isclose(correlations, maxima[:, None], atol=1e-12, rtol=0)
    credit = np.diag(tied) / tied.sum(1)
    return float(credit.mean()), correlations, credit


def score(prediction, truth):
    """Return exact tissue retrieval and its fixed 10,000-draw gene bootstrap."""
    n, tissues = truth.shape
    ordered = rank_order(np.column_stack((prediction, truth)))
    point, correlations, credit = retrieval(weighted_ranks(ordered, np.ones(n)), tissues)
    # A constant full-data profile stays constant under every resample.
    if not np.isfinite(point):
        return point, None, 10000, correlations, credit, np.full(10000, np.nan)
    rng = np.random.default_rng(20260917)
    draws = np.empty(10000)
    for index in range(len(draws)):
        counts = np.bincount(rng.integers(0, n, size=n), minlength=n)
        draws[index] = retrieval(weighted_ranks(ordered, counts), tissues)[0]
    finite = np.isfinite(draws)
    interval = np.percentile(draws[finite], [2.5, 97.5]).tolist() if finite.any() else None
    return point, interval, int((~finite).sum()), correlations, credit, draws


def run(data, embeddings=None, probabilities=None, *, shared=None):
    targets = data["targets"]
    train, validation = targets["train"], targets["validation"]
    test = data["test_indices"]
    truth = np.asarray(targets["truth"], dtype=float)
    required = data["required_indices"]
    values = matrix(
        (data["sequences"][int(i)] for i in required), embeddings, n=len(required)
    ).astype(float)
    row = np.full(len(truth), -1, dtype=int)
    row[required] = np.arange(len(required))
    feature_scaler = StandardScaler().fit(values[row[train]])
    target_scaler = StandardScaler().fit(truth[train])
    x_train = feature_scaler.transform(values[row[train]])
    x_validation = feature_scaler.transform(values[row[validation]])
    y_train = target_scaler.transform(truth[train])
    y_validation = target_scaler.transform(truth[validation])
    eigenvalues, vectors = np.linalg.eigh(x_train.T @ x_train)
    eigenvalues = np.maximum(eigenvalues, 0)
    projected = vectors.T @ (x_train.T @ y_train)
    losses, selected, best_coef = [], None, None
    for penalty in PENALTIES:
        coef = vectors @ (projected / (eigenvalues[:, None] + penalty))
        loss = float(np.mean((x_validation @ coef - y_validation) ** 2))
        losses.append(loss)
        if selected is None or loss < losses[selected] - 1e-12:
            selected, best_coef = len(losses) - 1, coef
    prediction = target_scaler.inverse_transform(
        feature_scaler.transform(values[row[test]]) @ best_coef
    )
    point, interval, invalid, correlations, credit, draws = score(prediction, truth[test])
    tissues = list(targets["tissues"])
    genes = np.asarray(targets["gene_ids"])[test]
    predictions = pd.DataFrame(prediction, columns=[f"predicted_{t}" for t in tissues])
    predictions.insert(0, "gene_id", genes)
    observed = pd.DataFrame(truth[test], columns=[f"observed_{t}" for t in tissues])
    predictions = pd.concat((predictions, observed), axis=1)
    queries = pd.DataFrame(correlations, columns=tissues)
    queries.insert(0, "predicted_tissue", tissues)
    queries["top1_credit"] = credit
    return TaskResult(
        "tissue_identification",
        {
            "name": "retrieval_top1",
            "value": float(100 * point) if np.isfinite(point) else None,
            "unit": "%",
            "direction": "higher",
            "ci95": [100 * v for v in interval] if interval else None,
        },
        {
            "n_training_genes": len(train),
            "n_validation_genes": len(validation),
            "n_test_genes": len(test),
            "n_tissues": len(tissues),
            "input": "131072 bp reference-forward TSS-centered sequence",
            "target": "log1p TPM",
            "readout": "51 ridge heads with a shared penalty",
            "ridge_alpha": PENALTIES[selected],
            "penalty_grid": PENALTIES,
            "penalty_criterion": "validation standardized MSE",
            "penalty_ties": "within 1e-12, choose stronger penalty",
            "scaling": "feature and target StandardScaler fitted on training genes only",
            "refit": "none; retain training-only membership",
            "retrieval": "Spearman between predicted and measured profiles across common test genes",
            "ties": "fractional credit within absolute 1e-12",
            "chance_percent": 100 / len(tissues),
            "invalid_bootstrap_replicates": invalid,
            "bootstrap": {
                "unit": "whole gene",
                "replicates": 10000,
                "seed": 20260917,
                "ranks": "recomputed exactly for each sample, including multiplicity ties",
                "invalid_handling": "omit constant-profile draws and report their count",
            },
        },
        {
            "predictions": predictions,
            "tissues": queries,
            "validation": pd.DataFrame({"alpha": PENALTIES, "standardized_mse": losses}),
            "bootstrap": pd.DataFrame({"retrieval_top1_percent": 100 * draws}),
        },
    )
