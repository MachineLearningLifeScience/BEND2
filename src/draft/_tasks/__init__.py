"""Task readouts and scoring."""

from dataclasses import dataclass

import pandas as pd


@dataclass
class TaskResult:
    """One task's metric, protocol details and result tables."""

    metric: dict
    details: dict
    tables: dict[str, pd.DataFrame]
