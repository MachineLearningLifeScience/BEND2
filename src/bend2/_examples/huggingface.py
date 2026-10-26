"""Pinned HyenaDNA embeddings. Requires the bend2[huggingface] runtime."""

from bend2.huggingface import model as huggingface_model

# Replace checkpoint, immutable revision and declarations for your model.
# This small checkpoint fits Atlas, not GTEx's 131,072-base windows.
# Weights load on the first batch. Custom Python uses the pinned revision.
model = huggingface_model(
    "LongSafari/hyenadna-tiny-1k-seqlen-hf",
    revision="e8c1effa8673814e257e627d2e1eda9ea5a373f6",
    training_data=(
        "Human reference genome hg38; next-nucleotide pretraining, according to "
        "the pinned model card. No additional fine-tuning."
    ),
    device="cpu",  # Use "cuda:0" for a supported GPU.
    trust_remote_code=True,
)
