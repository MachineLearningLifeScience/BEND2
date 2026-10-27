"""Predict splice effects in genes excluded from readout training."""

from bend2._tasks import TaskResult
from bend2.readouts import PROTOCOL, intervention_predictions, macro_spearman


def run(data, embeddings=None, probabilities=None, *, shared=None):
    shared = {} if shared is None else shared
    predictions = intervention_predictions(
        data["records"],
        embeddings,
        "gene_id",
        scratch_dir=shared.get("scratch_dir"),
        progress=shared.get("progress"),
    )
    return score(predictions)


def score(predictions):
    """Aggregate held-out predictions using the fixed gene-level protocol."""
    metric, groups = macro_spearman(predictions, "gene_id", replicates=2000, seed=20260822)
    return TaskResult(
        metric,
        {
            **PROTOCOL,
            "group": "gene_id",
            "n_records": len(predictions),
            "n_groups": len(groups),
            "n_defined_groups": int(groups.spearman.notna().sum()),
            "bootstrap": {"unit": "gene", "replicates": 2000, "seed": 20260822},
        },
        {"predictions": predictions, "groups": groups},
    )
