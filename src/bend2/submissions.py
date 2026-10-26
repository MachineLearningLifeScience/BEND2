"""A small, reviewable contribution file and an additive leaderboard build.

The JSON in ``submissions/`` is the source of truth for community rows. Merging
its pull request is the acceptance decision; no field in the file grants that
status. Evidence is read as data, never extracted or executed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from bend2.catalog import CATALOG
from bend2.datasets import COHORTS, FINGERPRINT_VERSION, MANIFEST, _TASK_ASSETS
from bend2.results import Run, digest, slug, write_json

SCHEMA_VERSION = 2
PROTOCOL_VERSION = "bend2-2026-v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
# The contract is deliberately about the frozen science, not package versions,
# hardware, chosen hyperparameters or model-dependent undefined group counts.
_RIDGE = {
    "readout": "ridge",
    "alpha": 10.0,
    "solver": "lsqr",
    "tol": 0.0001,
    "folds": 5,
    "splitter": "GroupKFold(shuffle=False)",
    "normalization": "none",
    "embedding_dtype": "float32",
    "features": [
        "alternate-minus-reference embedding",
        "length difference",
        "one-hot context",
        "one-hot intervention type",
    ],
}
_PROTOCOLS = {
    "prior": {
        "n_windows": 512,
        "sequence_length": 1200,
        "target_position": 600,
        "target_replacement": "N",
        "base_order": "ACGT",
        "probability_clipping": False,
        "bootstrap": {"unit": "1 Mb genomic block", "replicates": 4000, "seed": 20260910},
    },
    "opensplice": {
        **_RIDGE,
        "group": "gene_id",
        "n_records": 590104,
        "n_groups": 466,
        "bootstrap": {"unit": "gene", "replicates": 2000, "seed": 20260822},
    },
    "context": {
        **_RIDGE,
        "group": "unit_id",
        "n_records": 170292,
        "n_groups": 128,
        "target": "HepG2 minus K562",
        "prediction_dtype": "float32",
        "bootstrap": {"unit": "regulatory element", "replicates": 10000, "seed": 20260825},
    },
    "background": {
        **_RIDGE,
        "group": "unit_id",
        "n_pairs": 68026,
        "n_groups": 114,
        "target": "A-minus-R difference in mean two-cell effect",
        "bootstrap": {"unit": "regulatory element", "replicates": 10000, "seed": 20260826},
    },
    "repair_percentile": {
        **_RIDGE,
        "group": "unit_id",
        "n_requests": 331,
        "n_groups": 110,
        "request_filter": "absolute direct-swap effect >= 2 standard errors",
        "selector": "minimum absolute predicted residual to the direct-swap target",
        "candidate_pool": "frozen common pool; excludes all edits at background position 99",
        "tie_break": "ascending record_id",
        "percentile_rank": "average ties, (rank-1)/(n-1)",
        "aggregation": "mean requests within element, then mean elements",
        "bootstrap": {"unit": "regulatory element", "replicates": 10000, "seed": 20260827},
    },
    "cell_selective": {
        **_RIDGE,
        "group": "unit_id",
        "n_candidates": 167958,
        "n_groups": 127,
        "n_backgrounds": 280,
        "lambda": 1.0,
        "selector": "predicted target effect minus absolute other-cell effect",
        "readout_combination": "per-cell prediction mean plus/minus half the direct contrast",
        "no_edit": "zero utility; chosen when no candidate exceeds 1e-10",
        "ties": "uniform over candidates within absolute 1e-10 of the maximum",
        "decision_outcomes": "pooled direct-m0 raw-count effects",
        "aggregation": "backgrounds within target cell, target cells within locus, then loci",
        "bootstrap": {"unit": "complete locus", "replicates": 50000, "seed": 20260921},
    },
    "atlas_profile": {
        "cells": [
            "NT2_D1",
            "GM12878",
            "786_O",
            "SKNSH",
            "WERI_Rb1",
            "SJCRH30",
            "HepG2",
            "K562",
            "MCF7",
            "HeLaS3",
            "HEK293",
            "HMC3",
        ],
        "n_source_train": 4223,
        "n_source_validation": 1023,
        "n_source_refit": 5246,
        "n_candidates": 2411,
        "n_requests": 16,
        "n_selected_per_request": 10,
        "penalty_criterion": "unweighted 12-cell validation MSE",
        "feature_scaling": "source z-score, remove std<=1e-7, divide by sqrt retained dimension",
        "refit": "source train+validation only; recompute source scaling",
        "selector": "minimum ON activity minus max(0, maximum OFF activity)",
        "tie_break": "ascending candidate ID",
        "comparison": "intent-matched author design cohort",
        "aggregation": "mean requests per replicate, then mean of two replicates",
        "candidate_labels_used_for_fitting": False,
    },
    "tissue_identification": {
        "n_training_genes": 12146,
        "n_validation_genes": 1350,
        "n_test_genes": 5782,
        "n_tissues": 51,
        "input": "131072 bp reference-forward TSS-centered sequence",
        "target": "log1p TPM",
        "penalty_grid": [10000.0, 1000.0, 100.0, 10.0, 1.0, 0.1],
        "penalty_criterion": "validation standardized MSE",
        "scaling": "feature and target StandardScaler fitted on training genes only",
        "refit": "none; retain training-only membership",
        "retrieval": "Spearman between predicted and measured profiles across common test genes",
        "ties": "fractional credit within absolute 1e-12",
        "bootstrap": {"unit": "whole gene", "replicates": 10000, "seed": 20260917},
    },
}
_METRICS = {
    "prior": ("recovery_bits", "bits/base", 0, None),
    "opensplice": ("macro_spearman", "Spearman ρ", -1, 1),
    "context": ("macro_spearman", "Spearman ρ", -1, 1),
    "background": ("macro_spearman", "Spearman ρ", -1, 1),
    "repair_percentile": ("measured_rank_percentile", "%", 0, 100),
    "cell_selective": ("log2_reporter_utility", "log₂ reporter", None, None),
    "atlas_profile": ("held_u_minus_intended_random", "log₂ activity", None, None),
    "tissue_identification": ("retrieval_top1", "%", 0, 100),
}
_TABLES = {
    "prior": ["predictions"],
    "opensplice": ["predictions", "groups"],
    "context": ["predictions", "groups"],
    "background": ["predictions", "groups"],
    "repair_percentile": ["predictions", "choices", "groups"],
    "cell_selective": ["predictions", "choices", "groups"],
    "atlas_profile": ["predictions", "choices", "requests", "validation"],
    "tissue_identification": ["predictions", "tissues", "validation", "bootstrap"],
}


def _subset(expected, actual, label):
    if not isinstance(actual, dict):
        raise ValueError(f"Missing {label}")
    for key, value in expected.items():
        if isinstance(value, dict):
            _subset(value, actual.get(key), f"{label}.{key}")
        elif actual.get(key) != value:
            raise ValueError(f"{label}.{key} differs from the frozen benchmark protocol")


def _text(value, label, *, optional=False):
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise ValueError(f"Provide {label}")
    if len(value) > 20000:
        raise ValueError(f"{label} is too long")
    return value


def _https(value, label, *, optional=False):
    if optional and not value:
        return ""
    _text(value, label)
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{label} must be a public HTTPS URL without credentials")
    return value


def _sha(value, label):
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise ValueError(f"Invalid SHA256 for {label}")


def _number(value, label, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(f"{label} is outside the metric range")


def _model_id(identity):
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return f"community-{slug(identity['name'])[:60]}-{fingerprint[:12]}"


def _data_summary(data):
    return {
        "cohorts": {
            name: {
                key: row[key]
                for key in ("semantic_sha256", "fingerprint_version", "rows", "groups")
            }
            for name, row in data.get("cohorts", {}).items()
        },
        "assets": {
            name: {key: row[key] for key in ("sha256", "md5", "bytes") if key in row}
            for name, row in data.get("assets", {}).items()
        },
    }


def _task_summary(row):
    return {
        "metric": row["metric"],
        "protocol": row["details"],
        "data": _data_summary(row["data"]),
        "files": row["files"],
    }


def prepare_submission(
    run,
    evidence_url,
    output=None,
    *,
    model_url=None,
    adapter_url=None,
    family="",
    parameter_label="",
):
    """Package a completed run into one file to add in a leaderboard pull request.

    Upload the ZIP from ``run.bundle()`` first, then supply its stable download
    URL. This function does not upload files, create a PR, or publish a result.
    """
    run = run if isinstance(run, Run) else Run(run)
    result = run.validate()
    if result.get("status") != "complete" or not result.get("tasks"):
        raise ValueError("Complete at least one task before preparing a leaderboard submission")
    archive = run.directory / "submission.zip"
    if not archive.is_file():
        raise ValueError(
            "Export the run with bend2 export (or run.bundle()), upload that ZIP, then submit"
        )
    identity = result["identity_spec"]["model"]
    model_id = _model_id(identity)
    submission = {
        "schema_version": SCHEMA_VERSION,
        "benchmark": "BEND 2.0",
        "protocol_version": PROTOCOL_VERSION,
        "model": {
            "id": model_id,
            "name": result["model"]["name"],
            "url": model_url or result["model"].get("source", ""),
            "adapter_url": adapter_url or "",
            "family": family,
            "parameter_label": parameter_label,
            "identity": identity,
        },
        "evidence": {
            "url": evidence_url,
            "sha256": digest(archive),
            "bytes": archive.stat().st_size,
            "run_identity": result["identity"],
            "package_version": result["version"],
            "created_at": result["created_at"],
            "adapter_included": bool(result.get("adapter_file")),
        },
        "tasks": {task: _task_summary(row) for task, row in result["tasks"].items()},
        "coverage": {
            task: {"status": "evaluated"}
            if task in result["tasks"]
            else {
                "status": "not_evaluated",
                "reason": result.get("skipped", {}).get(task, "Not requested"),
            }
            for task in CATALOG
        },
    }
    validate_submission(submission, bundle=archive)
    destination = Path(output) if output else run.directory / f"{model_id}.json"
    if destination.is_dir():
        destination = destination / f"{model_id}.json"
    write_json(destination, submission)
    return destination


def validate_submission(source, *, bundle=None):
    """Check a contribution; optionally verify every evidence file in its ZIP.

    This establishes consistency with the recorded protocol and assets. It does
    not establish training-data provenance or prove that the declared model ran.
    Neither this function nor the website builder executes contributed code.
    """
    data = copy.deepcopy(source) if isinstance(source, dict) else _read_json(Path(source))
    try:
        _validate(data)
        if bundle is not None:
            _verify_bundle(data, Path(bundle))
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"Incomplete BEND submission: {error}") from error
    return data


def _read_json(path):
    if path.stat().st_size > 2_000_000:
        raise ValueError("A leaderboard contribution should be a compact JSON file under 2 MB")
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda x: (_ for _ in ()).throw(ValueError(f"Non-finite JSON value: {x}")),
    )


def _validate(data):
    _subset(
        {
            "schema_version": SCHEMA_VERSION,
            "benchmark": "BEND 2.0",
            "protocol_version": PROTOCOL_VERSION,
        },
        data,
        "submission",
    )
    if any(key in data for key in ("accepted", "approved", "review_status")):
        raise ValueError("Acceptance comes from maintainer review and merge, not a JSON flag")
    model = data["model"]
    identity = model["identity"]
    if model["id"] != _model_id(identity) or model["name"] != identity["name"]:
        raise ValueError("Model ID and name must match the evaluated model identity")
    for field in ("name", "revision", "training_data"):
        _text(identity[field], f"model {field}")
    _https(model["url"], "model URL")
    _https(model.get("adapter_url", ""), "adapter URL", optional=True)
    _text(model.get("family", ""), "model family", optional=True)
    _text(model.get("parameter_label", ""), "parameter label", optional=True)
    evidence = data["evidence"]
    _https(evidence["url"], "evidence download URL")
    _sha(evidence["sha256"], "evidence bundle")
    _sha(evidence["run_identity"], "run identity")
    if type(evidence["bytes"]) is not int or evidence["bytes"] <= 0:
        raise ValueError("Evidence bundle size must be positive")
    if not evidence.get("adapter_included") and not model.get("adapter_url"):
        raise ValueError("Provide an adapter URL for a run without an included model.py")
    tasks, coverage = data["tasks"], data["coverage"]
    if not isinstance(tasks, dict) or not tasks or set(tasks) - CATALOG.keys():
        raise ValueError("Provide at least one supported, fully evaluated task")
    if set(coverage) != set(CATALOG):
        raise ValueError("Coverage must account for all eight tasks")
    for task in CATALOG:
        if task in tasks:
            if coverage[task] != {"status": "evaluated"}:
                raise ValueError(f"Coverage does not match the result for {task}")
        elif coverage[task].get("status") != "not_evaluated":
            raise ValueError(f"Unrun task {task} must remain not_evaluated")
        else:
            _text(coverage[task].get("reason"), f"reason for missing {task}")
    capabilities = identity.get("capabilities", [])
    if not isinstance(capabilities, list) or set(capabilities) - {"embed", "probabilities"}:
        raise ValueError("Declare the model's supported capabilities")
    for task in tasks:
        if CATALOG[task][1] not in capabilities:
            raise ValueError(f"Model identity does not declare the capability needed for {task}")
    for capability in capabilities:
        _sha(identity["adapter"][capability]["source_sha256"], f"{capability} adapter")
    if identity["revision"].strip().lower() in {"main", "master", "latest", "head", "default"}:
        raise ValueError("Use an immutable checkpoint revision or weight hash, not a moving branch")
    if any(task != "prior" for task in tasks):
        for field in ("representation", "pooling"):
            _text(identity[field], f"model {field}")
    if "prior" in tasks:
        _text(identity["probability_interface"], "probability interface")
    for task, row in tasks.items():
        metric = row["metric"]
        name, unit, low, high = _METRICS[task]
        _subset({"name": name, "unit": unit, "direction": CATALOG[task][3]}, metric, task)
        _number(metric["value"], task, low, high)
        if "ci95" in metric:
            interval = metric["ci95"]
            if not isinstance(interval, list) or len(interval) != 2:
                raise ValueError(f"Invalid interval for {task}")
            for endpoint in interval:
                _number(endpoint, f"{task} interval", low, high)
            if interval[0] > interval[1] or task == "atlas_profile":
                raise ValueError(f"Invalid interval for {task}")
        elif task != "atlas_profile":
            raise ValueError(f"Missing frozen bootstrap interval for {task}")
        _subset(_PROTOCOLS[task], row["protocol"], f"{task}.protocol")
        _validate_data(task, row["data"])
        required = [f"{task}/{table}.parquet" for table in _TABLES[task]]
        required.append(f"{task}/protocol.json")
        if any(path not in row["files"] for path in required):
            raise ValueError(f"Missing prediction/protocol evidence for {task}")
        for path, checksum in row["files"].items():
            parts = PurePosixPath(path).parts
            if not parts or parts[0] != task or ".." in parts or "\\" in path:
                raise ValueError(f"Unsafe evidence path: {path}")
            _sha(checksum, path)


def _validate_data(task, data):
    if task in _TASK_ASSETS:
        assets = list(_TASK_ASSETS[task].values())
        cohorts = []
    elif task == "opensplice":
        assets, cohorts = ["opensplice.tsv.gz"], ["opensplice"]
    else:
        assets = ["siraj.zip", "siraj-numeric-reference.npz"]
        cohorts = ["context"] if task == "context" else ["siraj"]
        if task == "cell_selective":
            assets.append("siraj_selective.parquet")
            cohorts.append("context")
    for name in assets:
        expected = {
            key: value
            for key, value in MANIFEST["files"][name].items()
            if key in {"sha256", "md5", "bytes"}
        }
        _subset(expected, data["assets"].get(name), f"{task}.assets.{name}")
    for name in cohorts:
        spec = COHORTS[name]
        expected = {
            "semantic_sha256": spec["sha256"],
            "rows": spec["rows"],
            "groups": spec["groups"],
            "fingerprint_version": FINGERPRINT_VERSION,
        }
        _subset(expected, data["cohorts"].get(name), f"{task}.cohorts.{name}")


def _verify_bundle(data, bundle):
    evidence = data["evidence"]
    if bundle.stat().st_size != evidence["bytes"] or digest(bundle) != evidence["sha256"]:
        raise ValueError(
            "The downloaded evidence bundle does not match its declared size and SHA256"
        )
    with zipfile.ZipFile(bundle) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate paths in evidence bundle")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise ValueError(f"Unsafe path in evidence bundle: {name}")
        if archive.getinfo("result.json").file_size > 2_000_000:
            raise ValueError("Oversized result.json in evidence bundle")
        result = json.loads(archive.read("result.json"))
        identity = hashlib.sha256(
            json.dumps(result["identity_spec"], sort_keys=True).encode()
        ).hexdigest()
        if identity != result["identity"] or identity != evidence["run_identity"]:
            raise ValueError("Evidence run identity does not match the contribution")
        if result["identity_spec"]["model"] != data["model"]["identity"]:
            raise ValueError("Evidence model identity differs from the contribution")
        if result.get("status") != "complete" or result["benchmark"] != "BEND 2.0":
            raise ValueError("Evidence does not describe a complete BEND 2.0 run")
        if {task: _task_summary(row) for task, row in result["tasks"].items()} != data["tasks"]:
            raise ValueError("Submitted scores or protocols differ from the evidence")
        files = {}
        for task, row in result["tasks"].items():
            files.update(row["files"])
            if archive.getinfo(f"{task}/protocol.json").file_size > 2_000_000:
                raise ValueError(f"Oversized protocol evidence for {task}")
            protocol = json.loads(archive.read(f"{task}/protocol.json"))
            if protocol != {key: row[key] for key in ("metric", "details", "data")}:
                raise ValueError(f"Recorded protocol differs from result.json for {task}")
        if result.get("adapter_file"):
            files["model.py"] = result["adapter_file"]
        if bool(result.get("adapter_file")) != evidence["adapter_included"]:
            raise ValueError("Adapter inclusion differs from the contribution")
        for name, expected in files.items():
            with archive.open(name) as handle:
                actual = hashlib.file_digest(handle, "sha256").hexdigest()
            if actual != expected:
                raise ValueError(f"Evidence file hash mismatch: {name}")


def build_leaderboard(base, submissions, output=None):
    """Add reviewed community rows without modifying paper scores or anchors.

    Build from the publication branch's ``submissions/`` after review and merge.
    A PR checkout can use the same function for a local preview. The base should
    be the frozen ``website/data/benchmark.paper.json``, never a previously built file.
    """
    result = copy.deepcopy(base) if isinstance(base, dict) else _read_json(Path(base))
    existing = {model["id"] for model in result["models"]}
    if any(model.get("origin") == "community" for model in result["models"]):
        raise ValueError("Build from the frozen reference JSON, not a previous community build")
    directory = Path(submissions)
    paths = sorted(directory.glob("*.json"))
    for path in paths:
        data = validate_submission(path)
        model, evidence = data["model"], data["evidence"]
        model_id = model["id"]
        if path.name != f"{model_id}.json":
            raise ValueError(f"Name the contribution file {model_id}.json")
        if model_id in existing:
            raise ValueError(f"Duplicate or reserved leaderboard model ID: {model_id}")
        existing.add(model_id)
        identity = model["identity"]
        source_id = f"submission-{model_id}"
        capabilities = set(identity.get("capabilities", []))
        interface = "fitted" if "embed" in capabilities else "native"
        result["models"].append(
            {
                "id": model_id,
                "label": model["name"],
                "shortLabel": model["name"],
                "family": model.get("family") or model["name"],
                "kind": "foundation",
                "interface": interface,
                "parentModelId": None,
                "parameterLabel": model.get("parameter_label") or None,
                "description": identity.get("representation")
                or identity.get("probability_interface"),
                "sortOrder": len(result["models"]),
                "origin": "community",
                "url": model["url"],
                "submissionPath": f"submissions/{path.name}",
                "declarations": identity,
            }
        )
        result.setdefault("sources", []).append(
            {
                "id": source_id,
                "title": f"Community submission: {model['name']}",
                "url": evidence["url"],
                "sha256": evidence["sha256"],
                "submissionPath": f"submissions/{path.name}",
                "runIdentity": evidence["run_identity"],
                "protocolVersion": PROTOCOL_VERSION,
            }
        )
        for task in CATALOG:
            row = data["tasks"].get(task)
            precision = next(spec["precision"] for spec in result["tasks"] if spec["id"] == task)
            raw = row["metric"]["value"] if row else None
            # The published site ranks at the same precision as its fixed paper
            # cells; retain exact estimates in sourceValue and the contribution.
            displayed = f"{raw:.{precision}f}" if row else "—"
            item = {
                "modelId": model_id,
                "taskId": task,
                "value": float(displayed) if row else None,
                "displayValue": displayed,
                "sourceValue": raw,
                "status": "evaluated" if row else "not_evaluated",
                "interface": (
                    identity["probability_interface"]
                    if task == "prior"
                    else "fitted; frozen embeddings"
                )
                if row
                else None,
                "sourceId": source_id,
                "sourceRecordId": f"{model_id}/{task}",
                "notes": ["Community submission; see linked evidence."]
                if row
                else [data["coverage"][task]["reason"]],
                "uncertainty": None,
            }
            if row and row["metric"].get("ci95"):
                interval = row["metric"]["ci95"]
                item["uncertainty"] = {
                    "level": 0.95,
                    "low": interval[0],
                    "high": interval[1],
                    "type": "pointwise bootstrap interval",
                    "samplingUnit": row["protocol"]["bootstrap"]["unit"],
                    "sourceId": source_id,
                }
            result["measurements"].append(item)
    if output is not None:
        write_json(output, result)
    return result
