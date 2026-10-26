# Connect your model

An adapter supplies embeddings, nucleotide probabilities, or both. It can use
any model framework or inference service that returns NumPy arrays.

## Embeddings

In a notebook or script:

```python
import numpy as np
from bend2 import Model, evaluate

def embed(sequences: list[str]) -> np.ndarray:
    return your_encoder(sequences)  # shape: [batch, features]

model = Model("My encoder", embed=embed, revision="checkpoint-v1")
result = evaluate(model, tasks="atlas_profile", output="results/my-model")
```

For CLI use, save the function and `model` variable in `my_model.py`, then run
`bend2 run my_model.py --tasks atlas_profile`. `bend2 init my_model.py` creates
an editable [example](../src/bend2/_examples/custom.py).

Return one finite, fixed-width CPU NumPy vector per sequence, in input order.
Load weights once, disable gradients and use evaluation mode. Outputs must be
independent of batch size and ordering. Use `bend2 --debug run ...` for a full
traceback if an adapter fails.

Use the complete supplied sequence without truncation or extra genomic flanks.
Keep labels out of the adapter. BEND fits the task readout on training labels
and evaluates held-out examples. For mutation tasks it computes
mutant-minus-reference features from the individual sequence embeddings.

Record the output layer, pooling, padding treatment, strand handling and any
projection. Exclude padding and special tokens from mean pooling. Declare
reverse-complement ensembling if used. BEND records feature width, which affects
fitted readout capacity.

## Model details

Keep the following fields with the `Model`:

| Field | What to record |
|---|---|
| `revision` | Immutable checkpoint revision, release identifier or weight hash |
| `training_data` | Pretraining and subsequent training data, including possible benchmark exposure |
| `representation` | Output layer and any projection or feature transformation |
| `pooling` | How token or sequence outputs become one vector |
| `source` | Model, checkpoint or implementation URL |
| `inference_config` | JSON object of options affecting outputs, such as precision, device and preprocessing |

Local evaluation needs a name and a callable. Set `revision` to enable resume
and cache reuse; a moving branch such as `main` is not a checkpoint identity.
Update the revision when weights or external helper code change. Record
closure parameters and other output-affecting settings in `inference_config`.
Submissions also require training-data declarations, a source URL and a description
of the representation and pooling, or the probability interface.

Declare context limits with, for example,
`unsupported_tasks={"tissue_identification": "Maximum context is 1,024 bases"}`.
`--tasks all` skips these tasks; requesting one by name fails before inference.

## Nucleotide probabilities

The `prior` task needs probabilities at a supplied zero-based position:

```python
def probabilities(sequences: list[str], positions: list[int]) -> np.ndarray:
    return your_conditional_probabilities(sequences, positions)
    # shape: [batch, 4], columns A, C, G, T

model = Model(
    "My prior", probabilities=probabilities, revision="checkpoint-v1",
    probability_interface="Describe the conditional readout",
)
```

The target base is replaced by `N` before the callback. Return finite,
nonnegative probabilities summing to one; convert logits in the adapter.
BEND does not renormalize or clip them. A `Model` can provide both callbacks.

For repeated queries, return `[batch, queries, 4]` to average individual query
losses within each window before the genomic-block bootstrap. To ensemble
probabilities instead, average them in the adapter and return `[batch, 4]`.
These estimators differ; record which you use in `probability_interface`.

Use the task's sequence context. A left-context-only distribution differs from
one conditioned on both flanks. Declare additional masking, calibration or
denoising. Native functional heads, such as expression or splice predictors,
need task-specific readouts; the package does not yet provide adapters for them.

## Included adapters

Install the optional runtime and copy an adapter:

```bash
pip install "bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 init dnabert2.py --template dnabert2
bend2 run dnabert2.py --tasks atlas_profile --output results/dnabert2
```

| Template | Python factory | Interface |
|---|---|---|
| [`dnabert2`](../src/bend2/_examples/dnabert2.py) | `bend2.reference_models.dnabert2()` | Embeddings |
| [`ntv3-prior`](../src/bend2/_examples/ntv3_prior.py) | `bend2.reference_models.ntv3_prior()` | Probabilities |
| [`huggingface`](../src/bend2/_examples/huggingface.py) | `bend2.huggingface.model(...)` | Embeddings |

Weights load on the first batch. Edit the generated file to choose a device;
`device="cuda:0"` selects a compatible GPU. Reference adapters also support
`precision="bfloat16"` on compatible GPUs; the default is float32 on CPU.
Checkpoint and code revisions are pinned in the adapters and recorded in results.

### DNABERT-2

DNABERT-2 returns 768 features from the mean final-layer state over DNA tokens,
excluding padding and special tokens. It accepts at most 512 tokens, so it
cannot run tissue identification. This adapter provides embeddings only: BPE
token probabilities do not directly give probabilities for one hidden base.
It uses the released PyTorch attention path and pools in float32. The paper's
GPU extraction pooled in the hidden-state dtype; matching archived scores
requires matching that reduction precision too.

### NTv3 prior

Run `bend2 init ntv3.py --template ntv3-prior`, then
`bend2 run ntv3.py --tasks prior --output results/ntv3`. Accept the checkpoint's
terms on Hugging Face and authenticate with `hf auth login` if required.
Use `size="650m"` for the larger checkpoint; the default is `"100m"`.

The default `readout="paper"` uses two fixed queries for each of the 512 benchmark
windows. Each query masks the target plus 144 of the remaining 1,199 bases.
The complete window is padded to a multiple of 128; target logits are normalized
over A/C/G/T in float64. The adapter returns `[batch, 2, 4]` and BEND averages
query losses. Queries match Table 1 and are independent of batch size and order.

`readout="native"` masks only the target and returns `[batch, 4]`. It uses
different input conditions from the paper's two-query procedure. Neither readout
fits a head or calibrates against benchmark labels. See the
[implementation](../src/bend2/reference_models.py) for pinned checkpoints,
masking and precision settings.

### Hugging Face / HyenaDNA

The `huggingface` template provides a pinned HyenaDNA example. It averages
non-special `AutoModel.last_hidden_state` tokens in float32, groups equal token
lengths to avoid padding and rejects inputs beyond the context limit. Set
`max_tokens` if the checkpoint does not declare a limit. The example fits Atlas
but not GTEx's 131,072-base windows.

To use another compatible checkpoint, edit its name, immutable revision and
training-data declaration. `trust_remote_code=True` loads Python code from the
pinned checkpoint. For this adapter alone, the smaller `[huggingface]` extra
can replace `[reference]` in the install command.
