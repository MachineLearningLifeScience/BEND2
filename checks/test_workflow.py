"""Three checks for the public workflow; scientific engines stay uncluttered."""

import json
import urllib.request
import zipfile

import numpy as np
import pytest

import bend2
from bend2.model import composition


def test_offline_atlas_results_and_submission(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        raise AssertionError("The starter benchmark must not need network access")

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    result = bend2.evaluate(composition(), output=tmp_path / "run", cache_dir=tmp_path / "cache")
    assert result.scores["atlas_profile"] == pytest.approx(-0.7378073152527498, abs=1e-12)
    assert len(bend2.tasks()) == 8
    with zipfile.ZipFile(result.bundle()) as archive:
        assert {
            "result.json",
            "submission.json",
            "atlas_profile/choices.parquet",
        } <= set(archive.namelist())
        assert not any(name.endswith(".html") for name in archive.namelist())
    assert not list(result.directory.rglob("*.html"))
    submission = json.loads(result.submission.read_text())
    assert submission["ready_for_review"] and len(submission["coverage"]) == 8
    changed = result.data
    changed["tasks"]["atlas_profile"]["metric"]["value"] = 100.0
    (result.directory / "result.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="differs from recorded evidence"):
        result.bundle()


def test_interrupted_inference_resumes_completed_batches(tmp_path):
    class Encoder:
        calls = 0
        successful = 0

        def __call__(self, sequences):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("Simulated interrupted model job")
            self.successful += len(sequences)
            return composition().embed(sequences)

    encoder = Encoder()
    model = bend2.Model("Resume example", embed=encoder, revision="v1")
    options = dict(output=tmp_path / "run", cache_dir=tmp_path / "cache", batch_size=1000)
    with pytest.raises(RuntimeError, match="interrupted"):
        bend2.evaluate(model, **options)
    result = bend2.evaluate(model, **options)
    assert encoder.successful == 7657
    assert result.scores["atlas_profile"] == pytest.approx(-0.7378073152527498, abs=1e-12)
    assert not json.loads(result.submission.read_text())["ready_for_review"]
    calls = encoder.calls
    bend2.evaluate(model, **options)
    assert encoder.calls == calls


def test_prior_exposes_only_hidden_targets(tmp_path):
    def probabilities(sequences, positions):
        assert all(
            len(seq) == 1200 and pos == 600 and seq[pos] == "N"
            for seq, pos in zip(sequences, positions, strict=True)
        )
        return np.full((len(sequences), 4), 0.25)

    model = bend2.Model(
        "Uniform",
        probabilities=probabilities,
        revision="v1",
        training_data="none",
        probability_interface="uniform probabilities",
    )
    result = bend2.evaluate(
        model, tasks="prior", output=tmp_path / "run", cache_dir=tmp_path / "cache"
    )
    assert result.scores == {"prior": 2.0}
    assert result.data["tasks"]["prior"]["metric"]["ci95"] == [2.0, 2.0]
