"""The public evaluate() workflow: data → inference → fixed readout → results."""

from __future__ import annotations

import hashlib
import importlib.metadata
import importlib.util
import itertools
import json
import platform
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

from bend2 import datasets
from bend2.cache import Embeddings, Probabilities
from bend2.catalog import CATALOG
from bend2.model import Model
from bend2.results import Run, digest, slug, write_json
from bend2._tasks import run as score


def environment():
    result = {"python": platform.python_version(), "platform": platform.platform()}
    for package in (
        "bend2",
        "numpy",
        "pandas",
        "pyarrow",
        "scipy",
        "scikit-learn",
        "torch",
        "transformers",
        "tokenizers",
        "jax",
        "tensorflow",
        "py2bit",
    ):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            pass
    return result


def implementation():
    root = Path(__file__).parent
    sha = hashlib.sha256()
    for path in sorted([*root.rglob("*.py"), root / "assets.json"]):
        sha.update(str(path.relative_to(root)).encode())
        sha.update(path.read_bytes())
    return sha.hexdigest()


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def protocol_identity(runtime):
    """Only scientific code and numeric libraries invalidate completed scores."""
    root = Path(__file__).parent
    files = [
        *root.glob("_tasks/*.py"),
        root / "readouts.py",
        root / "datasets.py",
        root / "assets.json",
        root / "catalog.py",
        root / "runner.py",
    ]
    if (root / "_linear.py").exists():
        files.append(root / "_linear.py")
    return _hash(
        {
            "sources": {str(path.relative_to(root)): digest(path) for path in sorted(files)},
            "numeric_runtime": {
                key: runtime.get(key)
                for key in ("numpy", "scipy", "scikit-learn", "pandas", "py2bit")
            },
        }
    )


def _inputs(task, data):
    if task == "atlas_profile":
        return data["population"].query('split != "excluded_source_family"').sequence
    if task == "tissue_identification":
        return (data["sequences"][int(index)] for index in data["required_indices"])
    frame = data["context"] if task == "context" else data["records"]
    return itertools.chain(frame.sequence_ref, frame.sequence_alt)


def _receipt(data):
    receipt = dict(data["_provenance"])
    # Share immutable source identities, not the contributor's absolute paths.
    receipt["paths"] = {key: Path(path).name for key, path in receipt["paths"].items()}
    return receipt


def evaluate(
    model: Model,
    *,
    tasks="atlas_profile",
    output=None,
    batch_size=32,
    cache_dir=None,
    progress=None,
) -> Run:
    """Evaluate a model on complete frozen benchmark tasks.

    Start with ``evaluate(model)`` for the small, included enhancer benchmark.
    ``tasks='all'`` selects every supported capability, recording others as
    skipped. Explicitly requested unsupported tasks fail before data downloads.
    Reusing an output directory resumes completed tasks; a revision is required
    for resume. Batch size and descriptive metadata may change. Weights, adapter
    inference settings and the scientific protocol must match. Inference caches
    are independent of command-line, documentation and result-format changes.
    """
    if not isinstance(model, Model):
        raise TypeError("Pass a bend2.Model, for example Model('mine', embed=encode)")
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    all_tasks = tasks == "all" if isinstance(tasks, str) else False
    requested = (
        list(CATALOG) if all_tasks else tasks.split(",") if isinstance(tasks, str) else list(tasks)
    )
    requested = list(dict.fromkeys(task.strip() for task in requested))
    if not requested or any(task not in CATALOG for task in requested):
        raise ValueError(f"Choose task IDs from: {', '.join(CATALOG)}")
    skipped = {
        task: f"Model does not provide {CATALOG[task][1]}"
        for task in requested
        if getattr(model, CATALOG[task][1]) is None
    }
    if skipped and not all_tasks:
        raise ValueError("; ".join(f"{task}: {reason}" for task, reason in skipped.items()))
    selected = [task for task in requested if task not in skipped]
    if not selected:
        raise ValueError("No selected task is supported by this model")
    if "tissue_identification" in selected and importlib.util.find_spec("py2bit") is None:
        raise ImportError(
            "Tissue identification needs py2bit. Install bend2[genome] or choose another task before starting this run."
        )
    notify = progress or (lambda message: None)
    timestamp = datetime.now(UTC)
    output = (
        Path(output or Path("results") / f"{slug(model.name)}-{timestamp:%Y%m%d-%H%M%S}")
        .expanduser()
        .resolve()
    )
    output.mkdir(parents=True, exist_ok=True)
    runtime = environment()
    inference_runtime = {
        key: runtime[key]
        for key in ("python", "numpy", "torch", "transformers", "tokenizers", "jax", "tensorflow")
        if key in runtime
    }
    inference_specs = {
        capability: {
            "format": 2,
            "model": model.inference_identity(capability),
            "runtime": inference_runtime,
        }
        for capability in model.metadata()["capabilities"]
    }
    if not model.revision:
        for spec in inference_specs.values():
            spec["uncached_run"] = uuid.uuid4().hex
    inference_ids = {key: _hash(value) for key, value in inference_specs.items()}
    identity_spec = {
        "model": model.identity(),
        "inference": inference_ids,
        "protocol": protocol_identity(runtime),
    }
    identity = _hash(identity_spec)
    run = Run(output)
    # OS-backed locking is released after a crash and works on Windows, Linux and macOS.
    with FileLock(output / ".run.lock", timeout=0):
        if (output / "result.json").exists():
            result = run.validate()
            previous = result["identity_spec"]
            if (
                previous.get("inference") != inference_ids
                or previous.get("protocol") != identity_spec["protocol"]
            ):
                raise ValueError(
                    "This output uses different weights, inference settings or a scientific protocol. "
                    "Choose a new output directory; compatible cached inference is reused. "
                    "Declare revision= to enable resume."
                )
            result.update(identity=identity, identity_spec=identity_spec, model=model.metadata())
            result["requested_tasks"] = list(dict.fromkeys(result["requested_tasks"] + requested))
            result["skipped"].update(skipped)
        else:
            if any(path.name != ".run.lock" for path in output.iterdir()):
                raise ValueError(
                    "Output directory is not empty and has no BEND result.json; choose a new directory"
                )
            result = {
                "schema_version": 1,
                "benchmark": "BEND 2.0",
                "version": "0.2.0.dev0",
                "identity": identity,
                "identity_spec": identity_spec,
                "model": model.metadata(),
                "environment": runtime,
                "inference_specs": inference_specs,
                "created_at": timestamp.isoformat(),
                "requested_tasks": requested,
                "skipped": skipped,
                "tasks": {},
            }
            # Preserve the small installed implementation, including bundled adapters.
            # A development version string or source digest alone is not recoverable code.
            root = Path(__file__).parent
            result["implementation_files"] = {}
            for source in sorted([*root.rglob("*.py"), *root.rglob("*.json")]):
                relative = Path("implementation/bend2") / source.relative_to(root)
                destination = output / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
                result["implementation_files"][relative.as_posix()] = digest(destination)
        if model._source_file:
            (output / "model.py").write_bytes(model._source_file.read_bytes())
            result["adapter_file"] = digest(output / "model.py")
        result.setdefault("invocations", []).append(
            {
                "started_at": timestamp.isoformat(),
                "batch_size": batch_size,
                "environment": runtime,
                "implementation": implementation(),
            }
        )
        result["status"] = "running"
        result.pop("error", None)
        write_json(output / "result.json", result)
        store, prior_store = None, None
        cache_root = datasets.cache_root(cache_dir)
        shared = {"scratch_dir": cache_root / "readouts", "progress": notify}
        shared["scratch_dir"].mkdir(parents=True, exist_ok=True)
        data_cache = {}
        try:
            if any(task != "prior" for task in selected):
                store = Embeddings(cache_root / "embeddings" / f"{inference_ids['embed']}.sqlite")
            for task in selected:
                notify(f"{task}: {CATALOG[task][2]}")
                started = time.monotonic()
                # All four Siraj endpoints use one cached input set and two shared fits.
                family = (
                    "cell_selective"
                    if task in {"context", "background", "repair_percentile", "cell_selective"}
                    else task
                )
                if family not in data_cache:
                    data_cache[family] = datasets.load(family, cache_dir)
                data = data_cache[family]
                receipt = _receipt(data)
                if task in result["tasks"]:
                    if result["tasks"][task]["data"] != receipt:
                        raise ValueError(
                            f"Data identity changed for {task}; use a new output directory"
                        )
                    notify(f"{task}: using verified completed result")
                    if family != "cell_selective":
                        closed = data_cache.pop(family)
                        if hasattr(closed.get("sequences"), "close"):
                            closed["sequences"].close()
                    continue
                probabilities = None
                inference = {}
                if task == "prior":
                    panel = data["panel"].query('split == "evaluation"')
                    positions = panel.recovery_position.astype(int).tolist()
                    masked = [
                        sequence[:position] + "N" + sequence[position + 1 :]
                        for sequence, position in zip(panel.sequence, positions, strict=True)
                    ]
                    prior_store = Probabilities(
                        cache_root / "probabilities" / f"{inference_ids['probabilities']}.sqlite"
                    )
                    probabilities, inference = prior_store.evaluate(
                        masked, positions, model.probabilities, batch_size, notify
                    )
                else:
                    inference = store.fill(_inputs(task, data), model.embed, batch_size, notify)
                notify(f"{task}: fitting and scoring the fixed protocol")
                scored = score(task, data, store, probabilities, shared=shared)
                directory = output / task
                directory.mkdir(exist_ok=True)
                artifacts = {}
                for name, table in scored.tables.items():
                    path = directory / f"{name}.parquet"
                    table.to_parquet(path, index=False)
                    artifacts[str(path.relative_to(output))] = digest(path)
                protocol = directory / "protocol.json"
                write_json(
                    protocol, {"metric": scored.metric, "details": scored.details, "data": receipt}
                )
                artifacts[str(protocol.relative_to(output))] = digest(protocol)
                result["tasks"][task] = {
                    "metric": scored.metric,
                    "details": scored.details,
                    "data": receipt,
                    "inference": inference,
                    "seconds": time.monotonic() - started,
                    "files": artifacts,
                }
                write_json(output / "result.json", result)
                run.write_submission()
                notify(f"{task}: {scored.metric['value']} {scored.metric['unit']}")
                if family not in {"cell_selective"}:
                    closed = data_cache.pop(family)
                    if hasattr(closed.get("sequences"), "close"):
                        closed["sequences"].close()
            pending = set(result["requested_tasks"]) - set(result["tasks"]) - set(result["skipped"])
            result["status"] = "incomplete" if pending else "complete"
        except BaseException as error:
            result["status"] = "interrupted"
            result["error"] = f"{type(error).__name__}: {error}"
            write_json(output / "result.json", result)
            run.write_submission()
            raise
        finally:
            if store is not None:
                store.close()
            if prior_store is not None:
                prior_store.close()
            for data in data_cache.values():
                if hasattr(data.get("sequences"), "close"):
                    data["sequences"].close()
        write_json(output / "result.json", result)
        return run.write_submission()
