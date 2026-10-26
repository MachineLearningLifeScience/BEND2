# Reference model integrations

These adapters specify a complete representation: weights, tokenizer, code,
layer, pooling, numeric precision and context limit. They load frozen weights on
the first batch. Inference sees sequences and hidden target positions only.

```bash
pip install "bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark"
bend2 init dnabert2.py --template dnabert2
bend2 run dnabert2.py --tasks atlas_profile --batch-size 16 --output results/dnabert2
bend2 init ntv3.py --template ntv3-prior
bend2 run ntv3.py --tasks prior --batch-size 8 --output results/ntv3-paper-prior
```

The [DNABERT-2](../src/bend2/_examples/dnabert2.py) and
[NTv3](../src/bend2/_examples/ntv3_prior.py) examples are the exact files shipped
with the package and copied by `init`. Creating them does not download weights
and never overwrites an existing file. Edit the generated file
to select a GPU or another supported precision before running it. NTv3 may
require acceptance of its checkpoint terms, as described below.

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
This matches the representation and PyTorch attention path used by BEND's frozen
DNABERT-2 comparison. The adapter accepts up to 512 tokens and fails explicitly
on longer inputs; it does not crop GTEx's long genomic windows. It declares tissue
identification unsupported: `tasks="all"` records that omission, while requesting
the task explicitly fails before downloading data or starting inference.

The default uses float32 weights and float32 inference on CPU. For a compatible
NVIDIA or AMD GPU:

```python
model = dnabert2(device="cuda:0", precision="bfloat16")
```

The paper's GPU extraction used bfloat16 autocast. A float32 run has a different
recorded inference identity and need not give bit-identical results. Numeric
precision and device type are included in the inference cache identity. Model
names, output locations and batch size do not define a new representation.
This adapter accumulates the token mean in float32, including when model compute
uses bfloat16; the archived extraction pooled in the hidden-state dtype. The
underlying layer and pooling rule agree, but exact archived GPU numbers require
matching that reduction precision as well.

The pinned model has an optional Triton import that newer Transformers versions
try to resolve even on CPU. BEND verifies the SHA-256 of its two source modules
and replaces only that import block with `flash_attn_qkvpacked_func = None` before
loading them. This selects the authors' released PyTorch attention calculation,
also used in BEND's paper integration. It does not modify the downloaded source,
weights or Hugging Face cache. The compatibility patch and source hashes appear
in the run's inference metadata. No Triton installation is needed.

DNABERT-2 uses variable-length BPE tokens. Its token softmax is not a distribution
over one hidden nucleotide, so this adapter deliberately exposes embeddings only.

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
BEND averages **individual-query losses**, then resamples whole windows. It does
not average probabilities or use the separate eight-query ensemble study.

The tiny included query table contains only already-hidden-input SHA-256 hashes
and the exact two random seeds. It contains no original sequence, target base
or outcome. Its checksum is recorded in the model's inference configuration.
All 1,024 masks were compared with the frozen implementation. Query selection
depends on the input's hash, so changing order or batch size does not change
the queries. This paper readout accepts the 512 frozen benchmark inputs; it fails
for another input instead of silently choosing new seeds.

For a native single-mask probability readout, choose:

```python
native = ntv3_prior(readout="native")
```

Only the supplied hidden target becomes the mask token. This adapter returns
`[batch, 4]` and records the native method separately from the paper's two-query
readout. Neither method fits a head or calibrates against benchmark labels.

NTv3 access is governed by the checkpoint publisher's terms. Accept those terms
on the model page and authenticate with `hf auth login` if the download requires
it. BEND does not redistribute these weights or change their license. The default
is float32; `device="cuda:0", precision="bfloat16"` explicitly selects the
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
check. These are practical examples, not hardware requirements or throughput
guarantees. The checkpoint downloads are approximately 447 MiB and 458 MiB,
respectively; subsequent runs reuse them. Larger tasks such as OpenSplice contain
many more unique sequences and warrant a GPU.

The paper-prior run scored **1.4924317 bits/base**, compared with the frozen
GPU Table 1 value **1.4924619**. The absolute difference was 0.0000302 bits/base;
the input queries match exactly and numeric execution differs. The native run
scored 2.8898627 bits/base. These readouts describe the same frozen weights under
different input conditions, so the submission records the condition explicitly.

## What a score establishes

These integrations make the model input and readout reproducible. A completed
task uses the same frozen task cohorts and scoring protocol as any other model.
An identical model family name alone does not establish reproduction of a paper
row: checkpoint, representation, precision, assay context and probability readout
must also match. In particular, NTv3's Atlas paper row used human functional
tracks and verified reporter flanks, not a generic mean embedding.

For a new model, create an editable starter with `bend2 init my_model.py`. Keep its
training-data declaration and representation details with the adapter so that
reviewers can assess the submitted result.
