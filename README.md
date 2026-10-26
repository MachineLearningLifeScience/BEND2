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

Run your first task:

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
```

Atlas evaluates multi-cell sequence design using 7,657 short sequences and
sixteen design requests. Its data are included. The command prints your score
and saves the results for submission. Repeat it to resume an interrupted run;
completed inference batches survive changes to batch size.

To try the benchmark before connecting your encoder, run
`bend2 run composition --tasks atlas_profile` on CPU.

## Submit to the leaderboard

Any completed subset of tasks is welcome. With [GitHub CLI](https://cli.github.com/)
installed and authenticated, submit the saved result:

```bash
bend2 submit results/my-model --github your-lab/your-model
```

While BEND's repository is private, provide an existing public repository you
can write to. The command publishes the evidence there and opens a pull request
containing one generated JSON file in BEND. After BEND becomes public,
`bend2 submit results/my-model --github` can use your BEND fork for the evidence,
without a separate repository choice.

A maintainer reviews the evidence and model declaration. Once the PR is merged,
the model appears on the next website build. See the
[submission guide](docs/submitting.md) for authentication, model links, updates
and submission without GitHub CLI.

## Use Python directly

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

After Atlas, `siraj` adds four related regulatory tasks with a shared 93 MB
download and 169,912 unique input sequences. Continue in the same result
directory to keep all your scores together:

```bash
bend2 run my_model.py --tasks siraj --output results/my-model
```

Seven tasks use frozen embeddings. Sequence priors need a separate nucleotide
probability function. BEND keeps fitted and native interfaces explicit and
reports missing tasks without inventing scores or an overall ranking.

`--tasks all` selects tasks allowed by your adapter's declared interfaces and
limitations, including the large OpenSplice assay and long-context GTEx inputs.
Read [task sizes and requirements](docs/tasks.md) before that run; tissue
identification requires the `genome` extra.

## Inspect and continue your work

These commands are available when you need them:

```bash
bend2 tasks                              # List task capabilities and input sizes
bend2 plan my_model.py --tasks all       # Inspect requirements before a larger run
bend2 show results/my-model              # Read saved scores without loading your model
```

`plan` reports full input lengths, declared limitations, missing dependencies
and additional data downloads. For tasks evaluated in separate jobs,
[`bend2 combine`](docs/quickstart.md#combine-tasks-evaluated-separately) joins
compatible results into one submission without repeating inference.

**[Quickstart](docs/quickstart.md)** · **[Model interface](docs/models.md)** ·
**[Tasks and compute](docs/tasks.md)** · **[Submission guide](docs/submitting.md)** ·
**[Data and licenses](docs/data.md)**

## Contribute

This repository contains the package, examples, documentation, reviewed
contributions, and the website in `website/`. See [CONTRIBUTING.md](CONTRIBUTING.md)
for package changes and [CITATION.cff](CITATION.cff) for citation metadata.
Dataset terms are separate from the software license.
