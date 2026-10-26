"""Predict the HepG2-minus-K562 effect contrast in held-out elements."""

from bend2._tasks import TaskResult
from bend2.readouts import PROTOCOL, macro_spearman, siraj_predictions


def run(data, embeddings=None, probabilities=None, *, shared=None):
    predictions = siraj_predictions(data, embeddings, shared, "context")
    metric, groups = macro_spearman(predictions, "unit_id", replicates=10000, seed=20260825)
    return TaskResult(
        "context",
        metric,
        {
            **PROTOCOL,
            "group": "unit_id",
            "target": "HepG2 minus K562",
            "prediction_dtype": "float32",
            "n_records": len(predictions),
            "n_groups": len(groups),
            "n_defined_groups": int(groups.spearman.notna().sum()),
            "bootstrap": {"unit": "regulatory element", "replicates": 10000, "seed": 20260825},
        },
        {"predictions": predictions, "groups": groups},
    )
