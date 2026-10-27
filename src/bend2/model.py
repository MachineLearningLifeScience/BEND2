"""A model is a function and a description, independent of its ML framework."""

from __future__ import annotations

import hashlib
import inspect
import json
import marshal
import re
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
    inference_config: dict = field(default_factory=dict)
    unsupported_tasks: dict[str, str] = field(default_factory=dict)
    _source_file: Path | None = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if self.embed is None and self.probabilities is None:
            raise ValueError("Provide embed=, probabilities=, or both")

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
        result["inference_config"] = self.inference_config
        result["unsupported_tasks"] = self.unsupported_tasks
        result["capabilities"] = [
            name for name in ("embed", "probabilities") if getattr(self, name) is not None
        ]
        return result

    def inference_identity(self, capability):
        """Cache weights, representation and adapter code independently of display metadata.

        Declare inference-affecting options (precision, preprocessing and device) in
        ``inference_config``. Change ``revision`` when weights or external helpers change.
        Callbacks must produce the same representation independently of batch size.
        """
        if capability not in ("embed", "probabilities") or getattr(self, capability) is None:
            raise ValueError(f"Model does not provide {capability}")
        fields = (
            ("revision", "representation", "pooling")
            if capability == "embed"
            else ("revision", "probability_interface")
        )
        return {
            **{key: getattr(self, key).strip() for key in fields},
            "inference_config": self.inference_config,
            "adapter": _inference_code(getattr(self, capability)),
        }

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
            module = re.sub(r"^_bend2_model_[0-9a-f]+$", "user_model", getattr(target, "__module__", ""))
            result["adapter"][name] = {
                "callable": f"{module}.{getattr(target, '__qualname__', '')}",
                "source_sha256": hashlib.sha256(source).hexdigest(),
                "inference_sha256": hashlib.sha256(
                    json.dumps(self.inference_identity(name), sort_keys=True).encode()
                ).hexdigest(),
            }
        if self._source_file is not None:
            result["adapter"]["file"] = hashlib.sha256(self._source_file.read_bytes()).hexdigest()
        return result


def _inference_code(function):
    """Fingerprint executable callback source and its local callable helpers.

    Keep the complete adapter file in run provenance; editing its model label or
    citation should not invalidate expensive inference. External weights, mutable
    state and non-callable configuration are declared by revision/configuration.
    """

    def owner(value):
        if inspect.ismethod(value):
            bound = value.__self__
            return bound if inspect.isclass(bound) else type(bound)
        return value if inspect.isroutine(value) or inspect.isclass(value) else type(value)

    pending, seen, sources = [owner(function)], set(), {}
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        try:
            source = inspect.getsource(item).encode()
        except (OSError, TypeError):
            code = getattr(item, "__code__", None)
            source = marshal.dumps(code) if code else repr(item).encode()
        name = getattr(item, "__qualname__", type(item).__qualname__)
        sources[name] = hashlib.sha256(source).hexdigest()
        module = getattr(item, "__module__", None)
        if inspect.isclass(item):
            # Capture inherited adapter implementations, without following an
            # imported framework's class hierarchy or traversing model weights.
            pending.extend(base for base in item.__bases__ if base.__module__ == module)
            methods = []
            for member in vars(item).values():
                if isinstance(member, (staticmethod, classmethod)):
                    methods.append(member.__func__)
                elif isinstance(member, property):
                    methods.extend(part for part in (member.fget, member.fset) if part)
                else:
                    methods.append(member)
            # Fingerprint methods independently too: notebook-defined classes
            # often have no inspectable class source, while their code is present.
            pending.extend(
                member
                for member in methods
                if (inspect.isfunction(member) or inspect.isclass(member))
                and getattr(member, "__module__", None) == module
            )
            continue
        else:
            methods = [item]
        for method in methods:
            code = getattr(method, "__code__", None)
            namespace = getattr(method, "__globals__", {})
            helpers = [namespace.get(key) for key in code.co_names] if code else []
            for cell in getattr(method, "__closure__", None) or ():
                try:
                    helpers.append(cell.cell_contents)
                except ValueError:  # An uninitialized closure cell has no dependency yet.
                    pass
            for helper in helpers:
                if callable(helper):
                    target = owner(helper)
                    if getattr(target, "__module__", None) == module:
                        pending.append(target)
    return sources


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
