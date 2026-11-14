"""Recreate discovery-only strong membership from the bundled repeat table."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd


def select(frame):
    columns = [f"interaction_repeat_{i}" for i in range(1, 6)]
    centered = frame[columns] - frame.groupby("unit_id")[columns].transform("mean")
    discovery = centered.iloc[:, :3].to_numpy()
    strong = (np.abs(discovery.mean(1)) >= .5) & (
        (discovery > 0).all(1) | (discovery < 0).all(1)
    )
    counts = frame.loc[strong].groupby("unit_id").size()
    eligible = counts[counts >= 20].index
    result = frame[["unit_id", "mutation_position", "mutation_ref", "mutation_alt"]].copy()
    result["all_edits"] = result.unit_id.isin(eligible)
    result["strong"] = strong & result.all_edits
    assert len(eligible) == 89 and result.all_edits.sum() == 53101
    assert result.strong.sum() == 6136
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repeat_table", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    select(pd.read_parquet(args.repeat_table)).to_parquet(args.output, index=False)
