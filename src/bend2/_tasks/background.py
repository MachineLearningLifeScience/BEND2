"""Predict how an intervention's effect changes between genetic backgrounds."""

import pandas as pd

from bend2._tasks import TaskResult
from bend2._tasks._siraj import BACKGROUND_POSITION, paired_backgrounds
from bend2.readouts import PROTOCOL, macro_spearman, siraj_predictions


def run(data, embeddings=None, probabilities=None, *, shared=None):
    records, _ = paired_backgrounds(data["records"])
    per_cell = siraj_predictions(data, embeddings, shared)
    identity = [
        "ID",
        "unit_id",
        "background_id",
        "state",
        "mutation_position",
        "mutation_ref",
        "mutation_alt",
    ]
    states = records.pivot_table(
        index=identity, columns="context_id", values="delta_y", aggfunc="first"
    ).reset_index()
    states["truth"] = (states.HepG2 + states.K562) / 2
    states["prediction"] = states.ID.map(per_cell.groupby("ID").y_pred.mean())
    key = ["unit_id", "mutation_position", "mutation_ref", "mutation_alt"]
    complete = states.groupby(key).state.nunique()
    states = states.merge(complete[complete.eq(2)].reset_index()[key], on=key)
    predictions = states.pivot(index=key, columns="state", values=["truth", "prediction"]).dropna()
    predictions.columns = [f"{metric}_{state}" for metric, state in predictions.columns]
    predictions = predictions.reset_index()
    predictions["y_true"] = predictions.truth_A - predictions.truth_R
    predictions["y_pred"] = predictions.prediction_A - predictions.prediction_R
    predictions["distance_bp"] = (predictions.mutation_position - BACKGROUND_POSITION).abs()
    predictions["fold"] = predictions.unit_id.map(per_cell.groupby("unit_id").fold.first())
    metric, groups = macro_spearman(predictions, "unit_id", replicates=10000, seed=20260826)
    return TaskResult(
        "background",
        metric,
        {
            **PROTOCOL,
            "group": "unit_id",
            "target": "A-minus-R difference in mean two-cell effect",
            "n_pairs": len(predictions),
            "n_groups": len(groups),
            "n_defined_groups": int(pd.notna(groups.spearman).sum()),
            "bootstrap": {"unit": "regulatory element", "replicates": 10000, "seed": 20260826},
        },
        {"predictions": predictions, "groups": groups},
    )
