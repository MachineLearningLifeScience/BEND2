"""A small command line for the same Model/evaluate API used in notebooks."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
import time
from pathlib import Path

from bend2 import __version__, evaluate
from bend2.catalog import tasks
from bend2.model import Model, composition, uniform
from bend2.results import Run, slug

TEMPLATE = '''"""Run with: bend2 run {filename} --tasks atlas_profile"""
import numpy as np
from bend2 import Model


def embed(sequences: list[str]) -> np.ndarray:
    # Replace this working CPU example with your frozen model.
    # Load weights once, use eval mode, preserve order and the full input.
    return np.array([[seq.count(base) / len(seq) for base in "ACGT"]
                     for seq in sequences], dtype=np.float32)


model = Model(
    "My composition example",
    embed=embed,
    revision="composition-example-v1",  # replace with your checkpoint identity
    training_data="none; deterministic sequence statistics",
    representation="four A/C/G/T fractions",
    pooling="whole input sequence",
)
'''


def load_model(spec):
    if spec == "composition":
        return composition()
    if spec == "uniform":
        return uniform()
    path = Path(spec).expanduser().resolve()
    if not path.is_file() or path.suffix != ".py":
        raise ValueError(
            "Choose composition, uniform, or a model.py file. Create one with: bend2 init model.py"
        )
    name = "_bend2_model_" + hashlib.sha256(str(path).encode()).hexdigest()[:16]
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    # Match running a Python script: adjacent helper modules remain importable,
    # including imports performed lazily by the inference callback.
    sys.path.insert(0, str(path.parent))
    # Execute exactly the bytes whose source is recorded, avoiding stale .pyc files.
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    model = getattr(module, "model", None)
    if not isinstance(model, Model):
        raise ValueError(f"{path.name} must define model = Model(...)")
    model._source_file = path
    return model


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="bend2", description="BEND 2.0 — benchmark the capabilities needed to design DNA"
    )
    parser.add_argument("--version", action="version", version=f"bend2 {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tasks", help="List tasks, model capabilities and input sizes")
    init = commands.add_parser("init", help="Create a working one-file model adapter")
    init.add_argument("path", nargs="?", default="model.py")
    run = commands.add_parser("run", help="Evaluate a model and write a report")
    run.add_argument(
        "model", help="composition, uniform, or a Python file defining model = Model(...)"
    )
    run.add_argument(
        "--tasks",
        default="atlas_profile",
        help="Comma-separated task IDs, or all (large; includes long-context GTEx)",
    )
    run.add_argument(
        "--output", type=Path, help="Result directory; same identity resumes automatically"
    )
    run.add_argument(
        "--batch-size", type=int, default=32, help="Inference batch size (default: 32)"
    )
    run.add_argument(
        "--cache-dir",
        type=Path,
        help="Reusable data and embedding cache; defaults to BEND2_CACHE or ~/.cache/bend2",
    )
    export = commands.add_parser(
        "export", help="Check files and create a leaderboard submission.zip"
    )
    export.add_argument("directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "tasks":
            for task in tasks():
                print(f"{task['id']:24} {task['requires']:14} {task['inputs']}")
            return 0
        if args.command == "init":
            path = Path(args.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as handle:
                handle.write(TEMPLATE.format(filename=path.name))
            print(f"Created {path}. Run: bend2 run {path} --tasks atlas_profile")
            return 0
        if args.command == "export":
            result = Run(args.directory)
            print(result.bundle())
            import json

            submission = json.loads(result.submission.read_text())
            if not submission["ready_for_review"]:
                print(
                    "Bundle created for inspection; complete the run and declarations before submitting.",
                    file=sys.stderr,
                )
            return 0
        model = load_model(args.model)
        last = 0.0

        def progress(message):
            nonlocal last
            now = time.monotonic()
            if not message.startswith("Embedded") or now - last >= 5:
                print(message, file=sys.stderr, flush=True)
                last = now

        result = evaluate(
            model,
            tasks=args.tasks,
            output=args.output or Path("results") / slug(model.name),
            batch_size=args.batch_size,
            cache_dir=args.cache_dir,
            progress=progress,
        )
        print(f"Report: {result.report}")
        print(f"Submission: {result.submission}")
        print(f"Bundle: bend2 export {result.directory}")
        return 0
    except KeyboardInterrupt:
        print(
            "Interrupted. Completed embedding batches and tasks remain available for resume.",
            file=sys.stderr,
        )
        return 130
    except Exception as error:
        print(f"bend2: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
