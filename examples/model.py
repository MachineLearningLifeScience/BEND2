"""A complete adapter. Run: bend2 run examples/model.py --tasks atlas_profile"""

import numpy as np
from bend2 import Model


def embed(sequences: list[str]) -> np.ndarray:
    return np.array(
        [[sequence.count(base) / len(sequence) for base in "ACGT"] for sequence in sequences],
        dtype=np.float32,
    )


model = Model(
    "My composition example",
    embed=embed,
    revision="composition-example-v1",
    training_data="none; deterministic sequence statistics",
    representation="four A/C/G/T fractions",
    pooling="whole input sequence",
)
