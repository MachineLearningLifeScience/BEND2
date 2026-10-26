# Contributing to BEND 2.0

For leaderboard submissions, see the [submission guide](docs/submitting.md).
For code changes, describe the problem and how to reproduce it in your issue
or pull request.

## Development

```bash
git clone --single-branch --branch benchmark https://github.com/yhsure/genomic-bending.git
cd genomic-bending
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Keep model frameworks and weights in optional adapters. The core package
should run on a CPU without cluster tools or private data.
Examples live in `src/bend2/_examples/`. `bend2 init` copies them from the
installed package. Use portable paths and load weights on first inference.

Keep automated checks few and focused on evaluation and evidence integrity.
Exercise behavior changes with a small example. Build and install the wheel
when changing package contents, and check documented commands against the code.

Use short, factual prose. Comments should explain constraints or non-obvious
decisions; omit comments that restate the code.

## Preserve the benchmark definition

Define each task's scoring in its task module, shared by evaluation and evidence
review. Review code independently validates the cohort, labels and submitted
evidence before accepting the shared scorer's result.

Increment the affected entries in `TASK_VERSIONS` in `src/bend2/catalog.py` when
changing a task's inputs, splits, readout, selection rules or scores. A shared
readout change needs an increment for every affected task. Formatting, comments
and refactors that preserve results keep the same version. Explain whether
results remain comparable in the pull request.

Keep experimental labels out of model adapters. Use predictions to select candidates
before reading their measured outcomes. Record checkpoints, training data and
source attribution.

The `anonymous-review` branch is frozen for paper review. Development belongs
on branches based on `benchmark`; do not merge, push, or otherwise change the
review branch.

Keep generated runs, checkpoints, job scripts, manuscripts and experiment
archives outside the repository. Link to them when needed for review.
