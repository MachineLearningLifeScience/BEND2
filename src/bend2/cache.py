"""Batched, resumable inference without holding long DNA strings in memory."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping

import numpy as np


def key(sequence):
    return hashlib.sha256(sequence.encode("ascii")).digest()


def validate(value, rows, width=None):
    if not isinstance(value, np.ndarray) or value.ndim != 2 or value.shape[0] != rows:
        raise ValueError("embed must return a NumPy array [batch, features]; pool tokens first")
    if value.shape[1] == 0 or (width is not None and value.shape[1] != width):
        raise ValueError("Embedding dimension must be nonzero and fixed across batches")
    if value.dtype.kind not in "fiu":
        raise ValueError("Embeddings must be real numbers")
    with np.errstate(over="ignore", invalid="ignore"):
        value = np.asarray(value, dtype="<f4")
    if not np.isfinite(value).all():
        raise ValueError("Embeddings must be finite and fit in float32")
    return value


class Embeddings(Mapping):
    """SQLite commits each batch; only sequence hashes and vectors are retained."""

    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=60)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS vectors (key BLOB PRIMARY KEY, value BLOB, digest BLOB) WITHOUT ROWID"
        )
        row = self.db.execute("SELECT length(value) FROM vectors LIMIT 1").fetchone()
        self.width = row[0] // 4 if row else None

    def __len__(self):
        return self.db.execute("SELECT count(*) FROM vectors").fetchone()[0]

    def __iter__(self):
        raise TypeError("Look up embeddings by DNA sequence; raw DNA is not retained in the cache")

    def __getitem__(self, sequence):
        row = self.db.execute(
            "SELECT value,digest FROM vectors WHERE key=?", (key(sequence),)
        ).fetchone()
        if row is None:
            raise KeyError("Sequence was not embedded")
        value, digest = row
        if hashlib.sha256(value).digest() != digest:
            raise ValueError("Embedding cache checksum mismatch; remove this model cache and rerun")
        result = np.frombuffer(value, dtype="<f4")
        if len(result) != self.width or not np.isfinite(result).all():
            raise ValueError("Invalid cached embedding dimension or values")
        return result

    def fill(self, sequences, embed, batch_size, progress):
        batch, pending = [], set()
        seen = {row[0] for row in self.db.execute("SELECT key FROM vectors")}
        count = 0

        def flush():
            nonlocal count
            values = validate(embed(batch), len(batch), self.width)
            self.width = values.shape[1]
            rows = []
            for sequence, vector in zip(batch, values, strict=True):
                raw = vector.tobytes()
                rows.append((key(sequence), raw, hashlib.sha256(raw).digest()))
            with self.db:
                self.db.executemany("INSERT OR IGNORE INTO vectors VALUES (?,?,?)", rows)
            count += len(batch)
            seen.update(pending)
            progress(f"Embedded {count:,} new sequences ({len(seen):,} cached)")
            batch.clear()
            pending.clear()

        for sequence in sequences:
            digest = key(sequence)
            if digest not in seen and digest not in pending:
                batch.append(sequence)
                pending.add(digest)
                if len(batch) == batch_size:
                    flush()
        if batch:
            flush()
        return {
            "new_sequences": count,
            "cached_sequences": len(seen),
            "dimension": self.width,
            "dtype": "float32",
        }

    def close(self):
        self.db.close()


class Probabilities:
    """Checkpoint native-prior batches in float64, including individual-query shape."""

    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=60)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS probabilities "
            "(key BLOB PRIMARY KEY, shape TEXT, value BLOB, digest BLOB) WITHOUT ROWID"
        )

    def evaluate(self, sequences, positions, callback, batch_size, progress):
        keys = [
            key(f"{position}:{sequence}")
            for sequence, position in zip(sequences, positions, strict=True)
        ]
        values, missing = [None] * len(keys), []
        shape = None
        for index, identity in enumerate(keys):
            row = self.db.execute(
                "SELECT shape,value,digest FROM probabilities WHERE key=?", (identity,)
            ).fetchone()
            if row is None:
                missing.append(index)
                continue
            dimensions, raw, checksum = row
            if hashlib.sha256(raw).digest() != checksum:
                raise ValueError("Probability cache checksum mismatch; remove this model cache")
            values[index] = np.frombuffer(raw, dtype="<f8").reshape(json.loads(dimensions))
            shape = self._validate(values[index][None, ...], 1, shape)
        for start in range(0, len(missing), batch_size):
            indices = missing[start : start + batch_size]
            batch = callback([sequences[i] for i in indices], [positions[i] for i in indices])
            shape = self._validate(batch, len(indices), shape)
            batch = np.asarray(batch, dtype="<f8")
            rows = []
            for index, value in zip(indices, batch, strict=True):
                raw = value.tobytes()
                rows.append((keys[index], json.dumps(shape), raw, hashlib.sha256(raw).digest()))
                values[index] = value.copy()
            with self.db:
                self.db.executemany("INSERT OR IGNORE INTO probabilities VALUES (?,?,?,?)", rows)
            progress(f"Scored {start + len(indices):,} new prior windows")
        return np.stack(values), {
            "new_sequences": len(missing),
            "cached_sequences": len(keys) - len(missing),
            "shape_per_window": list(shape),
            "dtype": "float64",
        }

    @staticmethod
    def _validate(values, rows, shape):
        if (
            not isinstance(values, np.ndarray)
            or values.ndim not in (2, 3)
            or values.shape[0] != rows
            or values.shape[-1] != 4
            or (values.ndim == 3 and values.shape[1] < 1)
            or values.dtype.kind not in "fiu"
        ):
            raise ValueError("probabilities must return NumPy [batch, 4] or [batch, queries, 4]")
        if shape is not None and values.shape[1:] != shape:
            raise ValueError("Probability query shape must stay fixed across batches")
        if (
            not np.isfinite(values).all()
            or ((values < 0) | (values > 1)).any()
            or not np.allclose(values.sum(-1), 1, atol=1e-7, rtol=0)
        ):
            raise ValueError("Probabilities must be finite, in [0, 1], and sum to one")
        return values.shape[1:]

    def close(self):
        self.db.close()
