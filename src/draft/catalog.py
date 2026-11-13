"""Task names, interfaces and input sizes."""

CATALOG = {
    "prior": ("Sequence prior", "probabilities", "512 × 1,200 bp; included", "lower"),
    "opensplice": ("Splice effects", "embed", "590,104 interventions; 425 MB download", "higher"),
    "tissue_identification": (
        "Tissue identification",
        "embed",
        "131,072 bp windows; 835 MB genome",
        "higher",
    ),
    "context": (
        "Cell context",
        "embed",
        "170,292 paired substitutions; 93 MB shared download",
        "higher",
    ),
    "background": ("Genetic background", "embed", "68,026 contrasts; shared Siraj data", "higher"),
    "repair_percentile": (
        "Compensatory repair",
        "embed",
        "331 requests; shared Siraj data",
        "lower",
    ),
    "cell_selective": (
        "Cell-selective editing",
        "embed",
        "280 backgrounds; shared Siraj data",
        "higher",
    ),
    "atlas_profile": ("Enhancer profiles", "embed", "7,657 × 145 bp; included", "higher"),
}

# Bump affected tasks when their inputs, readout or scoring change.
TASK_VERSIONS = {
    "prior": 1,
    "opensplice": 1,
    "tissue_identification": 1,
    "context": 1,
    "background": 1,
    "repair_percentile": 1,
    "cell_selective": 1,
    "atlas_profile": 1,
}


def tasks():
    """Return task names, required interfaces and input sizes."""
    return [
        {"id": key, "name": row[0], "requires": row[1], "inputs": row[2], "direction": row[3]}
        for key, row in CATALOG.items()
    ]
