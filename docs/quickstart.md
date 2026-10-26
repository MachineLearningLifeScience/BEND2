# Working with BEND 2.0

The [README](../README.md) covers installation and a first Atlas evaluation.
This guide continues from a saved run in `results/my-model`.

## Use Python directly

Run this example in a script or notebook:

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
sequence. The function can use a model already loaded in your notebook.

In a notebook, `result.to_dataframe()` displays the scores with units, direction
and available confidence intervals. `result.scores` returns a dictionary of
scores. Use the returned `Run` to read prediction and analysis tables.

## Add more tasks

`siraj` selects `context`, `background`, `repair_percentile` and `cell_selective`. These four tasks share one 93 MB
download and 169,912 unique DNA inputs. Continue in the same directory to keep
all your scores together:

```bash
bend2 run my_model.py --tasks siraj --output results/my-model
```

You can also list individual task IDs separated by commas. OpenSplice is a
separate, larger assay. A probability callback enables the sequence-prior task;
see [model interfaces](models.md).

Check requirements before a larger run:

```bash
bend2 tasks
bend2 plan my_model.py --tasks all
```

`plan` lists input lengths, model limitations, missing dependencies and data
downloads. It imports your adapter but does not call it or download data. Load
weights on first inference so planning can run without them.
Use `from bend2 import plan` for the same information as a Python dictionary.

Tissue identification uses 131,072-base reference-genome windows. It needs the
`genome` extra and an approximately 835 MB assembly download:

```bash
python -m pip install "bend2[genome] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 run my_model.py --tasks tissue_identification --output results/my-model
```

Your encoder must accept the full input length.

`bend2 run my_model.py --tasks all --output results/my-model` evaluates tasks
compatible with your model's declared interfaces and limitations. An
embedding-only model does not receive a prior score. Read [task details](tasks.md)
to choose the environment and resources for the larger assays.

## Inspect and analyze saved results

Print saved scores:

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

`to_dataframe()` contains one row per completed task, with its units and score
direction. Unrun tasks are absent; undefined scores are missing values.

Use `table(task, name="predictions")` to load a saved table as a pandas DataFrame:

```python
predictions = result.table("atlas_profile")
choices = result.table("atlas_profile", "choices")
requests = result.table("atlas_profile", "requests")

# Mean selection gain for each expression program.
gain_by_program = requests.groupby("program")["gain"].mean().sort_values()
print(gain_by_program)
```

`result.tables` lists the tables saved by each task. Atlas has `predictions`,
`choices`, `requests` and `validation`; the regulatory effect tasks also save
per-group scores. For a larger table, select the columns
you need, for example
`result.table("opensplice", columns=["gene_id", "y_true", "y_pred"])`.
This checks the file's checksum and reads the selected columns into a new DataFrame.

Scores and provenance live in `result.json`, and each completed task has a
folder of Parquet tables and `protocol.json`. You can read them with other tools:
`pandas.read_parquet("results/my-model/atlas_profile/requests.parquet")` reads
the request table directly. `result.data` exposes the full saved manifest,
including the model declaration, per-task protocol, data provenance and run
status. `result.validate()` checks the manifest and recorded file hashes.

### Compare model runs

Give each checkpoint or inference configuration its own output directory. Compare
the saved scores:

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
checks model identity and each requested task's scientific version, pinned data
and numeric libraries before reusing completed work. Changing the checkpoint or
preprocessing means a new model revision and a new output directory.

If your encoder runs out of memory, lower `--batch-size` and repeat the command
with the same output directory. Completed embedding and native-prior batches
remain cached. Descriptive model metadata can be corrected without repeating
inference. Callbacks must produce the same representation independently of
batch size; declare numerical settings in `inference_config`.

Adding a task or updating BEND with a compatible refactor preserves completed
results. If a requested task's version, data or numeric libraries changed, use
a new output directory. Compatible inference is reused. Each task records the
benchmark source that produced it.

Older development runs that lack per-task compatibility records remain readable
and exportable. Use a new output directory to continue those evaluations.

Data are shared through `~/.cache/bend2`, configurable with `--cache-dir` or
`BEND2_CACHE`. Keep inference caches to continue a run; the result directory
stores scores and prediction tables separately from those caches. See
[data and caching](data.md) for offline use.

## Combine tasks evaluated separately

You can evaluate different tasks in separate jobs or on different machines.
Copy the result directories into one place and combine them:

```bash
bend2 combine results/my-model results/my-model-siraj results/my-model-gtex \
  --output results/my-model-complete
bend2 show results/my-model-complete
```

In Python, use `from bend2 import combine` and
`result = combine(["results/my-model", "results/my-model-siraj"],
output="results/my-model-complete")`. This returns a `Run` containing tasks
from the same model. To compare different models, use separate `Run` objects.

Use the same adapter, checkpoint, representation and inference configuration in
each job. Host environment details may differ and remain recorded for review;
declared numerical settings such as device type and precision must agree.
Keep the model name and training-data declarations consistent. If two inputs
contain the same task, its scores, protocol and evidence hashes must agree
exactly.

The combined directory contains each source run's manifest, adapter, benchmark
implementation and task evidence. Source directories are unchanged. To add
tasks later, continue the source runs and combine them into a new directory.
Combined runs cannot be resumed.

## Share a result on the leaderboard

To submit any completed subset of tasks, follow the
[submission guide](submitting.md). Submission is optional.
