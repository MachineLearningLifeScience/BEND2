"""Editable model adapters available from every installed BEND 2.0 package."""

from __future__ import annotations

import shlex
from pathlib import Path
from textwrap import dedent


TEMPLATES = {
    "custom": {
        "description": "Your encoder; starts with a working CPU composition example",
        "tasks": "atlas_profile",
        "extra": None,
        "source": """
            import numpy as np
            from bend2 import Model


            def embed(sequences: list[str]) -> np.ndarray:
                # Replace this working example with your frozen encoder.
                # Load weights once, disable gradients, and preserve input order.
                # Return CPU NumPy arrays with one fixed-width vector per sequence.
                return np.array(
                    [[seq.count(base) / len(seq) for base in "ACGT"] for seq in sequences],
                    dtype=np.float32,
                )


            model = Model(
                "My composition example",
                embed=embed,
                revision="composition-example-v1",  # Replace with your checkpoint identity.
                training_data="none; deterministic sequence statistics",
                representation="four A/C/G/T fractions",
                pooling="whole input sequence",
                # source="...",  # Your public checkpoint or model implementation URL.
                # Record options that affect inference, such as precision and device:
                # inference_config={"precision": "float32", "device": "cuda:0"},
            )
        """,
    },
    "huggingface": {
        "description": "A pinned HyenaDNA encoder using the generic Hugging Face adapter",
        "tasks": "atlas_profile",
        "extra": "huggingface",
        "source": """
            from bend2.huggingface import model as huggingface_model

            # Replace checkpoint, immutable revision and declarations for your model.
            # This small HyenaDNA checkpoint fits Atlas, not GTEx's 131,072-base windows.
            # Its custom Python is pinned to the same checkpoint revision.
            model = huggingface_model(
                "LongSafari/hyenadna-tiny-1k-seqlen-hf",
                revision="e8c1effa8673814e257e627d2e1eda9ea5a373f6",
                training_data=(
                    "Human reference genome hg38; next-nucleotide pretraining, according to "
                    "the pinned model card. No additional fine-tuning."
                ),
                device="cpu",  # Use "cuda:0" for a supported GPU.
                trust_remote_code=True,
            )
        """,
    },
    "dnabert2": {
        "description": "Pinned DNABERT-2 117M embeddings with the model-specific adapter",
        "tasks": "atlas_profile",
        "extra": "reference",
        "source": """
            from bend2.reference_models import dnabert2

            # Weights load once on the first batch. The checkpoint, tokenizer and
            # pooling are pinned by the factory and recorded in the results.
            model = dnabert2(device="cpu", precision="float32")
            # For a supported GPU, choose device="cuda:0", precision="bfloat16".
            # Precision changes the inference identity. The paper used GPU bfloat16;
            # this CPU float32 example need not produce bit-identical scores.
        """,
    },
    "ntv3-prior": {
        "description": "Pinned NTv3 100M-post with the paper's two-query prior readout",
        "tasks": "prior",
        "extra": "reference",
        "source": """
            from bend2.reference_models import ntv3_prior

            # Accept the checkpoint terms on Hugging Face and authenticate if required.
            # This reproduces the paper's two fixed 12%-mask queries per window.
            model = ntv3_prior(size="100m", readout="paper", device="cpu", precision="float32")
            # Use size="650m" for the larger checkpoint; a GPU is recommended.
            # For a supported GPU, choose device="cuda:0", precision="bfloat16".
            # readout="native" selects the single-target-mask alternative, recorded
            # separately because it does not reproduce the paper's input conditions.
        """,
    },
}


def write_template(path, template="custom") -> Path:
    """Create one editable adapter without downloading weights or replacing a file.

    ``TEMPLATES`` lists the installed choices, their descriptions, optional
    runtime extras and a suitable first task. Existing files are never replaced.
    """
    if template not in TEMPLATES:
        raise ValueError(f"Choose a template from: {', '.join(TEMPLATES)}")
    destination = Path(path).expanduser()
    if destination.suffix != ".py":
        raise ValueError("Choose a Python filename ending in .py, for example my_model.py")
    selected = TEMPLATES[template]
    command = f"bend2 run {shlex.quote(str(destination))} --tasks {selected['tasks']}"
    # repr creates a valid Python module docstring even when a filename contains
    # quotes, braces or newlines. Do not interpolate paths into Python source.
    source = repr(f"Run with: {command}") + "\n\n"
    source += dedent(selected["source"]).strip() + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(source)
    return destination
