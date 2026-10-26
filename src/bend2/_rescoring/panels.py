"""Rescore prior, Atlas and GTEx predictions against benchmark data.

Labels, cohort IDs and requests come from the installed assets. Validation-loss
tables check penalty selection; verifying how the model and readout produced
the predictions requires a separate rerun.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from bend2 import datasets
from bend2._tasks import atlas_profile, prior, tissue_identification


def _columns(frame, columns, label):
    if not isinstance(frame, pd.DataFrame):
        raise ValueError(f"Missing {label} table")
    if frame.columns.duplicated().any() or set(frame.columns) != set(columns):
        raise ValueError(f"{label} columns differ from the frozen evidence schema")


def _align(frame, expected, keys, label):
    """Require exactly one row per expected key, then restore canonical order."""
    if any(key not in frame for key in keys):
        raise ValueError(f"{label} is missing identifying columns")
    if frame[keys].isna().any().any() or frame.duplicated(keys).any():
        raise ValueError(f"{label} contains missing or duplicate identifiers")
    actual = frame.set_index(keys)
    index = expected.set_index(keys).index
    if len(actual) != len(index) or not actual.index.isin(index).all():
        raise ValueError(f"{label} does not contain the complete frozen cohort")
    return actual.reindex(index).reset_index()


def _numbers(frame, columns, label, *, allow_nan=False):
    for column in columns:
        if getattr(frame[column].dtype, "kind", "") not in "fiu":
            raise ValueError(f"{label}.{column} must contain numeric values")
    values = frame[columns].to_numpy(dtype=float)
    valid = ~np.isinf(values) if allow_nan else np.isfinite(values)
    if not valid.all():
        raise ValueError(f"{label} contains nonfinite values")
    return values


def _table(actual, expected, label, *, keys=None, exact=False, allow_nan=False):
    _columns(actual, expected.columns, label)
    if keys:
        actual = _align(actual, expected, keys, label)
    elif len(actual) != len(expected):
        raise ValueError(f"{label} has an unexpected number of rows")
    for column in expected:
        if pd.api.types.is_numeric_dtype(expected[column].dtype):
            found = _numbers(actual, [column], label, allow_nan=allow_nan)[:, 0]
            wanted = expected[column].to_numpy(dtype=float)
            exact_column = exact or pd.api.types.is_integer_dtype(expected[column].dtype)
            if not np.allclose(
                found,
                wanted,
                rtol=0 if exact_column else 1e-10,
                atol=0 if exact_column else 1e-12,
                equal_nan=allow_nan,
            ):
                raise ValueError(f"{label}.{column} differs from independent rescoring")
        elif actual[column].isna().any() or not np.array_equal(
            actual[column].to_numpy(), expected[column].to_numpy()
        ):
            raise ValueError(f"{label}.{column} differs from the frozen benchmark")


def _details(actual, expected, label):
    """Compare recomputable details, allowing only roundoff in derived floats."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise ValueError(f"Missing {label}")
        for key, value in expected.items():
            if key not in actual:
                raise ValueError(f"Missing {label}.{key}")
            _details(actual[key], value, f"{label}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"{label} differs from independent rescoring")
        for found, wanted in zip(actual, expected, strict=True):
            _details(found, wanted, label)
    elif isinstance(expected, float):
        exact = label.rsplit(".", 1)[-1] in {"ridge_lambda", "ridge_alpha", "penalty_grid"}
        if (
            isinstance(actual, bool)
            or not isinstance(actual, (int, float))
            or not np.isfinite(actual)
            or not np.isclose(
                actual, expected, rtol=0 if exact else 1e-10, atol=0 if exact else 1e-12
            )
        ):
            raise ValueError(f"{label} differs from independent rescoring")
    elif type(actual) is not type(expected) or actual != expected:
        raise ValueError(f"{label} differs from independent rescoring")


def _prior(tables, protocol, cache_dir):
    data = datasets.load("prior", cache_dir)
    panel = data["panel"].query('split == "evaluation"').reset_index(drop=True)
    predictions = _align(tables["predictions"], panel, ["window_id"], "prior.predictions")
    # Distinguish one distribution from a one-query stack: their accuracy tie
    # rules intentionally differ in the frozen protocol.
    single = [f"p_{base}" for base in "ACGT"]
    query_columns = [
        name
        for name in predictions
        if isinstance(name, str) and re.fullmatch(r"query_[1-9][0-9]*_p_[ACGT]", name)
    ]
    if query_columns:
        indices = {int(name.split("_")[1]) for name in query_columns}
        if indices != set(range(1, len(indices) + 1)) or any(c in predictions for c in single):
            raise ValueError("Prior query indices must be contiguous and unambiguous")
        columns = [[f"query_{i}_p_{base}" for base in "ACGT"] for i in sorted(indices)]
        if any(column not in predictions for group in columns for column in group):
            raise ValueError("Every prior query requires all four A/C/G/T probabilities")
        probabilities = np.stack(
            [_numbers(predictions, group, "prior.probabilities") for group in columns], axis=1
        )
    else:
        if any(column not in predictions for column in single):
            raise ValueError("Prior predictions require A/C/G/T probabilities")
        probabilities = _numbers(predictions, single, "prior.probabilities")
    scored = prior.run(data, probabilities=probabilities)
    # This also checks reference bases, positions, block membership, individual
    # query losses and accuracy, rather than accepting submitted target labels.
    _table(predictions, scored.tables["predictions"], "prior.predictions", keys=["window_id"])
    _details(protocol, scored.details, "prior.protocol")
    return {
        "metric": scored.metric,
        "checked": [
            "All 512 frozen windows, block IDs, reference bases and recovery positions",
            "Every probability distribution and individual-query loss/accuracy",
            "Within-window aggregation and 4,000 whole-block bootstrap draws",
        ],
    }


def _atlas(tables, protocol, cache_dir):
    data = datasets.load("atlas_profile", cache_dir)
    population = data["population"].query('split != "excluded_source_family"')
    candidates = population.loc[population.population.eq("candidate")].sort_values("id")
    submitted = tables["predictions"]
    _columns(submitted, ["id", *atlas_profile.CELLS], "atlas_profile.predictions")
    submitted = _align(submitted, candidates, ["id"], "atlas_profile.predictions")
    _numbers(submitted, atlas_profile.CELLS, "atlas_profile.predictions")

    validation = tables["validation"]
    _columns(validation, ["lambda", "mse"], "atlas_profile.validation")
    _table(
        validation[["lambda"]],
        pd.DataFrame({"lambda": atlas_profile.PENALTIES}),
        "atlas_profile.validation grid",
        exact=True,
    )
    losses = _numbers(validation, ["mse"], "atlas_profile.validation")[:, 0]
    if (losses < 0).any():
        raise ValueError("Atlas validation MSE must be nonnegative")
    scored = atlas_profile.score(data, submitted, losses)
    _table(
        tables["choices"],
        scored.tables["choices"],
        "atlas_profile.choices",
        keys=["program", "rank"],
    )
    _table(
        tables["requests"],
        scored.tables["requests"],
        "atlas_profile.requests",
        keys=["program", "replicate"],
    )
    _details(protocol, scored.details, "atlas_profile.protocol")
    return {
        "metric": scored.metric,
        "checked": [
            "All 2,411 frozen candidate IDs and finite 12-cell predictions",
            "All 16 requests, ten selections per request and ascending-ID ties",
            "Trusted candidate labels, intent-matched comparison cohorts and both replicate means",
            "Declared validation-grid penalty choice is internally consistent (fitting not rerun)",
        ],
    }


def _tissue(tables, protocol, cache_dir):
    # Do not call datasets.load/prepare: scoring needs no genome, DNA windows,
    # optional py2bit installation or model dependencies.
    with np.load(datasets.asset("gtex-targets.npz", cache_dir), allow_pickle=False) as archive:
        targets = {name: archive[name] for name in archive.files}
    genes = pd.read_csv(datasets.asset("gtex-genes.tsv", cache_dir), sep="\t")
    if not np.array_equal(genes.gene_id.to_numpy(str), targets["gene_ids"]):
        raise ValueError("Trusted GTEx sequence and target gene order differs")
    exclusions = set(datasets.MANIFEST["gtex_common_test_exclusions"])
    test = np.array([i for i in targets["test"] if targets["gene_ids"][i] not in exclusions])
    truth = np.asarray(targets["truth"][test], dtype=float)
    tissues = targets["tissues"].tolist()
    observed = [f"observed_{tissue}" for tissue in tissues]
    predicted = [f"predicted_{tissue}" for tissue in tissues]
    expected = pd.DataFrame(truth, columns=observed)
    expected.insert(0, "gene_id", targets["gene_ids"][test])
    submitted = tables["predictions"]
    _columns(submitted, ["gene_id", *predicted, *observed], "tissue_identification.predictions")
    submitted = _align(submitted, expected, ["gene_id"], "tissue_identification.predictions")
    _table(
        submitted[["gene_id", *observed]],
        expected,
        "tissue_identification.observed targets",
        keys=["gene_id"],
        exact=True,
    )
    prediction = _numbers(submitted, predicted, "tissue_identification.predictions")

    validation = tables["validation"]
    _columns(validation, ["alpha", "standardized_mse"], "tissue_identification.validation")
    _table(
        validation[["alpha"]],
        pd.DataFrame({"alpha": tissue_identification.PENALTIES}),
        "tissue_identification.validation grid",
        exact=True,
    )
    losses = _numbers(validation, ["standardized_mse"], "tissue_identification.validation")[:, 0]
    if (losses < 0).any():
        raise ValueError("GTEx validation MSE must be nonnegative")
    scored = tissue_identification.summarize(targets, test, prediction, losses)
    _table(
        tables["tissues"],
        scored.tables["tissues"],
        "tissue_identification.tissues",
        keys=["predicted_tissue"],
        allow_nan=True,
    )
    _table(
        tables["bootstrap"],
        scored.tables["bootstrap"],
        "tissue_identification.bootstrap",
        allow_nan=True,
    )
    _details(protocol, scored.details, "tissue_identification.protocol")
    return {
        "metric": scored.metric,
        "checked": [
            "All 5,782 common test genes, 51 tissues and checksum-verified expression targets",
            "Full tissue-retrieval matrix and fractional top-one tie credit",
            "All 10,000 whole-gene bootstrap draws, exclusions and confidence interval",
            "Declared validation-grid penalty choice is internally consistent (fitting not rerun)",
        ],
    }


def rescore(task: str, tables: dict[str, pd.DataFrame], protocol: dict, *, cache_dir=None) -> dict:
    """Recompute a panel score from submitted predictions and benchmark labels."""
    implementations = {"prior": _prior, "atlas_profile": _atlas, "tissue_identification": _tissue}
    if task not in implementations:
        raise ValueError(f"Unsupported panel task: {task}")
    required = {
        "prior": {"predictions"},
        "atlas_profile": {"predictions", "choices", "requests", "validation"},
        "tissue_identification": {"predictions", "tissues", "validation", "bootstrap"},
    }[task]
    if set(tables) != required:
        raise ValueError(
            f"{task} requires exactly these evidence tables: {', '.join(sorted(required))}"
        )
    for name, table in tables.items():
        if not isinstance(table, pd.DataFrame) or table.columns.duplicated().any():
            raise ValueError(f"Invalid {task}.{name} table")
    return implementations[task](tables, protocol, cache_dir)
