# Connect your model

BEND 2.0 works with the model environment you already use. Keep your PyTorch,
JAX, TensorFlow, or inference-service code; expose one function that accepts
DNA strings and returns NumPy arrays. No model registry or repository change
is required.

## Frozen embeddings

```python
import numpy as np

def embed(sequences: list[str]) -> np.ndarray:
    return your_encoder(sequences)  # shape: [len(sequences), feature_dimension]
```

Connect it directly:

```python
from bend2 import Model, evaluate

model = Model(
    "My encoder",
    embed=embed,
    revision="checkpoint-v1",
)
result = evaluate(model, tasks="atlas_profile", output="results/my-model")
```

For command-line use, save the function and this `model` variable in a Python
file, then run `bend2 run my_model.py --tasks atlas_profile`. `bend2 init
my_model.py` creates a complete starting file.

Return one fixed-width, finite vector per sequence in the original order.
Convert framework tensors to CPU NumPy arrays before returning. Load your
checkpoint once, either when creating the adapter or on the first call. Use
evaluation mode and disable gradients.

Only sequence strings reach the function. BEND computes the task-specific
features, fits the fixed readout on allowed training labels, and evaluates
held-out examples. The embedding model remains frozen throughout the run.
For paired mutation tasks, provide representations of each sequence; BEND
constructs the prescribed mutant-minus-reference features.

### Preserve the input

Use the complete sequence provided. Do not silently truncate it, add genomic
flanks, or look up labels by sequence identity. If your model cannot represent
an assay's inputs, choose another task or report that limitation.

Pooling is part of the model definition. Record the layer, token pooling,
padding treatment, strand handling, projections, precision, and other
preprocessing. Exclude padding and special tokens when averaging sequence
representations. If you use reverse-complement ensembling, declare it and
apply it consistently.

BEND records the feature dimension. It does not silently project wide
representations into a common width; readout capacity remains relevant when
comparing models.

### Describe the model once

Keep these declarations with your adapter:

| Field | What to record |
|---|---|
| `name` | A useful display name, including the model size or variant |
| `revision` | An immutable checkpoint revision, release identifier, or weight hash |
| `training_data` | Pretraining and subsequent training data, including possible benchmark exposure |
| `representation` | Output layer and any projection or feature transformation |
| `pooling` | How sequence or token outputs become one vector |
| `source` | Model, checkpoint, or implementation URL (needed for submission) |
| `inference_config` | JSON object of numerical/preprocessing options such as precision, device and windowing |
| `unsupported_tasks` | Optional mapping of task IDs to reasons, for example a known context-length limit |

Only a name and one callable are needed for local exploration. A stable
checkpoint revision makes longer experiments easier to manage. Recording the
representation, pooling and training data also makes your results useful to
you later, even when you never submit them to the leaderboard. These
declarations are required when sharing a result for review.

Examples: `revision="e8c1effa8673814e257e627d2e1eda9ea5a373f6"`
for a pinned repository checkpoint, or `revision="sha256:..."` for your own
weights. A moving branch such as `main` is not a checkpoint identity.

Changing weights, preprocessing, or a remote model endpoint requires a new
revision and a new run. Accurate training-data declarations matter even when
the package can reproduce the score.

Declare known task limits before a long run, for example
`unsupported_tasks={"tissue_identification": "This encoder cannot accept 131,072 bases"}`.
`--tasks all` records and skips these tasks. Requesting one explicitly fails before
any downloads or inference. Other input problems still produce an explicit error;
the benchmark never shortens sequences to make them fit.

### Inference configuration and reuse

For example, set `inference_config={"precision": "float32", "device": "cuda:0"}`
when these affect your implementation. Include closure parameters and helper
configuration that can alter outputs. The cache binds the checkpoint, representation,
pooling, callback/class source, local callable helpers, numerical runtime and
these explicit settings. Change the revision when external helper code or weights
change. Arbitrary mutable Python state cannot be inferred automatically.

Representations must be independent of batch size and input ordering. Disable
training-time randomness, padding-dependent pooling and stateful batch statistics.
Changing batch size, display name, source link or training-data description can
reuse completed inference; changing an inference setting cannot.

## Reference model adapters

[DNABERT-2 embeddings and NTv3 native prior](reference-models.md) have explicit,
pinned model-specific interfaces. They preserve the allowed sequence context and
identify their precision, pooling and checkpoint code. Use these when evaluating
those exact configurations; a generic model loader does not establish scientific
equivalence with a paper row.

## Hugging Face models

Install the optional runtime in the same environment:

```bash
python -m pip install "bend2[huggingface] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
```

This complete example runs a pinned small DNA model on Atlas:

```python
from bend2 import evaluate
from bend2.huggingface import model as huggingface_model

model = huggingface_model(
    "LongSafari/hyenadna-tiny-1k-seqlen-hf",
    revision="e8c1effa8673814e257e627d2e1eda9ea5a373f6",
    training_data=(
        "Human reference genome hg38; next-nucleotide pretraining; "
        "no additional fine-tuning"
    ),
    device="cpu",
    trust_remote_code=True,
)
result = evaluate(model, tasks="atlas_profile", output="results/hyenadna")
```

Generate the same editable example directly from the installed package:

```bash
bend2 init hyenadna.py --template huggingface
bend2 run hyenadna.py --tasks atlas_profile --output results/hyenadna
```

Weights download on first use. HyenaDNA requires custom Python from the pinned
checkpoint, which the explicit `trust_remote_code=True` enables. Use
`device="cuda:0"` for an NVIDIA GPU.

This integration uses `AutoModel.last_hidden_state` and averages non-special
tokens in float32. It groups equal token lengths so no padding is needed, and
rejects inputs beyond the model's context limit. It does not silently truncate
DNA. Supply `max_tokens` when a checkpoint does not declare its limit.
The small example fits Atlas inputs; it cannot process the full GTEx windows.
Review the declared pooling for your own checkpoint before using it.

## Native nucleotide probabilities

The sequence-prior task uses a different interface:

```python
import numpy as np

def predict_base_probabilities(
    sequences: list[str], positions: list[int]
) -> np.ndarray:
    return your_conditional_probabilities(sequences, positions)
    # shape: [len(sequences), 4], columns A, C, G, T
```

Pass it as `Model(..., probabilities=predict_base_probabilities,
probability_interface="Describe the conditional readout")`, with the same
checkpoint and training-data declarations. You may provide both `embed` and
`probabilities` in one `Model`, or just the interface your model supports.

The target position has already been replaced by `N`; its true nucleotide is
not passed to the function. Return finite, nonnegative probabilities that sum
to one. Convert logits yourself. BEND does not silently renormalize vocabulary
mass or clip zero probabilities to improve log loss.

For repeated queries, you may return `[batch, queries, 4]`. BEND then averages
the individual query losses within each window before the genomic-block
bootstrap, matching the paper's two-query NTv3 interface. If your intended
method ensembles probabilities instead, average them in your adapter and
return `[batch, 4]`. These are different estimators; declare which you use.
The saved results record query count, aggregation and accuracy tie handling.

This task requires a conditional distribution given the prescribed sequence
context. A left-context-only next-token distribution is not interchangeable
with a conditional readout that uses both flanks. Record the probability
interface and any calibration, denoising, or additional masking. Such choices
change how results should be compared.

Embedding vectors alone cannot supply a sequence-prior score. A model can
contribute embedding-task results without implementing probabilities, and
vice versa.

## Native functional heads

The packaged embedding workflow evaluates fitted readouts. It currently does
not expose a generic adapter for native splice, expression, or other
functional heads. The paper's native-head results have their own allowed
inputs and scientific contracts; passing those predictions off as embeddings
does not reproduce them.

## Resource use and reproducibility

Start with `atlas_profile` before a large assay. Choose a batch size your
encoder can handle. Keep model dependencies in your environment; the core
package has no mandatory deep learning framework.

Data preparation, sequence inference, readout fitting, and result export are
separate stages. Repeated sequences share embeddings within a dataset, and
the Siraj tasks share their inputs. Keep run caches when continuing a run.
Keep the model revision and preprocessing stable while doing so.

An adapter is ordinary Python executed in your process. Checkpoint loaders
that execute remote Python require the same care as any code dependency.
The result bundle records declarations and computation provenance; it cannot
independently authenticate a remote service or establish what a model saw
during training.
