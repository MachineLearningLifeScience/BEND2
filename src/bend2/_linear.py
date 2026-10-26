"""Disk-backed features and bounded-memory products for the fixed ridge readout."""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

import numpy as np
from scipy.sparse.linalg import LinearOperator

# A float32 gather, its float64 conversion and the previous yielded block can
# coexist. Budget all three, independently of cohort size.
WORKING_BYTES = 32 * 1024**2


def chunk_rows(width):
    return max(1, min(8192, WORKING_BYTES // (20 * width)))


@contextmanager
def intervention_matrix(frame, embeddings, *, scratch_dir=None, progress=None):
    """Materialize float32 differences once; never hold reference/alternate matrices.

    The subtraction intentionally happens in float32 before LSQR sees float64,
    matching the frozen intervention protocol. Only this disposable matrix is
    temporary: the model inference cache belongs to the caller and is untouched.
    """
    notify = progress or (lambda message: None)
    if not len(frame):
        raise ValueError("At least one intervention is required for the readout")
    width = len(embeddings[frame.sequence_ref.iloc[0]])
    if scratch_dir is not None:
        scratch_dir = Path(scratch_dir)
        scratch_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="bend2-readout-", dir=scratch_dir) as directory:
        size = len(frame) * width * 4
        available = shutil.disk_usage(directory).free
        if size + 64 * 1024**2 > available:
            raise OSError(
                f"The fixed readout needs {size / 1024**3:.2f} GiB of temporary disk "
                f"space, but {available / 1024**3:.2f} GiB is free in {directory}. "
                "Choose a cache directory on a larger disk. Inference remains cached."
            )
        notify(
            f"Preparing {len(frame):,} × {width:,} readout features "
            f"({size / 1024**3:.2f} GiB of temporary disk space)"
        )
        path = Path(directory) / "differences.f32"
        rows = chunk_rows(width)
        buffer = np.empty((min(rows, len(frame)), width), dtype=np.float32)
        references = iter(frame.sequence_ref)
        alternates = iter(frame.sequence_alt)
        last_update = monotonic()
        with path.open("wb") as file:
            for start in range(0, len(frame), rows):
                count = min(rows, len(frame) - start)
                for index in range(count):
                    np.subtract(
                        embeddings[next(alternates)],
                        embeddings[next(references)],
                        out=buffer[index],
                        dtype=np.float32,
                    )
                buffer[:count].tofile(file)
                if monotonic() - last_update >= 10:
                    notify(f"Prepared {start + count:,}/{len(frame):,} readout rows")
                    last_update = monotonic()
        del buffer
        values = np.memmap(path, dtype=np.float32, mode="r", shape=(len(frame), width))
        try:
            yield values
        finally:
            values._mmap.close()


class InterventionDesign(LinearOperator):
    """A fold's float64 feature matrix, centered implicitly like sparse Ridge.

    The large delta block stays on disk. The small length/category block stays
    sparse. Products gather bounded row chunks, so neither a dense nor a CSR copy
    of the full fold's embedding features is allocated.
    """

    def __init__(self, values, indices, extras, *, center=False):
        self.values = values
        self.indices = np.asarray(indices)
        self.extras = extras
        self.width = values.shape[1]
        self.rows = chunk_rows(self.width)
        super().__init__(
            dtype=np.dtype("float64"), shape=(len(indices), self.width + extras.shape[1])
        )
        self.offset = np.zeros(self.shape[1])
        if center:
            total = np.zeros(self.width)
            for _, block in self.blocks():
                total += block.sum(axis=0)
            self.offset[: self.width] = total / len(indices)
            self.offset[self.width :] = np.asarray(extras.mean(axis=0)).ravel()

    def blocks(self):
        # GroupKFold's row indices are sorted. Mapping one *file* window at a time
        # also bounds resident memory on systems that ignore mmap reclaim hints.
        # Fancy-indexing an entire memmap would leave touched pages resident.
        for first in range(0, len(self.values), self.rows):
            last = min(first + self.rows, len(self.values))
            start, stop = np.searchsorted(self.indices, [first, last])
            if start == stop:
                continue
            window = np.memmap(
                self.values.filename,
                dtype=np.float32,
                mode="r",
                offset=first * self.width * 4,
                shape=(last - first, self.width),
            )
            try:
                block = np.asarray(window[self.indices[start:stop] - first], dtype=np.float64)
            finally:
                window._mmap.close()
            yield slice(start, stop), block

    def _matvec(self, coefficients):
        coefficients = np.asarray(coefficients).ravel()
        prediction = np.asarray(self.extras @ coefficients[self.width :]).ravel()
        for rows, block in self.blocks():
            prediction[rows] += block @ coefficients[: self.width]
        prediction -= self.offset @ coefficients
        return prediction

    def _rmatvec(self, values):
        values = np.asarray(values).ravel()
        product = np.empty(self.shape[1], dtype=np.float64)
        product[: self.width] = 0
        for rows, block in self.blocks():
            product[: self.width] += block.T @ values[rows]
        product[self.width :] = np.asarray(self.extras.T @ values).ravel()
        product -= self.offset * values.sum()
        return product
