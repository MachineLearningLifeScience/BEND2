"""Fixed readouts shared by intervention tasks.

Frozen sequence embeddings are never fine-tuned. Five-fold GroupKFold holds out
whole biological groups; category encoders and the ridge fit see training rows
only. These choices are part of the benchmark protocol, not tuning options.
"""

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import OneHotEncoder

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
}


def matrix(sequences, embeddings, *, n=None):
    """Gather into one allocation; a lazy sequence iterator supplies its row count."""
    n = len(sequences) if n is None else n
    if n < 1:
        raise ValueError("At least one sequence is required for the readout")
    iterator = iter(sequences)
    first = embeddings[next(iterator)]
    values = np.empty((n, len(first)), dtype=np.float32)
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


def intervention_predictions(frame, embeddings, group_column="unit_id", dtype="float64"):
    """Return out-of-group predictions in the input record order."""
    groups = frame[group_column].to_numpy()
    if len(np.unique(groups)) < 5:
        raise ValueError("The fixed readout requires at least five biological groups")
    prediction = np.empty(len(frame), dtype=dtype)
    folds = np.empty(len(frame), dtype=np.int8)

    def features(rows, encoder, fit=False):
        delta = matrix(rows.sequence_alt, embeddings) - matrix(rows.sequence_ref, embeddings)
        length = (rows.sequence_alt.str.len() - rows.sequence_ref.str.len()).to_numpy()[:, None]
        categories = rows[["context_id", "intervention_type"]]
        encoded = encoder.fit_transform(categories) if fit else encoder.transform(categories)
        return sparse.hstack(
            (sparse.csr_matrix(delta), sparse.csr_matrix(length), encoded), format="csr"
        )

    for fold, (train, test) in enumerate(GroupKFold(5).split(frame, groups=groups)):
        encoder = OneHotEncoder(handle_unknown="ignore")
        ridge = Ridge(alpha=10.0, solver="lsqr", tol=1e-4)
        ridge.fit(
            features(frame.iloc[train], encoder, fit=True),
            frame.iloc[train].delta_y.to_numpy(float),
        )
        prediction[test] = ridge.predict(features(frame.iloc[test], encoder))
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
            frame, embeddings, dtype="float32" if head == "context" else "float64"
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
