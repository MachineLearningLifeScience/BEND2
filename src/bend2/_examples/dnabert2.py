"""Pinned DNABERT-2 117M embeddings. Requires the bend2[reference] runtime."""

from bend2.reference_models import dnabert2

# Weights load once on the first batch. The checkpoint, tokenizer and
# pooling are pinned by the factory and recorded in the results.
model = dnabert2(device="cpu", precision="float32")
# For a supported GPU, choose device="cuda:0", precision="bfloat16".
# Precision changes the inference identity. The paper used GPU bfloat16;
# this CPU float32 example need not produce bit-identical scores.
