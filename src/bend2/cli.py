"""A small command line for the same Model/evaluate API used in notebooks."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shlex
import sys
import time
from pathlib import Path

from bend2 import __version__, evaluate
from bend2.catalog import tasks
from bend2.model import Model, composition, uniform
from bend2.results import Run, slug
from bend2.templates import TEMPLATES, write_template


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
    source = path.read_bytes()
    name = "_bend2_model_" + hashlib.sha256(source).hexdigest()[:16]
    module_spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[name] = module
    # Match running a Python script: adjacent helper modules remain importable,
    # including imports performed lazily by the inference callback.
    sys.path.insert(0, str(path.parent))
    # Execute exactly the bytes whose source is recorded, avoiding stale .pyc files.
    exec(compile(source, str(path), "exec"), module.__dict__)
    model = getattr(module, "model", None)
    if not isinstance(model, Model):
        raise ValueError(f"{path.name} must define model = Model(...)")
    model._source_file = path
    return model


def _table(rows):
    widths = [max(len(str(row[index])) for row in rows) for index in range(len(rows[0]))]
    for row in rows:
        print("  ".join(str(value).ljust(width) for value, width in zip(row, widths)).rstrip())


def _show(result):
    data = result.data
    print(f"{data['model']['name']} — {data['status']}")
    rows = [("Task", "Score", "Unit", "Better", "95% CI")]
    for task, row in data["tasks"].items():
        metric = row["metric"]
        value = "undefined" if metric["value"] is None else f"{metric['value']:.6g}"
        interval = metric.get("ci95")
        ci = "—" if not interval else f"[{interval[0]:.6g}, {interval[1]:.6g}]"
        rows.append((task, value, metric["unit"], metric["direction"], ci))
    _table(rows)
    for task in data["requested_tasks"]:
        if task not in data["tasks"]:
            print(f"{task}: {data.get('skipped', {}).get(task, 'pending')}")
    if data.get("error"):
        print(f"Last interruption: {data['error']}")
    print(f"Results: {result.directory / 'result.json'}")


def _show_plan(proposal):
    print(f"{proposal['model']} — evaluation plan")
    rows = [("Task", "Status", "DNA inputs", "Full input length")]
    for row in proposal["tasks"]:
        inputs = row["inputs"]
        count = inputs.get("unique_sequences", inputs.get("sequences"))
        length = inputs["sequence_bases"]
        span = (
            f"{length['min']:,}–{length['max']:,}"
            if length["min"] != length["max"]
            else f"{length['max']:,}"
        )
        rows.append((row["id"], row["status"], f"{count:,}", f"{span} bp"))
    _table(rows)
    if (
        sum(
            row["inputs"].get("shared_inputs") == "siraj" and row["status"] == "selected"
            for row in proposal["tasks"]
        )
        > 1
    ):
        print(
            "Siraj tasks share these DNA inputs: representations are computed once, not once per task."
        )
    for task, reason in proposal["skipped"].items():
        print(f"{task}: {reason}")
    print(
        f"Additional data download: {proposal['additional_download_bytes'] / 1_000_000:.1f} MB (model weights excluded)"
    )
    print(f"Cache: {proposal['cache_dir']}")
    if proposal["missing_extras"]:
        extra = ",".join(proposal["missing_extras"])
        print(
            f'Missing runtime: pip install "bend2[{extra}] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"'
        )
    for message in proposal["problems"]:
        print(f"Resolve before running: {message}")
    for message in proposal["warnings"]:
        print(message)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="bend2", description="BEND 2.0 — benchmark the capabilities needed to design DNA"
    )
    parser.add_argument("--version", action="version", version=f"bend2 {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tasks", help="List tasks, model capabilities and input sizes")
    init = commands.add_parser("init", help="Create a working one-file model adapter")
    init.add_argument("path", nargs="?", default="model.py")
    init.add_argument(
        "--template", choices=TEMPLATES, default="custom", help="Installed starter adapter"
    )
    preflight = commands.add_parser(
        "plan", help="Inspect tasks, context limits and downloads before running"
    )
    preflight.add_argument("model", help="composition, uniform, or your model.py")
    preflight.add_argument("--tasks", default="atlas_profile", help="Task IDs, siraj, or all")
    preflight.add_argument("--cache-dir", type=Path)
    preflight.add_argument("--json", action="store_true", help="Print the machine-readable plan")
    show = commands.add_parser(
        "show", help="Read saved scores and run status without loading a model"
    )
    show.add_argument("directory", type=Path)
    show.add_argument("--json", action="store_true", help="Print the saved result JSON")
    combine = commands.add_parser(
        "combine", help="Combine compatible task runs into one submission"
    )
    combine.add_argument("directories", nargs="+", type=Path)
    combine.add_argument("--output", required=True, type=Path)
    run = commands.add_parser("run", help="Evaluate a model, print scores and save results")
    run.add_argument(
        "model", help="composition, uniform, or a Python file defining model = Model(...)"
    )
    run.add_argument(
        "--tasks",
        default="atlas_profile",
        help="Task IDs, siraj (four shared tasks), or all (includes long-context GTEx)",
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
    submit = commands.add_parser(
        "submit", help="Submit results to the leaderboard or prepare a local record"
    )
    submit.add_argument("directory", type=Path)
    destination = submit.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "--evidence-url", help="Already hosted submission.zip; prepare a local JSON file"
    )
    destination.add_argument(
        "--github",
        nargs="?",
        const=True,
        metavar="OWNER/REPO",
        help="Publish evidence in your BEND fork (or OWNER/REPO) and open a PR using gh",
    )
    submit.add_argument("--output", type=Path, help="Destination submissions/<model-id>.json")
    submit.add_argument("--model-url", help="Model/checkpoint page, if not declared in source=")
    submit.add_argument(
        "--adapter-url", help="Adapter source, if model.py is absent from the bundle"
    )
    submit.add_argument("--family", default="", help="Model family name")
    submit.add_argument("--parameter-label", default="", help="Display size, for example 117M")
    validate = commands.add_parser("validate-submission", help="Validate a contribution as data")
    validate.add_argument("path", type=Path)
    validate.add_argument("--bundle", type=Path, help="Also check a downloaded evidence ZIP")
    leaderboard = commands.add_parser(
        "build-leaderboard", help="Combine reviewed submissions with frozen paper results"
    )
    leaderboard.add_argument(
        "--reference", type=Path, default=Path("website/data/benchmark.paper.json")
    )
    leaderboard.add_argument("--submissions", type=Path, default=Path("submissions"))
    leaderboard.add_argument("--output", type=Path, default=Path("website/data/benchmark.json"))
    args = parser.parse_args(argv)
    try:
        if args.command == "tasks":
            for task in tasks():
                print(f"{task['id']:24} {task['requires']:14} {task['inputs']}")
            return 0
        if args.command == "init":
            path = write_template(args.path, args.template)
            template = TEMPLATES[args.template]
            print(f"Created {path}: {template['description']}")
            if template["extra"]:
                print(
                    f'Runtime: pip install "bend2[{template["extra"]}] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"'
                )
            print(f"Plan: bend2 plan {shlex.quote(str(path))} --tasks {template['tasks']}")
            print(f"Run: bend2 run {shlex.quote(str(path))} --tasks {template['tasks']}")
            return 0
        if args.command == "plan":
            from bend2 import plan

            proposal = plan(load_model(args.model), tasks=args.tasks, cache_dir=args.cache_dir)
            if args.json:
                print(json.dumps(proposal, indent=2))
            else:
                _show_plan(proposal)
            return 0 if proposal["ready"] else 1
        if args.command == "show":
            result = Run(args.directory)
            if args.json:
                print(json.dumps(result.data, indent=2))
            else:
                _show(result)
            return 0
        if args.command == "combine":
            from bend2 import combine

            result = combine(args.directories, output=args.output)
            _show(result)
            print(f"Submit: bend2 submit {shlex.quote(str(result.directory))} --github OWNER/REPO")
            return 0
        if args.command == "export":
            result = Run(args.directory)
            print(result.bundle())
            submission = json.loads(result.submission.read_text())
            if not submission["ready_for_review"]:
                print(
                    "Bundle created for inspection; complete the run and declarations before submitting.",
                    file=sys.stderr,
                )
            return 0
        if args.command == "submit":
            if args.github is not None:
                if args.output:
                    raise ValueError(
                        "--output is for a local record with --evidence-url; GitHub submission saves its record beside the run"
                    )
                from bend2.github import publish_submission

                posted = publish_submission(
                    Run(args.directory),
                    None if args.github is True else args.github,
                    model_url=args.model_url,
                    adapter_url=args.adapter_url,
                    family=args.family,
                    parameter_label=args.parameter_label,
                    progress=lambda message: print(message, file=sys.stderr, flush=True),
                )
                print(f"{posted['status']}: {posted['url']}")
                print(f"Evidence: {posted['evidence_url']}")
                return 0
            from bend2.submissions import prepare_submission

            path = prepare_submission(
                Run(args.directory),
                args.evidence_url,
                args.output,
                model_url=args.model_url,
                adapter_url=args.adapter_url,
                family=args.family,
                parameter_label=args.parameter_label,
            )
            print(f"Prepared {path}")
            print(
                "Open a pull request adding this file under submissions/ on the benchmark branch."
            )
            print(
                "Guide: https://github.com/yhsure/genomic-bending/blob/benchmark/docs/submitting.md"
            )
            print("Nothing has been uploaded or published by this command.")
            return 0
        if args.command == "validate-submission":
            from bend2.submissions import validate_submission

            record = validate_submission(args.path, bundle=args.bundle)
            print(f"Valid: {record['model']['name']}")
            print(
                "Evidence bundle verified."
                if args.bundle
                else "Metadata/protocol checked; evidence bundle not checked."
            )
            return 0
        if args.command == "build-leaderboard":
            from bend2.submissions import build_leaderboard

            data = build_leaderboard(args.reference, args.submissions, args.output)
            count = sum(model.get("origin") == "community" for model in data["models"])
            print(f"Built {args.output}: {count} community models; frozen paper rows retained")
            return 0
        model = load_model(args.model)
        output = args.output or Path("results") / slug(model.name)
        print(f"Output: {output.expanduser().resolve()}", file=sys.stderr)
        repeat = [
            "bend2",
            "run",
            args.model,
            "--tasks",
            args.tasks,
            "--output",
            str(output),
            "--batch-size",
            str(args.batch_size),
        ]
        if args.cache_dir:
            repeat += ["--cache-dir", str(args.cache_dir)]
        print(f"Resume: {shlex.join(repeat)}", file=sys.stderr)
        last = 0.0

        def progress(message):
            nonlocal last
            now = time.monotonic()
            if not message.startswith(("Embedded", "Scored")) or now - last >= 5:
                print(message, file=sys.stderr, flush=True)
                last = now

        result = evaluate(
            model,
            tasks=args.tasks,
            output=output,
            batch_size=args.batch_size,
            cache_dir=args.cache_dir,
            progress=progress,
        )
        print()
        _show(result)
        submission = json.loads(result.submission.read_text())
        if submission["missing_metadata"]:
            print(f"Before submitting, declare: {', '.join(submission['missing_metadata'])}")
        print(f"Submit: bend2 submit {shlex.quote(str(result.directory))} --github OWNER/REPO")
        print(
            f"Manual hosting: bend2 export {shlex.quote(str(result.directory))}; see bend2 submit --help."
        )
        return 0
    except KeyboardInterrupt:
        print(
            "Interrupted. Completed inference batches and tasks remain available for resume.",
            file=sys.stderr,
        )
        return 130
    except Exception as error:
        print(f"bend2: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
