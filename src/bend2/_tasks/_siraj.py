"""The frozen Siraj paired-background and common candidate definitions."""

import numpy as np

BACKGROUND_POSITION = 99
# This four-background indel locus is outside the paper's common design pool.
EXCLUDED_UNIT = "6:160560880:CATG:C:wC:Alt_6:160560897:CTGGTAAGT:C"


def paired_backgrounds(records):
    counts = records.groupby("unit_id").background_id.nunique()
    frame = records.loc[records.unit_id.isin(counts[counts.eq(2)].index)].copy()
    frame["state"] = frame.background_id.str.extract(r":([AR]):w")[0]
    references = frame.drop_duplicates(["unit_id", "state"]).pivot(
        index="unit_id", columns="state", values="sequence_ref"
    )
    for row in references.itertuples():
        differences = [i for i, (a, r) in enumerate(zip(row.A, row.R, strict=True)) if a != r]
        if differences != [BACKGROUND_POSITION]:
            raise ValueError("Siraj paired backgrounds must differ only at position 99")
    return frame, references


def repair_candidates(records):
    frame, references = paired_backgrounds(records)
    bases = references.map(lambda sequence: sequence[BACKGROUND_POSITION])
    opposite = np.where(frame.state.eq("A"), frame.unit_id.map(bases.R), frame.unit_id.map(bases.A))
    frame["is_direct"] = frame.mutation_position.eq(BACKGROUND_POSITION) & frame.mutation_alt.eq(
        opposite
    )
    frame["is_candidate"] = frame.mutation_position.ne(BACKGROUND_POSITION)
    frame["resolved"] = frame.delta_y.abs().ge(2 * frame.sigma)
    return frame.loc[frame.unit_id.ne(EXCLUDED_UNIT)].copy()
