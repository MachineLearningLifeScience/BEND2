"""Choose another-position edit predicted to repair a measured background change."""

from bend2._tasks import TaskResult
from bend2._tasks._siraj import repair_candidates
from bend2.readouts import PROTOCOL, mean_interval, siraj_predictions


def run(data, embeddings=None, probabilities=None, *, shared=None):
    construct = repair_candidates(data["records"])
    predictions = siraj_predictions(data, embeddings, shared)
    scored = construct.merge(
        predictions[["record_id", "y_pred", "fold"]], on="record_id", validate="one_to_one"
    )
    key = ["unit_id", "state", "context_id"]
    targets = scored.loc[
        scored.is_direct & scored.resolved, key + ["delta_y", "sigma", "y_pred"]
    ].rename(
        columns={
            "delta_y": "target_y",
            "sigma": "target_sigma",
            "y_pred": "target_prediction",
        }
    )
    columns = key + ["record_id", "mutation_position", "delta_y", "sigma", "y_pred", "fold"]
    candidates = scored.loc[scored.is_candidate, columns].merge(
        targets, on=key, validate="many_to_one"
    )
    return score(candidates)


def score(candidates):
    """Choose predicted repairs, then rank their measured residuals within each request."""
    candidates = candidates.copy()
    key = ["unit_id", "state", "context_id"]
    candidates["predicted_residual"] = (candidates.y_pred - candidates.target_prediction).abs()
    candidates["observed_residual"] = (candidates.delta_y - candidates.target_y).abs()
    candidates = candidates.sort_values(key + ["predicted_residual", "record_id"])
    counts = candidates.groupby(key).record_id.transform("size")
    if candidates.empty or (counts < 2).any():
        raise ValueError(
            "Repair requires resolved target requests with at least two candidate edits"
        )
    ranks = candidates.groupby(key).observed_residual.rank(method="average")
    candidates["observed_percentile"] = (ranks - 1) / (counts - 1)
    selected = candidates.groupby(key, sort=False).head(1).copy()
    groups = selected.groupby("unit_id", as_index=False).agg(
        candidate_percentile=("observed_percentile", "mean"), n_requests=("record_id", "size")
    )
    interval = mean_interval(groups.candidate_percentile, replicates=10000, seed=20260827)
    return TaskResult(
        {
            "name": "measured_rank_percentile",
            "value": float(100 * groups.candidate_percentile.mean()),
            "unit": "%",
            "direction": "lower",
            "ci95": [100 * v for v in interval] if interval else None,
        },
        {
            **PROTOCOL,
            "group": "unit_id",
            "n_requests": len(selected),
            "n_groups": len(groups),
            "request_filter": "absolute direct-swap effect >= 2 standard errors",
            "selector": "minimum absolute predicted residual to the direct-swap target",
            "candidate_pool": "frozen common pool; excludes all edits at background position 99",
            "tie_break": "ascending record_id",
            "percentile_rank": "average ties, (rank-1)/(n-1)",
            "aggregation": "mean requests within element, then mean elements",
            "bootstrap": {"unit": "regulatory element", "replicates": 10000, "seed": 20260827},
        },
        {"predictions": candidates, "choices": selected, "groups": groups},
    )
