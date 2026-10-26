"""A working CPU example. Replace embed with your frozen encoder."""

import numpy as np
from bend2 import Model


def embed(sequences: list[str]) -> np.ndarray:
    # Load weights once, disable gradients and preserve input order.
    # Return CPU NumPy arrays with one fixed-width vector per complete sequence.
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
