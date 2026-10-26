"""Readable results and a portable, inspectable leaderboard submission."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from bend2.catalog import CATALOG


def digest(path):
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".bend2-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "model"


class Run:
    """A result directory that remains useful without Python or BEND installed."""

    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()

    @property
    def data(self):
        return json.loads((self.directory / "result.json").read_text())

    @property
    def scores(self):
        return {task: row["metric"]["value"] for task, row in self.data["tasks"].items()}

    @property
    def submission(self):
        return self.directory / "submission.json"

    def to_dataframe(self):
        import pandas as pd

        return pd.DataFrame(
            [{"task": task, **row["metric"]} for task, row in self.data["tasks"].items()]
        )

    def prepare_submission(self, evidence_url, output=None, **metadata):
        """Prepare the JSON for a leaderboard PR after hosting :meth:`bundle`."""
        from bend2.submissions import prepare_submission

        return prepare_submission(self, evidence_url, output, **metadata)

    def validate(self):
        """Check recorded files and scores, not authorship or absence of leakage."""
        data = self.data
        if data.get("schema_version") != 1 or data.get("benchmark") != "BEND 2.0":
            raise ValueError("This is not a supported BEND 2.0 result directory")
        identity = hashlib.sha256(
            json.dumps(data["identity_spec"], sort_keys=True).encode()
        ).hexdigest()
        declared = {
            key: value for key, value in data["identity_spec"]["model"].items() if key != "adapter"
        }
        if identity != data["identity"] or declared != data["model"]:
            raise ValueError("Recorded model identity or declarations have changed")
        for task, row in data["tasks"].items():
            if task not in CATALOG:
                raise ValueError(f"Unknown task in result: {task}")
            value = row["metric"]["value"]
            if value is not None and (isinstance(value, bool) or not math.isfinite(value)):
                raise ValueError(f"Invalid score: {task}")
            for relative, expected in row["files"].items():
                if Path(relative).is_absolute() or ".." in Path(relative).parts:
                    raise ValueError(f"Unsafe result artifact: {relative}")
                path = (self.directory / relative).resolve()
                if not path.is_relative_to(self.directory) or not path.is_file():
                    raise ValueError(f"Missing or unsafe result artifact: {relative}")
                if digest(path) != expected:
                    raise ValueError(f"Result artifact changed: {relative}")
            protocol = self.directory / task / "protocol.json"
            if f"{task}/protocol.json" not in row["files"]:
                raise ValueError(f"Missing protocol evidence for {task}")
            recorded = json.loads(protocol.read_text())
            if recorded != {key: row[key] for key in ("metric", "details", "data")}:
                raise ValueError(f"Score or protocol differs from recorded evidence: {task}")
        if data.get("adapter_file"):
            path = self.directory / "model.py"
            if not path.is_file() or digest(path) != data["adapter_file"]:
                raise ValueError("The saved model adapter has changed")
        for relative, expected in data.get("implementation_files", {}).items():
            path = (self.directory / relative).resolve()
            if (
                not relative.startswith("implementation/")
                or ".." in Path(relative).parts
                or not path.is_relative_to(self.directory)
                or not path.is_file()
                or digest(path) != expected
            ):
                raise ValueError(f"Recorded benchmark implementation changed: {relative}")
        return data

    def write_submission(self):
        """Write the machine-readable leaderboard handoff from verified results."""
        data = self.validate()
        metadata = data["model"]
        required = ["revision", "training_data"]
        if any(task != "prior" for task in data["tasks"]):
            required += ["representation", "pooling"]
        if "prior" in data["tasks"]:
            required += ["probability_interface"]
        missing = [field for field in required if not metadata.get(field, "").strip()]
        undefined = [task for task, row in data["tasks"].items() if row["metric"]["value"] is None]
        ready = (
            bool(data["tasks"]) and not missing and not undefined and data["status"] == "complete"
        )
        model_id = slug(metadata["name"]) + "-" + data["identity"][:8]
        measurements = []
        coverage = {
            task: (
                "evaluated"
                if task in data["tasks"]
                else data.get("skipped", {}).get(
                    task, "not completed" if task in data["requested_tasks"] else "not requested"
                )
            )
            for task in CATALOG
        }
        for task, row in data["tasks"].items():
            metric = row["metric"]
            item = {
                "modelId": model_id,
                "taskId": task,
                "value": metric["value"],
                "sourceValue": metric["value"],
                "status": "submitted",
                "interface": metadata.get("probability_interface")
                if task == "prior"
                else "fitted; frozen embeddings",
                "sourceId": "bend2-submission",
                "sourceRecordId": f"{model_id}/{task}",
            }
            if metric.get("ci95"):
                item["uncertainty"] = {
                    "level": 0.95,
                    "low": metric["ci95"][0],
                    "high": metric["ci95"][1],
                    "type": "pointwise bootstrap interval",
                }
            measurements.append(item)
        write_json(
            self.submission,
            {
                "schema_version": 1,
                "benchmark": "BEND 2.0",
                "review_status": "unreviewed",
                "ready_for_review": ready,
                "missing_metadata": missing,
                "undefined_tasks": undefined,
                "run_identity": data["identity"],
                "model": {
                    "id": model_id,
                    "label": metadata["name"],
                    "shortLabel": metadata["name"],
                    "kind": "submission",
                    "interface": "sequence",
                    "description": metadata["representation"],
                    "declarations": metadata,
                },
                "measurements": measurements,
                "coverage": coverage,
                "skipped": data.get("skipped", {}),
                "note": "Candidate rows for maintainer review. Integrity checks do not establish training provenance or absence of label leakage.",
            },
        )
        return self

    def bundle(self):
        """Validate and zip the results, declarations and score evidence for review."""
        self.write_submission()
        data = self.data
        files = {"result.json", "submission.json"}
        files.update(data.get("implementation_files", {}))
        if data.get("adapter_file"):
            files.add("model.py")
        for row in data["tasks"].values():
            files.update(row["files"])
        destination = self.directory / "submission.zip"
        temporary = self.directory / ".submission.zip"
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(files):
                # Stable bytes make an already uploaded bundle reusable when preparing
                # its PR record. Filesystem timestamps and umasks are not evidence.
                entry = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                with (self.directory / path).open("rb") as source, archive.open(entry, "w") as dest:
                    shutil.copyfileobj(source, dest)
        os.replace(temporary, destination)
        return destination
