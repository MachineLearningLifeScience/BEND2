"""Copy the packaged examples into editable model adapters."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path


TEMPLATES = {
    "custom": {
        "description": "Your encoder; starts with a working CPU composition example",
        "tasks": "atlas_profile",
        "extra": None,
        "file": "custom.py",
    },
    "huggingface": {
        "description": "A pinned HyenaDNA encoder using the generic Hugging Face adapter",
        "tasks": "atlas_profile",
        "extra": "huggingface",
        "file": "huggingface.py",
    },
    "dnabert2": {
        "description": "Pinned DNABERT-2 117M embeddings with the model-specific adapter",
        "tasks": "atlas_profile",
        "extra": "reference",
        "file": "dnabert2.py",
    },
    "ntv3-prior": {
        "description": "Pinned NTv3 100M-post with the paper's two-query prior readout",
        "tasks": "prior",
        "extra": "reference",
        "file": "ntv3_prior.py",
    },
}


def write_template(path, template="custom") -> Path:
    """Copy an example without importing it or replacing an existing file.

    The source is identical to the example shipped in the package. Adapter
    generation never loads a model or interpolates a filename into Python code.
    """
    if template not in TEMPLATES:
        raise ValueError(f"Choose a template from: {', '.join(TEMPLATES)}")
    destination = Path(path).expanduser()
    if destination.suffix != ".py":
        raise ValueError("Choose a Python filename ending in .py, for example my_model.py")
    source = files("bend2").joinpath("_examples", TEMPLATES[template]["file"]).read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(source)
    return destination
