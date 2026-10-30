from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder, StandardScaler, normalize


def load_readout(path: str | Path):
    """Load a saved readout, including class paths from before the package rename."""
    aliases = {
        "gimbench" + suffix: import_module("genomic_bending" + suffix)
        for suffix in (
            "", ".models", ".models.embeddings", ".models.context", ".models.kmer",
            ".models.projection",
        )
    }
    previous = {name: sys.modules.get(name) for name in aliases}
    sys.modules.update(aliases)
    try:
        return joblib.load(path)
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def load_embedding_archive(path: str) -> tuple[dict[str, int], np.ndarray]:
    archive = np.load(path, allow_pickle=False)
    sequences = archive["sequences"].astype(str)
    embeddings = archive["embeddings"].astype(np.float32, copy=False)
    if len(sequences) != len(embeddings):
        raise ValueError("Embedding archive sequence and matrix lengths differ")
    if len(set(sequences)) != len(sequences):
        raise ValueError("Embedding archive contains duplicate sequences")
    nonfinite_rows = ~np.isfinite(embeddings).all(axis=1)
    invalid_nonfinite = [
        sequence
        for sequence in sequences[nonfinite_rows]
        if not sequence or set(sequence.upper()) != {"N"}
    ]
    if invalid_nonfinite:
        raise ValueError("Embedding archive contains non-finite values for a valid sequence")
    return {sequence: index for index, sequence in enumerate(sequences)}, embeddings


class EmbeddingContextRidge:
    def __init__(
        self,
        sequence_index: dict[str, int],
        embeddings: np.ndarray,
        alpha: float = 10.0,
        normalization: str = "none",
    ) -> None:
        if normalization not in {"none", "l2", "standardize"}:
            raise ValueError("normalization must be one of: none, l2, standardize")
        self.sequence_index = sequence_index
        self.embeddings = embeddings
        self.context = OneHotEncoder(handle_unknown="ignore")
        self.regressor = Ridge(alpha=alpha, solver="lsqr")
        self.normalization = normalization
        self.scaler = StandardScaler() if normalization == "standardize" else None

    def _sequence_features(self, frame: pd.DataFrame) -> np.ndarray:
        try:
            indices = np.fromiter(
                (self.sequence_index[sequence] for sequence in frame["sequence_alt"]),
                dtype=np.int64,
                count=len(frame),
            )
        except KeyError as error:
            missing = error.args[0]
            raise KeyError(f"Missing sequence in embedding archive: {missing[:30]}...") from error
        return self.embeddings[indices]

    def fit(self, frame: pd.DataFrame, target: str = "y_alt") -> EmbeddingContextRidge:
        sequence_values = self._sequence_features(frame)
        if self.normalization == "l2":
            sequence_values = normalize(sequence_values, norm="l2")
        elif self.scaler is not None:
            sequence_values = self.scaler.fit_transform(sequence_values)
        sequence = sparse.csr_matrix(sequence_values)
        context = self.context.fit_transform(frame[["context_id"]])
        self.regressor.fit(
            sparse.hstack([sequence, context], format="csr"),
            frame[target].to_numpy(dtype=float),
        )
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        sequence_values = self._sequence_features(frame)
        if self.normalization == "l2":
            sequence_values = normalize(sequence_values, norm="l2")
        elif self.scaler is not None:
            sequence_values = self.scaler.transform(sequence_values)
        sequence = sparse.csr_matrix(sequence_values)
        context = self.context.transform(frame[["context_id"]])
        return self.regressor.predict(sparse.hstack([sequence, context], format="csr"))


class InterventionEmbeddingRidge:
    """Linear probe over alternate-minus-reference frozen representations."""

    def __init__(
        self,
        sequence_index: dict[str, int],
        embeddings: np.ndarray,
        alpha: float = 10.0,
        normalization: str = "none",
    ) -> None:
        if normalization not in {"none", "l2", "standardize"}:
            raise ValueError("normalization must be one of: none, l2, standardize")
        self.sequence_index = sequence_index
        self.embeddings = embeddings
        self.context = OneHotEncoder(handle_unknown="ignore")
        self.intervention = OneHotEncoder(handle_unknown="ignore")
        self.regressor = Ridge(alpha=alpha, solver="lsqr")
        self.normalization = normalization
        self.scaler = StandardScaler() if normalization == "standardize" else None

    def _indices(self, values: pd.Series) -> np.ndarray:
        try:
            return np.fromiter(
                (self.sequence_index[sequence] for sequence in values),
                dtype=np.int64,
                count=len(values),
            )
        except KeyError as error:
            missing = error.args[0]
            raise KeyError(f"Missing sequence in embedding archive: {missing[:30]}...") from error

    def _features(self, frame: pd.DataFrame, fit: bool) -> sparse.csr_matrix:
        reference = self._indices(frame["sequence_ref"])
        alternate = self._indices(frame["sequence_alt"])
        delta_values = self.embeddings[alternate] - self.embeddings[reference]
        if self.normalization == "l2":
            delta_values = normalize(delta_values, norm="l2")
        elif self.scaler is not None:
            delta_values = (
                self.scaler.fit_transform(delta_values)
                if fit
                else self.scaler.transform(delta_values)
            )
        delta = sparse.csr_matrix(delta_values)
        length_delta = sparse.csr_matrix(
            (
                frame["sequence_alt"].str.len().to_numpy()
                - frame["sequence_ref"].str.len().to_numpy()
            ).reshape(-1, 1)
        )
        if fit:
            context = self.context.fit_transform(frame[["context_id"]])
            intervention = self.intervention.fit_transform(frame[["intervention_type"]])
        else:
            context = self.context.transform(frame[["context_id"]])
            intervention = self.intervention.transform(frame[["intervention_type"]])
        return sparse.hstack([delta, length_delta, context, intervention], format="csr")

    def fit(self, frame: pd.DataFrame, target: str = "delta_y") -> InterventionEmbeddingRidge:
        self.regressor.fit(self._features(frame, fit=True), frame[target].to_numpy(dtype=float))
        return self

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        return self.regressor.predict(self._features(frame, fit=False))
