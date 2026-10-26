# BEND 2.0

**Evaluate a DNA model with one Python function.**

BEND 2.0 measures sequence priors, functional prediction and sequence design
across eight tasks. It prepares the data, runs your frozen model, fits the fixed
readouts and saves scores and prediction tables. Use it in a notebook, a script
or a cluster job; leaderboard submission is optional.

## Install

Python 3.11 or later, in your model's environment:

```bash
python -m pip install "bend2 @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
```

The repository currently requires GitHub access. **PyPI publication is pending**;
`pip install bend2` will be the public installation command. The core package
does not install PyTorch, JAX or model weights.

## Connect and evaluate

Create an editable adapter:

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
data are included. To try it before connecting a model, run
`bend2 run composition --tasks atlas_profile` on CPU. Repeat a run command to
resume it; completed inference batches remain cached.

The same adapter works directly in Python:

```python
from bend2 import evaluate
from my_model import model

result = evaluate(model, tasks="atlas_profile", output="results/my-model")
result.to_dataframe()  # Scores, units, directions and confidence intervals
```

An encoder already in memory can be passed to `Model("My encoder", embed=encoder)`.
See the [model interface](docs/models.md) and [complete Python example](docs/quickstart.md#use-python-directly).

## Inspect your results

`bend2 show results/my-model` prints saved scores without loading the model.
For analysis, reopen the same directory in Python:

```python
from bend2 import Run

result = Run("results/my-model")
result.scores                              # Headline values by task
result.tables                              # Available tables by task
predictions = result.table("atlas_profile")
requests = result.table("atlas_profile", "requests")
```

Results are ordinary JSON and Parquet files. The [quickstart](docs/quickstart.md)
covers adding tasks, resuming, comparing models and combining cluster jobs.
Use `bend2 tasks` to explore the eight tasks and `bend2 plan my_model.py --tasks all`
to check requirements before a larger run. See [tasks and compute](docs/tasks.md)
for input sizes and the separate probability interface used by the prior task.

## Examples and further use

These are the exact files copied by `bend2 init --template NAME`:

| Template | Adapter |
|---|---|
| `custom` | [Your encoder, starting from a working CPU example](src/bend2/_examples/custom.py) |
| `huggingface` | [Pinned HyenaDNA encoder](src/bend2/_examples/huggingface.py) |
| `dnabert2` | [DNABERT-2 embeddings](src/bend2/_examples/dnabert2.py) |
| `ntv3-prior` | [NTv3 paper prior](src/bend2/_examples/ntv3_prior.py) |

[Reference models](docs/reference-models.md) explains optional runtimes and GPU
settings. To share a completed result, follow the optional [submission guide](docs/submitting.md).

[Data and licenses](docs/data.md) · [Contributing](CONTRIBUTING.md) · [Citation](CITATION.cff)
