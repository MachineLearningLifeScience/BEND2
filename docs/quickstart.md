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

## Connect and evaluate your model

Create an editable adapter:

```bash
bend2 init my_model.py
```

Replace its `embed` function with your encoder. Return one finite, fixed-width
NumPy vector per input sequence, in the same order. Update the `model = Model(...)`
declaration with your model's name and a stable checkpoint revision. Describe
its representation and pooling so you can distinguish runs later. Only a name
and callback are required for a local experiment; publication declarations can
be completed later. See [model interfaces](models.md) for the contract and examples.

Run Atlas:

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
```

Atlas uses 7,657 short sequences and sixteen multi-cell design requests, with
its data included. The command prints a score table and saves predictions,
selected designs and per-request outcomes. To try the benchmark before
connecting your encoder, the optional
`bend2 run composition --tasks atlas_profile` runs a base-composition baseline
on CPU.

Your Python file must expose a variable named `model`. The command imports it
in your environment, so your model libraries must be installed there. Load
weights once, outside the per-batch function or lazily on its first call.
Use evaluation mode and disable gradients.

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

In a notebook, `result.to_dataframe()` displays the scores with units, direction
and available confidence intervals. `result.scores` returns a dictionary of
headline values. The returned `Run` also gives access to the saved prediction
and analysis tables, as shown below.

## Start from a released DNA model

Ready-to-run model adapters are also included in the installed package; you do
not need to clone the repository to obtain them:

```bash
python -m pip install "bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 init dnabert2.py --template dnabert2
bend2 run dnabert2.py --tasks atlas_profile --batch-size 16 --output results/dnabert2
```

`bend2 init --help` lists all choices: `custom`, `huggingface`, `dnabert2`, and
`ntv3-prior`. Generation writes an editable Python file and never downloads
weights or replaces an existing file. The reference adapters default to CPU;
edit their device and precision settings to use your GPU. The generic
Hugging Face starter uses the small pinned HyenaDNA encoder and needs the
`huggingface` extra. See [reference adapters](reference-models.md) for checkpoint
access, numeric precision and the distinction between NTv3 readouts.

## Add more tasks

The next step after Atlas is `siraj`, which selects `context`, `background`,
`repair_percentile` and `cell_selective`. These four tasks share one 93 MB
download and 169,912 unique DNA inputs. Continue in the same directory to keep
all your scores together:

```bash
bend2 run my_model.py --tasks siraj --output results/my-model
```

You can also list individual task IDs separated by commas. OpenSplice is a
separate, larger assay. A probability callback enables the sequence-prior task;
see [model interfaces](models.md).

Before larger runs, inspect the requirements with the optional planning command:

```bash
bend2 tasks
bend2 plan my_model.py --tasks all
```

`plan` lists complete input lengths, declared task limitations, missing optional
dependencies and additional benchmark-data downloads. It does not call your
model or fetch benchmark data. Since the CLI imports your adapter module,
keep weight loading lazy if you want planning to avoid that work too.
Use `from bend2 import plan` for the same information as a Python dictionary.

Tissue identification uses 131,072-base reference-genome windows. It needs the
`genome` extra and an approximately 835 MB assembly download:

```bash
python -m pip install "bend2[genome] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 run my_model.py --tasks tissue_identification --output results/my-model
```

Confirm that your encoder accepts those complete inputs before running it.
BEND does not silently shorten sequences to fit a model.

`bend2 run my_model.py --tasks all --output results/my-model` evaluates tasks
compatible with your model's declared interfaces and limitations. An
embedding-only model does not receive a prior score. Read [task details](tasks.md)
to choose the environment and resources for the larger assays.

## Inspect and analyze saved results

Return to your results without importing the model, downloading data or
repeating evaluation:

```bash
bend2 show results/my-model
```

In a new Python session, open the same directory:

```python
from bend2 import Run

result = Run("results/my-model")
print(result.to_dataframe())
print(result.scores)
print(result.tables)
```

`to_dataframe()` contains one row per completed task. Each task keeps its own
units and direction; there is no combined score. Tasks that have not run remain
missing, and a failed or undefined result does not become a zero.

Use `table(task, name="predictions")` to load a saved table as a pandas DataFrame:

```python
predictions = result.table("atlas_profile")
choices = result.table("atlas_profile", "choices")
requests = result.table("atlas_profile", "requests")

# Which requested expression programs benefited most from selection?
gain_by_program = requests.groupby("program")["gain"].mean().sort_values()
print(gain_by_program)
```

Table names and columns follow the task. `result.tables` lists what is available:
Atlas has `predictions`, `choices`, `requests` and `validation`; the regulatory
effect tasks also save per-group scores. For a larger table, select the columns
you need, for example
`result.table("opensplice", columns=["gene_id", "y_true", "y_pred"])`.
This reads only those columns after checking the saved file's checksum. It does
not refit the readout or recompute the published score. Editing the returned
DataFrame does not change your saved results.

Scores and provenance live in `result.json`, and each completed task has a
folder of Parquet tables and `protocol.json`. These are standard formats that
can be read independently of BEND. For example,
`pandas.read_parquet("results/my-model/atlas_profile/requests.parquet")` reads
the request table directly. `result.data` exposes the full saved manifest,
including the model declaration, per-task protocol, data provenance and run
status. `result.validate()` checks the manifest and recorded file hashes.

### Compare model runs

Give each checkpoint or inference configuration its own output directory. Once
the runs finish, compare the saved scores without loading either model:

```python
import pandas as pd
from bend2 import Run

runs = {"Model A": Run("results/model-a"), "Model B": Run("results/model-b")}
scores = pd.concat(
    [run.to_dataframe().assign(model=name) for name, run in runs.items()],
    ignore_index=True,
)
print(scores.pivot(index="task", columns="model", values="value"))
```

Compare within each task using the same benchmark protocol. Check the `unit`,
`direction` and any `ci95` columns in `scores` when interpreting differences.
A blank cell means that model has no result for that task.

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
`BEND2_CACHE`. Keep inference caches to continue a run; the result directory
stores scores and prediction tables separately from those caches. See
[data and caching](data.md) for offline use.

## Combine tasks evaluated separately

You can evaluate different tasks in separate jobs or on different machines.
Copy the complete result directories into one place, then combine them without
running model inference or fitted readouts again:

```bash
bend2 combine results/my-model results/my-model-siraj results/my-model-gtex \
  --output results/my-model-complete
bend2 show results/my-model-complete
```

In Python, use `from bend2 import combine` and
`result = combine(["results/my-model", "results/my-model-siraj"],
output="results/my-model-complete")`. The returned object supports the same
score and analysis-table methods as an evaluated run. Use `combine` for tasks
from one model; compare different models with separate `Run` objects as above.

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
directory. Combined results preserve the original evaluations; they cannot be
resumed as a new evaluation job.

## Share a result on the leaderboard

This is optional: evaluation and analysis work entirely locally. Any completed
subset of tasks can be proposed for review using the same saved results. Add
checkpoint, training-data and interface declarations to your adapter before
an evaluation you intend to share. You can correct descriptive fields such as
`training_data` and `source` by repeating the run command without repeating
inference. A different checkpoint or representation requires a new run.

With GitHub CLI installed and authenticated:

```bash
bend2 submit results/my-model --github your-lab/your-model
```

While BEND's repository is private, choose an existing public repository you
can write to. The command publishes your evidence there and opens a one-file
leaderboard PR for maintainer review. It uses the model declarations saved in
your result; `--model-url` can supply a missing checkpoint/model link.

After BEND becomes public, `bend2 submit results/my-model --github` can use your
BEND fork to host the evidence. An explicit `OWNER/REPO` remains available when
you prefer another public repository. Maintainers rescore the predictions
against trusted benchmark data before acceptance; an independent model rerun
is recorded separately. See the [submission guide](submitting.md) for required
declarations, evidence contents, review, updates and the route without GitHub CLI.
