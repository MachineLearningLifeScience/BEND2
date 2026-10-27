![BEND 2.0 — Benchmarking the capabilities needed to design DNA](docs/assets/readme-banner.png)

[Model guide](docs/models.md) · [Tasks & compute](docs/tasks.md) ·
[Submit results](#add-your-model-to-the-leaderboard)

BEND 2.0 benchmarks DNA models on eight tasks, from sequence prediction to
choosing sequences for a desired response. It prepares the data, runs inference,
fits task readouts and saves scores and predictions. Model weights stay fixed.

## Get started

**Install** in your model's environment, with Python 3.11 or later:

```bash
python -m pip install "bend2 @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
```

GitHub access is required while the repository is private. The package is not
yet on PyPI. Install your model's framework and weights separately.

**Connect your model.** Create an adapter:

```bash
bend2 init my_model.py
```

Replace its `embed` function with your encoder. Return one finite, fixed-width
NumPy vector per complete input sequence, in input order:

```python
def embed(sequences: list[str]) -> np.ndarray:
    return your_encoder(sequences)  # shape: [batch, features]
```

Set the model's name and checkpoint revision in the generated file.
The [model guide](docs/models.md) covers the callback contract and declarations,
with [DNABERT-2, NTv3 and HyenaDNA adapters](docs/models.md#included-adapters).

**Evaluate.** Start with Atlas, whose data are included:

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
bend2 show results/my-model
```

Atlas uses 7,657 short sequences and sixteen multi-cell design requests.
To try it on CPU without a model, run `bend2 run composition --tasks atlas_profile`.

<details>
<summary>Use Python instead</summary>

```python
from bend2 import evaluate
from my_model import model

result = evaluate(model, tasks="atlas_profile", output="results/my-model")
result.to_dataframe()  # Scores, units, directions and confidence intervals
```

An encoder already in memory can be passed to `Model("My encoder", embed=encoder)`,
with `Model` imported from `bend2`.

</details>

## Work with the results

Reopen a saved run without loading the model:

```python
from bend2 import Run

result = Run("results/my-model")
result.scores  # Scores by task
result.tables  # Available tables by task
predictions = result.table("atlas_profile")
requests = result.table("atlas_profile", "requests")
```

Results are saved as JSON and Parquet. `result.tables` lists the available tables;
`result.table(task, columns=[...])` reads selected columns into a DataFrame.
Keep separate output directories for different models or inference settings.

## Run more tasks

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

<details>
<summary>Combine runs from separate jobs</summary>

```bash
bend2 combine results/my-model results/my-model-siraj --output results/combined
```

Use the same adapter, model revision, declarations and inference settings in
each job. Duplicate tasks must agree. A combined run can be read or submitted;
continue evaluations in the source runs and combine them again into a new directory.
The Python equivalent is `combine(["results/my-model", "results/my-model-siraj"],
output="results/combined")`, imported from `bend2`.

</details>

## Add your model to the leaderboard

Submit results for any subset of the eight tasks. Maintainers check the model
setup and rescore the saved predictions before accepting a submission.
The [submission guide](docs/submitting.md) explains how to share the evidence
and open a pull request. Your runs stay local until you choose to submit them.

[Data & licenses](docs/data.md) · [Contributing](CONTRIBUTING.md) · [Citation](CITATION.cff)
