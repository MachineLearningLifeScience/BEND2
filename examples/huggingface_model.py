"""Run a real DNA model on CPU: bend2 run examples/huggingface_model.py --tasks atlas_profile

Install the optional runtime first:
pip install 'bend2[huggingface] @ git+https://github.com/yhsure/genomic-bending.git@benchmark'
Weights download on the first run and remain in the standard Hugging Face cache.
This small checkpoint supports the 145-base Atlas sequences. It cannot cover
GTEx's 131,072-base inputs; choose a longer-context model for that task.
"""

from bend2.huggingface import model as huggingface_model

model = huggingface_model(
    "LongSafari/hyenadna-tiny-1k-seqlen-hf",
    revision="e8c1effa8673814e257e627d2e1eda9ea5a373f6",
    training_data=(
        "Human reference genome hg38; next-nucleotide pretraining, according to "
        "the pinned model card. This example applies no additional fine-tuning."
    ),
    device="cpu",  # Change to cuda:0 for an NVIDIA GPU.
    # HyenaDNA uses custom Python at the same pinned checkpoint revision.
    trust_remote_code=True,
)
