# Contributing to BEND 2.0

BEND is a package for evaluating DNA models and inspecting their results.
Improvements to installation, model adapters, local evaluation and analysis are
welcome. Sharing a leaderboard result is optional: submit one generated JSON
file in a pull request. An issue
form is available if you prefer maintainer help. Neither route requires adding
your model implementation to this repository. See [the submission guide](docs/submitting.md).

## Improve the package

Useful changes make an actual step easier: installing in a model environment,
running an existing encoder, choosing a task, recovering an interrupted run,
or understanding a result. Describe that step in your issue or pull request.

```bash
git clone --single-branch --branch benchmark https://github.com/yhsure/genomic-bending.git
cd genomic-bending
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Keep the public interface small. Model-specific frameworks belong in optional
adapters or examples. The default installation should not require a deep
learning framework, model weights, cluster tooling, or private storage.
Examples live in `src/bend2/_examples/`. `bend2 init` copies those exact files
from the installed package; keep each example in that one place. They must
avoid developer-machine paths and load model weights only on first inference.

Keep automated checks few and focused on core evaluation and evidence integrity. For a
behavior change, exercise the affected path with a compact example; do not
grow a fixture hierarchy or test matrix. Build and install the wheel when
changing package contents. Documentation changes should be checked against
the actual commands and public signatures.

## Preserve the benchmark definition

Task cohorts, biological splits, allowed model inputs, candidate menus, metric
units, and selection rules define the benchmark. Fixing presentation must not
silently change any of them. A proposed scientific change needs a clear
protocol description and an explicit decision about comparability with
existing results.

Define each task's scoring in its task module, shared by evaluation and evidence
review. Review code independently validates the cohort, labels and submitted
evidence before accepting the shared scorer's result.

Increment the affected entries in `TASK_VERSIONS` in `src/bend2/catalog.py` when
changing a task's inputs, splits, readout, selection rules or scores. A shared
readout change needs an increment for every affected task. Formatting, comments
and refactors that preserve results keep the same version. Resume checks these
versions, pinned data and numeric libraries; exact source hashes record provenance.

Keep labels out of model adapters. Keep candidate measurements separate from
selection. Record checkpoint and training-data declarations, and retain the
source attribution for included data. Report missing tasks as missing.

The `anonymous-review` branch is frozen for paper review. Development belongs
on branches based on `benchmark`; do not merge, push, or otherwise change the
review branch.

## Keep the repository usable

- `src/bend2/`: the installable package and task implementations.
- `src/bend2/_examples/`: the editable adapters used by `bend2 init`.
- `docs/`: model, task, and submission guidance.
- `submissions/`: contributor result records.
- `reviews/`: maintainer-reviewed rescoring and per-task reproduction records.
- `website/`: static site and additive leaderboard build.

Generated runs, model checkpoints, personal job scripts, manuscripts, figures,
and experiment archives do not belong in this source tree. Link a scientific
source or attach a result bundle when that is the material a reviewer needs.
