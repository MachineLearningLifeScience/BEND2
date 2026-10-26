"""Fit ridge readouts to model embeddings.

Five-fold GroupKFold holds out whole biological groups. Category encoders and
ridge coefficients are fitted on training rows; the embedding model stays fixed.
"""

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import spearmanr
from scipy.sparse.linalg import lsqr
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import OneHotEncoder

from bend2._linear import InterventionDesign, intervention_matrix

PROTOCOL = {
    "readout": "ridge",
    "alpha": 10.0,
    "solver": "lsqr",
    "tol": 1e-4,
    "folds": 5,
    "splitter": "GroupKFold(shuffle=False)",
    "features": [
        "alternate-minus-reference embedding",
        "length difference",
        "one-hot context",
        "one-hot intervention type",
    ],
    "normalization": "none",
    "embedding_dtype": "float32",
    "execution": {
        "features": "float32 differences on temporary disk; removed after fitting",
        "small_design": "sklearn sparse Ridge within a 128 MiB allocation estimate",
        "large_design": "implicitly centered float64 LSQR with bounded row chunks",
        "feature_chunk_budget_bytes": 32 * 1024**2,
    },
}


def matrix(sequences, embeddings, *, n=None, dtype="float32"):
    """Gather into one allocation; a lazy sequence iterator supplies its row count."""
    n = len(sequences) if n is None else n
    if n < 1:
        raise ValueError("At least one sequence is required for the readout")
    iterator = iter(sequences)
    first = embeddings[next(iterator)]
    values = np.empty((n, len(first)), dtype=dtype)
    values[0] = first
    count = 1
    for index, sequence in enumerate(iterator, start=1):
        if index >= n:
            raise ValueError("Sequence iterator exceeds its declared row count")
        values[index] = embeddings[sequence]
        count += 1
    if count != n:
        raise ValueError("Sequence iterator ended before its declared row count")
    return values


def intervention_predictions(
    frame, embeddings, group_column="unit_id", dtype="float64", *, scratch_dir=None, progress=None
):
    """Return out-of-group predictions; large representations stay on disk."""
    groups = frame[group_column].to_numpy()
    if len(np.unique(groups)) < 5:
        raise ValueError("The fixed readout requires at least five biological groups")
    prediction = np.empty(len(frame), dtype=dtype)
    folds = np.empty(len(frame), dtype=np.int8)
    notify = progress or (lambda message: None)
    length = (frame.sequence_alt.str.len() - frame.sequence_ref.str.len()).to_numpy()[:, None]
    categories = frame[["context_id", "intervention_type"]]

    with intervention_matrix(
        frame, embeddings, scratch_dir=scratch_dir, progress=notify
    ) as differences:
        for fold, (train, test) in enumerate(GroupKFold(5).split(frame, groups=groups)):
            notify(f"Fitting fixed ridge readout: fold {fold + 1}/5")
            encoder = OneHotEncoder(handle_unknown="ignore")
            training_extras = sparse.hstack(
                (sparse.csr_matrix(length[train]), encoder.fit_transform(categories.iloc[train])),
                format="csr",
            )
            target = frame.delta_y.to_numpy(float)[train]
            test_extras = sparse.hstack(
                (sparse.csr_matrix(length[test]), encoder.transform(categories.iloc[test])),
                format="csr",
            )
            # Retain sklearn's original arithmetic for small representations.
            # This conservative allowance covers temporary gathers and CSR copies;
            # larger representations use exactly the same LSQR objective below.
            small = len(train) * 32 * (differences.shape[1] + 3) <= 128 * 1024**2
            if small:
                training_features = sparse.hstack(
                    (sparse.csr_matrix(differences[train]), training_extras), format="csr"
                )
                ridge = Ridge(alpha=10.0, solver="lsqr", tol=1e-4)
                ridge.fit(training_features, target)
                del training_features
                held_out = sparse.hstack(
                    (sparse.csr_matrix(differences[test]), test_extras), format="csr"
                )
                prediction[test] = ridge.predict(held_out)
            else:
                design = InterventionDesign(differences, train, training_extras, center=True)
                target_mean = target.mean()
                # Same objective, centering, damping, tolerance and default iteration
                # limit as sklearn Ridge(alpha=10, solver="lsqr", fit_intercept=True).
                coefficients = lsqr(
                    design, target - target_mean, damp=np.sqrt(10.0), atol=1e-4, btol=1e-4
                )[0]
                intercept = target_mean - design.offset @ coefficients
                held_out = InterventionDesign(differences, test, test_extras)
                prediction[test] = held_out @ coefficients + intercept
            folds[test] = fold
    if not np.isfinite(prediction).all():
        raise ValueError("The fixed readout produced nonfinite predictions")
    columns = list(
        dict.fromkeys(
            ["record_id", group_column, "delta_y"] + (["ID", "context_id"] if "ID" in frame else [])
        )
    )
    result = frame[columns].copy()
    result["y_true"] = frame.delta_y.to_numpy(float)
    result["y_pred"], result["fold"] = prediction, folds
    return result


def siraj_predictions(data, embeddings, shared, head="per_cell"):
    """Reuse the same two Siraj readouts across all four endpoints in a run."""
    shared = {} if shared is None else shared
    key = ("siraj", head)
    if key not in shared:
        frame = data["context"] if head == "context" else data["records"]
        shared[key] = intervention_predictions(
            frame,
            embeddings,
            dtype="float32" if head == "context" else "float64",
            scratch_dir=shared.get("scratch_dir"),
            progress=shared.get("progress"),
        )
    return shared[key]


def mean_interval(values, *, replicates, seed, multinomial=False):
    """Percentile interval over whole groups, preserving each task's draw scheme."""
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    if multinomial:
        counts = rng.multinomial(
            len(values), np.full(len(values), 1 / len(values)), size=replicates
        )
        estimates = (counts / len(values)) @ values
    else:
        estimates = rng.choice(values, size=(replicates, len(values)), replace=True).mean(1)
    return np.quantile(estimates, [0.025, 0.975]).tolist()


def macro_spearman(predictions, group_column, *, replicates, seed):
    """Macro-average defined within-group correlations; report undefined groups."""
    rows = []
    for identifier, group in predictions.groupby(group_column, sort=True):
        truth, prediction = group.y_true.to_numpy(float), group.y_pred.to_numpy(float)
        defined = len(truth) >= 2 and np.ptp(truth) > 0 and np.ptp(prediction) > 0
        value = float(spearmanr(truth, prediction).statistic) if defined else np.nan
        rows.append({group_column: identifier, "spearman": value, "n_records": len(group)})
    groups = pd.DataFrame(rows)
    defined = groups.spearman.dropna()
    metric = {
        "name": "macro_spearman",
        "value": float(defined.mean()) if len(defined) else None,
        "unit": "Spearman ρ",
        "direction": "higher",
        "ci95": mean_interval(defined, replicates=replicates, seed=seed),
    }
    return metric, groups
