# BEND 2.0

BEND 2.0 benchmarks DNA models on eight tasks covering sequence priors,
functional prediction and sequence design. It prepares the data, runs model
inference, fits task readouts and saves scores and predictions. Model weights
remain fixed during evaluation.

## Install

Python 3.11 or later, in your model's environment:

```bash
python -m pip install "bend2 @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
```

The repository requires GitHub access. BEND 2.0 has not been released on PyPI
yet. Install your model's framework and weights separately.

## Connect and evaluate

Create an adapter:

```bash
bend2 init my_model.py
```

Replace its `embed` function with your encoder. Return one finite NumPy vector
per complete input sequence, preserving order:

```python
def embed(sequences: list[str]) -> np.ndarray:
    return your_encoder(sequences)  # shape: [batch, features]
```

Set the model's name and checkpoint revision, then run Atlas:

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
```

Atlas uses 7,657 short sequences and sixteen multi-cell design requests; its
data are included. To try the composition baseline, run
`bend2 run composition --tasks atlas_profile` on CPU.

In Python:

```python
from bend2 import evaluate
from my_model import model

result = evaluate(model, tasks="atlas_profile", output="results/my-model")
result.to_dataframe()  # Scores, units, directions and confidence intervals
```

An encoder already in memory can be passed to `Model("My encoder", embed=encoder)`.
See the [model guide](docs/models.md) for the callback contract and declarations.

## Inspect your results

`bend2 show results/my-model` prints saved scores without loading the model.
For analysis, reopen the same directory in Python:

```python
from bend2 import Run

result = Run("results/my-model")
result.scores                              # Scores by task
result.tables                              # Available tables by task
predictions = result.table("atlas_profile")
requests = result.table("atlas_profile", "requests")
```

Results are saved as JSON and Parquet files. `result.tables` lists the available
tables; `result.table(task, columns=[...])` reads selected columns into a DataFrame.
Keep separate output directories for different models or inference settings.

## Add tasks and continue a run

`siraj` runs four related regulatory tasks together. Check their requirements,
then add them to the same result directory:

```bash
bend2 plan my_model.py --tasks siraj
bend2 run my_model.py --tasks siraj --output results/my-model
```

Use a comma-separated list of task IDs or `all` for all compatible tasks.
See [tasks and compute](docs/tasks.md) for input lengths, downloads and scores.

Repeat a command to resume. If inference runs out of memory, lower `--batch-size`;
completed batches remain cached. A changed checkpoint, preprocessing, task
protocol or numeric runtime requires a new output directory. Compatible updates
to BEND and changes to descriptive metadata preserve completed work.

To combine tasks evaluated in separate jobs:

```bash
bend2 combine results/my-model results/my-model-siraj --output results/combined
```

Use the same adapter, model revision, declarations and inference settings in
each job. Duplicate tasks must agree. A combined run can be read or submitted;
continue evaluations in the source runs and combine them again into a new directory.
The Python equivalent is `combine(["results/my-model", "results/my-model-siraj"],
output="results/combined")`, imported from `bend2`.

For DNABERT-2, NTv3 and HyenaDNA examples, see
[included adapters](docs/models.md#included-adapters). To add a result to the
leaderboard, see the [submission guide](docs/submitting.md).

[Data and licenses](docs/data.md) · [Contributing](CONTRIBUTING.md) · [Citation](CITATION.cff)
