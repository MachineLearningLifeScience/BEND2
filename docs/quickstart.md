# From installation to your first result

Start with Atlas. It is a complete scientific task with compact included data,
and it uses the same embedding interface as the larger assays.

## Install

Use Python 3.11+ and your model's existing environment, or create a new one:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install "bend2 @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
```

This installs the development branch and currently requires access to the
private GitHub repository. `pip install bend2` will become the public
installation command after a PyPI release is published.
The core package does not install PyTorch, JAX, or model weights.

## Run the included baseline

```bash
bend2 plan composition --tasks atlas_profile
bend2 run composition --tasks atlas_profile --output results/first-run
bend2 show results/first-run
```

The command prints a score table. The baseline represents a sequence using
its four base fractions. BEND fits the source-only Atlas
readout and evaluates its selected candidates against the measured outcomes.
This is an actual benchmark score, not a synthetic installation check.

Scores and provenance are saved in `results/first-run/result.json`;
`submission.json` also records coverage across all eight tasks. The command
explains any requested tasks it could not run. There is no combined score.
`show` reads the saved result whenever you return to it; it does not load a
model, download data or repeat evaluation.

## Use Python directly

This complete example runs in a script or notebook:

```python
import numpy as np
from bend2 import Model, evaluate


def embed(sequences):
    return np.asarray(
        [[sequence.count(base) / len(sequence) for base in "ACGT"]
         for sequence in sequences],
        dtype=np.float32,
    )


model = Model(
    "My composition baseline",
    embed=embed,
    revision="composition-v1",
    training_data="None; deterministic sequence statistics",
    representation="Four A/C/G/T base fractions",
    pooling="Whole input sequence",
)

result = evaluate(model, tasks="atlas_profile", output="results/python-example")
print(result.to_dataframe())
```

Replace `embed` with your encoder and update the model declaration. Your
encoder receives batches of DNA strings and returns one NumPy vector per
sequence. You can close over an already-loaded model; no file or import hook
is required.

The result object exposes:

| Attribute or method | Contents |
|---|---|
| `result.scores` | Mapping from evaluated task IDs to headline scores |
| `result.submission` | Path to the machine-readable submission |
| `result.to_dataframe()` | A Pandas table of task metrics |
| `result.bundle()` | Create the review ZIP and return its path |
| `result.prepare_submission(evidence_url=...)` | Generate the JSON for a leaderboard PR |

In a notebook, use `result.to_dataframe()` to display and work with the
scores. In a script, use `result.scores` for a dictionary of headline values.

## Use the command line

```bash
bend2 init my_model.py
```

Edit the generated `embed` function and `model = Model(...)` declaration.
Then inspect the requirements, run it and inspect the saved result:

```bash
bend2 plan my_model.py --tasks atlas_profile
bend2 run my_model.py --tasks atlas_profile \
  --batch-size 32 --output results/my-model
bend2 show results/my-model
```

The module must expose a variable named `model`. The command imports that
module in your environment, so your model libraries must be installed there.
Keep expensive model loading outside the per-batch function, or initialize
it lazily once.

`plan` lists complete input lengths, declared task limitations, missing optional
dependencies and estimated additional benchmark-data downloads. It does not
call your model or fetch benchmark data. Since the CLI imports your adapter
module, keep weight loading lazy if you want planning to avoid that work too.
Use `from bend2 import plan` for the same information as a Python dictionary.

Ready-to-run model adapters are also included in the installed package; you do
not need to clone the repository to obtain them:

```bash
python -m pip install "bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 init dnabert2.py --template dnabert2
bend2 plan dnabert2.py --tasks atlas_profile
bend2 run dnabert2.py --tasks atlas_profile --batch-size 16 --output results/dnabert2
bend2 show results/dnabert2
```

`bend2 init --help` lists all choices: `custom`, `huggingface`, `dnabert2`, and
`ntv3-prior`. Generation writes an editable Python file and never downloads
weights or replaces an existing file. The reference adapters default to CPU;
edit their device and precision settings to use your GPU. The generic
Hugging Face starter uses the small pinned HyenaDNA encoder and needs the
`huggingface` extra. See [reference adapters](reference-models.md) for checkpoint
access, numeric precision and the distinction between NTv3 readouts.

## Add more tasks

```bash
bend2 tasks
bend2 plan my_model.py --tasks siraj
bend2 run my_model.py --tasks siraj --output results/my-model-siraj
```

`siraj` selects `context`, `background`, `repair_percentile` and `cell_selective`.
These four tasks share one download and reuse representations and readouts.
You can also list individual task IDs separated by commas. OpenSplice is a
separate, larger assay. A probability callback enables the sequence-prior task;
see [model interfaces](models.md).

Tissue identification uses long reference-genome windows and needs the
optional genome reader:

```bash
python -m pip install "bend2[genome] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 plan my_model.py --tasks tissue_identification
bend2 run my_model.py --tasks tissue_identification --output results/my-model-gtex
```

Confirm that your encoder accepts the prescribed 131,072-base sequences
before this run. The first run downloads the approximately 835 MB human
reference assembly. It does not silently shorten sequences to fit a model.

Once you have chosen the right environment and resource budget:

```bash
bend2 plan my_model.py --tasks all
bend2 run my_model.py --tasks all --output results/my-model-all
```

`all` runs tasks compatible with the model's declared interfaces and records
why other tasks are missing. For example, an embedding-only model does not
receive a prior score. [Task details](tasks.md) describe cohorts, downloads,
and what each metric means.

## Continue a run

Repeat the same command to continue in the same output directory. BEND
checks model identity, inputs, and implementation before reusing completed
work. Changing the checkpoint or preprocessing means a new model revision
and a new output directory.

If your encoder runs out of memory, lower `--batch-size` and repeat the command
with the same output directory. Completed embedding and native-prior batches
remain cached. Descriptive model metadata can be corrected without repeating
inference. Callbacks must produce the same representation independently of
batch size; declare numerical settings in `inference_config`.

Changing a scientific readout requires a new output directory, but reuses
compatible inference. Changes to command-line presentation, submission handling
or documentation do not invalidate it.

Data are shared through `~/.cache/bend2`, configurable with `--cache-dir` or
`BEND2_CACHE`. Keep inference caches to continue a run; they do not belong in
the submission. See [data and caching](data.md) for offline use.

## Submit a result

Any completed subset of tasks can be submitted. With GitHub CLI installed and
authenticated, choose an existing public repository you can write to:

```bash
bend2 show results/my-model
bend2 submit results/my-model --github your-lab/your-model
```

The submission command publishes your evidence as a release asset in that
repository and opens a one-file leaderboard PR for maintainer review. It uses
the model declarations saved in the result; `--model-url` can supply a missing
checkpoint/model link. See the [submission guide](submitting.md) for setup,
evidence contents and updating a submission.

For another evidence host or a manual PR, start with
`bend2 export results/my-model`. This creates a local ZIP without publishing;
follow the [manual submission instructions](submitting.md#manual-submission-or-other-evidence-hosting)
to host it and generate the contribution JSON with `--evidence-url`.

## Combine tasks evaluated separately

You can evaluate different tasks in separate jobs or on different machines.
Copy the complete result directories into one place, then combine them without
running model inference or fitted readouts again:

```bash
bend2 combine results/my-model results/my-model-siraj results/my-model-gtex \
  --output results/my-model-complete
bend2 show results/my-model-complete
bend2 submit results/my-model-complete --github your-lab/your-model
```

In Python, use `from bend2 import combine` and
`result = combine(["results/my-model", "results/my-model-siraj"],
output="results/my-model-complete")`. The returned object supports the same
score table, bundle and submission methods as an evaluated run.

Use the same adapter, checkpoint, representation and inference configuration in
each job. Host environment details may differ and remain recorded for review;
declared numerical settings such as device type and precision must agree.
Keep the model name and training-data declarations consistent. If two inputs
contain the same task, its scores, protocol and evidence hashes must agree
exactly. BEND rejects conflicting outcomes instead of choosing a score.

The new directory preserves each original run's manifest, adapter and benchmark
implementation alongside the combined task evidence. It never changes the
source directories. Missing requested tasks remain incomplete. To add future
tasks, continue the original evaluations and combine them into another new
directory; a combined directory is a submission artifact, not a resumable job.
