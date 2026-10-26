"""Recover one hidden base per independent genomic block."""

import numpy as np

from bend2._tasks import TaskResult


def run(data, embeddings=None, probabilities=None, *, shared=None):
    panel = data["panel"].query('split == "evaluation"').reset_index(drop=True)
    values = np.asarray(probabilities)
    if (
        values.ndim not in (2, 3)
        or values.shape[0] != len(panel)
        or values.shape[-1] != 4
        or (values.ndim == 3 and values.shape[1] < 1)
        or values.dtype.kind not in "fiu"
    ):
        raise ValueError(
            "Prior probabilities must have shape [windows, 4] or [windows, queries, 4], A/C/G/T"
        )
    multiple_queries = values.ndim == 3
    values = values.astype(float)
    if not np.isfinite(values).all() or ((values < 0) | (values > 1)).any():
        raise ValueError("Base probabilities must be finite and within [0, 1]")
    if not np.allclose(values.sum(-1), 1, atol=1e-7, rtol=0):
        raise ValueError(
            "Each query's base probabilities must sum to one; no normalization is applied"
        )
    queries = values if multiple_queries else values[:, None, :]
    truth = np.array(["ACGT".index(base) for base in panel.reference_base])
    actual = np.take_along_axis(queries, truth[:, None, None], axis=-1).squeeze(-1)
    if (actual == 0).any():
        raise ValueError(
            "A true base has zero probability: log loss is infinite; no clipping is applied"
        )
    losses = -np.log2(actual)
    if multiple_queries:
        # The paper's individual-query scorer uses argmax, including its A/C/G/T tie order.
        accuracy = (queries.argmax(-1) == truth[:, None]).astype(float)
    else:
        tied = queries == queries.max(-1, keepdims=True)
        accuracy = np.take_along_axis(tied, truth[:, None, None], axis=-1).squeeze(-1) / tied.sum(
            -1
        )
    # Average individual scores, never probabilities, before resampling complete windows.
    scores = np.column_stack((losses.mean(1), accuracy.mean(1)))
    counts = np.random.default_rng(20260910).multinomial(
        len(panel), np.full(len(panel), 1 / len(panel)), 4000
    )
    intervals = np.quantile(counts @ scores / len(panel), [0.025, 0.975], axis=0)
    predictions = panel[["window_id", "block_id", "reference_base", "recovery_position"]].copy()
    if multiple_queries:
        for query in range(queries.shape[1]):
            predictions[[f"query_{query + 1}_p_{base}" for base in "ACGT"]] = queries[:, query]
            predictions[f"query_{query + 1}_recovery_bits"] = losses[:, query]
            predictions[f"query_{query + 1}_recovery_accuracy"] = accuracy[:, query]
    else:
        predictions[[f"p_{base}" for base in "ACGT"]] = values
    predictions[["recovery_bits", "recovery_accuracy"]] = scores
    return TaskResult(
        "prior",
        {
            "name": "recovery_bits",
            "value": float(scores[:, 0].mean()),
            "unit": "bits/base",
            "direction": "lower",
            "ci95": intervals[:, 0].tolist(),
        },
        {
            "n_windows": len(panel),
            "sequence_length": 1200,
            "target_position": 600,
            "target_replacement": "N",
            "base_order": "ACGT",
            "readout": "declared probability adapter",
            "queries_per_window": queries.shape[1],
            "query_aggregation": (
                "mean individual-query loss and accuracy within each window, then block bootstrap"
                if multiple_queries
                else "one probability distribution per window"
            ),
            "recovery_accuracy": float(scores[:, 1].mean()),
            "accuracy_ci95": intervals[:, 1].tolist(),
            "tie_accuracy": "first maximum in A/C/G/T order"
            if multiple_queries
            else "fractional credit",
            "probability_clipping": False,
            "bootstrap": {"unit": "1 Mb genomic block", "replicates": 4000, "seed": 20260910},
        },
        {"predictions": predictions},
    )
