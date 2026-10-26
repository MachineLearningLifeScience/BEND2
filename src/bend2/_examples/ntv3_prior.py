"""NTv3 100M-post paper prior. Requires the bend2[reference] runtime."""

from bend2.reference_models import ntv3_prior

# Accept the checkpoint terms on Hugging Face and authenticate if required.
# Weights load on the first batch. The paper readout uses two fixed 12%-mask
# queries per window and averages their losses, not their probabilities.
model = ntv3_prior(size="100m", readout="paper", device="cpu", precision="float32")
# Use size="650m" for the larger checkpoint; a GPU is recommended.
# For a supported GPU, choose device="cuda:0", precision="bfloat16".
# readout="native" selects the single-target-mask alternative, recorded
# separately because it does not reproduce the paper's input conditions.
