"""Assemble independently evaluated tasks into one reviewable result directory."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

from bend2 import __version__
from bend2.catalog import CATALOG
from bend2.results import Run, digest, write_json
from bend2.submissions import _PROTOCOLS, _TABLES, _data_summary, _subset, _validate_data


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _adapter_identity(result, capability):
    model = result["identity_spec"]["model"]
    recorded = result.get("inference_specs", {}).get(capability, {}).get("model", {})
    semantic = recorded.get("adapter")
    source = model.get("adapter", {}).get(capability, {})
    # Older CLI versions gave the same source a different module name in each
    # directory. Its function name and source digest still identify the code.
    callable_name = re.sub(r"^_bend2_model_[0-9a-f]+\.", "user_model.", source.get("callable", ""))
    legacy = {"callable": callable_name, "source_sha256": source.get("source_sha256")}
    return semantic, source.get("inference_sha256"), legacy


def _merge_model(results):
    models = [result["identity_spec"]["model"] for result in results]
    merged = copy.deepcopy(models[0])
    revision = merged.get("revision", "").strip()
    if not revision or revision.lower() in {"main", "master", "latest", "head", "default"}:
        raise ValueError("Declare a stable model revision before combining independent runs")
    scientific = ("revision", "representation", "pooling", "probability_interface")
    for index, model in enumerate(models[1:], start=1):
        for field in scientific:
            if model.get(field, "") != merged.get(field, ""):
                raise ValueError(f"Cannot combine runs with different model {field}")
        if model.get("inference_config", {}) != merged.get("inference_config", {}):
            raise ValueError("Cannot combine runs with different model inference_config")
        if set(model.get("capabilities", [])) != set(merged.get("capabilities", [])):
            raise ValueError("Combine runs made with the same model capabilities and adapter")
        if model.get("unsupported_tasks", {}) != merged.get("unsupported_tasks", {}):
            raise ValueError("Cannot combine contradictory unsupported-task declarations")
        for capability in merged["capabilities"]:
            left_semantic, left_digest, left_source = _adapter_identity(results[0], capability)
            right_semantic, right_digest, right_source = _adapter_identity(results[index], capability)
            if left_digest and right_digest:
                same = left_digest == right_digest
            elif left_semantic is not None and right_semantic is not None:
                same = left_semantic == right_semantic
            else:
                same = left_source == right_source and bool(left_source["source_sha256"])
            if not same:
                raise ValueError(f"Cannot combine different {capability} adapter implementations")
        for field in ("name", "training_data", "source"):
            existing, value = merged.get(field, ""), model.get(field, "")
            if existing and value and existing != value:
                raise ValueError(f"Resolve conflicting model {field} declarations before combining")
            if not existing and value:
                merged[field] = value
    return merged


def _check_task(task, row):
    """Check the frozen science without demanding publication-only metadata."""
    _subset(_PROTOCOLS[task], row["details"], f"{task}.protocol")
    _validate_data(task, _data_summary(row["data"]))
    required = [f"{task}/{table}.parquet" for table in _TABLES[task]]
    required.append(f"{task}/protocol.json")
    if any(path not in row["files"] for path in required):
        raise ValueError(f"Missing prediction/protocol evidence for {task}")
    for relative in row["files"]:
        if Path(relative).parts[0] != task or "\\" in relative:
            raise ValueError(f"Unexpected evidence path for {task}: {relative}")


def _copy_verified(source, destination, expected):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, destination.open("xb") as writer:
        shutil.copyfileobj(reader, writer, length=1024 * 1024)
    if digest(destination) != expected:
        raise ValueError(f"Source artifact changed while combining: {source}")


def combine(runs, output) -> Run:
    """Combine task evidence from the same model without running inference again.

    ``runs`` is a sequence of :class:`Run` objects or result-directory paths.
    ``output`` must not exist. Identical overlapping tasks are retained once;
    conflicting results are rejected rather than selected or averaged. Original
    environments, adapters and benchmark implementations remain in the bundle.
    Add future tasks to the original runs, then combine into a new directory.
    """
    if isinstance(runs, (str, Path, Run)):
        raise TypeError("Pass a list of at least two result directories or Run objects")
    sources = [run if isinstance(run, Run) else Run(run) for run in runs]
    if len(sources) < 2:
        raise ValueError("Choose at least two runs to combine")
    if len({run.directory for run in sources}) != len(sources):
        raise ValueError("The same result directory was supplied more than once")
    destination = Path(output).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Combined output already exists: {destination}; choose a new directory")
    with ExitStack() as stack:
        for run in sorted(sources, key=lambda item: str(item.directory)):
            if not (run.directory / "result.json").is_file():
                raise ValueError(f"No BEND result.json in {run.directory}")
            stack.enter_context(FileLock(run.directory / ".run.lock", timeout=0))
        results = [run.validate() for run in sources]
        merged_model = _merge_model(results)
        rows, owners, origins = {}, {}, []
        for run, result in zip(sources, results, strict=True):
            source_result_hash = digest(run.directory / "result.json")
            # Bind the complete source manifest, not only its model/protocol identity:
            # the latter intentionally does not change as more tasks finish.
            origin_key = source_result_hash
            origin = {
                "run_identity": result["identity"],
                "result_sha256": source_result_hash,
                "manifest": f"implementation/origins/{origin_key}/result.json",
                "created_at": result["created_at"],
                "status": result["status"],
                "package_version": result["version"],
                "environment": result.get("environment", {}),
                "tasks": list(result["tasks"]),
            }
            origins.append(origin)
            for task, row in result["tasks"].items():
                if CATALOG[task][1] not in merged_model["capabilities"]:
                    raise ValueError(f"Model does not declare the capability required for {task}")
                if task in merged_model.get("unsupported_tasks", {}):
                    raise ValueError(f"Model declares evaluated task {task} unsupported")
                _check_task(task, row)
                if task in rows:
                    keys = ("metric", "details", "data", "files")
                    if any(rows[task][key] != row[key] for key in keys):
                        raise ValueError(
                            f"Conflicting results for {task}; combine complementary runs or "
                            "identical evidence, never selected scores"
                        )
                    rows[task]["origins"].append(copy.deepcopy(origin))
                else:
                    rows[task] = copy.deepcopy(row)
                    rows[task]["origins"] = [copy.deepcopy(origin)]
                    owners[task] = run
        if not rows:
            raise ValueError("No completed tasks are available to combine")
        requested = list(
            dict.fromkeys(task for result in results for task in result["requested_tasks"])
        )
        skipped = {}
        for result in results:
            for task, reason in result.get("skipped", {}).items():
                if task not in rows:
                    if task in skipped and skipped[task] != reason:
                        raise ValueError(f"Conflicting skipped-task explanations for {task}")
                    skipped[task] = reason
        pending = set(requested) - set(rows) - set(skipped)
        identity_spec = {
            "model": merged_model,
            "combined_from": [
                {key: item[key] for key in ("run_identity", "result_sha256")}
                for item in origins
            ],
        }
        data = {
            "schema_version": 1,
            "benchmark": "BEND 2.0",
            "version": __version__,
            "identity": _hash(identity_spec),
            "identity_spec": identity_spec,
            "model": {key: value for key, value in merged_model.items() if key != "adapter"},
            "created_at": datetime.now(UTC).isoformat(),
            "status": "incomplete" if pending else "complete",
            "combined_from": origins,
            "requested_tasks": requested,
            "skipped": skipped,
            "tasks": {task: rows[task] for task in CATALOG if task in rows},
            "implementation_files": {},
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.mkdir()  # Exclusive: never replace an existing result directory.
        try:
            for task, row in data["tasks"].items():
                for relative, checksum in row["files"].items():
                    _copy_verified(owners[task].directory / relative, destination / relative, checksum)
            for run, result, origin in zip(sources, results, origins, strict=True):
                prefix = Path(origin["manifest"]).parent
                files = {"result.json": origin["result_sha256"]}
                files.update(result.get("implementation_files", {}))
                if result.get("adapter_file"):
                    files["model.py"] = result["adapter_file"]
                for relative, checksum in files.items():
                    copied = (prefix / relative).as_posix()
                    if copied in data["implementation_files"]:
                        continue  # Byte-identical source manifests share one snapshot.
                    _copy_verified(run.directory / relative, destination / copied, checksum)
                    data["implementation_files"][copied] = checksum
            # Preserve a convenient top-level adapter while retaining every source
            # copy above, including different descriptive comments/declarations.
            for run, result in zip(sources, results, strict=True):
                if result.get("adapter_file"):
                    _copy_verified(
                        run.directory / "model.py", destination / "model.py", result["adapter_file"]
                    )
                    data["adapter_file"] = result["adapter_file"]
                    break
            write_json(destination / "result.json", data)
            return Run(destination).write_submission()
        except BaseException:
            shutil.rmtree(destination)
            raise
