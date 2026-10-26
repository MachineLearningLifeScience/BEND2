# BEND 2.0

**Bring a DNA model. Measure what it can predict—and what it can help design.**

BEND 2.0 evaluates genomic models across sequence priors, mutation effects,
biological context, genetic interactions, and sequence design. It prepares
the data, runs your model, fits the prescribed readouts, and returns scores
you can submit to the leaderboard.

One Python function connects your model. No fork, model-registry patch, or
cluster-specific environment is required.

## Start with a real task

Python 3.11 or later. Install into your model's environment:

```bash
python -m pip install "bend2 @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 run composition --tasks atlas_profile --output results/first-run
```

The command prints a score table and saves the results as JSON. It evaluates
a CPU base-composition baseline on the actual Atlas task: 7,657 short sequences
and sixteen design requests. The data are included; no model weights are needed.

This development repository currently requires GitHub access. **A PyPI
release has not been published yet.** The intended public release install
is `pip install bend2`.

## Connect your model

```bash
bend2 init my_model.py
```

The generated file contains a `model` descriptor and an embedding function.
Replace the function with your encoder and fill in its checkpoint and
preprocessing details. The interface is:

```python
def embed(sequences: list[str]) -> np.ndarray:
    # One finite, fixed-width vector per sequence, in the same order.
    return your_encoder(sequences)
```

Then run:

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
```

Or use the same model from a notebook:

```python
from bend2 import evaluate
from my_model import model

result = evaluate(model, tasks="atlas_profile", output="results/my-model")
result.to_dataframe()
```

Already have an encoder in memory? Pass it directly to
[`Model`](docs/quickstart.md#use-python-directly); no adapter file is needed.
For a pretrained DNA model, use the [pinned DNABERT-2 embedding or NTv3
native-prior adapters](docs/reference-models.md). A [generic Hugging Face
integration](docs/models.md#hugging-face-models) is also available.

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
bend2 run my_model.py --tasks context,background,repair_percentile,cell_selective \
  --output results/my-model-siraj
```

The Siraj tasks share data, embeddings, and fitted readouts. Repeating a
command with the same model and output directory continues verified work.
`--tasks all` selects every compatible task, including the large OpenSplice
assay and long-context GTEx inputs. Read [task sizes and requirements](docs/tasks.md)
before that run; tissue identification requires the `genome` extra.

## Submit to the leaderboard

```bash
bend2 export results/my-model
# Upload submission.zip to a versioned public download location, then:
bend2 submit results/my-model --evidence-url https://your-host/submission.zip
```

The second command prepares one small JSON file. Add it under `submissions/`
in a pull request targeting `benchmark`. Review and merge adds the model to
our next website build; weights and prediction archives stay outside Git.
You can also send the JSON and evidence link through the model-submission issue
form, and a maintainer can open the PR. See the [submission guide](docs/submitting.md)
for model/source declarations, evidence hosting and review.

The same steps work in Python with `result.bundle()` and
`result.prepare_submission(evidence_url=...)`. Evaluation never uploads results.

**[Quickstart](docs/quickstart.md)** · **[Model interface](docs/models.md)** ·
**[Tasks and compute](docs/tasks.md)** · **[Submission guide](docs/submitting.md)** ·
**[Data and licenses](docs/data.md)**

## Contribute

This repository contains the benchmark package, runnable examples, user
documentation, reviewed contribution files, and the website in `website/`. See [CONTRIBUTING.md](CONTRIBUTING.md) for package changes
and [CITATION.cff](CITATION.cff) for citation metadata. Dataset terms are
separate from the software license.
