"""Check task requirements and cached file sizes before evaluation.

Evaluation verifies file checksums and cohort contents.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from bend2.catalog import CATALOG
from bend2.datasets import COHORTS, MANIFEST, cache_root
from bend2.model import Model

SIRAJ_TASKS = ("context", "background", "repair_percentile", "cell_selective")
TASK_GROUPS = {"siraj": SIRAJ_TASKS, "all": tuple(CATALOG)}

# Counts describe model inputs, before filtering to each task's scoring cohort.
# The four Siraj tasks share 169,912 distinct DNA sequences.
_INPUTS = {
    "prior": {
        "sequences": 512,
        "sequence_bases": {"min": 1200, "max": 1200},
        "description": "512 hidden-base windows; one or more queries per window",
    },
    "opensplice": {
        "unique_sequences": 590703,
        "readout_rows": 590104,
        "sequence_bases": {"min": 77, "max": 245},
        "description": "590,104 interventions across 466 held-out gene groups",
    },
    "tissue_identification": {
        "sequences": 19278,
        "sequence_bases": {"min": 131072, "max": 131072},
        "description": "12,146 train, 1,350 validation and 5,782 test gene windows; 51 tissues",
    },
    "atlas_profile": {
        "unique_sequences": 7657,
        "sequence_bases": {"min": 145, "max": 145},
        "description": "5,246 source constructs and 2,411 candidates; 16 design requests",
    },
    **{
        task: {
            "unique_sequences": 169912,
            "readout_rows": 170292 if task == "context" else 340584,
            "sequence_bases": {"min": 189, "max": 200},
            "shared_inputs": "siraj",
            "description": "Shared Siraj inference; 128 biological elements",
        }
        for task in SIRAJ_TASKS
    },
}
_ASSETS = {
    "prior": ("prior-panel.parquet",),
    "atlas_profile": (
        "atlas-population.parquet",
        "atlas-programs.csv",
        "atlas-source-activities.parquet",
        "atlas-candidate-activities.parquet",
    ),
    "tissue_identification": ("gtex-targets.npz", "gtex-genes.tsv", "hg38.2bit"),
}
_EXTRA_MODULES = {
    "genome": ("py2bit",),
    "huggingface": ("torch", "transformers", "huggingface_hub"),
    "reference": ("torch", "transformers", "huggingface_hub", "einops"),
}


def resolve_tasks(tasks="atlas_profile") -> list[str]:
    """Expand task IDs, ``siraj`` and ``all``, preserving order without duplicates.

    Accept a comma-separated string or an iterable of task IDs and group names.
    """
    requested = tasks.split(",") if isinstance(tasks, str) else list(tasks)
    if not requested or any(not isinstance(task, str) for task in requested):
        raise ValueError("Choose task IDs, siraj, or all")
    selected = []
    for token in requested:
        token = token.strip()
        if token in TASK_GROUPS:
            selected.extend(TASK_GROUPS[token])
        elif token in CATALOG:
            selected.append(token)
        else:
            raise ValueError(f"Unknown task {token!r}. Choose: {', '.join(CATALOG)}, siraj, or all")
    return list(dict.fromkeys(selected))


def _file_state(path: Path, expected_bytes=None):
    if not path.is_file():
        return "invalid_path" if path.exists() else "missing"
    if expected_bytes is not None and path.stat().st_size != expected_bytes:
        return "size_mismatch"
    if path.stat().st_size == 0:
        return "size_mismatch"
    return "present_unverified"


def _asset(name, root, needed_by):
    spec = MANIFEST["files"][name]
    if spec.get("distribution") == "bundled":
        path = Path(__file__).with_name("_data") / name
        location = "package"
    else:
        algorithm = "sha256" if "sha256" in spec else "md5"
        path = root / "assets" / spec[algorithm] / name
        location = "cache"
        mirror = os.environ.get("BEND2_ASSET_DIR")
        if not path.exists() and mirror:
            candidate = Path(mirror).expanduser().resolve() / name
            if candidate.exists():
                path, location = candidate, "offline_mirror"
    state = _file_state(path, spec["bytes"])
    download = state == "missing" and location == "cache"
    return {
        "name": name,
        "bytes": spec["bytes"],
        "path": str(path),
        "location": location,
        "state": "download" if download else state,
        "download_bytes": spec["bytes"] if download else 0,
        "needed_by": needed_by,
    }


def _model_extra(model, capability):
    callback = getattr(model, capability)
    module = getattr(callback, "__module__", type(callback).__module__)
    return {
        "bend2.reference_models": "reference",
        "bend2.huggingface": "huggingface",
    }.get(module)


def plan(model: Model, *, tasks="atlas_profile", cache_dir=None) -> dict:
    """Describe supported tasks, input lengths, dependencies and data downloads.

    Checks cached file sizes without loading data, running inference or making
    network requests. Download sizes exclude model weights and generated files.
    ``inference_config['maximum_bases']`` declares a limit in bases; tokenizer
    limits must be checked by the adapter.
    """
    if not isinstance(model, Model):
        raise TypeError("Pass a bend2.Model")
    selectors = tasks.split(",") if isinstance(tasks, str) else list(tasks)
    requested = resolve_tasks(selectors)
    allow_skips = any(selector.strip() == "all" for selector in selectors)
    root = cache_root(cache_dir).resolve()
    rows, selected, skipped, extras = [], [], {}, set()
    maximum = model.inference_config.get("maximum_bases")
    if maximum is not None and (type(maximum) is not int or maximum < 1):
        raise ValueError("inference_config['maximum_bases'] must be a positive integer")
    for task in requested:
        name, capability, _, _ = CATALOG[task]
        inputs = {**_INPUTS[task], "sequence_bases": dict(_INPUTS[task]["sequence_bases"])}
        reason = model.unsupported_tasks.get(task)
        if reason is None and getattr(model, capability) is None:
            reason = f"Model does not provide {capability}"
        if not reason and maximum is not None and inputs["sequence_bases"]["max"] > maximum:
            reason = (
                f"Task requires up to {inputs['sequence_bases']['max']:,} bases; "
                f"model declares a {maximum:,}-base limit. Inputs are never truncated."
            )
        required = ["genome"] if task == "tissue_identification" else []
        extra = _model_extra(model, capability)
        if extra:
            required.append(extra)
        if reason:
            skipped[task] = reason
        else:
            selected.append(task)
            extras.update(required)
        rows.append(
            {
                "id": task,
                "name": name,
                "requires": capability,
                "status": "skipped" if reason else "selected",
                "reason": reason,
                "inputs": inputs,
                "required_extras": required,
            }
        )

    prepared, requirements = [], {}

    def need(name, task_ids):
        requirements.setdefault(name, []).extend(task_ids)

    def cohort(name, task_ids):
        path = root / "prepared" / COHORTS[name]["sha256"] / f"{name}.parquet"
        state = _file_state(path)
        prepared.append({"name": name, "path": str(path), "state": state, "needed_by": task_ids})
        return state

    if "opensplice" in selected and cohort("opensplice", ["opensplice"]) == "missing":
        need("opensplice.tsv.gz", ["opensplice"])
    siraj = [task for task in selected if task in SIRAJ_TASKS]
    if siraj:
        # evaluate() loads the shared cell-selective data once for every Siraj
        # endpoint. A prepared Siraj table can rebuild context without raw data.
        if cohort("siraj", siraj) == "missing":
            need("siraj.zip", siraj)
            need("siraj-numeric-reference.npz", siraj)
        cohort("context", siraj)
        need("siraj_selective.parquet", siraj)
    for task in selected:
        for asset in _ASSETS.get(task, ()):
            need(asset, [task])
    assets = [_asset(name, root, owners) for name, owners in requirements.items()]
    missing_extras = [
        extra
        for extra in sorted(extras)
        if any(importlib.util.find_spec(module) is None for module in _EXTRA_MODULES[extra])
    ]
    problems = [
        f"{asset['name']}: {asset['state']} at {asset['path']}"
        for asset in assets
        if asset["state"] in {"missing", "size_mismatch", "invalid_path"}
    ]
    problems.extend(
        f"Prepared {item['name']}: {item['state']} at {item['path']}"
        for item in prepared
        if item["state"] in {"size_mismatch", "invalid_path"}
    )
    warnings = [
        "Existing data are only checked for location and size; evaluation verifies their checksums.",
        "Download bytes exclude model weights, prepared data and inference/readout storage.",
        "Existing inference caches are not inspected; input counts describe the complete tasks.",
    ]
    if not model.revision:
        warnings.append("Declare revision= before a long run to enable inference reuse and resume.")
    if maximum is None and selected:
        warnings.append(
            "No base-context limit is declared; check the full input lengths against your adapter. "
            "Token limits depend on tokenization and are not converted to base limits."
        )
    return {
        "benchmark": "BEND 2.0",
        "model": model.name,
        "cache_dir": str(root),
        "requested_tasks": requested,
        "allow_skips": allow_skips,
        "selected_tasks": selected,
        "skipped": skipped,
        "tasks": rows,
        "required_extras": sorted(extras),
        "missing_extras": missing_extras,
        "assets": assets,
        "prepared_data": prepared,
        "additional_download_bytes": sum(asset["download_bytes"] for asset in assets),
        "problems": problems,
        "ready": bool(selected)
        and not missing_extras
        and not problems
        and (allow_skips or not skipped),
        "warnings": warnings,
    }
