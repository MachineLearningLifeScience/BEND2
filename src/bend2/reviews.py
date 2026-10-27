"""Rescore submitted predictions and record maintainer review.

Receipts describe the checks performed. Publication requires maintainer approval;
rescoring alone does not verify how the predictions were produced.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import tempfile
import zipfile
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from bend2 import __version__
from bend2.catalog import CATALOG
from bend2.results import Run, digest, write_json
from bend2.submissions import (
    PROTOCOL_VERSION,
    _TABLES,
    _https,
    _model_id,
    _read_json,
    _sha,
    _text,
    prepare_submission,
    validate_submission,
)

SCHEMA_VERSION = 1
# Rescoring compares identical predictions; reruns allow hardware roundoff.
# Tolerances use each task's units and do not affect ranking.
RESCORE_ATOL = 1e-10
REPRODUCTION_ATOL = 1e-4
_TABLE_ROWS = {
    "prior": {"predictions": 512},
    "opensplice": {"predictions": 590104, "groups": 466},
    "context": {"predictions": 170292, "groups": 128},
    "background": {"predictions": 68026, "groups": 114},
    "repair_percentile": {"predictions": 197572, "choices": 331, "groups": 110},
    "cell_selective": {"predictions": 167958, "choices": 336476, "groups": 127},
    "atlas_profile": {"predictions": 2411, "choices": 160, "requests": 32, "validation": 17},
    "tissue_identification": {
        "predictions": 5782,
        "tissues": 51,
        "validation": 6,
        "bootstrap": 10000,
    },
}


def _read_table(archive, task, name):
    # Check Parquet allocation sizes before decoding. Task scorers check schemas.
    contents = io.BytesIO(archive.read(f"{task}/{name}.parquet"))
    metadata = pq.read_metadata(contents)
    if (
        metadata.num_rows > _TABLE_ROWS[task][name]
        or metadata.num_columns > (8192 if task == "prior" else 128)
        or sum(metadata.row_group(i).total_byte_size for i in range(metadata.num_row_groups))
        > 512_000_000
    ):
        raise ValueError(
            f"{task}/{name}: Parquet dimensions or decoded size exceed benchmark limits"
        )
    contents.seek(0)
    return pd.read_parquet(contents)


def record_digest(value):
    """Bind JSON content independently of indentation or key order."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _scorer():
    root = Path(__file__).parent
    paths = [*root.rglob("*.py"), root / "assets.json"]
    return {
        "package_version": __version__,
        "libraries": {
            name: version(name) for name in ("numpy", "pandas", "pyarrow", "scipy", "scikit-learn")
        },
        "files": {p.relative_to(root).as_posix(): digest(p) for p in sorted(paths)},
    }


def _compare_metric(expected, actual, task, *, tolerance=RESCORE_ATOL):
    if set(expected) != set(actual):
        raise ValueError(f"{task}: recomputed metric fields differ from the submitted result")
    for key, value in expected.items():
        observed = actual[key]
        if key in {"value", "ci95"}:
            left = value if isinstance(value, list) else [value]
            right = observed if isinstance(observed, list) else [observed]
            if (
                len(left) != len(right)
                or any(
                    isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                    for v in left + right
                )
                or any(
                    not math.isclose(a, b, rel_tol=0, abs_tol=tolerance)
                    for a, b in zip(left, right, strict=True)
                )
            ):
                raise ValueError(f"{task}: recomputed {key} differs from the submitted result")
        elif observed != value:
            raise ValueError(f"{task}: recomputed metric {key} differs from the submission")


def rescore_submission(source, bundle, *, output=None, cache_dir=None, progress=None):
    """Rescore all submitted tasks against benchmark labels and write a receipt.

    ``bundle`` is a local ZIP containing prediction tables. Each task must pass
    before a receipt is written. Source labels come from the installed asset
    manifest; model weights and a reference-genome download are unnecessary.
    """
    from bend2._rescoring import interventions, panels

    destination = Path(output) if output is not None else None
    if destination is not None and destination.exists():
        raise FileExistsError(f"Review record already exists: {destination}; choose a new output")
    data = validate_submission(source, bundle=bundle)
    tasks = {}
    with zipfile.ZipFile(bundle) as archive:
        result_bytes = archive.read("result.json")
        for task in CATALOG:
            if task not in data["tasks"]:
                continue
            if progress:
                progress(f"Rescoring {task} against trusted benchmark data")
            tables = {name: _read_table(archive, task, name) for name in _TABLES[task]}
            engine = (
                panels
                if task in {"prior", "atlas_profile", "tissue_identification"}
                else interventions
            )
            checked = engine.rescore(
                task, tables, data["tasks"][task]["protocol"], cache_dir=cache_dir
            )
            _compare_metric(data["tasks"][task]["metric"], checked["metric"], task)
            tasks[task] = checked
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "benchmark": "BEND 2.0",
        "protocol_version": PROTOCOL_VERSION,
        "model_id": data["model"]["id"],
        "submission_sha256": record_digest(data),
        "evidence_sha256": data["evidence"]["sha256"],
        "result_sha256": hashlib.sha256(result_bytes).hexdigest(),
        "rescoring": {
            "created_at": datetime.now(UTC).isoformat(),
            "scorer": _scorer(),
            "absolute_tolerance": RESCORE_ATOL,
            "tasks": tasks,
        },
        "reproductions": {},
    }
    validate_review(receipt, data)
    if destination is not None:
        write_json(destination, receipt)
    return receipt


def validate_review(source, submission):
    """Check that a receipt matches its submission and recorded results."""
    data = validate_submission(submission)
    receipt = copy.deepcopy(source) if isinstance(source, dict) else _read_json(Path(source))
    try:
        expected = {
            "schema_version": SCHEMA_VERSION,
            "benchmark": "BEND 2.0",
            "protocol_version": PROTOCOL_VERSION,
            "model_id": data["model"]["id"],
            "submission_sha256": record_digest(data),
            "evidence_sha256": data["evidence"]["sha256"],
        }
        if any(receipt.get(key) != value for key, value in expected.items()):
            raise ValueError(
                "Review record is stale or belongs to another submission/evidence bundle"
            )
        _sha(receipt["result_sha256"], "reviewed result")
        rescoring = receipt["rescoring"]
        _text(rescoring["created_at"], "rescoring time")
        if rescoring["absolute_tolerance"] != RESCORE_ATOL:
            raise ValueError("Unexpected rescoring tolerance")
        scorer = rescoring["scorer"]
        _text(scorer["package_version"], "scorer package version")
        if not scorer["files"]:
            raise ValueError("Missing trusted scorer source fingerprints")
        for name, checksum in scorer["files"].items():
            _text(name, "scorer filename")
            _sha(checksum, name)
        if set(rescoring["tasks"]) != set(data["tasks"]):
            raise ValueError("Review must independently rescore every submitted task")
        for task, checked in rescoring["tasks"].items():
            _compare_metric(data["tasks"][task]["metric"], checked["metric"], task)
            if not isinstance(checked["checked"], list) or not checked["checked"]:
                raise ValueError(f"Missing rescoring scope for {task}")
            for scope in checked["checked"]:
                _text(scope, f"{task} rescoring scope")
        reproductions = receipt["reproductions"]
        if not isinstance(reproductions, dict) or set(reproductions) - set(data["tasks"]):
            raise ValueError("Reproduction records must refer to submitted tasks")
        for task, audit in reproductions.items():
            _text(audit["reviewer"], "reproduction reviewer")
            _text(audit["created_at"], "reproduction time")
            _text(audit["notes"], "reproduction notes")
            if audit["independent_execution"] is not True:
                raise ValueError(
                    "Reproduction requires a maintainer's independent-execution attestation"
                )
            if audit["absolute_tolerance"] != REPRODUCTION_ATOL:
                raise ValueError("Unexpected reproduction tolerance")
            if audit["model_id"] != data["model"]["id"]:
                raise ValueError("Reproduction uses a different model or interface")
            _sha(audit["run_identity"], "reproduction run identity")
            _sha(audit["result_sha256"], "reproduction result")
            _sha(audit["rescoring_sha256"], "reproduction rescoring record")
            repeated = audit["rescoring"]
            if record_digest(repeated) != audit["rescoring_sha256"]:
                raise ValueError("Reproduction rescoring record fingerprint differs")
            if (
                repeated["evidence_sha256"] != audit["evidence"]["sha256"]
                or repeated["result_sha256"] != audit["result_sha256"]
                or repeated["absolute_tolerance"] != RESCORE_ATOL
            ):
                raise ValueError("Reproduction rescoring does not match its evidence")
            _compare_metric(audit["metric"], repeated["task"]["metric"], task)
            if not repeated["task"]["checked"] or not repeated["scorer"]["files"]:
                raise ValueError("Missing reproduction rescoring scope or scorer")
            _https(audit["evidence"]["url"], "reproduction evidence URL")
            _sha(audit["evidence"]["sha256"], "reproduction evidence")
            if type(audit["evidence"]["bytes"]) is not int or audit["evidence"]["bytes"] <= 0:
                raise ValueError("Invalid reproduction evidence size")
            if (
                audit["result_sha256"] == receipt["result_sha256"]
                or audit["evidence"]["sha256"] == receipt["evidence_sha256"]
            ):
                raise ValueError("The submitted run itself is not an independent reproduction")
            _compare_metric(
                data["tasks"][task]["metric"], audit["metric"], task, tolerance=REPRODUCTION_ATOL
            )
            if task == "atlas_profile":
                _compare_metric(
                    {"ci95": data["tasks"][task]["protocol"]["replicate_values"]},
                    {"ci95": audit["replicate_values"]},
                    task,
                    tolerance=REPRODUCTION_ATOL,
                )
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"Incomplete BEND review record: {error}") from error
    return receipt


def record_reproduction(
    source,
    review,
    run,
    *,
    evidence_url,
    reviewer,
    notes,
    attest_independent=False,
    tasks=None,
    output=None,
    cache_dir=None,
    progress=None,
):
    """Record tasks rerun by a maintainer with a fresh inference cache.

    The caller attests to the independent run. ``evidence_url`` must point to
    the rerun's exported ZIP, uploaded separately.
    """
    if attest_independent is not True:
        raise ValueError("Attest that you independently ran the model with a fresh inference cache")
    _text(reviewer, "reviewer")
    _text(notes, "reproduction notes (environment, setup and differences)")
    _https(evidence_url, "reproduction evidence URL")
    data = validate_submission(source)
    receipt = validate_review(review, data)
    rerun = run if isinstance(run, Run) else Run(run)
    result = rerun.validate()
    if result.get("combined_from"):
        raise ValueError(
            "Use original independent task runs for reproduction, not a combined bundle"
        )
    if _model_id(result["identity_spec"]["model"]) != data["model"]["id"]:
        raise ValueError(
            "The rerun uses a different checkpoint, adapter or inference configuration"
        )
    if (
        digest(rerun.directory / "result.json") == receipt["result_sha256"]
        or result["created_at"] == data["evidence"]["created_at"]
    ):
        raise ValueError("The submitted run itself is not an independent reproduction")
    selected = (
        list(data["tasks"])
        if tasks is None
        else (tasks.split(",") if isinstance(tasks, str) else list(tasks))
    )
    if not selected or len(set(selected)) != len(selected) or set(selected) - set(data["tasks"]):
        raise ValueError("Choose distinct tasks present in the reviewed submission")
    for task in selected:
        if task not in result["tasks"]:
            raise ValueError(f"Independent run has no completed {task} result")
    bundle = rerun.bundle()
    with tempfile.TemporaryDirectory(prefix="bend2-reproduction-") as directory:
        candidate = prepare_submission(
            rerun,
            evidence_url,
            Path(directory) / "submission.json",
            model_url=data["model"]["url"],
            adapter_url=data["model"].get("adapter_url"),
        )
        checked = rescore_submission(candidate, bundle, cache_dir=cache_dir, progress=progress)
    for task in selected:
        repeated = {
            "created_at": checked["rescoring"]["created_at"],
            "scorer": checked["rescoring"]["scorer"],
            "absolute_tolerance": RESCORE_ATOL,
            "evidence_sha256": checked["evidence_sha256"],
            "result_sha256": checked["result_sha256"],
            "task": checked["rescoring"]["tasks"][task],
        }
        receipt["reproductions"][task] = {
            "reviewer": reviewer,
            "notes": notes,
            "independent_execution": True,
            "created_at": datetime.now(UTC).isoformat(),
            "model_id": _model_id(result["identity_spec"]["model"]),
            "run_identity": result["identity"],
            "result_sha256": digest(rerun.directory / "result.json"),
            "rescoring": repeated,
            "rescoring_sha256": record_digest(repeated),
            "evidence": {
                "url": evidence_url,
                "sha256": digest(bundle),
                "bytes": bundle.stat().st_size,
            },
            "metric": result["tasks"][task]["metric"],
            "absolute_tolerance": REPRODUCTION_ATOL,
        }
        if task == "atlas_profile":
            receipt["reproductions"][task]["replicate_values"] = result["tasks"][task]["details"][
                "replicate_values"
            ]
    validate_review(receipt, data)
    destination = (
        Path(output)
        if output is not None
        else (Path(review) if not isinstance(review, dict) else None)
    )
    if destination is not None:
        write_json(destination, receipt)
    return receipt
