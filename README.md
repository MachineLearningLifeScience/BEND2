# BEND 2.0

**Bring a DNA model. Measure what it can predict—and what it can help design.**

BEND 2.0 evaluates DNA models across eight tasks covering sequence priors,
mutation effects, biological context, genetic interactions, and sequence design.
It prepares the data, runs your model, fits the fixed readouts, and produces
results ready for leaderboard review.

One Python function connects your model. No fork, model-registry patch, or
cluster-specific environment is required.

## Evaluate your model

Python 3.11 or later. Install into your model's environment:

```bash
python -m pip install "bend2 @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
```

The repository currently requires GitHub access. **The package is not yet
published on PyPI**; `pip install bend2` is the intended public release command.

Create an adapter for your model:

```bash
bend2 init my_model.py
```

Replace the generated embedding function with your encoder and describe its
checkpoint and preprocessing. The interface is one function:

```python
def embed(sequences: list[str]) -> np.ndarray:
    # One finite, fixed-width vector per sequence, in the same order.
    return your_encoder(sequences)
```

Inspect the requirements, evaluate, and return to the saved scores:

```bash
bend2 plan my_model.py --tasks siraj
bend2 run my_model.py --tasks siraj --output results/my-model
bend2 show results/my-model
```

`siraj` evaluates four related regulatory tasks with one shared 93 MB download.
The plan lists full sequence lengths, declared limitations, missing dependencies
and additional data downloads before inference. The run prints a score table
and saves JSON and Parquet files. Repeat the run command to resume; completed
inference batches survive interruptions and changes to batch size.

For a smaller first run, choose `--tasks atlas_profile`: 7,657 short sequences
and sixteen design requests, with data included. To try it before connecting
your encoder, run `bend2 run composition --tasks atlas_profile` on CPU.

The same interface works from Python:

```python
from bend2 import evaluate
from my_model import model

result = evaluate(model, tasks="atlas_profile", output="results/my-model")
result.to_dataframe()
```

Already have an encoder in memory? Pass it directly to
[`Model`](docs/quickstart.md#use-python-directly). No adapter file is needed.

## Start from a released DNA model

Generate a complete, editable adapter for the pinned DNABERT-2 checkpoint:

```bash
python -m pip install "bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 init dnabert2.py --template dnabert2
bend2 plan dnabert2.py --tasks atlas_profile
bend2 run dnabert2.py --tasks atlas_profile --output results/dnabert2
```

The adapter defaults to CPU; edit its device setting to use your GPU. Weights
load on the first inference batch. Templates also cover NTv3's sequence prior
and a generic Hugging Face encoder. See [reference models](docs/reference-models.md)
for checkpoint access, precision and the evaluated interfaces.

## Choose what to evaluate

| Capability | Tasks |
|---|---|
| Sequence priors | Hidden-base probability: `prior` |
| Functional prediction | Splicing effects: `opensplice` |
| Biological context | Cell contrast: `context`; tissue identification: `tissue_identification` |
| Genetic interactions | Background-dependent effects: `background` |
| Genomic design | Single-edit repair: `repair_percentile`; cell-selective editing: `cell_selective`; multi-cell design: `atlas_profile` |

Seven tasks use frozen embeddings. Sequence priors need a separate nucleotide
probability function. BEND keeps fitted and native interfaces explicit and
reports missing tasks without inventing scores or an overall ranking.

```bash
bend2 tasks
bend2 plan my_model.py --tasks all
```

`--tasks all` selects tasks allowed by your adapter's declared interfaces and
limitations, including the large OpenSplice assay and long-context GTEx inputs.
Read [task sizes and requirements](docs/tasks.md) before that run; tissue
identification requires the `genome` extra.

## Submit to the leaderboard

Any completed subset of tasks is welcome. With [GitHub CLI](https://cli.github.com/)
installed and authenticated, choose a public repository you can write to:

```bash
bend2 submit results/my-model --github your-lab/your-model
```

This command publishes the evidence as a release asset in that repository and
opens a pull request containing one generated JSON file in BEND. It uses the
checkpoint/source declarations in your adapter; `--model-url` can supply a
missing model link. A maintainer reviews the evidence and model declaration.
Once the PR is merged, the model appears on the next website build.

The [submission guide](docs/submitting.md) covers authentication, evidence contents,
updates, and the manual `--evidence-url` route for other hosting. An issue-form
route is available for contributors who prefer maintainer help with the PR.

**[Quickstart](docs/quickstart.md)** · **[Model interface](docs/models.md)** ·
**[Tasks and compute](docs/tasks.md)** · **[Submission guide](docs/submitting.md)** ·
**[Data and licenses](docs/data.md)**

## Contribute

This repository contains the package, examples, documentation, reviewed
contributions, and the website in `website/`. See [CONTRIBUTING.md](CONTRIBUTING.md)
for package changes and [CITATION.cff](CITATION.cff) for citation metadata.
Dataset terms are separate from the software license.
