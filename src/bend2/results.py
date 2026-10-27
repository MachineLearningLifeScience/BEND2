"""Read saved scores and tables, and export submission bundles."""

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
    """Read scores and tables from a saved run.

    ``evaluate`` and ``combine`` return a Run. Use ``Run("results/my-model")``
    to reopen one. Results are stored as JSON and Parquet files.
    """

    def __init__(self, directory):
        self.directory = Path(directory).expanduser().resolve()

    @property
    def data(self):
        return json.loads((self.directory / "result.json").read_text())

    @property
    def scores(self):
        """Scores by completed task; to_dataframe() also includes units and intervals."""
        return {task: row["metric"]["value"] for task, row in self.data["tasks"].items()}

    @property
    def tables(self):
        """List saved table names by task."""
        return {
            task: sorted(_table_paths(task, row)) for task, row in self.data["tasks"].items()
        }

    def table(self, task, name="predictions", *, columns=None):
        """Read a saved table as a pandas DataFrame.

        Use ``run.tables`` to list table names. ``columns=[...]`` selects columns
        to load. The file checksum is verified before reading.
        """
        import pandas as pd

        data = self.data
        if task not in data["tasks"]:
            available = ", ".join(data["tasks"]) or "none"
            raise ValueError(f"No saved result for task {task!r}. Available tasks: {available}")
        row = data["tasks"][task]
        tables = _table_paths(task, row)
        if name not in tables:
            available = ", ".join(sorted(tables)) or "none"
            raise ValueError(
                f"No saved table {name!r} for {task}. Available tables: {available}"
            )
        relative = tables[name]
        path = (self.directory / relative).resolve()
        if not path.is_relative_to(self.directory) or not path.is_file():
            raise ValueError(f"Missing or unsafe result artifact: {relative}")
        if digest(path) != row["files"][relative]:
            raise ValueError(f"Result artifact changed: {relative}")
        return pd.read_parquet(path, columns=columns)

    def to_dataframe(self):
        """One row per completed task, with its value, units, direction and any interval."""
        import pandas as pd

        rows = [{"task": task, **row["metric"]} for task, row in self.data["tasks"].items()]
        if not rows:
            return pd.DataFrame(columns=["task", "name", "value", "unit", "direction", "ci95"])
        return pd.DataFrame(rows)

    def prepare_submission(self, evidence_url, output=None, **metadata):
        """Prepare the JSON for a leaderboard PR after hosting :meth:`bundle`."""
        from bend2.submissions import prepare_submission

        return prepare_submission(self, evidence_url, output, **metadata)

    def validate(self):
        """Check the run manifest against its recorded files and hashes."""
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

    def bundle(self):
        """Validate and zip the results, declarations and score evidence for review."""
        data = self.validate()
        files = {"result.json"}
        files.update(data.get("implementation_files", {}))
        if data.get("adapter_file"):
            files.add("model.py")
        for row in data["tasks"].values():
            files.update(row["files"])
        destination = self.directory / "submission.zip"
        temporary = self.directory / ".submission.zip"
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(files):
                # Fixed timestamps and permissions keep repeated exports byte-identical.
                entry = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o100644 << 16
                with (self.directory / path).open("rb") as source, archive.open(entry, "w") as dest:
                    shutil.copyfileobj(source, dest)
        os.replace(temporary, destination)
        return destination


def _table_paths(task, row):
    """Map table names to their recorded Parquet paths."""
    return {
        Path(relative).stem: relative
        for relative in row["files"]
        if Path(relative).parent == Path(task) and Path(relative).suffix == ".parquet"
    }
