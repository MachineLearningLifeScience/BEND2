"""The eight BEND 2.0 endpoints, with no inference or file handling."""

from dataclasses import dataclass, field
from importlib import import_module

import pandas as pd


@dataclass
class TaskResult:
    """One task's headline metric, protocol details and inspectable score tables."""

    task_id: str
    metric: dict
    details: dict = field(default_factory=dict)
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)


TASK_IDS = (
    "prior",
    "opensplice",
    "context",
    "tissue_identification",
    "background",
    "repair_percentile",
    "cell_selective",
    "atlas_profile",
)


def run(task_id, data, embeddings=None, probabilities=None, *, shared=None):
    """Score prepared inputs using the task's fixed BEND 2.0 protocol."""
    if task_id not in TASK_IDS:
        raise ValueError(f"Unknown or unavailable task: {task_id}")
    module = import_module(f"bend2._tasks.{task_id}")
    return module.run(data, embeddings, probabilities, shared=shared)
