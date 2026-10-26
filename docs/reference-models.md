# Reference model integrations

The reference adapters specify the checkpoint, tokenizer, model code, layer,
pooling, precision and context limit. Weights load on the first batch.

```bash
pip install "bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 init dnabert2.py --template dnabert2
bend2 run dnabert2.py --tasks atlas_profile --batch-size 16 --output results/dnabert2
bend2 init ntv3.py --template ntv3-prior
bend2 run ntv3.py --tasks prior --batch-size 8 --output results/ntv3-paper-prior
```

The [DNABERT-2](../src/bend2/_examples/dnabert2.py) and
[NTv3](../src/bend2/_examples/ntv3_prior.py) examples are included in the package.
Edit the generated file to select a GPU or another precision. NTv3 may require
acceptance of its checkpoint terms, as described below.

Use the same adapters directly in Python:

```python
from bend2 import evaluate
from bend2.reference_models import dnabert2, ntv3_prior

run = evaluate(dnabert2(), tasks="atlas_profile", output="results/dnabert2")
print(run.scores)

prior = evaluate(ntv3_prior(), tasks="prior", output="results/ntv3-paper-prior")
print(prior.scores)
```

## DNABERT-2 117M

The [released DNABERT-2 checkpoint](https://huggingface.co/zhihan1996/DNABERT-2-117M/tree/b5d88cda421f106afef78cd286200a5b5b8f6fea)
produces 768 features: the mean final-layer state over non-special, non-padding
DNA tokens. No projection, fine-tuning or reverse-complement ensemble is applied.
This matches the representation and PyTorch attention path in BEND's DNABERT-2
comparison. The adapter accepts up to 512 tokens and rejects longer inputs.
Tissue identification is unsupported: `tasks="all"` skips it, and requesting it
by name fails before downloading data or starting inference.

The default uses float32 weights and float32 inference on CPU. For a compatible
NVIDIA or AMD GPU:

```python
model = dnabert2(device="cuda:0", precision="bfloat16")
```

The paper's GPU extraction used bfloat16 autocast and pooled in the hidden-state
dtype. This adapter accumulates the token mean in float32 even with bfloat16
compute. Reproducing archived GPU numbers requires matching the reduction
precision as well as the layer and pooling rule. Device and precision are
recorded in the inference cache identity.

The pinned model has an optional Triton import that newer Transformers versions
try to resolve even on CPU. BEND verifies the SHA-256 of its two source modules
and replaces only that import block with `flash_attn_qkvpacked_func = None` before
loading them. This selects the authors' released PyTorch attention calculation,
also used in BEND's paper integration. The downloaded files stay unchanged.
The patch and source hashes are recorded in the run's inference metadata;
Triton is not required.

This adapter provides embeddings only. DNABERT-2 uses variable-length BPE
tokens, whose softmax does not directly give probabilities for one hidden base.

## NTv3 paper prior and native alternative

`ntv3_prior(size="100m")` uses the human-conditioned post-trained
[100M checkpoint](https://huggingface.co/InstaDeepAI/NTv3_100M_post/tree/b7292f0bd1b5b004d28561783a1890e1ec6f94fd).
`size="650m"` selects the pinned
[650M checkpoint](https://huggingface.co/InstaDeepAI/NTv3_650M_post/tree/ad622051abbe9376bdea3f2727863fa559957e9f).
Both use the separately pinned
[model implementation](https://huggingface.co/InstaDeepAI/ntv3_base_model/tree/0ecff3637f0d3ba5b686d1095083218157c2ca34).

The default `readout="paper"` reproduces the Table 1 input procedure: **two fixed
queries per window**, each masking the target plus 144 of the other 1,199 bases
(12%, rounded). For each draw, the original seeded RNG assigns a random priority
to every input position; the 144 smallest priorities outside the target are
masked. Padding is never eligible. The model receives the complete window,
right-padded with its pad token to a multiple of 128. Its target-position logits
are normalized over A/C/G/T in float64. The adapter returns `[batch, 2, 4]` and
BEND averages the **individual-query losses**, then resamples whole windows.
This follows Table 1's two-query procedure; the eight-query ensemble study used
a different readout.

The query table contains SHA-256 hashes of masked inputs and two random seeds
per input. It excludes original sequences, target bases and outcomes. Its checksum
is recorded in the model's inference configuration. All 1,024 masks match the
paper implementation. The input hash determines the queries independently of
batch size and order. The paper readout accepts only the 512 benchmark inputs.

For a native single-mask probability readout, choose:

```python
native = ntv3_prior(readout="native")
```

Only the supplied hidden target becomes the mask token. This adapter returns
`[batch, 4]` and records the native method separately from the paper's two-query
readout. Neither method fits a head or calibrates against benchmark labels.

NTv3 access is governed by the checkpoint publisher's terms. Accept those terms
on the model page and authenticate with `hf auth login` if the download requires
it. The default is float32; `device="cuda:0", precision="bfloat16"` selects the
publisher's mixed-precision compute settings for the stem, convolution,
transformer and modulation blocks. Embeddings, layer normalization and the
nucleotide output head remain float32. NTv3 controls these settings inside each
block, so wrapping its unchanged default in external autocast would not express
the same readout. No TF32 acceleration is applied by either reference adapter.

## Example run sizes

On an Apple Silicon machine with 18 GiB RAM, using Python 3.12, PyTorch 2.14.1 and
Transformers 4.57.6, complete float32 runs with already downloaded weights took:

| Model and task | Work performed | Time | Peak resident memory |
| --- | --- | --- | --- |
| DNABERT-2, Atlas | 7,657 sequences, 768 features, full fitted readout | 108 seconds | 0.85 GiB |
| NTv3 100M-post, paper prior | 512 complete windows, 1,024 fixed queries and bootstrap | 74 seconds | 1.36 GiB |
| NTv3 100M-post, native prior | 512 complete windows, native probabilities and bootstrap | 50 seconds | 1.20 GiB |

DNABERT-2 used batches of 16 and four CPU threads; NTv3 used batches of eight and
two CPU threads. The NTv3 process peak includes a separate native-head equivalence
check. The checkpoint downloads are approximately 447 MiB and 458 MiB,
respectively; subsequent runs reuse them. Larger tasks such as OpenSplice have
many more sequences and benefit from a GPU.

The paper-prior run scored **1.4924317 bits/base**, compared with the
GPU Table 1 value **1.4924619**. The absolute difference was 0.0000302 bits/base,
with identical input queries and different numerical execution. The native run
scored 2.8898627 bits/base using the same weights under different input conditions.
Submissions record which readout was used.

## What a score establishes

To reproduce a paper row, match its checkpoint, representation, precision,
sequence context and probability readout. NTv3's Atlas paper row, for example,
used human functional tracks and verified reporter flanks.

For a new model, create an editable starter with `bend2 init my_model.py`. Keep its
training-data declaration and representation details with the adapter so that
reviewers can assess the submitted result.
