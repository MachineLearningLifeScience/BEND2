"""Paper prior readout: bend2 run examples/reference_ntv3_prior.py --tasks prior

Install: pip install 'bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark'
Accept the checkpoint's terms on Hugging Face, then run `hf auth login` if needed.
Two fixed 12%-mask queries per window; average losses, not probabilities.
"""

from bend2.reference_models import ntv3_prior

model = ntv3_prior(size="100m", readout="paper", device="cpu", precision="float32")
# Use size="650m" for the larger checkpoint; GPU inference is recommended.
# Use readout="native" for the one-target-mask alternative, recorded separately.
