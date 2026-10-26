# Connect your model

Provide a function that accepts DNA strings and returns NumPy arrays. The
function can call a model in PyTorch, JAX, TensorFlow, or an inference service.

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
my_model.py` copies the [custom example](../src/bend2/_examples/custom.py)
from the installed package.

Return one fixed-width, finite vector per sequence in the original order.
Convert framework tensors to CPU NumPy arrays before returning. Load your
checkpoint once, either when creating the adapter or on the first call. Use
evaluation mode and disable gradients.

If an adapter fails, BEND reports the task and batch. Invalid outputs include
the returned type, shape or dtype and the expected format. Use
`bend2 --debug run my_model.py --tasks atlas_profile` for the full Python traceback.

BEND fits the task's readout on training labels and evaluates held-out examples.
The embedding model remains frozen. For paired mutation tasks, return a
representation of each sequence; BEND computes mutant-minus-reference features.

### Preserve the input

Use the complete sequence provided. Do not truncate it, add genomic
flanks, or look up labels by sequence identity. If your model cannot represent
an assay's inputs, choose another task or report that limitation.

Pooling is part of the model definition. Record the layer, token pooling,
padding treatment, strand handling, projections, precision, and other
preprocessing. Exclude padding and special tokens when averaging sequence
representations. If you use reverse-complement ensembling, declare it and
apply it consistently.

BEND uses and records the returned feature dimension. Readout capacity therefore
varies with embedding width.

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

Local evaluation requires a name and one callable. Set `revision` to enable
resume and cache reuse. Submissions require training-data declarations and,
for embedding tasks, the representation and pooling.

Examples: `revision="e8c1effa8673814e257e627d2e1eda9ea5a373f6"`
for a pinned repository checkpoint, or `revision="sha256:..."` for your own
weights. A moving branch such as `main` is not a checkpoint identity.

Changing weights, preprocessing, or a remote model endpoint requires a new
revision and a new run.

Declare known task limits before a long run, for example
`unsupported_tasks={"tissue_identification": "This encoder cannot accept 131,072 bases"}`.
`--tasks all` records and skips these tasks. Requesting one by name fails before
downloads or inference.

### Inference configuration and reuse

For example, set `inference_config={"precision": "float32", "device": "cuda:0"}`
when these affect your implementation. Include closure parameters and helper
configuration that can alter outputs. Cache reuse requires the same checkpoint,
representation, pooling, callback/class source, local callable helpers, numerical
runtime and declared settings. Change the revision when external helper code or
weights change. BEND cannot infer changes to arbitrary mutable Python state.

Representations must be independent of batch size and input ordering. Disable
training-time randomness, padding-dependent pooling and stateful batch statistics.
Changing batch size, display name, source link or training-data description can
reuse completed inference; changing an inference setting cannot.

## Reference model adapters

The [reference adapters](reference-models.md) provide DNABERT-2 embeddings and
NTv3 prior probabilities with specified checkpoints, readouts and precision.

## Hugging Face models

Install the optional runtime in the same environment:

```bash
python -m pip install "bend2[huggingface] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
```

Generate the [pinned HyenaDNA example](../src/bend2/_examples/huggingface.py)
and run it on Atlas:

```bash
bend2 init hyenadna.py --template huggingface
bend2 run hyenadna.py --tasks atlas_profile --output results/hyenadna
```

The generated file calls `bend2.huggingface.model(...)`. You can use that factory
directly in a notebook, or edit the checkpoint, revision and declarations to
connect another compatible encoder.

Weights download on first use. HyenaDNA requires custom Python from the pinned
checkpoint, enabled by `trust_remote_code=True`. Use
`device="cuda:0"` for an NVIDIA GPU.

This integration uses `AutoModel.last_hidden_state` and averages non-special
tokens in float32. It groups equal token lengths so no padding is needed, and
rejects inputs beyond the model's context limit. Supply `max_tokens` when a
checkpoint does not declare its limit.
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

The target position is replaced by `N` before the function is called. Return
finite, nonnegative probabilities that sum to one. Convert logits in your
adapter. BEND uses the returned probabilities without renormalizing or clipping.

For repeated queries, you may return `[batch, queries, 4]`. BEND then averages
the individual query losses within each window before the genomic-block
bootstrap, matching the paper's two-query NTv3 interface. If your intended
method ensembles probabilities instead, average them in your adapter and
return `[batch, 4]`. These are different estimators; declare which you use.
The saved results record query count, aggregation and accuracy tie handling.

The probability readout must use the task's sequence context. A left-context-only
distribution is not equivalent to one conditioned on both flanks. Record the
probability interface and any calibration, denoising, or additional masking.

## Native functional heads

The embedding workflow uses fitted readouts. Native splice, expression and
other functional heads require task-specific inputs and readouts; the package
does not yet provide adapters for them.

## Resource use and reproducibility

Start with `atlas_profile` before a large assay. Choose a batch size your
encoder can handle. Keep model dependencies in your environment; the core
package has no mandatory deep learning framework.

Repeated sequences share cached embeddings, including across the four Siraj
tasks. Keep the caches, model revision and preprocessing when continuing a run.

Adapter code runs in your Python process, including any remote code loaded by
the checkpoint. Results record your model declarations; training-data exposure
and remote model identity still depend on those declarations.
