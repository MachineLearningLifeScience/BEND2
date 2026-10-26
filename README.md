# BEND 2.0

**Bring a DNA model. Measure what it can predict—and what it can help design.**

BEND 2.0 evaluates DNA models across eight tasks covering sequence priors,
mutation effects, biological context, genetic interactions, and sequence design.
It prepares the data, runs your model, fits the fixed readouts, and saves scores
and prediction tables you can explore in Python.

One Python function connects your model. Use BEND in a notebook, a script or a
cluster job. You do not need to join the leaderboard or change this repository.

## Evaluate your model

Python 3.11 or later. Install into your model's environment:

```bash
python -m pip install "bend2 @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
```

The repository currently requires GitHub access. **The package is not yet
published on PyPI**; `pip install bend2` is the intended public release command.
The core package does not install PyTorch, JAX or model weights.

Create an editable adapter:

```bash
bend2 init my_model.py
```

Replace its embedding function with your encoder and set your model's name and
checkpoint revision. The interface is one function:

```python
def embed(sequences: list[str]) -> np.ndarray:
    # One finite, fixed-width vector per sequence, in the same order.
    return your_encoder(sequences)
```

Run your first task:

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
```

Atlas evaluates multi-cell sequence design using 7,657 short sequences and
sixteen design requests. Its data are included. The command prints your score
and saves per-candidate predictions, selected designs and per-request outcomes.
Repeat it to resume an interrupted run; completed inference batches survive
changes to batch size.

To try BEND before connecting your encoder, run
`bend2 run composition --tasks atlas_profile` on CPU.

## Use Python directly

The same evaluation works in a script or notebook:

```python
from bend2 import evaluate
from my_model import model

result = evaluate(model, tasks="atlas_profile", output="results/my-model")
result.to_dataframe()  # Scores, units, direction and available confidence intervals
```

Already have an encoder in memory? Connect it with
`Model("My encoder", embed=your_encoder, revision="checkpoint-v1")`;
no adapter file is needed. See the [complete Python example](docs/quickstart.md#use-python-directly)
and [model interface](docs/models.md).

## Work with your results

Reopen a saved result without loading the model or repeating evaluation:

```python
from bend2 import Run

result = Run("results/my-model")
result.scores                              # Headline values by task
result.tables                              # Available analysis tables by task
predictions = result.table("atlas_profile")
requests = result.table("atlas_profile", "requests")
```

The command-line equivalent for saved scores is `bend2 show results/my-model`.
Results are ordinary JSON and Parquet files, so other tools can read them too.
The [quickstart](docs/quickstart.md#inspect-and-analyze-saved-results) covers
analysis, comparing models and continuing work across jobs.

## Choose what to evaluate

| Capability | Tasks |
|---|---|
| Sequence priors | Hidden-base probability: `prior` |
| Functional prediction | Splicing effects: `opensplice` |
| Biological context | Cell contrast: `context`; tissue identification: `tissue_identification` |
| Genetic interactions | Background-dependent effects: `background` |
| Genomic design | Single-edit repair: `repair_percentile`; cell-selective editing: `cell_selective`; multi-cell design: `atlas_profile` |

After Atlas, `siraj` adds four related regulatory tasks with a shared 93 MB
download and 169,912 unique input sequences. Continue in the same result
directory to keep your scores together:

```bash
bend2 run my_model.py --tasks siraj --output results/my-model
```

Seven tasks use frozen embeddings. Sequence priors need a separate nucleotide
probability function. BEND keeps fitted and native interfaces explicit and
reports missing tasks without inventing scores or an overall ranking.

Before a larger run, inspect the requirements:

```bash
bend2 tasks                              # List capabilities and input sizes
bend2 plan my_model.py --tasks all       # Check input lengths, dependencies and downloads
```

`--tasks all` selects tasks allowed by your adapter's declared interfaces and
limitations, including the large OpenSplice assay and long-context GTEx inputs.
Read [task sizes and requirements](docs/tasks.md) before that run; tissue
identification requires the `genome` extra. Tasks evaluated in separate jobs can
be [combined](docs/quickstart.md#combine-tasks-evaluated-separately) without
repeating inference.

## Start from a released DNA model

Generate a complete, editable adapter for the pinned DNABERT-2 checkpoint:

```bash
python -m pip install "bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 init dnabert2.py --template dnabert2
bend2 run dnabert2.py --tasks atlas_profile --output results/dnabert2
```

The adapter defaults to CPU; edit its device setting to use your GPU. Weights
load on the first inference batch. Templates also cover NTv3's sequence prior
and a generic Hugging Face encoder. See [reference models](docs/reference-models.md)
for checkpoint access, precision and the evaluated interfaces.

## Share a result on the leaderboard

Leaderboard submission is optional. Any completed subset of tasks can be
proposed for review, using the results you already saved:

```bash
bend2 submit results/my-model --github your-lab/your-model
```

This uses an authenticated [GitHub CLI](https://cli.github.com/), publishes the
evidence in a public repository you can write to, and opens a pull request with
one generated JSON record. Once BEND's repository becomes public, `--github`
without a repository can use your BEND fork instead.

Maintainers independently rescore the saved predictions against benchmark data
before accepting a result. Contributor evaluations and independent BEND reruns
are identified separately. See the [submission guide](docs/submitting.md) for
required model declarations, evidence, review and submission without GitHub CLI.

**[Quickstart](docs/quickstart.md)** · **[Model interface](docs/models.md)** ·
**[Tasks and compute](docs/tasks.md)** · **[Data and licenses](docs/data.md)** ·
**[Submission guide](docs/submitting.md)**

## Contribute

This repository contains the package, examples, documentation, reviewed
contributions, and the website in `website/`. See [CONTRIBUTING.md](CONTRIBUTING.md)
for package changes and [CITATION.cff](CITATION.cff) for citation metadata.
Dataset terms are separate from the software license.
