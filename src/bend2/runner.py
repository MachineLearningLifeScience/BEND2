"""The public evaluate() workflow: data → inference → fixed readout → results."""

from __future__ import annotations

import hashlib
import importlib.metadata
import itertools
import json
import platform
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

from bend2 import __version__, datasets
from bend2.cache import Embeddings, Probabilities
from bend2.catalog import CATALOG, TASK_VERSIONS
from bend2.model import Model
from bend2.planning import plan
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


def task_protocol(task, runtime):
    """Resume compatibility, independent of source formatting and other tasks."""
    packages = ["numpy", "pandas"]
    if task != "prior":
        packages += ["scipy", "scikit-learn"]
    if task == "tissue_identification":
        packages.append("py2bit")
    data = datasets.task_identity(task)
    if task == "tissue_identification":
        data["test_exclusions"] = datasets.MANIFEST["gtex_common_test_exclusions"]
    return {
        "version": TASK_VERSIONS[task],
        "data": data,
        "numeric_runtime": {key: runtime.get(key) for key in packages},
    }


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
    for resume. Batch size and descriptive metadata may change. Model inference
    must match; completed tasks requested again must have the same scientific
    version, data and numeric libraries. Source-only refactors preserve resume.
    """
    if not isinstance(model, Model):
        raise TypeError("Pass a bend2.Model, for example Model('mine', embed=encode)")
    if type(batch_size) is not int or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    proposal = plan(model, tasks=tasks, cache_dir=cache_dir)
    requested = proposal["requested_tasks"]
    skipped = proposal["skipped"]
    selected = proposal["selected_tasks"]
    if skipped and not proposal["allow_skips"]:
        raise ValueError("; ".join(f"{task}: {reason}" for task, reason in skipped.items()))
    if not selected:
        raise ValueError("No selected task is supported by this model")
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
        "protocols": {task: task_protocol(task, runtime) for task in selected},
    }
    run = Run(output)
    # OS-backed locking is released after a crash and works on Windows, Linux and macOS.
    with FileLock(output / ".run.lock", timeout=0):
        if (output / "result.json").exists():
            result = run.validate()
            if result.get("combined_from"):
                raise ValueError(
                    "This directory combines finished task evidence and cannot be resumed. "
                    "Evaluate into a source run, then combine the updated runs into a new directory."
                )
            previous = result["identity_spec"]
            if "protocols" not in previous:
                raise ValueError(
                    "This run predates per-task resume. Its saved results can still be read and "
                    "exported. Use a new output directory to continue; compatible inference is reused."
                )
            if not model.revision:
                raise ValueError(
                    "Declare revision= before starting a resumable run. "
                    "This run has no fixed model revision; choose a new output directory."
                )
            for capability, old_id in previous["inference"].items():
                if inference_ids.get(capability) != old_id:
                    raise ValueError(
                        f"Cannot resume: {capability} weights, adapter, settings or runtime changed. "
                        "Choose a new output directory."
                    )
            for task in selected:
                if task not in result["tasks"]:
                    continue
                old, new = previous["protocols"][task], identity_spec["protocols"][task]
                changed = []
                if old["version"] != new["version"]:
                    changed.append(f"scientific version {old['version']} → {new['version']}")
                if old["data"] != new["data"]:
                    changed.append("benchmark data changed")
                changed.extend(
                    f"{package} {old['numeric_runtime'][package]} → {version}"
                    for package, version in new["numeric_runtime"].items()
                    if old["numeric_runtime"][package] != version
                )
                if changed:
                    raise ValueError(
                        f"Cannot resume {task}: {', '.join(changed)}. "
                        "Choose a new output directory; compatible inference is reused."
                    )
            identity_spec["protocols"] = {**previous["protocols"], **identity_spec["protocols"]}
            result.update(
                identity=_hash(identity_spec),
                identity_spec=identity_spec,
                model=model.metadata(),
                inference_specs=inference_specs,
            )
            result["requested_tasks"] = list(dict.fromkeys(result["requested_tasks"] + requested))
            result["skipped"].update(skipped)
            for task in selected:
                result["skipped"].pop(task, None)
        else:
            if any(path.name != ".run.lock" for path in output.iterdir()):
                raise ValueError(
                    "Output directory is not empty and has no BEND result.json; choose a new directory"
                )
            result = {
                "schema_version": 1,
                "benchmark": "BEND 2.0",
                "version": __version__,
                "identity": _hash(identity_spec),
                "identity_spec": identity_spec,
                "model": model.metadata(),
                "environment": runtime,
                "inference_specs": inference_specs,
                "created_at": timestamp.isoformat(),
                "requested_tasks": requested,
                "skipped": skipped,
                "tasks": {},
            }
        pending_tasks = [task for task in selected if task not in result["tasks"]]
        if pending_tasks:
            pending_plan = plan(model, tasks=pending_tasks, cache_dir=cache_dir)
            if pending_plan["missing_extras"]:
                extras = ",".join(pending_plan["missing_extras"])
                raise ImportError(
                    f"Missing optional dependencies: bend2[{extras}]. "
                    "Install the matching runtime before starting this run."
                )
            if pending_plan["problems"]:
                raise ValueError("; ".join(pending_plan["problems"]))
        source_id = implementation()
        root = Path(__file__).parent
        source_files = result.setdefault("implementation_files", {})
        for source in sorted([*root.rglob("*.py"), *root.rglob("*.json")]):
            relative = (
                Path("implementation") / source_id / "bend2" / source.relative_to(root)
            ).as_posix()
            if relative not in source_files:
                destination = output / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
                source_files[relative] = digest(destination)
        if model._source_file:
            (output / "model.py").write_bytes(model._source_file.read_bytes())
            result["adapter_file"] = digest(output / "model.py")
        result.setdefault("invocations", []).append(
            {
                "started_at": timestamp.isoformat(),
                "batch_size": batch_size,
                "environment": runtime,
                "implementation": source_id,
                "version": __version__,
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
            for task in selected:
                if task in result["tasks"]:
                    notify(f"{task}: using verified completed result")
                    continue
                notify(f"{task}: {CATALOG[task][2]}")
                started = time.monotonic()
                # All four Siraj endpoints use one cached input set and two shared fits.
                family = (
                    "cell_selective"
                    if task in {"context", "background", "repair_percentile", "cell_selective"}
                    else task
                )
                if family not in data_cache:
                    notify(f"{task}: preparing and verifying the frozen dataset")
                    data_cache[family] = datasets.load(family, cache_dir)
                data = data_cache[family]
                receipt = _receipt(data)
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
                    if store is None:
                        store = Embeddings(
                            cache_root / "embeddings" / f"{inference_ids['embed']}.sqlite"
                        )
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
                    "invocation": len(result["invocations"]) - 1,
                    "files": artifacts,
                }
                write_json(output / "result.json", result)
                notify(f"{task}: {scored.metric['value']} {scored.metric['unit']}")
                if family not in {"cell_selective"}:
                    closed = data_cache.pop(family)
                    if hasattr(closed.get("sequences"), "close"):
                        closed["sequences"].close()
            pending = set(result["requested_tasks"]) - set(result["tasks"]) - set(result["skipped"])
            result["status"] = "incomplete" if pending else "complete"
        except BaseException as error:
            error.add_note(f"Task: {task}")
            result["status"] = "interrupted"
            result["error"] = "\n".join([f"{type(error).__name__}: {error}", *error.__notes__])
            write_json(output / "result.json", result)
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
        return run
