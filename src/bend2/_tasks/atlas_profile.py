"""Select ten enhancer sequences for each of sixteen requested cell profiles.

Only source labels tune and fit the readout. Families related to the candidate
pool are already excluded from the frozen source population. Candidate outcomes
are consulted after all selections have been made.
"""

import numpy as np
import pandas as pd
from scipy.linalg import eigh

from bend2._tasks import TaskResult
from bend2.readouts import matrix

CELLS = [
    "NT2_D1",
    "GM12878",
    "786_O",
    "SKNSH",
    "WERI_Rb1",
    "SJCRH30",
    "HepG2",
    "K562",
    "MCF7",
    "HeLaS3",
    "HEK293",
    "HMC3",
]
PENALTIES = np.logspace(-8, 0, 17)


def scale(train, other):
    mean, std = train.mean(0), train.std(0)
    keep = std > 1e-7
    if not keep.any():
        raise ValueError("Atlas needs at least one feature varying across source sequences")
    return ((train[:, keep] - mean[keep]) / std[keep]) / np.sqrt(keep.sum()), (
        (other[:, keep] - mean[keep]) / std[keep]
    ) / np.sqrt(keep.sum())


def ridge_grid(train, labels, other, penalties):
    """Ridge with mean squared loss: the spectral penalty is n × lambda."""
    n, dimension = train.shape
    mean = labels.mean(0)
    centered = labels - mean
    if dimension <= n:
        values, vectors = eigh(train.T @ train, check_finite=False, driver="evd")
        left, right = other @ vectors, vectors.T @ train.T @ centered
    else:
        values, vectors = eigh(train @ train.T, check_finite=False, driver="evd")
        left, right = (other @ train.T) @ vectors, vectors.T @ centered
    values = np.maximum(values, 0.0)
    return np.stack([(left / (values + n * penalty)) @ right + mean for penalty in penalties])


def utility(values, on, off):
    return values[:, on].min(1) - np.maximum(0, values[:, off].max(1))


def activities(table, ids, replicate):
    if "id" in table.columns:
        table = table.set_index("id", verify_integrity=True)
    return table.loc[ids, [f"r{replicate}_{cell}" for cell in CELLS]].to_numpy(float)


def run(data, embeddings=None, probabilities=None, *, shared=None):
    population = (
        data["population"].query('split != "excluded_source_family"').reset_index(drop=True)
    )
    values = matrix(population.sequence, embeddings, dtype="float64")
    train = population.split.eq("train").to_numpy()
    validation = population.split.eq("validation").to_numpy()
    source = train | validation
    candidate = population.population.eq("candidate").to_numpy()
    source_ids = population.loc[source, "id"].tolist()
    labels = np.full((len(population), len(CELLS)), np.nan)
    labels[source] = (
        activities(data["source_activities"], source_ids, 1)
        + activities(data["source_activities"], source_ids, 2)
    ) / 2
    x_train, x_validation = scale(values[train], values[validation])
    validation_predictions = ridge_grid(x_train, labels[train], x_validation, PENALTIES)
    losses = ((validation_predictions - labels[validation][None]) ** 2).mean(axis=(1, 2))
    best = int(losses.argmin())
    x_source, x_candidate = scale(values[source], values[candidate])
    prediction = ridge_grid(x_source, labels[source], x_candidate, [PENALTIES[best]])[0]
    predictions = pd.DataFrame(prediction, columns=CELLS)
    predictions.insert(0, "id", population.loc[candidate, "id"].to_numpy())
    return score(data, predictions, losses)


def score(data, predictions, losses):
    """Select candidates from predicted profiles, then score held-out activities.

    Shared by evaluation and submission review. ``losses`` contains the readout's
    validation errors.
    """
    population = data["population"].query('split != "excluded_source_family"')
    train = population.split.eq("train")
    validation = population.split.eq("validation")
    source = train | validation
    candidate = population.population.eq("candidate")
    best = int(np.argmin(losses))
    candidates = population.loc[candidate].sort_values("id")
    ids = candidates.id.tolist()
    prediction = predictions.set_index("id").loc[ids, CELLS].to_numpy(dtype=float)

    # Store every selection before consulting the held-out candidate activities.
    selections, requests = [], []
    for request in data["programs"].itertuples():
        on = [CELLS.index(cell) for cell in request.on_cells.split("|")]
        off = [CELLS.index(cell) for cell in request.off_cells.split("|")]
        score = utility(prediction, on, off)
        chosen = np.lexsort((np.asarray(ids), -score))[:10]
        intended = (
            candidates.program_annotations.fillna("")
            .map(lambda annotation, name=request.program: name in annotation.split(";;"))
            .to_numpy()
        )
        if intended.sum() < 10:
            raise ValueError("Atlas intent-matched comparison cohort has fewer than ten rows")
        for rank, index in enumerate(chosen, 1):
            selections.append(
                {
                    "program": request.program,
                    "rank": rank,
                    "id": ids[index],
                    "selection_score": float(score[index]),
                }
            )
        requests.append((request.program, on, off, chosen, intended))
    measured = [activities(data["candidate_activities"], ids, rep) for rep in (1, 2)]
    scores = []
    for name, on, off, chosen, intended in requests:
        for replicate, values in enumerate(measured, 1):
            observed = utility(values, on, off)
            selected_mean, random_mean = (
                float(observed[chosen].mean()),
                float(observed[intended].mean()),
            )
            scores.append(
                {
                    "program": name,
                    "replicate": replicate,
                    "selected_utility": selected_mean,
                    "intended_random_utility": random_mean,
                    "gain": selected_mean - random_mean,
                }
            )
    scores = pd.DataFrame(scores)
    repeats = scores.groupby("replicate").gain.mean()
    return TaskResult(
        "atlas_profile",
        {
            "name": "held_u_minus_intended_random",
            "value": float(repeats.mean()),
            "unit": "log₂ activity",
            "direction": "higher",
        },
        {
            "cells": CELLS,
            "n_source_train": int(train.sum()),
            "n_source_validation": int(validation.sum()),
            "n_source_refit": int(source.sum()),
            "n_candidates": int(candidate.sum()),
            "n_requests": len(requests),
            "n_selected_per_request": 10,
            "ridge_lambda": float(PENALTIES[best]),
            "source_validation_mse": float(losses[best]),
            "penalty_grid": PENALTIES.tolist(),
            "penalty_criterion": "unweighted 12-cell validation MSE",
            "feature_scaling": "source z-score, remove std<=1e-7, divide by sqrt retained dimension",
            "refit": "source train+validation only; recompute source scaling",
            "target": "published35-normalized log2 RNA/DNA; mean of source replicates",
            "selector": "minimum ON activity minus max(0, maximum OFF activity)",
            "tie_break": "ascending candidate ID",
            "comparison": "intent-matched author design cohort",
            "aggregation": "mean requests per replicate, then mean of two replicates",
            "replicate_values": repeats.tolist(),
            "uncertainty": "descriptive replicates; no bootstrap CI",
            "candidate_labels_used_for_fitting": False,
        },
        {
            "predictions": predictions,
            "choices": pd.DataFrame(selections),
            "requests": scores,
            "validation": pd.DataFrame({"lambda": PENALTIES, "mse": losses}),
        },
    )
