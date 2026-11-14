"""Current interaction endpoint: independent targets, fixed cohort and versioning."""
import copy
import csv
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

import draft
from draft import datasets
from draft._tasks import background
from draft._rescoring.interventions import _compare
from draft.catalog import TASK_VERSIONS
from draft.model import composition
from draft.runner import task_protocol, environment
from draft.submissions import _PROTOCOLS, _subset

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def repeats():
    return pd.read_parquet(datasets.asset("siraj-interaction-repeats.parquet"))


def predictions(repeats):
    frame = repeats[background.KEY].copy()
    frame["prediction_A"] = repeats.interaction_repeat_1.to_numpy()
    frame["prediction_R"] = 0.
    frame["truth_A"] = 123.  # Historical fitting labels do not define this score.
    frame["truth_R"] = -123.
    frame["fold"] = 0
    return frame


def test_reference_matches_audited_manuscript(repeats):
    metric, groups = background.experimental_reference(repeats)
    assert len(groups) == 114 and groups.n_records.sum() == 68026
    assert metric["value"] == pytest.approx(.38939954806598315, abs=1e-14)
    assert metric["ci95"] == pytest.approx([.3642901198085067, .41419061413518304], abs=1e-14)


def test_repeat_score_matches_independent_scipy_and_ignores_training_labels(repeats):
    frame = predictions(repeats)
    result = background.score(frame, repeats)
    changed = frame.copy()
    changed[["truth_A", "truth_R"]] = 0.
    assert background.score(changed, repeats).metric == result.metric
    unit = repeats.unit_id.iloc[0]
    group = repeats.loc[repeats.unit_id.eq(unit)]
    scores = []
    for pair in itertools.combinations(range(5), 2):
        other = [i for i in range(5) if i not in pair]
        for selected in [pair, other]:
            truth = group[[background.REPEATS[i] for i in selected]].mean(axis=1)
            scores.append(spearmanr(truth, group.interaction_repeat_1).statistic)
    actual = result.tables["groups"].set_index("unit_id").loc[unit, "spearman"]
    assert actual == pytest.approx(np.mean(scores), abs=1e-14)
    assert result.details["bootstrap"]["replicates"] == 20000
    assert len(result.tables["groups"]) == 114
    _compare(result.tables["groups"], result.tables["groups"], ["unit_id"], "groups")
    corrupted = result.tables["predictions"].copy()
    corrupted.loc[0, "interaction_repeat_1"] += .01
    with pytest.raises(ValueError, match="disagrees with trusted rescoring"):
        _compare(corrupted, result.tables["predictions"], background.KEY,
                 "predictions", exact=background.REPEATS)
    _subset(_PROTOCOLS["background"], result.details, "background.protocol")
    old = copy.deepcopy(result.details)
    old["target"] = "A-minus-R difference in mean two-cell effect"
    with pytest.raises(ValueError, match="frozen benchmark protocol"):
        _subset(_PROTOCOLS["background"], old, "background.protocol")


def test_complete_cohort_and_constant_predictions(repeats):
    frame = predictions(repeats)
    with pytest.raises(ValueError, match="complete"):
        background.score(frame.iloc[:-1], repeats)
    frame["prediction_A"] = frame["prediction_R"] = 0.
    result = background.score(frame, repeats)
    assert result.metric["value"] == 0.
    assert result.details["n_constant_prediction_groups"] == 114
    assert result.tables["groups"].n_records.sum() == 68026


def test_background_version_invalidates_saved_run(tmp_path, monkeypatch, repeats):
    # Exercise the actual resume gate without expensive model inference or fitting.
    scored = background.score(predictions(repeats), repeats)
    source = pd.DataFrame({"sequence_ref": ["AAAA"], "sequence_alt": ["AAAC"]})
    receipt = {"paths": {}, **datasets.task_identity("background")}
    monkeypatch.setattr(datasets, "load", lambda *a, **k: {"records": source, "_provenance": receipt})
    monkeypatch.setattr(background, "run", lambda *a, **k: scored)
    options = dict(tasks="background", output=tmp_path / "run", cache_dir=tmp_path / "cache")
    monkeypatch.setitem(TASK_VERSIONS, "background", 1)
    draft.evaluate(composition(), **options)
    monkeypatch.setitem(TASK_VERSIONS, "background", 2)
    with pytest.raises(ValueError, match="scientific version 1 → 2"):
        draft.evaluate(composition(), **options)
    assert TASK_VERSIONS["background"] == 2
    assert all(v == 1 for k, v in TASK_VERSIONS.items() if k != "background")
    assert "siraj-interaction-repeats.parquet" in task_protocol("background", environment())["data"]["assets"]
    assert "siraj-interaction-repeats.parquet" not in task_protocol("context", environment())["data"]["assets"]


def test_all_current_reference_records_match_audited_source():
    data = json.loads((ROOT / "data/benchmark.paper.json").read_text())
    with (ROOT / "provenance/siraj-repeat-interactions/table-ready.csv").open() as f:
        source = {row["model"]: row for row in csv.DictReader(f)}
    checked = []
    for row in data["measurements"] + data["references"]:
        if row["taskId"] != "background" or row.get("value") is None:
            continue
        expected = source[row["modelId"]]
        assert row["sourceValue"] == float(expected["value"])
        assert row["displayValue"] == f'{float(expected["value"]):.3f}'
        assert row["uncertainty"]["low"] == float(expected["ci_low"])
        assert row["uncertainty"]["high"] == float(expected["ci_high"])
        checked.append(row["modelId"])
    assert len(checked) == 16 and set(checked) == set(source)
    assert next(t for t in data["tasks"] if t["id"] == "background")["reference"]["value"] == .389


def test_strong_membership_uses_only_discovery_repeats(repeats):
    import runpy
    select = runpy.run_path(str(ROOT / "provenance/siraj-repeat-interactions/components/select_strong.py"))["select"]
    selected = select(repeats)
    assert selected.strong.sum() == 6136
    assert selected.all_edits.sum() == 53101
    changed = repeats.copy()
    changed[["interaction_repeat_4", "interaction_repeat_5"]] = 1000.
    pd.testing.assert_frame_equal(select(changed), selected)
