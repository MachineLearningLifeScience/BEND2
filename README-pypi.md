![BEND 2.0 — Benchmarking the capabilities needed to design DNA](https://huggingface.co/datasets/yhsure/BEND2/resolve/0c1dda471ad13c6126c2cd00cb3fa34852e70673/media/readme-banner.png)

We built BEND 2.0 to test whether genomic models can guide the design of DNA.
Across eight tasks, we examine how they predict sequence function, account for
cell type and genetic background, and choose sequences that produce a desired
response.

![Five capabilities: sequence priors, functional prediction, biological context, genetic interactions and genomic design](https://huggingface.co/datasets/yhsure/BEND2/resolve/d187d3a2fe4fe091da76a50cc280986b6783425c/media/capabilities-wide-light.svg)

BEND prepares the data, fits linear readouts to your model's frozen embeddings,
and reports task scores and predictions. Python 3.11 or later is required.
Your model's framework and weights are installed separately.

## Evaluate your model

With BEND installed, save an adapter as `my_model.py`:

```python
import numpy as np
from bend2 import Model


def embed(sequences: list[str]) -> np.ndarray:
    return your_encoder(sequences)  # [batch, features]


model = Model("My model", embed=embed, revision="checkpoint-v1")
```

Replace `your_encoder` with your model's inference. Return one finite,
fixed-width CPU NumPy vector per complete sequence, in input order, and record
the actual model revision.

Start with Atlas: 7,657 short sequences, sixteen multi-cell design patterns,
and data included with the package.

```bash
bend2 run my_model.py --tasks atlas_profile --output results/my-model
bend2 show results/my-model
```

To try the included base-composition baseline without model weights:

```bash
bend2 run composition --tasks atlas_profile --output results/composition
```

## Tasks

| Task | What it tests |
| --- | --- |
| `prior` | Recovering a hidden DNA base |
| `opensplice` | Predicting mutation effects on splicing |
| `context` | Predicting effect differences between cells |
| `tissue_identification` | Identifying tissues from expression predictions |
| `background` | Predicting interactions between mutations |
| `repair_percentile` | Choosing an edit that matches a reference response |
| `cell_selective` | Increasing expression in one cell while limiting changes in another |
| `atlas_profile` | Choosing enhancers for a desired pattern of activity across cells |

Seven tasks use embeddings; `prior` needs nucleotide probabilities. The `siraj`
task group runs `context`, `background`, `repair_percentile` and `cell_selective`
together, sharing inference work. Inspect requirements before a larger run:

```bash
bend2 plan my_model.py --tasks siraj
```

## Data and results

Small datasets ship with the package. Larger files download from the public
[BEND 2.0 data release](https://huggingface.co/datasets/yhsure/BEND2), pinned to a
fixed revision and checked against the original file sizes and checksums.
Source-specific terms apply to the data; see the
[data guide](https://huggingface.co/datasets/yhsure/BEND2/blob/main/FILES.md) and
[source terms](https://huggingface.co/datasets/yhsure/BEND2/blob/main/LICENSE.md).

Saved results can be opened without loading the model:

```python
from bend2 import Run

run = Run("results/my-model")
scores = run.to_dataframe()
predictions = run.table("atlas_profile")
```

Runs stay local until you choose to share them. The
[source repository and full documentation](https://github.com/yhsure/genomic-bending/tree/benchmark)
currently require GitHub access.
