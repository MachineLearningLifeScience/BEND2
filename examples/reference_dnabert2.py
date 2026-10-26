"""A complete 768-feature run: bend2 run examples/reference_dnabert2.py --tasks atlas_profile

Install: pip install 'bend2[reference] @ git+https://github.com/yhsure/genomic-bending.git@benchmark'
The pinned checkpoint downloads once into the standard Hugging Face cache.
"""

from bend2.reference_models import dnabert2

model = dnabert2(device="cpu", precision="float32")
# On a supported GPU, explicitly choose device="cuda:0", precision="bfloat16".
# The precision changes the recorded inference identity. The paper's frozen
# DNABERT-2 extraction used bfloat16 GPU autocast; this example uses float32.
