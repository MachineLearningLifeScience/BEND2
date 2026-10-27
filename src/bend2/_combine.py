"""Combine task results from separate evaluations."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

from bend2 import __version__
from bend2.catalog import CATALOG
from bend2.datasets import task_identity
from bend2.results import Run, digest, write_json
from bend2.submissions import _PROTOCOLS, _TABLES, _data_summary, _subset


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _merge_model(results):
    models = [result["identity_spec"]["model"] for result in results]
    merged = copy.deepcopy(models[0])
    revision = merged.get("revision", "").strip()
    if not revision or revision.lower() in {"main", "master", "latest", "head", "default"}:
        raise ValueError("Declare a stable model revision before combining independent runs")
    for model in models[1:]:
        for field in merged:
            if field != "adapter" and model[field] != merged[field]:
                raise ValueError(f"Cannot combine runs with different model {field}")
        for capability in merged["capabilities"]:
            if (
                merged["adapter"][capability]["inference_sha256"]
                != model["adapter"][capability]["inference_sha256"]
            ):
                raise ValueError(f"Cannot combine different {capability} adapter implementations")
    return merged


def _check_task(task, row):
    """Check task protocols, data identities and evidence files."""
    _subset(_PROTOCOLS[task], row["details"], f"{task}.protocol")
    _subset(task_identity(task), _data_summary(row["data"]), f"{task}.data")
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
    """Combine task results from the same model.

    ``runs`` is a sequence of :class:`Run` objects or result-directory paths.
    ``output`` must not exist. Duplicate tasks must have identical results.
    The new directory includes the original environments, adapters and benchmark
    source. To add tasks later, evaluate them separately and combine again.
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
            # The manifest hash distinguishes separate executions of the same model.
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
                    rows[task].pop("invocation", None)  # Resolved in each original manifest below.
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
        destination.mkdir()
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
            # Keep an adapter at the top level as well as in the source snapshots.
            for run, result in zip(sources, results, strict=True):
                if result.get("adapter_file"):
                    _copy_verified(
                        run.directory / "model.py", destination / "model.py", result["adapter_file"]
                    )
                    data["adapter_file"] = result["adapter_file"]
                    break
            write_json(destination / "result.json", data)
            return Run(destination)
        except BaseException:
            shutil.rmtree(destination)
            raise
