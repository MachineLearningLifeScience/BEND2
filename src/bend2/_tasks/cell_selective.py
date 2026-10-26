"""Select an edit for one cell while penalizing its effect in the other cell."""

import numpy as np
import pandas as pd

from bend2._tasks import TaskResult
from bend2._tasks._siraj import EXCLUDED_UNIT
from bend2.readouts import PROTOCOL, mean_interval, siraj_predictions


def nominate(predictions):
    """Fix all choices using predictions alone, including the no-edit action."""
    rows = []
    for background, group in predictions.groupby("background_id", sort=True):
        for target, other in (("hepg2", "k562"), ("k562", "hepg2")):
            score = group[f"pred_{target}"].to_numpy() - group[f"pred_{other}"].abs().to_numpy()
            if score.max() <= 1e-10:
                rows.append(
                    {
                        "background_id": background,
                        "unit_id": group.unit_id.iloc[0],
                        "target_cell": target,
                        "ID": None,
                        "weight": 1.0,
                        "predicted_utility": 0.0,
                    }
                )
            else:
                chosen = np.flatnonzero(np.isclose(score, score.max(), rtol=0, atol=1e-10))
                for index in chosen:
                    rows.append(
                        {
                            "background_id": background,
                            "unit_id": group.unit_id.iloc[0],
                            "target_cell": target,
                            "ID": group.ID.iloc[index],
                            "weight": 1 / len(chosen),
                            "predicted_utility": float(score[index]),
                        }
                    )
    return pd.DataFrame(rows)


def run(data, embeddings=None, probabilities=None, *, shared=None):
    shared = {} if shared is None else shared
    per_cell = siraj_predictions(data, embeddings, shared)
    contrast = (
        siraj_predictions(data, embeddings, shared, "context").set_index("ID").y_pred.astype(float)
    )
    pool = data["records"].loc[data["records"].unit_id.ne(EXCLUDED_UNIT)]
    predictions = pool[["ID", "unit_id", "background_id"]].drop_duplicates("ID").sort_values("ID")
    mean = per_cell.groupby("ID").y_pred.mean()
    predictions["pred_hepg2"] = predictions.ID.map(mean) + predictions.ID.map(contrast) / 2
    predictions["pred_k562"] = predictions.ID.map(mean) - predictions.ID.map(contrast) / 2
    predictions["fold"] = predictions.unit_id.map(per_cell.groupby("unit_id").fold.first())
    # No decision outcomes are referenced until every nomination is fixed.
    choices = nominate(predictions)
    measured = data["selective_outcomes"].set_index("ID")
    for cell in ("hepg2", "k562"):
        predictions[f"truth_{cell}"] = predictions.ID.map(measured[f"truth_{cell}"])
    if not np.isfinite(predictions[["truth_hepg2", "truth_k562"]].to_numpy()).all():
        raise ValueError("Selective outcomes are missing nominated candidate measurements")
    evaluated = choices.copy()
    target, other = np.zeros(len(choices)), np.zeros(len(choices))
    for cell, off in (("hepg2", "k562"), ("k562", "hepg2")):
        use = choices.target_cell.eq(cell) & choices.ID.notna()
        if not use.any():
            continue
        target[use] = choices.loc[use, "ID"].map(measured[f"truth_{cell}"])
        other[use] = choices.loc[use, "ID"].map(measured[f"truth_{off}"]).abs()
    evaluated["target"] = evaluated.weight * target
    evaluated["other"] = evaluated.weight * other
    backgrounds = evaluated.groupby(["unit_id", "background_id", "target_cell"], as_index=False)[
        ["target", "other"]
    ].sum()
    cells = backgrounds.groupby(["unit_id", "target_cell"], as_index=False)[
        ["target", "other"]
    ].mean()
    groups = cells.groupby("unit_id", as_index=False)[["target", "other"]].mean()
    groups["utility"] = groups.target - groups.other
    return TaskResult(
        "cell_selective",
        {
            "name": "log2_reporter_utility",
            "value": float(groups.utility.mean()),
            "unit": "log₂ reporter",
            "direction": "higher",
            "ci95": mean_interval(
                groups.utility, replicates=50000, seed=20260921, multinomial=True
            ),
        },
        {
            **PROTOCOL,
            "group": "unit_id",
            "n_candidates": len(predictions),
            "n_groups": len(groups),
            "n_backgrounds": predictions.background_id.nunique(),
            "lambda": 1.0,
            "selector": "predicted target effect minus absolute other-cell effect",
            "readout_combination": "per-cell prediction mean plus/minus half the direct contrast",
            "no_edit": "zero utility; chosen when no candidate exceeds 1e-10",
            "ties": "uniform over candidates within absolute 1e-10 of the maximum",
            "decision_outcomes": "pooled direct-m0 raw-count effects",
            "aggregation": "backgrounds within target cell, target cells within locus, then loci",
            "bootstrap": {"unit": "complete locus", "replicates": 50000, "seed": 20260921},
        },
        {"predictions": predictions, "choices": choices, "groups": groups},
    )
