"""Predict how an intervention's effect changes between genetic backgrounds."""

import itertools

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from draft._tasks import TaskResult
from draft._tasks._siraj import BACKGROUND_POSITION, paired_backgrounds
from draft.readouts import PROTOCOL, siraj_predictions


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
    predictions["fold"] = predictions.unit_id.map(per_cell.groupby("unit_id").fold.first())
    return score(predictions, data["interaction_repeats"])


KEY = ["unit_id", "mutation_position", "mutation_ref", "mutation_alt"]
REPEATS = [f"interaction_repeat_{i}" for i in range(1, 6)]
BOOTSTRAP = {"unit": "regulatory element", "replicates": 20000, "seed": 20261111}


def _rank(values, *, prediction=False):
    values = np.asarray(values, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all():
        raise ValueError("Interaction correlations require at least two finite values")
    ranks = rankdata(values).astype(float) - (len(values) + 1) / 2
    norm = np.linalg.norm(ranks)
    if norm == 0:
        if prediction:
            return np.zeros(len(values))
        raise ValueError("Experimental interaction measurements must vary within each element")
    return ranks / norm


def _pools(repeats):
    values = repeats[REPEATS].to_numpy(dtype=float).T
    pools = []
    for pair in itertools.combinations(range(5), 2):
        other = [i for i in range(5) if i not in pair]
        pools.extend([values[list(pair)].mean(0), values[other].mean(0)])
    return np.array(pools)


def _metric(groups):
    values = groups.spearman.to_numpy(dtype=float)
    indices = np.random.default_rng(BOOTSTRAP["seed"]).integers(
        len(values), size=(BOOTSTRAP["replicates"], len(values))
    )
    interval = np.quantile(values[indices].mean(1), [.025, .975]).tolist()
    return {"name": "macro_spearman", "value": float(values.mean()),
            "unit": "Spearman ρ", "direction": "higher", "ci95": interval}


def experimental_reference(repeats):
    """Agreement of disjoint two- and three-repeat pools, within each element."""
    rows = []
    for unit, group in repeats.groupby("unit_id", sort=True):
        ranks = np.array([_rank(v) for v in _pools(group)])
        value = np.mean([np.dot(ranks[2*j], ranks[2*j+1]) for j in range(10)])
        rows.append({"unit_id": unit, "spearman": float(value), "n_records": len(group)})
    groups = pd.DataFrame(rows)
    return _metric(groups), groups


def score(predictions, repeats):
    """Score unchanged model effects against the independent-repeat targets."""
    if repeats.duplicated(KEY).any() or predictions.duplicated(KEY).any():
        raise ValueError("Duplicate interaction identities")
    wanted = pd.MultiIndex.from_frame(repeats[KEY])
    actual = pd.MultiIndex.from_frame(predictions[KEY])
    positions = actual.get_indexer(wanted)
    if len(actual) != len(wanted) or (positions < 0).any():
        raise ValueError("Predictions must cover the complete repeat-interaction cohort")
    predictions = predictions.iloc[positions].reset_index(drop=True).copy()
    repeats = repeats.reset_index(drop=True)
    if len(repeats) != 68026 or repeats.unit_id.nunique() != 114:
        raise ValueError("Expected 68,026 paired edits across 114 elements")
    predictions[REPEATS] = repeats[REPEATS].to_numpy(dtype=float)
    predictions["y_true"] = predictions[REPEATS].mean(axis=1)
    predictions["y_pred"] = predictions.prediction_A - predictions.prediction_R
    predictions["distance_bp"] = (predictions.mutation_position - BACKGROUND_POSITION).abs()
    rows = []
    for unit, group in predictions.groupby("unit_id", sort=True):
        target_ranks = np.array([_rank(v) for v in _pools(group)])
        rank = _rank(group.y_pred.to_numpy(), prediction=True)
        rows.append({"unit_id": unit, "spearman": float(np.mean(target_ranks @ rank)),
                     "n_records": len(group), "constant_prediction": int(np.ptp(group.y_pred) == 0)})
    groups = pd.DataFrame(rows)
    return TaskResult(
        _metric(groups),
        {**PROTOCOL, "group": "unit_id", "target": "cell-averaged four-genotype interactions from independent repeat groups",
         "n_pairs": len(predictions), "n_groups": len(groups), "n_defined_groups": len(groups),
         "n_constant_prediction_groups": int(groups.constant_prediction.sum()),
         "repeat_protocol": "all ten disjoint 2-versus-3 partitions of five repeats; twenty correlations per element",
         "experimental_activity": "log2((RNA + 0.5)/(DNA + 0.5)); A - A0 - R + R0; mean of HepG2 and K562",
         "training_target": "unchanged published pooled-assay mutation effects",
         "constant_predictions": "correlation assigned zero, retaining the element",
         "bootstrap": BOOTSTRAP},
        {"predictions": predictions, "groups": groups},
    )
