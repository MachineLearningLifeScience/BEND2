"""Optional Hugging Face integration; model weights load on the first batch."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import numpy as np

from bend2.model import Model


def model(
    checkpoint: str,
    *,
    revision: str,
    training_data: str,
    device: str = "cpu",
    trust_remote_code: bool = False,
    max_tokens: int | None = None,
) -> Model:
    """Create a frozen embedding model with a pinned checkpoint and tokenizer.

    Install ``bend2[huggingface]``. The encoder averages final-layer states over
    non-special tokens, preserves complete sequences, and never pads a batch.
    ``revision`` must be a complete 40-character Hub commit SHA. Custom model or
    tokenizer Python runs only when ``trust_remote_code=True`` is explicit.
    This generic embedding readout is distinct from a model's native predictions.
    """
    if not isinstance(checkpoint, str) or not re.fullmatch(r"[\w.-]+(?:/[\w.-]+)?", checkpoint):
        raise ValueError("checkpoint must be a Hugging Face model repository ID")
    if Path(checkpoint).exists():
        raise ValueError("Use a Hub repository ID; local weights need a custom Model adapter")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError("Pin revision to the full 40-character Hugging Face commit SHA")
    if not isinstance(training_data, str) or not training_data.strip():
        raise ValueError("Declare the checkpoint's training data, or explicitly state unknown")
    if not isinstance(device, str) or not device.strip():
        raise ValueError("device must be a PyTorch device string, such as cpu or cuda:0")
    if type(trust_remote_code) is not bool:
        raise TypeError("trust_remote_code must be True or False")
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 1):
        raise ValueError("max_tokens must be a positive integer")
    revision = revision.lower()
    encoder = _Encoder(checkpoint, revision, device, trust_remote_code, max_tokens)
    return Model(
        checkpoint,
        embed=encoder,
        revision=revision,
        training_data=training_data,
        representation=(
            f"AutoModel.last_hidden_state; float32; device={device}; "
            f"max_tokens={max_tokens}; trust_remote_code={trust_remote_code}"
        ),
        pooling="mean non-special tokens; same-length batches; no padding or truncation",
        source=f"https://huggingface.co/{checkpoint}/tree/{revision}",
        inference_config={
            "checkpoint": checkpoint,
            "device": device,
            "precision": "float32",
            "max_tokens": max_tokens,
            "trust_remote_code": trust_remote_code,
        },
    )


class _Encoder:
    def __init__(self, checkpoint, revision, device, trust_remote_code, max_tokens):
        self.checkpoint, self.revision, self.device = checkpoint, revision, device
        self.trust_remote_code, self.max_tokens = trust_remote_code, max_tokens
        self._model = None

    def _load(self):
        if self._model is not None:
            return
        try:
            import torch
            from huggingface_hub import hf_hub_download
            from huggingface_hub.errors import EntryNotFoundError
            from transformers import AutoModel, AutoTokenizer
        except ImportError:
            raise ImportError(
                "Install the model runtime: pip install 'bend2[huggingface]'"
            ) from None
        if self.trust_remote_code:
            # A model's pin cannot pin code hosted in an unrelated repository.
            for filename in ("config.json", "tokenizer_config.json"):
                try:
                    path = hf_hub_download(self.checkpoint, filename, revision=self.revision)
                except EntryNotFoundError:
                    if filename == "config.json":
                        raise
                    continue
                metadata = json.loads(Path(path).read_text())
                for value in metadata.get("auto_map", {}).values():
                    for reference in value if isinstance(value, (list, tuple)) else [value]:
                        if isinstance(reference, str) and "--" in reference:
                            if reference.split("--", 1)[0] != self.checkpoint:
                                raise ValueError(
                                    "Custom code comes from another repository. "
                                    "Use an adapter that pins its code separately."
                                )
        options = dict(
            revision=self.revision,
            code_revision=self.revision,
            trust_remote_code=self.trust_remote_code,
        )
        tokenizer = AutoTokenizer.from_pretrained(self.checkpoint, **options)
        encoder = (
            AutoModel.from_pretrained(self.checkpoint, dtype=torch.float32, **options)
            .to(self.device)
            .eval()
        )
        encoder.requires_grad_(False)
        limits = [self.max_tokens, getattr(tokenizer, "model_max_length", None)]
        limits.extend(
            getattr(encoder.config, key, None)
            for key in (
                "max_position_embeddings",
                "max_seq_len",
                "max_sequence_length",
            )
        )
        limit = min((n for n in limits if type(n) is int and 0 < n < 1_000_000_000), default=None)
        if limit is None:
            raise ValueError(
                "Cannot infer the model's context limit; provide max_tokens explicitly"
            )
        self._tokenizer, self._model, self._limit = tokenizer, encoder, limit
        self._accepts_mask = "attention_mask" in inspect.signature(encoder.forward).parameters

    def __call__(self, sequences: list[str]) -> np.ndarray:
        if not sequences:
            raise ValueError("Pass a nonempty sequence batch")
        self._load()
        import torch

        encoded = self._tokenizer(
            sequences,
            padding=False,
            truncation=False,
            return_special_tokens_mask=True,
            return_attention_mask=False,
        )
        tokens, special = encoded["input_ids"], encoded.get("special_tokens_mask")
        if special is None or len(tokens) != len(sequences) or len(special) != len(tokens):
            raise ValueError("Tokenizer must return IDs and a special-token mask per sequence")
        if any(len(row) != len(mask) for row, mask in zip(tokens, special, strict=True)):
            raise ValueError("Tokenizer IDs and special-token masks have different lengths")
        if any(len(row) > self._limit for row in tokens):
            raise ValueError(
                f"Input exceeds the model's {self._limit}-token context. "
                "Choose a longer-context model or declare a custom representation; "
                "BEND does not silently truncate sequences."
            )
        groups, result = {}, [None] * len(tokens)
        for index, row in enumerate(tokens):
            groups.setdefault(len(row), []).append(index)
        with torch.inference_mode():
            for indices in groups.values():
                ids = torch.tensor([tokens[i] for i in indices], device=self.device)
                keep = torch.tensor(
                    [[not value for value in special[i]] for i in indices], device=self.device
                )
                if (keep.sum(dim=1) == 0).any():
                    raise ValueError("Tokenizer produced no sequence tokens to pool")
                arguments = {"input_ids": ids, "return_dict": True}
                if self._accepts_mask:
                    arguments["attention_mask"] = torch.ones_like(ids)
                hidden = getattr(self._model(**arguments), "last_hidden_state", None)
                if hidden is None or hidden.ndim != 3 or hidden.shape[:2] != ids.shape:
                    raise ValueError(
                        "AutoModel must return last_hidden_state [batch, tokens, features]"
                    )
                pooled = (hidden.float() * keep.unsqueeze(-1)).sum(1) / keep.sum(1, keepdim=True)
                for index, row in zip(indices, pooled.cpu().numpy(), strict=True):
                    result[index] = row
        values = np.asarray(result, dtype=np.float32)
        if not np.isfinite(values).all():
            raise ValueError("Model produced nonfinite embeddings")
        return values
