"""Checks for evaluation, submission and interrupted runs."""

import json
import urllib.request
import zipfile

import numpy as np
import pytest

import bend2
from bend2.model import composition
from bend2.results import digest
from bend2.reviews import rescore_submission, validate_review
from bend2.submissions import build_leaderboard, validate_submission


def test_offline_atlas_results_and_submission(tmp_path, monkeypatch):
    def offline(*args, **kwargs):
        raise AssertionError("The starter benchmark must not need network access")

    monkeypatch.setattr(urllib.request, "urlopen", offline)
    result = bend2.evaluate(composition(), output=tmp_path / "run", cache_dir=tmp_path / "cache")
    assert result.scores["atlas_profile"] == pytest.approx(-0.7378073152527498, abs=1e-12)
    assert len(bend2.tasks()) == 8
    assert not result.submission.exists()
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
    checksum = digest(result.bundle())
    assert digest(result.bundle()) == checksum
    contribution = result.prepare_submission(
        "https://example.org/submission.zip",
        model_url="https://example.org/model",
        adapter_url="https://example.org/adapter.py",
    )
    record = validate_submission(contribution, bundle=result.directory / "submission.zip")
    assert record["coverage"]["atlas_profile"]["status"] == "evaluated"
    assert len(record["coverage"]) == 8
    assert result.tables["atlas_profile"] == ["choices", "predictions", "requests", "validation"]
    assert len(result.table("atlas_profile", columns=["id"])) == 2411
    receipt = rescore_submission(contribution, result.directory / "submission.zip")
    assert (
        receipt["rescoring"]["tasks"]["atlas_profile"]["metric"]
        == record["tasks"]["atlas_profile"]["metric"]
    )
    altered = json.loads(contribution.read_text())
    altered["model"]["family"] = "Changed after review"
    with pytest.raises(ValueError, match="stale"):
        validate_review(receipt, altered)
    submissions = tmp_path / "submissions"
    submissions.mkdir()
    (submissions / contribution.name).write_text(contribution.read_text())
    reference = {
        "models": [],
        "measurements": [],
        "tasks": [{"id": row["id"], "precision": 3} for row in bend2.tasks()],
    }
    with pytest.raises(ValueError, match="Missing trusted rescoring"):
        build_leaderboard(reference, submissions)
    preview = build_leaderboard(reference, submissions, preview=True)
    assert preview["measurements"][-1]["verification"]["status"] == "pending_review"
    reviews = tmp_path / "reviews"
    reviews.mkdir()
    (reviews / contribution.name).write_text(json.dumps(receipt))
    accepted = build_leaderboard(reference, submissions)
    assert accepted["measurements"][-1]["verification"]["status"] == "contributor_evaluated"
    changed = result.data
    changed["tasks"]["atlas_profile"]["metric"]["value"] = 100.0
    (result.directory / "result.json").write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="differs from recorded evidence"):
        result.bundle()


def test_interrupted_inference_resumes_completed_batches(tmp_path, monkeypatch):
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
    options["batch_size"] = 128
    model.name = "Corrected display name"
    model.training_data = "none"
    result = bend2.evaluate(model, **options)
    assert encoder.successful == 7657
    assert result.scores["atlas_profile"] == pytest.approx(-0.7378073152527498, abs=1e-12)
    assert not result.submission.exists()
    calls = encoder.calls
    monkeypatch.setitem(bend2.catalog.TASK_VERSIONS, "prior", 2)
    bend2.evaluate(model, **options)
    assert encoder.calls == calls
    monkeypatch.setitem(bend2.catalog.TASK_VERSIONS, "atlas_profile", 2)
    with pytest.raises(ValueError, match="atlas_profile: scientific version 1 → 2"):
        bend2.evaluate(model, **options)


def test_prior_exposes_only_hidden_targets(tmp_path):
    calls, successful = 0, 0

    def probabilities(sequences, positions):
        nonlocal calls, successful
        calls += 1
        if calls == 2:
            raise RuntimeError("Interrupted native prior")
        assert all(
            len(seq) == 1200 and pos == 600 and seq[pos] == "N"
            for seq, pos in zip(sequences, positions, strict=True)
        )
        successful += len(sequences)
        return np.full((len(sequences), 4), 0.25)

    model = bend2.Model(
        "Uniform",
        probabilities=probabilities,
        revision="v1",
        training_data="none",
        probability_interface="uniform probabilities",
    )
    options = dict(tasks="prior", output=tmp_path / "run", cache_dir=tmp_path / "cache")
    with pytest.raises(RuntimeError, match="Interrupted native prior"):
        bend2.evaluate(model, **options)
    result = bend2.evaluate(model, batch_size=7, **options)
    assert successful == 512
    assert result.scores == {"prior": 2.0}
    assert result.data["tasks"]["prior"]["metric"]["ci95"] == [2.0, 2.0]
