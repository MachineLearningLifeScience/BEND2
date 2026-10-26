"""Rescore saved intervention predictions against the pinned experimental data.

Only predictions are contributor inputs. Cohorts, measurements, fold membership,
selection rules and aggregation come from the installed benchmark. This checks
the reported experiment's scoring, not whether its readout or model was run.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from bend2 import datasets
from bend2._tasks import background, cell_selective, context, opensplice, repair_percentile
from bend2._tasks._siraj import EXCLUDED_UNIT, paired_backgrounds, repair_candidates


# Frozen measurements and identifiers must match exactly. The tolerance applies
# only to arithmetic derived from them and submitted predictions, never ranking
# or nomination decisions. Those always use the original prediction values.
RTOL = 1e-12
ATOL = 1e-12


def _align(actual, expected, keys, name):
    if not isinstance(actual, pd.DataFrame) or actual.columns.duplicated().any():
        raise ValueError(f"{name}: expected a table with unique column names")
    if not set(keys).issubset(actual.columns):
        raise ValueError(f"{name}: missing identity columns {keys}")
    if len(actual) != len(expected):
        raise ValueError(f"{name}: expected all {len(expected)} rows, found {len(actual)}")
    actual_index = pd.MultiIndex.from_frame(actual[keys])
    expected_index = pd.MultiIndex.from_frame(expected[keys])
    if actual_index.has_duplicates:
        raise ValueError(f"{name}: duplicate identifiers")
    if expected_index.has_duplicates:
        raise ValueError(f"{name}: benchmark produced duplicate identifiers")
    positions = actual_index.get_indexer(expected_index)
    if (positions < 0).any():
        raise ValueError(f"{name}: identifiers differ from the complete frozen cohort")
    return actual.iloc[positions].reset_index(drop=True)


def _finite(frame, columns, name):
    for column in columns:
        if column not in frame or not pd.api.types.is_numeric_dtype(frame[column]):
            raise ValueError(f"{name}: {column} must contain numeric predictions")
        if pd.api.types.is_bool_dtype(frame[column]) or pd.api.types.is_complex_dtype(
            frame[column]
        ):
            raise ValueError(f"{name}: {column} must contain numeric predictions")
        if not np.isfinite(frame[column].to_numpy(dtype=float)).all():
            raise ValueError(f"{name}: {column} contains missing or nonfinite predictions")


def _compare(actual, expected, keys, name, *, exact=()):
    actual = _align(actual, expected, keys, name)
    expected = expected.reset_index(drop=True)
    if set(actual.columns) != set(expected.columns):
        raise ValueError(f"{name}: columns differ from the frozen evidence format")
    for column in expected:
        wanted, found = expected[column], actual[column]
        if pd.api.types.is_numeric_dtype(wanted):
            if (
                not pd.api.types.is_numeric_dtype(found)
                or pd.api.types.is_bool_dtype(found)
                or pd.api.types.is_complex_dtype(found)
            ):
                raise ValueError(f"{name}: {column} must contain numeric values")
            a, b = found.to_numpy(dtype=float), wanted.to_numpy(dtype=float)
            if np.isinf(a).any() or np.isinf(b).any():
                raise ValueError(f"{name}: {column} contains an infinite value")
            if column in exact or column in keys or pd.api.types.is_integer_dtype(wanted):
                matches = (a == b) | (np.isnan(a) & np.isnan(b))
            else:
                matches = np.isclose(a, b, rtol=RTOL, atol=ATOL, equal_nan=True)
            if not matches.all():
                raise ValueError(f"{name}: {column} disagrees with trusted rescoring")
        else:
            same_missing = found.isna().to_numpy() == wanted.isna().to_numpy()
            same_values = found.eq(wanted).fillna(False).to_numpy(dtype=bool)
            matches = same_missing & (same_values | wanted.isna().to_numpy())
            if not matches.all():
                raise ValueError(f"{name}: {column} disagrees with trusted rescoring")


def _protocol(actual, expected):
    # Execution is a later descriptive annotation. Older evidence with the same
    # numerical protocol remains reviewable; if present, the annotation is checked.
    expected = dict(expected)
    if "execution" not in actual:
        expected.pop("execution", None)
    if set(actual) != set(expected):
        raise ValueError("Task protocol fields differ from the frozen scoring contract")
    for key, value in expected.items():
        if actual[key] != value or (
            isinstance(value, (int, float)) and isinstance(actual[key], bool)
        ):
            raise ValueError(f"Task protocol {key} differs from trusted rescoring")


def _folds(frame, group):
    values = frame[group].to_numpy()
    folds = np.empty(len(frame), dtype=np.int8)
    for fold, (_, test) in enumerate(GroupKFold(5).split(frame, groups=values)):
        folds[test] = fold
    return folds


def _group_folds(frame):
    return pd.Series(_folds(frame, "unit_id"), index=frame.unit_id).groupby(level=0).first()


def _intervention_predictions(frame, actual, group, *, context=False):
    columns = list(
        dict.fromkeys(
            ["record_id", group, "delta_y"] + (["ID", "context_id"] if "ID" in frame else [])
        )
    )
    expected = frame[columns].copy().reset_index(drop=True)
    aligned = _align(actual, expected, ["record_id"], "predictions")
    _finite(aligned, ["y_pred"], "predictions")
    predictions = aligned.y_pred.to_numpy()
    if context and not np.array_equal(predictions, predictions.astype(np.float32)):
        raise ValueError("Context predictions must preserve the frozen float32 readout")
    expected["y_true"] = frame.delta_y.to_numpy(float)
    expected["y_pred"] = predictions
    expected["fold"] = _folds(frame, group)
    return expected


def _correlation(task, data, tables):
    is_context = task == "context"
    group = "unit_id" if is_context else "gene_id"
    frame = data["context"] if is_context else data["records"]
    predictions = _intervention_predictions(frame, tables["predictions"], group, context=is_context)
    result = (context if is_context else opensplice).score(predictions)
    return result, {
        "predictions": (["record_id"], ["delta_y", "y_true"]),
        "groups": ([group], []),
    }


def _background(data, tables):
    records, _ = paired_backgrounds(data["records"])
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
    key = ["unit_id", "mutation_position", "mutation_ref", "mutation_alt"]
    complete = states.groupby(key).state.nunique()
    states = states.merge(complete[complete.eq(2)].reset_index()[key], on=key)
    predictions = states.pivot(index=key, columns="state", values="truth").dropna()
    predictions = predictions.rename(columns={"A": "truth_A", "R": "truth_R"}).reset_index()
    actual = _align(tables["predictions"], predictions, key, "predictions")
    _finite(actual, ["prediction_A", "prediction_R"], "predictions")
    for state in ("A", "R"):
        predictions[f"prediction_{state}"] = actual[f"prediction_{state}"].to_numpy()
    predictions["fold"] = predictions.unit_id.map(_group_folds(data["records"]))
    return background.score(predictions), {
        "predictions": (key, ["truth_A", "truth_R", "y_true"]),
        "groups": (["unit_id"], []),
    }


def _repair(data, tables):
    construct = repair_candidates(data["records"])
    key = ["unit_id", "state", "context_id"]
    targets = construct.loc[
        construct.is_direct & construct.resolved, key + ["delta_y", "sigma"]
    ].rename(columns={"delta_y": "target_y", "sigma": "target_sigma"})
    columns = key + ["record_id", "mutation_position", "delta_y", "sigma"]
    candidates = construct.loc[construct.is_candidate, columns].merge(
        targets, on=key, validate="many_to_one"
    )
    actual = _align(tables["predictions"], candidates, ["record_id"], "predictions")
    _finite(actual, ["y_pred", "target_prediction"], "predictions")
    candidates["y_pred"] = actual.y_pred.to_numpy()
    candidates["target_prediction"] = actual.target_prediction.to_numpy()
    if not candidates.groupby(key).target_prediction.nunique().eq(1).all():
        raise ValueError("Repair target predictions differ within the same frozen request")
    candidates["fold"] = candidates.unit_id.map(_group_folds(data["records"]))
    exact = ["delta_y", "sigma", "target_y", "target_sigma"]
    return repair_percentile.score(candidates), {
        "predictions": (["record_id"], exact),
        "choices": (key, exact),
        "groups": (["unit_id"], []),
    }


def _selective(data, tables):
    pool = data["records"].loc[data["records"].unit_id.ne(EXCLUDED_UNIT)]
    predictions = pool[["ID", "unit_id", "background_id"]].drop_duplicates("ID").sort_values("ID")
    actual = _align(tables["predictions"], predictions, ["ID"], "predictions")
    _finite(actual, ["pred_hepg2", "pred_k562"], "predictions")
    for cell in ("hepg2", "k562"):
        predictions[f"pred_{cell}"] = actual[f"pred_{cell}"].to_numpy()
    predictions["fold"] = predictions.unit_id.map(_group_folds(data["records"]))
    return cell_selective.score(predictions, data["selective_outcomes"]), {
        "predictions": (["ID"], ["truth_hepg2", "truth_k562"]),
        "choices": (["background_id", "target_cell", "ID"], []),
        "groups": (["unit_id"], []),
    }


def rescore(task: str, tables: dict[str, pd.DataFrame], protocol: dict, *, cache_dir=None) -> dict:
    """Check complete saved evidence and return its independently recomputed metric.

    No contributor code is imported or run. Prediction values are inputs to this
    review; verifying that a declared model/readout produced them requires a rerun.
    """
    if task not in {"opensplice", "context", "background", "repair_percentile", "cell_selective"}:
        raise ValueError(f"Unknown intervention rescoring task: {task}")
    names = {"predictions", "groups"} | (
        {"choices"} if task in {"repair_percentile", "cell_selective"} else set()
    )
    if set(tables) != names:
        raise ValueError(f"{task}: expected evidence tables {sorted(names)}")
    data = datasets.load(task, cache_dir)
    if task in {"opensplice", "context"}:
        result, identities = _correlation(task, data, tables)
    else:
        function = {
            "background": _background,
            "repair_percentile": _repair,
            "cell_selective": _selective,
        }[task]
        result, identities = function(data, tables)
    for name, frame in result.tables.items():
        keys, exact = identities[name]
        _compare(tables[name], frame, keys, f"{task}/{name}", exact=exact)
    _protocol(protocol, result.details)
    checked = [
        "Complete frozen cohort identifiers and biological group membership",
        "Frozen experimental measurements from checksum-verified benchmark data",
        "Five-fold GroupKFold membership reconstructed from the complete frozen readout cohort",
        "Per-group scores, aggregation, bootstrap interval and protocol counts recomputed",
    ]
    if task == "background":
        checked.append(
            "Complete paired-background contrasts reconstructed from submitted state predictions"
        )
    elif task == "repair_percentile":
        checked.append(
            "Resolved direct-swap requests, full candidate pools, tie-breaking, choices and measured ranks reconstructed"
        )
    elif task == "cell_selective":
        checked.append(
            "Complete candidate pools, uniform tied choices, no-edit decisions and measured utility reconstructed"
        )
    return {"metric": result.metric, "checked": checked}
