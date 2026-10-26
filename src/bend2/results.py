"""Readable results and a portable, inspectable leaderboard submission."""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
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
    def report(self):
        return self.directory / "report.html"

    @property
    def submission(self):
        return self.directory / "submission.json"

    def to_dataframe(self):
        import pandas as pd

        return pd.DataFrame(
            [{"task": task, **row["metric"]} for task, row in self.data["tasks"].items()]
        )

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
        return data

    def refresh(self):
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
        esc = html.escape
        rows = []
        for task, row in data["tasks"].items():
            metric = row["metric"]
            value = "undefined" if metric["value"] is None else f"{metric['value']:.6g}"
            interval = metric.get("ci95")
            ci = "—" if not interval else f"[{interval[0]:.6g}, {interval[1]:.6g}]"
            detail = esc(json.dumps(row["details"], indent=2))
            links = " · ".join(
                f'<a href="{esc(path)}">{esc(Path(path).name)}</a>' for path in row["files"]
            )
            rows.append(
                f"<tr><td>{esc(CATALOG[task][0])}<small>{esc(task)}</small></td>"
                f'<td class="number">{value}</td><td>{esc(metric["unit"])}</td>'
                f"<td>{esc(metric['direction'])} is better</td><td>{ci}</td></tr>"
                f'<tr><td colspan="5"><details><summary>Protocol &amp; predictions</summary>'
                f"<p>{links}</p><pre>{detail}</pre></details></td></tr>"
            )
        status = (
            "Ready for maintainer review" if ready else "Local result — not ready for submission"
        )
        notes = ""
        if missing:
            notes += f"<p>Add model declarations: {esc(', '.join(missing))}.</p>"
        missing_tasks = [
            f"{task}: {reason}" for task, reason in coverage.items() if reason != "evaluated"
        ]
        if missing_tasks:
            notes += (
                "<details><summary>Task coverage</summary><p>"
                + "<br>".join(esc(item) for item in missing_tasks)
                + "</p></details>"
            )
        if data.get("error"):
            notes += f"<p>Run interrupted: {esc(data['error'])}</p>"
        self.report.write_text(
            f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(metadata["name"])} · BEND 2.0</title>
<style>body{{font:16px/1.6 system-ui,sans-serif;color:#19312b;background:#f4f7f3;max-width:1100px;margin:48px auto;padding:0 24px}}h1{{font-size:42px;line-height:1.15}}.eyebrow{{letter-spacing:.16em;text-transform:uppercase;color:#356e59}}table{{width:100%;border-collapse:collapse;background:white;border:1px solid #d9e2da}}th,td{{text-align:left;padding:12px 16px;border-bottom:1px solid #e4ebe5}}th{{font-size:13px;text-transform:uppercase}}small{{display:block;color:#64746a}}.number{{font:600 24px ui-monospace,monospace}}a{{color:#176b4e}}pre{{white-space:pre-wrap;font-size:13px}}details{{font-size:14px}}.status{{padding:12px 18px;background:#e5eddf;border-radius:8px}}footer{{margin-top:36px;color:#64746a;font-size:13px}}</style>
<p class="eyebrow">BEND 2.0 · benchmark result</p><h1>{esc(metadata["name"])}</h1>
<p>{esc(metadata["revision"] or "Checkpoint revision undeclared")} · {len(rows)} completed tasks</p>
<p class="status">{status}</p>{notes}<table><thead><tr><th>Task</th><th>Score</th><th>Unit</th><th>Direction</th><th>95% interval</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
<p>Scores use the task's fixed protocol. Intervals are pointwise; they do not establish a significant difference between models. The enhancer task reports a descriptive mean across two replicates.</p>
<details><summary>Model &amp; environment</summary><pre>{esc(json.dumps({"model": metadata, "environment": data["environment"]}, indent=2))}</pre></details>
<p><a href="result.json">Full result</a> · <a href="submission.json">Leaderboard candidate</a></p>
<footer>Created {esc(data["created_at"])} · BEND {esc(data["version"])}<br>Run identity {esc(data["identity"])}</footer></html>""",
            encoding="utf-8",
        )
        return self

    def bundle(self):
        """Validate and zip the report, declarations and score evidence for review."""
        self.refresh()
        data = self.data
        files = {"result.json", "submission.json", "report.html"}
        if data.get("adapter_file"):
            files.add("model.py")
        for row in data["tasks"].values():
            files.update(row["files"])
        destination = self.directory / "submission.zip"
        temporary = self.directory / ".submission.zip"
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(files):
                archive.write(self.directory / path, arcname=path)
        os.replace(temporary, destination)
        return destination
