"""A model is a function and a description, independent of its ML framework."""

from __future__ import annotations

import hashlib
import inspect
import marshal
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Model:
    """Connect a frozen model to BEND 2.0.

    ``embed(list[str])`` returns a finite [batch, features] NumPy array.
    ``probabilities(list[str], list[int])`` returns [batch, 4] probabilities in
    A/C/G/T order for the supplied, already hidden, zero-based target positions.
    Return [batch, queries, 4] to average individual query losses instead.
    Declare a stable revision before reusing inference across runs.
    """

    name: str
    embed: Callable | None = field(default=None, repr=False)
    probabilities: Callable | None = field(default=None, repr=False)
    revision: str = ""
    training_data: str = ""
    representation: str = ""
    pooling: str = ""
    probability_interface: str = ""
    source: str = ""
    _source_file: Path | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Give your model a nonempty name")
        if self.embed is None and self.probabilities is None:
            raise ValueError("Provide embed=, probabilities=, or both")
        for key in ("embed", "probabilities"):
            if getattr(self, key) is not None and not callable(getattr(self, key)):
                raise TypeError(f"{key} must be callable")
        for key in (
            "revision",
            "training_data",
            "representation",
            "pooling",
            "probability_interface",
            "source",
        ):
            if not isinstance(getattr(self, key), str):
                raise TypeError(f"{key} must be a string")

    def metadata(self):
        fields = (
            "name",
            "revision",
            "training_data",
            "representation",
            "pooling",
            "probability_interface",
            "source",
        )
        result = {name: getattr(self, name).strip() for name in fields}
        result["capabilities"] = [
            name for name in ("embed", "probabilities") if getattr(self, name) is not None
        ]
        return result

    def identity(self):
        """Bind declared weights/preprocessing and the adapter's available source."""
        result = self.metadata()
        result["adapter"] = {}
        for name in result["capabilities"]:
            function = getattr(self, name)
            target = function if inspect.isroutine(function) else type(function)
            try:
                path = inspect.getsourcefile(target)
                source = (
                    Path(path).read_bytes()
                    if path and Path(path).is_file()
                    else inspect.getsource(target).encode()
                )
            except (OSError, TypeError):
                source = (
                    marshal.dumps(function.__code__)
                    if hasattr(function, "__code__")
                    else repr(target).encode()
                )
            result["adapter"][name] = {
                "callable": f"{getattr(target, '__module__', '')}.{getattr(target, '__qualname__', '')}",
                "source_sha256": hashlib.sha256(source).hexdigest(),
            }
        if self._source_file is not None:
            result["adapter"]["file"] = hashlib.sha256(self._source_file.read_bytes()).hexdigest()
        return result


def composition():
    """The four-feature base-composition baseline. No model download required."""

    def embed(sequences):
        return np.array(
            [[sequence.count(base) / len(sequence) for base in "ACGT"] for sequence in sequences],
            dtype=np.float32,
        )

    return Model(
        "Base composition",
        embed=embed,
        revision="composition-v1",
        training_data="none; deterministic sequence statistics",
        representation="four A/C/G/T fractions",
        pooling="whole input sequence",
    )


def uniform():
    """A native prior baseline with exactly two bits per hidden nucleotide."""

    def probabilities(sequences, positions):
        return np.full((len(sequences), 4), 0.25)

    return Model(
        "Uniform prior",
        probabilities=probabilities,
        revision="uniform-v1",
        training_data="none",
        probability_interface="uniform A/C/G/T distribution",
    )
