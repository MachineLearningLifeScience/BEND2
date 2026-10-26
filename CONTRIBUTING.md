# Contributing to BEND 2.0

The main contribution is a benchmark result. **Adding your model does not
require a fork or pull request.** Implement the model interface, run the tasks,
and follow [the submission guide](docs/submitting.md).

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
Examples must run from an installed package and avoid developer-machine paths.

Keep automated checks few and focused on the contributor workflow. For a
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

Keep labels out of model adapters. Keep candidate measurements separate from
selection. Record checkpoint and training-data declarations, and retain the
source attribution for included data. Report missing tasks as missing.

The `anonymous-review` branch is frozen for paper review. Development belongs
on branches based on `benchmark`; do not merge, push, or otherwise change the
review branch.

## Keep the repository usable

- `src/bend2/`: the installable package and task implementations.
- `examples/`: small, complete examples people can adapt.
- `docs/`: model, task, and submission guidance.

Generated runs, model checkpoints, personal job scripts, manuscripts, figures,
and experiment archives do not belong in this source tree. Link a scientific
source or attach a result bundle when that is the material a reviewer needs.
