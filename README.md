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
`bend2 run composition --tasks atlas_profile` on CPU. Repeat a run command to
resume it; completed inference batches remain cached.

In Python:

```python
from bend2 import evaluate
from my_model import model

result = evaluate(model, tasks="atlas_profile", output="results/my-model")
result.to_dataframe()  # Scores, units, directions and confidence intervals
```

An encoder already in memory can be passed to `Model("My encoder", embed=encoder)`.
See the [model interface](docs/models.md) and [Python example](docs/quickstart.md#use-python-directly).

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

Results are saved as JSON and Parquet files. The [quickstart](docs/quickstart.md)
covers adding tasks, resuming, comparing models and combining cluster jobs.
Use `bend2 tasks` to list the tasks and `bend2 plan my_model.py --tasks all`
to check requirements before a larger run. See [tasks and compute](docs/tasks.md)
for input sizes and the separate probability interface used by the prior task.

## Examples

Choose an adapter with `bend2 init --template NAME`:

| Template | Adapter |
|---|---|
| `custom` | [Custom encoder (composition example)](src/bend2/_examples/custom.py) |
| `huggingface` | [HyenaDNA embeddings](src/bend2/_examples/huggingface.py) |
| `dnabert2` | [DNABERT-2 embeddings](src/bend2/_examples/dnabert2.py) |
| `ntv3-prior` | [NTv3 paper prior](src/bend2/_examples/ntv3_prior.py) |

[Reference models](docs/reference-models.md) explains optional runtimes and GPU
settings. To add a result to the leaderboard, see the [submission guide](docs/submitting.md).

[Data and licenses](docs/data.md) · [Contributing](CONTRIBUTING.md) · [Citation](CITATION.cff)
